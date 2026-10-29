"""KPI : requêtes SQL paramétrées (utilisées par le dashboard) + implémentation Pandas de référence.

Le dashboard n'affiche QUE ce que renvoient ces fonctions : aucune valeur n'est codée en dur.
Les tests d'intégration vérifient que SQL et Pandas donnent les mêmes résultats sur les mêmes données.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy import Engine, bindparam, text

KPI_FIELDS = [
    "gross_revenue", "cancelled_amount", "net_revenue", "orders", "customers", "units",
    "avg_order_value", "revenue_share_without_customer",
]


@dataclass(frozen=True)
class Filters:
    dataset: str
    start: date | None = None          # inclus
    end: date | None = None            # inclus
    countries: tuple[str, ...] = field(default_factory=tuple)  # vide = tous les pays


def _where(f: Filters) -> tuple[str, dict]:
    clauses = ["dataset = :dataset"]
    params: dict = {"dataset": f.dataset}
    if f.start:
        clauses.append("invoice_day >= :start")
        params["start"] = f.start
    if f.end:
        clauses.append("invoice_day <= :end")
        params["end"] = f.end
    if f.countries:
        clauses.append("country IN :countries")
        params["countries"] = list(f.countries)
    return " AND ".join(clauses), params


def _query(engine: Engine, sql: str, params: dict) -> pd.DataFrame:
    stmt = text(sql)
    if "countries" in params:
        stmt = stmt.bindparams(bindparam("countries", expanding=True))
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn, params=params)


def _num(v) -> float | int | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, Decimal):
        return float(v)
    return v.item() if hasattr(v, "item") else v


# --------------------------------------------------------------------------- métadonnées

def available_datasets(engine: Engine) -> pd.DataFrame:
    return _query(engine, """
        SELECT c.dataset, r.source_file, r.finished_at, r.rows_extracted, r.run_id
        FROM meta.dataset_current c JOIN meta.load_runs r USING (run_id)
        ORDER BY c.dataset""", {})


def date_bounds(engine: Engine, dataset: str) -> tuple[date | None, date | None]:
    """Période couvrant ventes valides ET annulations : c'est la période par défaut du dashboard, qui doit donc
    reproduire exactement les totaux des marts (une annulation postérieure à la dernière vente compte aussi)."""
    df = _query(engine, """
        SELECT MIN(d) AS lo, MAX(d) AS hi FROM (
            SELECT invoice_day AS d FROM marts.fct_sales WHERE dataset = :dataset
            UNION ALL
            SELECT invoice_day FROM marts.fct_cancellations WHERE dataset = :dataset
        ) days""", {"dataset": dataset})
    lo, hi = df.iloc[0]["lo"], df.iloc[0]["hi"]
    return (None if pd.isna(lo) else lo, None if pd.isna(hi) else hi)


def list_countries(engine: Engine, dataset: str) -> list[str]:
    df = _query(engine, "SELECT country FROM marts.country_sales WHERE dataset = :dataset "
                        "ORDER BY revenue_rank", {"dataset": dataset})
    return df["country"].dropna().tolist()


# --------------------------------------------------------------------------- KPI filtrables

def kpis(engine: Engine, f: Filters) -> dict:
    where, params = _where(f)
    sales = _query(engine, f"""
        SELECT COALESCE(SUM(line_amount), 0) AS gross_revenue,
               COUNT(DISTINCT invoice)       AS orders,
               COUNT(DISTINCT customer_id)   AS customers,
               COALESCE(SUM(quantity), 0)    AS units,
               COALESCE(SUM(line_amount) FILTER (WHERE customer_id IS NULL), 0) AS revenue_without_customer
        FROM marts.fct_sales WHERE {where}""", params).iloc[0]
    canc = _query(engine, f"SELECT COALESCE(SUM(cancelled_amount), 0) AS c FROM marts.fct_cancellations "
                          f"WHERE {where}", params).iloc[0]["c"]
    gross, cancelled = float(sales["gross_revenue"]), float(canc)
    orders = int(sales["orders"])
    return {
        "gross_revenue": round(gross, 2),
        "cancelled_amount": round(cancelled, 2),
        "net_revenue": round(gross - cancelled, 2),
        "orders": orders,
        "customers": int(sales["customers"]),
        "units": int(sales["units"]),
        "avg_order_value": round(gross / orders, 2) if orders else None,
        "revenue_share_without_customer":
            round(float(sales["revenue_without_customer"]) / gross, 4) if gross else None,
    }


def monthly_trend(engine: Engine, f: Filters) -> pd.DataFrame:
    where, params = _where(f)
    df = _query(engine, f"""
        WITH s AS (
            SELECT invoice_month, SUM(line_amount) AS gross_revenue, COUNT(DISTINCT invoice) AS orders,
                   COUNT(DISTINCT customer_id) AS customers, SUM(quantity) AS units
            FROM marts.fct_sales WHERE {where} GROUP BY invoice_month
        ), c AS (
            SELECT invoice_month, SUM(cancelled_amount) AS cancelled_amount
            FROM marts.fct_cancellations WHERE {where} GROUP BY invoice_month
        )
        SELECT invoice_month,
               COALESCE(s.gross_revenue, 0) AS gross_revenue, COALESCE(s.orders, 0) AS orders,
               COALESCE(s.customers, 0) AS customers, COALESCE(s.units, 0) AS units,
               COALESCE(c.cancelled_amount, 0) AS cancelled_amount,
               COALESCE(s.gross_revenue, 0) - COALESCE(c.cancelled_amount, 0) AS net_revenue
        FROM s FULL JOIN c USING (invoice_month) ORDER BY invoice_month""", params)
    if df.empty:
        return df
    return df.astype({"gross_revenue": float, "cancelled_amount": float, "net_revenue": float})


PRODUCT_RANKINGS = ("gross_revenue", "net_revenue", "units")


def top_products(engine: Engine, f: Filters, n: int = 10, by: str = "gross_revenue") -> pd.DataFrame:
    """Classement produits. by='net_revenue' déduit les annulations de la même période / des mêmes pays :
    indispensable sur Online Retail II, où certaines très grosses commandes ont été intégralement annulées."""
    if by not in PRODUCT_RANKINGS:  # liste blanche : seule partie dynamique du SQL
        raise ValueError(f"by doit valoir l'une de {PRODUCT_RANKINGS}")
    where, params = _where(f)
    params["n"] = n
    df = _query(engine, f"""
        WITH s AS (
            SELECT stock_code, SUM(line_amount) AS gross_revenue, SUM(quantity) AS units,
                   COUNT(DISTINCT invoice) AS orders
            FROM marts.fct_sales WHERE {where} GROUP BY stock_code
        ), c AS (
            SELECT stock_code, SUM(cancelled_amount) AS cancelled_amount
            FROM marts.fct_cancellations WHERE {where} GROUP BY stock_code
        ), sc AS (
            SELECT stock_code, COALESCE(s.gross_revenue, 0) AS gross_revenue,
                   COALESCE(c.cancelled_amount, 0) AS cancelled_amount,
                   COALESCE(s.gross_revenue, 0) - COALESCE(c.cancelled_amount, 0) AS net_revenue,
                   COALESCE(s.units, 0) AS units, COALESCE(s.orders, 0) AS orders
            FROM s FULL JOIN c USING (stock_code)
        )
        SELECT sc.stock_code, COALESCE(p.product_name, 'UNKNOWN') AS product_name,
               sc.gross_revenue, sc.cancelled_amount, sc.net_revenue, sc.units, sc.orders
        FROM sc
        LEFT JOIN marts.dim_product p ON p.dataset = :dataset AND p.stock_code = sc.stock_code
        ORDER BY {by} DESC, sc.stock_code LIMIT :n""", params)
    if df.empty:
        return df
    return df.astype({"gross_revenue": float, "cancelled_amount": float, "net_revenue": float})


def country_ranking(engine: Engine, f: Filters, n: int = 15) -> pd.DataFrame:
    where, params = _where(f)
    params["n"] = n
    df = _query(engine, f"""
        SELECT country, SUM(line_amount) AS gross_revenue, COUNT(DISTINCT invoice) AS orders,
               COUNT(DISTINCT customer_id) AS customers
        FROM marts.fct_sales WHERE {where}
        GROUP BY country ORDER BY gross_revenue DESC, country LIMIT :n""", params)
    return df.astype({"gross_revenue": float}) if len(df) else df


# --------------------------------------------------------------------------- qualité & anomalies

def quality_breakdown(engine: Engine, dataset: str) -> pd.DataFrame:
    return _query(engine, """
        SELECT line_type, is_duplicate, invalid_reason, lines, amount, lines_without_customer
        FROM marts.data_quality WHERE dataset = :dataset ORDER BY lines DESC""", {"dataset": dataset})


def anomalies(engine: Engine, dataset: str) -> pd.DataFrame:
    return _query(engine, """
        SELECT invoice_day, gross_revenue, orders, lower_bound, upper_bound, direction
        FROM marts.daily_anomalies WHERE dataset = :dataset ORDER BY gross_revenue DESC""", {"dataset": dataset})


def kpi_summary_mart(engine: Engine, dataset: str) -> dict | None:
    df = _query(engine, "SELECT * FROM marts.kpi_summary WHERE dataset = :dataset", {"dataset": dataset})
    if df.empty:
        return None
    return {k: _num(v) for k, v in df.iloc[0].items()}


# --------------------------------------------------------------------------- référence Pandas

def compute_kpis(clean: pd.DataFrame, start: date | None = None, end: date | None = None,
                 countries: tuple[str, ...] = ()) -> dict:
    """Mêmes définitions que le SQL, calculées sur la couche nettoyée en mémoire."""
    day = clean["invoice_date"].dt.date
    mask = pd.Series(True, index=clean.index)
    if start:
        mask &= day >= start
    if end:
        mask &= day <= end
    if countries:
        mask &= clean["country"].isin(countries)
    scoped = clean[mask]
    sales = scoped[scoped["is_valid_sale"]]
    canc = scoped[(scoped["line_type"] == "cancellation") & scoped["is_product_code"] & ~scoped["is_duplicate"]]
    gross = float(sales["line_amount"].sum())
    cancelled = float(-canc["line_amount"].sum())
    orders = int(sales["invoice"].nunique())
    return {
        "gross_revenue": round(gross, 2),
        "cancelled_amount": round(cancelled, 2),
        "net_revenue": round(gross - cancelled, 2),
        "orders": orders,
        "customers": int(sales["customer_id"].nunique()),
        "units": int(sales["quantity"].sum()),
        "avg_order_value": round(gross / orders, 2) if orders else None,
        "revenue_share_without_customer":
            round(float(sales.loc[~sales["has_customer"], "line_amount"].sum()) / gross, 4) if gross else None,
    }
