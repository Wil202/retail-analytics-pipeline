"""Tests d'intégration sur un vrai PostgreSQL (base *_test, remise à zéro à chaque test)."""

from datetime import date

import pytest
from sqlalchemy import text

from conftest import sale, write_csv
from retail_analytics import kpis
from retail_analytics.config import SAMPLE_FILE
from retail_analytics.extract import extract_file
from retail_analytics.kpis import Filters, compute_kpis
from retail_analytics.pipeline import run_pipeline
from retail_analytics.transform import clean
from test_kpis import EXPECTED

pytestmark = pytest.mark.integration


def scalar(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def test_end_to_end_tiny_dataset_matches_hand_computed_kpis(pg_engine, tiny_rows, tmp_path):
    path = write_csv(tmp_path / "tiny.csv", tiny_rows)
    res = run_pipeline(path, "t", pg_engine, reports_dir=tmp_path, max_invalid_ratio=0.2)
    assert res.load.rows_new_raw == 10 and res.load.rows_staging == 10
    assert kpis.kpis(pg_engine, Filters("t")) == EXPECTED
    mart = kpis.kpi_summary_mart(pg_engine, "t")
    assert mart["gross_revenue"] == 49.0 and mart["orders"] == 3 and mart["net_revenue"] == 41.0
    assert scalar(pg_engine, "SELECT count(*) FROM raw.sales_lines") == 10  # le brut garde tout
    assert scalar(pg_engine, "SELECT count(*) FROM marts.fct_sales") == 4


def test_reloading_same_file_is_idempotent(pg_engine, tmp_path):
    first = run_pipeline(SAMPLE_FILE, "s", pg_engine, reports_dir=tmp_path)
    before = kpis.kpis(pg_engine, Filters("s"))
    for _ in range(2):
        again = run_pipeline(SAMPLE_FILE, "s", pg_engine, reports_dir=tmp_path)
        assert again.load.rows_new_raw == 0
    assert scalar(pg_engine, "SELECT count(*) FROM raw.sales_lines") == first.rows
    assert scalar(pg_engine, "SELECT count(*) FROM staging.sales_lines") == first.rows
    assert kpis.kpis(pg_engine, Filters("s")) == before
    assert scalar(pg_engine, "SELECT count(*) FROM meta.load_runs WHERE status = 'success'") == 3


def test_new_file_version_replaces_old_one_without_double_counting(pg_engine, tmp_path):
    v1 = write_csv(tmp_path / "v1.csv", [sale(invoice="1", qty="1", price="10")])
    v2 = write_csv(tmp_path / "v2.csv", [sale(invoice="1", qty="1", price="10"), sale(invoice="2", qty="2", price="10")])
    run_pipeline(v1, "d", pg_engine, reports_dir=tmp_path)
    run_pipeline(v2, "d", pg_engine, reports_dir=tmp_path)
    k = kpis.kpis(pg_engine, Filters("d"))
    assert k["gross_revenue"] == 30.0 and k["orders"] == 2  # pas 40 / 3
    assert scalar(pg_engine, "SELECT count(*) FROM raw.sales_lines") == 3  # l'historique brut est conservé


def test_datasets_are_isolated(pg_engine, tiny_rows, tmp_path):
    path = write_csv(tmp_path / "tiny.csv", tiny_rows)
    run_pipeline(path, "a", pg_engine, reports_dir=tmp_path, max_invalid_ratio=0.2)
    run_pipeline(path, "b", pg_engine, reports_dir=tmp_path, max_invalid_ratio=0.2)
    assert kpis.kpis(pg_engine, Filters("a")) == kpis.kpis(pg_engine, Filters("b")) == EXPECTED
    assert kpis.available_datasets(pg_engine)["dataset"].tolist() == ["a", "b"]


def test_sql_kpis_equal_pandas_reference_on_sample(pg_engine, tmp_path):
    run_pipeline(SAMPLE_FILE, "s", pg_engine, reports_dir=tmp_path)
    cleaned = clean(extract_file(SAMPLE_FILE).data)
    cases = [
        {},
        {"start": date(2024, 10, 1), "end": date(2024, 12, 31)},
        {"countries": ("France", "Germany")},
        {"start": date(2025, 1, 1), "countries": ("United Kingdom",)},
    ]
    for c in cases:
        assert kpis.kpis(pg_engine, Filters("s", **c)) == compute_kpis(cleaned, **c), c
    # Le mart pré-calculé et la requête filtrable donnent le même total.
    mart, live = kpis.kpi_summary_mart(pg_engine, "s"), kpis.kpis(pg_engine, Filters("s"))
    for key in ["gross_revenue", "cancelled_amount", "net_revenue", "orders", "customers", "units"]:
        assert mart[key] == pytest.approx(live[key]), key


def test_marts_are_consistent(pg_engine, tmp_path):
    run_pipeline(SAMPLE_FILE, "s", pg_engine, reports_dir=tmp_path)
    total = scalar(pg_engine, "SELECT gross_revenue FROM marts.kpi_summary")
    for mart in ["monthly_sales", "daily_country_sales", "product_performance", "country_sales"]:
        assert scalar(pg_engine, f"SELECT SUM(gross_revenue) FROM marts.{mart}") == total, mart
    cancelled = scalar(pg_engine, "SELECT cancelled_amount FROM marts.kpi_summary")
    for mart in ["monthly_sales", "product_performance"]:
        assert scalar(pg_engine, f"SELECT SUM(cancelled_amount) FROM marts.{mart}") == cancelled, mart
    assert scalar(pg_engine, "SELECT SUM(lines) FROM marts.data_quality") == scalar(
        pg_engine, "SELECT count(*) FROM staging.sales_lines")
    assert scalar(pg_engine, "SELECT SUM(revenue_share) FROM marts.country_sales") == pytest.approx(1, abs=1e-3)


def test_dashboard_queries_handle_empty_results(pg_engine, tiny_rows, tmp_path):
    run_pipeline(write_csv(tmp_path / "t.csv", tiny_rows), "t", pg_engine, reports_dir=tmp_path, max_invalid_ratio=0.2)
    f = Filters("t", countries=("Japan",))
    assert kpis.kpis(pg_engine, f)["orders"] == 0
    assert kpis.monthly_trend(pg_engine, f).empty
    assert kpis.top_products(pg_engine, f).empty
    assert kpis.country_ranking(pg_engine, f).empty
    assert kpis.date_bounds(pg_engine, "unknown") == (None, None)


def test_top_products_ranking(pg_engine, tiny_rows, tmp_path):
    run_pipeline(write_csv(tmp_path / "t.csv", tiny_rows), "t", pg_engine, reports_dir=tmp_path, max_invalid_ratio=0.2)
    top = kpis.top_products(pg_engine, Filters("t"), n=2)
    assert top["stock_code"].tolist() == ["70003", "70001"]  # 24.00 puis 15.00 (CUP 5 + 10)
    assert kpis.top_products(pg_engine, Filters("t"), by="units")["stock_code"].iloc[0] == "70001"
    with pytest.raises(ValueError):
        kpis.top_products(pg_engine, Filters("t"), by="DROP TABLE")


def test_failed_load_is_rolled_back_and_recorded(pg_engine, tiny_rows, tmp_path, monkeypatch):
    path = write_csv(tmp_path / "t.csv", tiny_rows)

    def boom(conn):
        raise RuntimeError("panne simulée pendant la construction des marts")

    monkeypatch.setattr("retail_analytics.load.build_marts", boom)
    with pytest.raises(RuntimeError):
        run_pipeline(path, "t", pg_engine, reports_dir=tmp_path, max_invalid_ratio=0.2)
    assert scalar(pg_engine, "SELECT count(*) FROM raw.sales_lines") == 0  # rien de partiel
    assert scalar(pg_engine, "SELECT status FROM meta.load_runs") == "failed"


def test_too_many_unreadable_rows_stops_before_database(pg_engine, tiny_rows, tmp_path):
    path = write_csv(tmp_path / "t.csv", tiny_rows)  # 10 % de lignes illisibles > seuil par défaut de 5 %
    with pytest.raises(ValueError, match="illisibles"):
        run_pipeline(path, "t", pg_engine, reports_dir=tmp_path)
    assert scalar(pg_engine, "SELECT to_regclass('raw.sales_lines') IS NULL")  # base jamais touchée


def test_schema_error_stops_before_database(pg_engine, tmp_path):
    bad = write_csv(tmp_path / "bad.csv", [["1", "2"]], header=["Invoice", "StockCode"])
    with pytest.raises(ValueError, match="colonnes manquantes"):
        run_pipeline(bad, "x", pg_engine, reports_dir=tmp_path)


def test_net_revenue_ranking_demotes_fully_cancelled_products(pg_engine, tmp_path):
    # Cas réel d'Online Retail II : une énorme commande annulée en totalité gonfle le CA brut.
    rows = [
        sale(invoice="1", code="90001", desc="BIG BUT CANCELLED", qty="100", price="1.00"),
        sale(invoice="C2", code="90001", desc="BIG BUT CANCELLED", qty="-100", price="1.00"),
        sale(invoice="3", code="90002", desc="STEADY SELLER", qty="50", price="1.00"),
    ]
    run_pipeline(write_csv(tmp_path / "c.csv", rows), "c", pg_engine, reports_dir=tmp_path)
    gross = kpis.top_products(pg_engine, Filters("c"), by="gross_revenue")
    net = kpis.top_products(pg_engine, Filters("c"), by="net_revenue")
    assert gross["stock_code"].tolist() == ["90001", "90002"]
    assert net["stock_code"].tolist() == ["90002", "90001"]
    assert net.set_index("stock_code").loc["90001", "net_revenue"] == 0.0


def test_monthly_trend_matches_monthly_mart(pg_engine, tmp_path):
    run_pipeline(SAMPLE_FILE, "s", pg_engine, reports_dir=tmp_path)
    live = kpis.monthly_trend(pg_engine, Filters("s"))
    with pg_engine.connect() as conn:
        mart = conn.execute(text("SELECT SUM(net_revenue), SUM(cancelled_amount) FROM marts.monthly_sales")).one()
    assert live["net_revenue"].sum() == pytest.approx(float(mart[0]))
    assert live["cancelled_amount"].sum() == pytest.approx(float(mart[1]))
    assert live["net_revenue"].to_numpy() == pytest.approx(
        (live["gross_revenue"] - live["cancelled_amount"]).to_numpy())


def test_cancellations_without_sales_are_not_lost(pg_engine, tmp_path):
    # Annulation d'un produit vendu AVANT la période couverte, dans un mois sans aucune vente.
    rows = [sale(invoice="1", code="90001", qty="10", price="1.00", date="2024-01-10 10:00:00"),
            sale(invoice="C2", code="90009", qty="-3", price="2.00", date="2024-02-10 10:00:00")]
    run_pipeline(write_csv(tmp_path / "o.csv", rows), "o", pg_engine, reports_dir=tmp_path)
    trend = kpis.monthly_trend(pg_engine, Filters("o")).set_index("invoice_month")
    assert len(trend) == 2 and trend["cancelled_amount"].sum() == 6.0
    top = kpis.top_products(pg_engine, Filters("o")).set_index("stock_code")
    assert top.loc["90009", "cancelled_amount"] == 6.0 and top.loc["90009", "gross_revenue"] == 0.0
    total = kpis.kpis(pg_engine, Filters("o"))["cancelled_amount"]
    for mart in ["monthly_sales", "product_performance"]:
        assert scalar(pg_engine, f"SELECT SUM(cancelled_amount) FROM marts.{mart}") == total, mart
