"""Le rapport d'analyse est généré depuis les marts : ses chiffres doivent égaler les KPI."""

import pytest

from conftest import write_csv
from retail_analytics import cli, kpis
from retail_analytics.config import SAMPLE_FILE
from retail_analytics.kpis import Filters
from retail_analytics.pipeline import run_pipeline
from retail_analytics.report import _int, _money, build_report

pytestmark = pytest.mark.integration


def test_report_figures_come_from_the_database(pg_engine, tmp_path):
    run_pipeline(SAMPLE_FILE, "synthetic_sample", pg_engine, reports_dir=tmp_path)
    md = build_report(pg_engine, "synthetic_sample")
    k = kpis.kpis(pg_engine, Filters("synthetic_sample"))
    assert f"| CA brut | {_money(k['gross_revenue'])} |" in md
    assert f"| Commandes (factures avec ≥ 1 vente valide) | {_int(k['orders'])} |" in md
    assert "SYNTHÉTIQUE" in md and "inventées" in md
    for section in ["Tendance mensuelle", "Produits", "Géographie", "Clients", "Jours atypiques", "Qualité"]:
        assert f"## {section}" in md


def test_report_on_minimal_dataset_and_unknown_dataset(pg_engine, tiny_rows, tmp_path):
    run_pipeline(write_csv(tmp_path / "t.csv", tiny_rows), "t", pg_engine, reports_dir=tmp_path,
                 max_invalid_ratio=0.2)
    md = build_report(pg_engine, "t")
    assert "| CA brut | £49 |" in md and "Comparaison à périmètre égal" not in md  # < 2 années complètes
    with pytest.raises(ValueError, match="absent"):
        build_report(pg_engine, "inconnu")


def test_report_cli_writes_file(pg_engine, pg_url, tmp_path, monkeypatch):
    run_pipeline(SAMPLE_FILE, "synthetic_sample", pg_engine, reports_dir=tmp_path)
    monkeypatch.setenv("DATABASE_URL", pg_url)
    out = tmp_path / "r.md"
    assert cli.main(["report", "--dataset", "synthetic_sample", "--output", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("# Analyse")
