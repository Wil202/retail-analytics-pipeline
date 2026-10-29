"""Fiabilité : erreurs explicites, chargements concurrents, cohérence des marts, fraîcheur du dashboard.

Défauts D1, D9 à D16 du rapport QA (docs/qa_report.md). Tests écrits avant les corrections.
"""

import threading
import time
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from conftest import sale, write_csv
from retail_analytics import cli, kpis, load
from retail_analytics.config import SAMPLE_FILE
from retail_analytics.kpis import Filters
from retail_analytics.pipeline import run_pipeline
from retail_analytics.report import build_report
from retail_analytics.validate import quality_report
from retail_analytics.transform import clean
from conftest import make_raw

UNREACHABLE = "postgresql+psycopg://u:p@10.255.255.1:5432/x"  # adresse non routée : la connexion ne répond pas
REFUSED = "postgresql+psycopg://u:p@127.0.0.1:1/x"


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar_one()


# ---------------------------------------------------------------- D1 : erreurs CLI lisibles (sans base)
def test_run_without_reachable_db_prints_clear_message(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", REFUSED)
    monkeypatch.setattr(cli, "REPORTS_DIR", tmp_path)
    code = cli.main(["run", "--source", "sample"])
    err = capsys.readouterr().err
    assert code == 2
    assert "PostgreSQL" in err and "Traceback" not in err


def test_run_without_configuration_prints_clear_message(capsys, monkeypatch):
    import retail_analytics.db as db
    from retail_analytics.config import Settings

    monkeypatch.setattr(db, "get_settings", lambda: Settings(None, None))
    assert cli.main(["run", "--source", "sample"]) == 2
    assert ".env" in capsys.readouterr().err


def test_report_without_reachable_db_prints_clear_message(capsys, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", REFUSED)
    assert cli.main(["report", "--dataset", "x"]) == 2
    assert "PostgreSQL" in capsys.readouterr().err


def test_invalid_source_file_exits_with_data_error(capsys, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Invoice,StockCode\n1,2\n")
    assert cli.main(["run", "--source", "sample", "--file", str(bad), "--dry-run"]) == 3
    assert "colonnes manquantes" in capsys.readouterr().err


# ---------------------------------------------------------------- D14 : délai de connexion borné
def test_unreachable_host_fails_fast(capsys, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE)
    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "2")
    t0 = time.perf_counter()
    assert cli.main(["check-db"]) == 2
    assert time.perf_counter() - t0 < 15


# ---------------------------------------------------------------- D12 : pays non renseigné mesuré
def test_unspecified_country_is_counted_in_quality_report():
    q = quality_report(clean(make_raw([sale(country="Unspecified"), sale(invoice="2")])))
    assert q["unspecified_country_lines"] == 1


# ---------------------------------------------------------------- tests avec PostgreSQL
@pytest.mark.integration
def test_cancellation_only_dataset_has_a_consistent_summary(pg_engine, tmp_path):  # D9
    p = write_csv(tmp_path / "c.csv", [sale(invoice="C1", qty="-2", price="3.00")])
    run_pipeline(p, "oc", pg_engine, reports_dir=tmp_path)
    mart = kpis.kpi_summary_mart(pg_engine, "oc")
    live = kpis.kpis(pg_engine, Filters("oc"))
    assert mart is not None
    assert mart["cancelled_amount"] == live["cancelled_amount"] == 6.0
    assert mart["gross_revenue"] == 0 and mart["orders"] == 0
    assert "| Montant annulé | £6 |" in build_report(pg_engine, "oc")


@pytest.mark.integration
def test_error_while_recording_failure_keeps_original_error(pg_engine, tmp_path, monkeypatch):  # D10
    def boom(conn):
        raise RuntimeError("ERREUR D'ORIGINE")

    def broken_fail_run(engine, run_id, error):
        raise ConnectionError("connexion perdue")

    monkeypatch.setattr(load, "build_marts", boom)
    monkeypatch.setattr(load, "_fail_run", broken_fail_run)
    with pytest.raises(RuntimeError, match="ERREUR D'ORIGINE"):
        run_pipeline(SAMPLE_FILE, "s", pg_engine, reports_dir=tmp_path)


@pytest.mark.integration
def test_interrupted_runs_are_marked_failed_on_next_load(pg_engine, tmp_path):  # D10
    from retail_analytics.db import init_schema

    init_schema(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("INSERT INTO meta.load_runs (dataset, source_file, file_sha256) "
                          "VALUES ('s', 'x', repeat('0', 64))"))
    run_pipeline(SAMPLE_FILE, "s", pg_engine, reports_dir=tmp_path)
    assert scalar(pg_engine, "SELECT count(*) FROM meta.load_runs WHERE status = 'running'") == 0
    assert scalar(pg_engine, "SELECT count(*) FROM meta.load_runs WHERE status = 'failed' "
                             "AND error_message LIKE '%interrompu%'") == 1


@pytest.mark.integration
def test_concurrent_loads_are_serialised(pg_engine, pg_url, tmp_path):  # D11
    errors: list[str] = []

    def go(i: int) -> None:
        eng = create_engine(pg_url)
        try:
            run_pipeline(SAMPLE_FILE, f"c{i % 2}", eng, reports_dir=tmp_path / str(i))
        except Exception as exc:  # noqa: BLE001 - on veut toutes les erreurs
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            eng.dispose()

    threads = [threading.Thread(target=go, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert scalar(pg_engine, "SELECT count(*) FROM meta.load_runs WHERE status = 'success'") == 4
    rows = scalar(pg_engine, "SELECT count(*) FROM raw.sales_lines")
    assert rows == 2 * scalar(pg_engine, "SELECT rows_extracted FROM meta.load_runs LIMIT 1")


# ---------------------------------------------------------------- dashboard (D13, D16)
st = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")


@pytest.fixture
def clear_st_cache():
    st.cache_data.clear()
    st.cache_resource.clear()
    yield


def _metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


@pytest.mark.integration
def test_dashboard_shows_new_data_immediately_after_reload(pg_engine, pg_url, tmp_path, monkeypatch,
                                                           clear_st_cache):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    v1 = write_csv(tmp_path / "v1.csv", [sale(invoice="1")])
    v2 = write_csv(tmp_path / "v2.csv", [sale(invoice="1"), sale(invoice="2"), sale(invoice="3")])
    run_pipeline(v1, "d", pg_engine, reports_dir=tmp_path)
    assert _metric(AppTest.from_file(APP, default_timeout=60).run(), "Commandes") == "1"
    run_pipeline(v2, "d", pg_engine, reports_dir=tmp_path)  # cache Streamlit volontairement NON vidé
    assert _metric(AppTest.from_file(APP, default_timeout=60).run(), "Commandes") == "3"


@pytest.mark.integration
def test_dashboard_single_date_selection_filters_that_day(pg_engine, pg_url, tmp_path, monkeypatch,
                                                          clear_st_cache):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    rows = [sale(invoice="1", date="2024-03-01 10:00:00"), sale(invoice="2", date="2024-03-02 10:00:00")]
    run_pipeline(write_csv(tmp_path / "t.csv", rows), "t", pg_engine, reports_dir=tmp_path)
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.date_input[0].set_value((date(2024, 3, 2),)).run()  # sélection en cours : une seule date
    assert not at.exception
    assert _metric(at, "Commandes") == "1"


@pytest.mark.integration
def test_dashboard_db_failure_shows_error_not_traceback(monkeypatch, clear_st_cache):
    monkeypatch.setenv("DATABASE_URL", REFUSED)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("PostgreSQL" in e.value for e in at.error)


@pytest.mark.integration
def test_dashboard_db_lost_during_session_shows_error(pg_engine, pg_url, tmp_path, monkeypatch, clear_st_cache):
    from sqlalchemy.exc import OperationalError

    monkeypatch.setenv("DATABASE_URL", pg_url)
    run_pipeline(write_csv(tmp_path / "t.csv", [sale()]), "t", pg_engine, reports_dir=tmp_path)

    def lost(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))

    monkeypatch.setattr(kpis, "monthly_trend", lost)  # la base tombe après les premiers indicateurs
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Connexion PostgreSQL perdue" in e.value for e in at.error)
