from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, make_url, text

from retail_analytics.config import get_settings
from retail_analytics.extract import CANONICAL_COLUMNS

UCI_HEADER = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]


def make_raw(rows: list[list[str | None]]) -> pd.DataFrame:
    """Construit une couche brute (texte) comme la produirait extract_file."""
    df = pd.DataFrame(rows, columns=CANONICAL_COLUMNS, dtype=object)
    df["source_file"] = "test.csv"
    df["source_sheet"] = "csv"
    df["source_row"] = range(2, len(df) + 2)
    df["file_sha256"] = "0" * 64
    return df


def sale(invoice="500001", code="70001", desc="CUP", qty="2", date="2024-03-01 10:00:00", price="2.50",
         customer="20001", country="France") -> list[str | None]:
    return [invoice, code, desc, qty, date, price, customer, country]


def write_csv(path: Path, rows: list[list[str | None]], header: list[str] = UCI_HEADER) -> Path:
    pd.DataFrame(rows, columns=header).to_csv(path, index=False)
    return path


@pytest.fixture
def tiny_rows() -> list[list[str | None]]:
    """Jeu minuscule dont tous les KPI sont calculables à la main (voir test_kpis.py)."""
    return [
        sale("500001", "70001", "CUP", "2", "2024-01-10 10:00:00", "2.50", "20001", "France"),    # 5.00
        sale("500001", "70002", "MUG", "1", "2024-01-10 10:00:00", "10.00", "20001", "France"),   # 10.00
        sale("500001", "70002", "MUG", "1", "2024-01-10 10:00:00", "10.00", "20001", "France"),   # doublon exact
        sale("500002", "70001", "CUP", "4", "2024-02-05 12:00:00", "2.50", None, "United Kingdom"),  # 10.00 sans client
        sale("500003", "70003", "TRAY", "3", "2024-02-20 09:00:00", "8.00", "20002", "United Kingdom"),  # 24.00
        sale("C500004", "70003", "TRAY", "-1", "2024-02-25 09:00:00", "8.00", "20002", "United Kingdom"),  # annul. 8
        sale("500005", "POST", "POSTAGE", "1", "2024-02-20 09:00:00", "18.00", "20002", "United Kingdom"),  # non produit
        sale("500006", "70001", "damaged", "-5", "2024-02-21 09:00:00", "0", None, "United Kingdom"),  # ajust. stock
        sale("500007", "70002", "MUG", "1", "2024-02-22 09:00:00", "0", "20003", "France"),         # prix nul
        sale("500008", "70002", "MUG", "x", "2024-02-22 09:00:00", "10.00", "20003", "France"),     # invalide
    ]


# ---------------------------------------------------------------- PostgreSQL (tests d'intégration)

def _test_url() -> str | None:
    return os.getenv("TEST_DATABASE_URL") or get_settings().test_database_url


def _unavailable(reason: str):
    """Sans base, les tests d'intégration sont ignorés… sauf si REQUIRE_DB=1 (CI) : ils échouent alors,
    pour qu'une base absente ne passe jamais pour une suite verte."""
    if os.getenv("REQUIRE_DB") == "1":
        pytest.fail(f"REQUIRE_DB=1 mais {reason}")
    pytest.skip(reason)


@pytest.fixture(scope="session")
def pg_url() -> str:
    url = _test_url()
    if not url:
        _unavailable("TEST_DATABASE_URL non défini : tests d'intégration ignorés")
    db = make_url(url).database or ""
    if not db.endswith("_test"):
        pytest.fail(f"Par sécurité, la base de test doit se terminer par '_test' (reçu : {db!r})")
    try:
        eng = create_engine(url)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
    except Exception as exc:  # pragma: no cover - dépend de l'environnement
        _unavailable(f"PostgreSQL de test injoignable : {str(exc).splitlines()[0]}")
    return url


@pytest.fixture
def pg_engine(pg_url):
    """Base de test remise à zéro avant chaque test (uniquement les schémas du pipeline)."""
    eng = create_engine(pg_url)
    with eng.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA IF EXISTS marts, staging, raw, meta CASCADE")
    yield eng
    eng.dispose()
