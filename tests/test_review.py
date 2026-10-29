"""Revue avant publication (docs/review.md) : verrou borné, version du schéma, cohérence dashboard/marts."""

import re
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import text

from conftest import sale, write_csv
from retail_analytics import cli, kpis
from retail_analytics.config import SQL_DIR
from retail_analytics.db import PIPELINE_LOCK_KEY, SCHEMA_VERSION, PipelineBusy, SchemaVersionMismatch, init_schema
from retail_analytics.kpis import Filters
from retail_analytics.pipeline import run_pipeline


def test_schema_version_constant_matches_sql_script():
    sql = (SQL_DIR / "01_schema.sql").read_text(encoding="utf-8")
    assert re.search(r"INSERT INTO meta\.schema_info \(version\) VALUES \((\d+)\)", sql).group(1) == str(SCHEMA_VERSION)


@pytest.mark.integration
def test_incompatible_schema_version_is_refused_before_any_write(pg_engine, pg_url, tmp_path, monkeypatch, capsys):
    init_schema(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("UPDATE meta.schema_info SET version = 999"))
    with pytest.raises(SchemaVersionMismatch, match="v999"):
        run_pipeline(write_csv(tmp_path / "t.csv", [sale()]), "t", pg_engine, reports_dir=tmp_path)
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM meta.load_runs")).scalar() == 0
    monkeypatch.setenv("DATABASE_URL", pg_url)
    assert cli.main(["run", "--source", "sample"]) == 2
    assert "Base incompatible" in capsys.readouterr().err


@pytest.mark.integration
def test_database_created_before_versioning_is_accepted(pg_engine, tmp_path):
    init_schema(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE meta.schema_info"))  # base créée par la v0.2, sans table de version
    run_pipeline(write_csv(tmp_path / "t.csv", [sale()]), "t", pg_engine, reports_dir=tmp_path)
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT version FROM meta.schema_info")).scalar() == SCHEMA_VERSION


@pytest.mark.integration
def test_waiting_for_the_load_lock_is_bounded(pg_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("PIPELINE_LOCK_TIMEOUT", "1")
    held, release = threading.Event(), threading.Event()

    def hold_lock():
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": PIPELINE_LOCK_KEY})
            held.set()
            release.wait(30)
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": PIPELINE_LOCK_KEY})

    t = threading.Thread(target=hold_lock)
    t.start()
    try:
        assert held.wait(10)
        t0 = time.perf_counter()
        with pytest.raises(PipelineBusy, match="autre chargement"):
            run_pipeline(write_csv(tmp_path / "t.csv", [sale()]), "t", pg_engine, reports_dir=tmp_path)
        assert time.perf_counter() - t0 < 10
    finally:
        release.set()
        t.join()
    run_pipeline(write_csv(tmp_path / "t.csv", [sale()]), "t", pg_engine, reports_dir=tmp_path)  # verrou libéré : OK


@pytest.mark.integration
def test_dashboard_default_period_reproduces_mart_totals(pg_engine, tmp_path):
    # Annulation APRÈS la dernière vente valide : la période par défaut doit l'inclure.
    rows = [sale(invoice="1", qty="10", price="2.00", date="2024-03-01 10:00:00"),
            sale(invoice="C2", qty="-1", price="2.00", date="2024-03-20 10:00:00")]
    run_pipeline(write_csv(tmp_path / "t.csv", rows), "t", pg_engine, reports_dir=tmp_path)
    lo, hi = kpis.date_bounds(pg_engine, "t")
    default_view = kpis.kpis(pg_engine, Filters("t", start=lo, end=hi))
    mart = kpis.kpi_summary_mart(pg_engine, "t")
    for key in ["gross_revenue", "cancelled_amount", "net_revenue", "orders", "customers", "units"]:
        assert default_view[key] == pytest.approx(mart[key]), key
    assert default_view["net_revenue"] == 18.0


def test_cli_module_contains_no_download_logic():
    src = Path(cli.__file__).read_text(encoding="utf-8")
    assert "urllib" not in src and "zipfile" not in src
