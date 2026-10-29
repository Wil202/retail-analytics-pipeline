"""Exécute le vrai dashboard sans navigateur (streamlit.testing) sur la base de test."""

from pathlib import Path

import pytest

from retail_analytics import kpis
from retail_analytics.config import DATASET_SAMPLE, SAMPLE_FILE
from retail_analytics.kpis import Filters
from retail_analytics.pipeline import run_pipeline

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import streamlit as st  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")
pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _clear_streamlit_cache():
    """Le cache Streamlit vit dans le processus : on le vide pour isoler chaque test."""
    st.cache_data.clear()
    st.cache_resource.clear()
    yield


@pytest.fixture
def app(pg_engine, pg_url, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", pg_url)
    run_pipeline(SAMPLE_FILE, DATASET_SAMPLE, pg_engine, reports_dir=tmp_path)
    return AppTest.from_file(APP, default_timeout=60)


def metrics(at) -> dict:
    return {m.label: m.value for m in at.metric}


def test_dashboard_displays_values_computed_from_database(app, pg_engine):
    at = app.run()
    assert not at.exception
    expected = kpis.kpis(pg_engine, Filters(DATASET_SAMPLE))
    m = metrics(at)
    assert m["Commandes"] == f"{expected['orders']:,}".replace(",", " ")
    assert m["Clients identifiés"] == f"{expected['customers']:,}".replace(",", " ")
    assert any("synthétiques" in w.value for w in at.warning)  # l'étiquetage synthétique est visible


def test_dashboard_country_filter_changes_kpis(app, pg_engine):
    at = app.run()
    at.sidebar.multiselect[0].set_value(["France"]).run()
    assert not at.exception
    expected = kpis.kpis(pg_engine, Filters(DATASET_SAMPLE, countries=("France",)))
    assert metrics(at)["Commandes"] == str(expected["orders"])


def test_dashboard_without_data_shows_message(pg_engine, pg_url, monkeypatch):
    from retail_analytics.db import init_schema

    monkeypatch.setenv("DATABASE_URL", pg_url)
    init_schema(pg_engine)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert any("Aucun dataset" in w.value for w in at.warning)


def test_dashboard_empty_filter_shows_message_instead_of_charts(app):
    from datetime import date

    at = app.run()
    saturday = date(2024, 3, 2)  # le générateur ne crée aucune vente le samedi
    at.sidebar.date_input[0].set_value((saturday, saturday)).run()
    assert not at.exception
    assert any("Aucune vente pour ces filtres" in i.value for i in at.info)
    assert len(at.metric) == 0


def test_dashboard_net_revenue_ranking_runs(app):
    at = app.run()
    at.sidebar.radio[0].set_value("net_revenue").run()
    assert not at.exception


def test_dashboard_ranks_products_by_net_revenue_by_default(app):
    """Au CA brut, une commande géante intégralement annulée gonfle un produit : la vue par défaut ne doit pas
    le mettre en avant (cas réel d'Online Retail II, docs/findings.md)."""
    at = app.run()
    assert not at.exception
    assert at.sidebar.radio[0].value == "net_revenue"
