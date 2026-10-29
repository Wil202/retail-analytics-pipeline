"""Rapport d'analyse généré depuis les marts PostgreSQL (aucun chiffre saisi à la main).

    python -m retail_analytics.cli report --dataset uci_online_retail_ii --output docs/analysis_uci.md
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import Engine, text

from retail_analytics import kpis
from retail_analytics.config import DATASET_SAMPLE, UCI_DOI


def _df(engine: Engine, sql: str, dataset: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params={"d": dataset})


def _missing(v) -> bool:
    return v is None or (not isinstance(v, str) and pd.isna(v))


def _money(v) -> str:
    return "—" if _missing(v) else f"£{float(v):,.0f}".replace(",", " ")


def _int(v) -> str:
    return "—" if _missing(v) else f"{int(v):,}".replace(",", " ")


def _pct(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{float(v):.1%}"


def _day(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{pd.Timestamp(v):%d/%m/%Y}"


def _cell(v) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def _table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def build_report(engine: Engine, dataset: str, top_n: int = 10) -> str:
    k = kpis.kpi_summary_mart(engine, dataset)
    if k is None:
        raise ValueError(f"Dataset {dataset!r} absent des marts : lancez d'abord le pipeline.")
    run = _df(engine, """SELECT r.run_id, r.source_file, r.file_sha256, r.finished_at, r.quality_report
                         FROM meta.dataset_current c JOIN meta.load_runs r USING (run_id)
                         WHERE c.dataset = :d""", dataset).iloc[0]
    q = run["quality_report"]

    monthly = _df(engine, """SELECT invoice_month, gross_revenue, cancelled_amount, net_revenue, orders, customers
                             FROM marts.monthly_sales WHERE dataset = :d ORDER BY invoice_month""", dataset)
    full_months = monthly[monthly["invoice_month"].map(lambda m: m.month) <= 11]
    yoy = (full_months.assign(year=full_months["invoice_month"].map(lambda m: m.year))
           .groupby("year").agg(gross_revenue=("gross_revenue", "sum"), orders=("orders", "sum"),
                                months=("invoice_month", "count")))
    yoy = yoy[yoy["months"] == 11]

    top_gross = _df(engine, """SELECT revenue_rank, stock_code, product_name, gross_revenue, cancelled_amount,
                                      net_revenue, units_sold
                               FROM marts.product_performance WHERE dataset = :d
                               ORDER BY revenue_rank, stock_code LIMIT :n""".replace(":n", str(int(top_n))), dataset)
    top_net = _df(engine, """SELECT net_revenue_rank, stock_code, product_name, net_revenue, units_sold, orders
                             FROM marts.product_performance WHERE dataset = :d
                             ORDER BY net_revenue_rank, stock_code LIMIT :n""".replace(":n", str(int(top_n))), dataset)
    concentration = _df(engine, """
        WITH p AS (SELECT gross_revenue, ROW_NUMBER() OVER (ORDER BY gross_revenue DESC) AS r,
                          COUNT(*) OVER () AS n
                   FROM marts.product_performance WHERE dataset = :d AND gross_revenue > 0)
        SELECT MAX(n) AS products, SUM(gross_revenue) FILTER (WHERE r <= n * 0.2) / SUM(gross_revenue) AS top20_share
        FROM p""", dataset).iloc[0]
    countries = _df(engine, """SELECT revenue_rank, country, gross_revenue, revenue_share, orders, customers
                               FROM marts.country_sales WHERE dataset = :d ORDER BY revenue_rank LIMIT :n"""
                    .replace(":n", str(int(top_n))), dataset)
    n_countries = len(_df(engine, "SELECT country FROM marts.country_sales WHERE dataset = :d", dataset))
    repeat = _df(engine, """
        WITH c AS (SELECT customer_id, COUNT(DISTINCT invoice) AS n FROM marts.fct_sales
                   WHERE dataset = :d AND customer_id IS NOT NULL GROUP BY customer_id)
        SELECT COUNT(*) AS customers, COUNT(*) FILTER (WHERE n > 1) AS repeat_customers,
               AVG(n) AS orders_per_customer FROM c""", dataset).iloc[0]
    weekday = _df(engine, """SELECT EXTRACT(ISODOW FROM invoice_day)::int AS dow, COUNT(DISTINCT invoice) AS orders
                             FROM marts.fct_sales WHERE dataset = :d GROUP BY 1 ORDER BY 1""", dataset)
    anomalies = _df(engine, """SELECT invoice_day, gross_revenue, orders, upper_bound, direction
                               FROM marts.daily_anomalies WHERE dataset = :d ORDER BY gross_revenue DESC""", dataset)
    big_cancel = _df(engine, """
        SELECT c.invoice_day, c.invoice, c.stock_code, COALESCE(p.product_name, 'UNKNOWN') AS product_name,
               -c.quantity AS units, c.cancelled_amount
        FROM marts.fct_cancellations c
        LEFT JOIN marts.dim_product p ON p.dataset = c.dataset AND p.stock_code = c.stock_code
        WHERE c.dataset = :d ORDER BY c.cancelled_amount DESC LIMIT 5""", dataset)

    out: list[str] = []
    title = "Analyse — échantillon SYNTHÉTIQUE" if dataset == DATASET_SAMPLE else "Analyse — Online Retail II (données réelles)"
    out += [f"# {title}", ""]
    if dataset == DATASET_SAMPLE:
        out += ["> ⚠️ Données **inventées** par `sample_data.py` : aucune conclusion métier n'est possible.", ""]
    else:
        out += [f"> Source : Online Retail II, UCI Machine Learning Repository, DOI {UCI_DOI}, CC BY 4.0.", ""]
    out += [
        f"_Rapport généré automatiquement le {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC depuis les marts "
        f"PostgreSQL — run #{run['run_id']}, fichier `{run['source_file']}`, SHA-256 `{run['file_sha256'][:12]}…`. "
        f"Régénérer : `python -m retail_analytics.cli report --dataset {dataset}`._",
        "",
        "## Indicateurs globaux",
        "",
        _table(pd.DataFrame([
            ("Période des ventes valides", f"{_day(k['first_sale_at'])} → {_day(k['last_sale_at'])}"),
            ("CA brut", _money(k["gross_revenue"])),
            ("Montant annulé", _money(k["cancelled_amount"])),
            ("CA net des annulations", _money(k["net_revenue"])),
            ("Commandes (factures avec ≥ 1 vente valide)", _int(k["orders"])),
            ("Factures d'annulation", _int(k["cancelled_invoices"])),
            ("Clients identifiés distincts", _int(k["customers"])),
            ("Unités vendues", _int(k["units"])),
            ("Panier moyen (CA brut / commande)", _money(k["avg_order_value"])),
            ("Part du CA sans client identifié", _pct(k["revenue_share_without_customer"])),
            ("Marge", "non calculable (aucun coût dans les données)"),
        ], columns=["Indicateur", "Valeur"])),
        "",
        "## Qualité des données",
        "",
        f"{_int(q['rows_total'])} lignes lues, **aucune supprimée** ; {_int(q['rows_valid_sale'])} ventes valides "
        f"({_pct(q['valid_sale_ratio'])}).",
        "",
        _table(pd.DataFrame(
            [(t, _int(n)) for t, n in q["line_types"].items()]
            + [("doublons exacts (toutes catégories, exclus)", _int(q["exact_duplicates"])),
               ("client manquant (toutes lignes)", _int(q["missing_values"]["customer_id"])),
               ("description manquante (toutes lignes)", _int(q["missing_values"]["description"])),
               ("codes produit à plusieurs libellés", _int(q["stock_codes_with_several_descriptions"]))],
            columns=["Catégorie", "Lignes"])),
        "",
        "## Tendance mensuelle",
        "",
        _table(monthly.assign(
            invoice_month=monthly["invoice_month"].map(lambda m: f"{m:%Y-%m}"),
            gross_revenue=monthly["gross_revenue"].map(_money),
            cancelled_amount=monthly["cancelled_amount"].map(_money),
            net_revenue=monthly["net_revenue"].map(_money),
            orders=monthly["orders"].map(_int), customers=monthly["customers"].map(_int),
        ).rename(columns={"invoice_month": "Mois", "gross_revenue": "CA brut", "cancelled_amount": "Annulé",
                          "net_revenue": "CA net", "orders": "Commandes", "customers": "Clients"})),
        "",
        f"Le premier et le dernier mois peuvent être partiels (ventes du "
        f"{_day(k['first_sale_at'])} au {_day(k['last_sale_at'])}).",
        "",
    ]
    if len(yoy) >= 2:
        a, b = yoy.iloc[-2], yoy.iloc[-1]
        out += [
            f"**Comparaison à périmètre égal (janvier–novembre)** : {yoy.index[-2]} = {_money(a['gross_revenue'])}, "
            f"{yoy.index[-1]} = {_money(b['gross_revenue'])} "
            f"({(b['gross_revenue'] / a['gross_revenue'] - 1):+.1%} de CA brut, "
            f"{(b['orders'] / a['orders'] - 1):+.1%} de commandes).",
            "",
        ]
    days = {1: "lun", 2: "mar", 3: "mer", 4: "jeu", 5: "ven", 6: "sam", 7: "dim"}
    out += [
        "Commandes par jour de semaine : "
        + ", ".join(f"{days[int(r.dow)]} {_int(r.orders)}" for r in weekday.itertuples()) + ".",
        "",
        f"## Produits (top {top_n})",
        "",
        "Par CA brut :",
        "",
        _table(top_gross.assign(**{c: top_gross[c].map(_money) for c in ["gross_revenue", "cancelled_amount",
                                                                         "net_revenue"]},
                                units_sold=top_gross["units_sold"].map(_int))),
        "",
        "Par CA net des annulations :",
        "",
        _table(top_net.assign(net_revenue=top_net["net_revenue"].map(_money),
                              units_sold=top_net["units_sold"].map(_int), orders=top_net["orders"].map(_int))),
        "",
        (f"Concentration : les 20 % de produits les plus vendus (sur {_int(concentration['products'])}) "
         f"réalisent {_pct(concentration['top20_share'])} du CA brut.")
        if not _missing(concentration["products"]) else "Concentration : aucun produit vendu.",
        "",
        "Plus grosses annulations :",
        "",
        _table(big_cancel.assign(cancelled_amount=big_cancel["cancelled_amount"].map(_money),
                                 units=big_cancel["units"].map(_int))),
        "",
        f"## Géographie (top {top_n} sur {n_countries} pays)",
        "",
        _table(countries.assign(gross_revenue=countries["gross_revenue"].map(_money),
                                revenue_share=countries["revenue_share"].map(_pct),
                                orders=countries["orders"].map(_int), customers=countries["customers"].map(_int))),
        "",
        "## Clients",
        "",
        (f"{_int(repeat['customers'])} clients identifiés, dont {_int(repeat['repeat_customers'])} "
         f"({repeat['repeat_customers'] / repeat['customers']:.1%}) ont passé au moins deux commandes ; "
         f"{float(repeat['orders_per_customer']):.2f} commandes par client en moyenne. Les ventes sans client "
         f"identifié ({_pct(k['revenue_share_without_customer'])} du CA) sont exclues de ces calculs.")
        if repeat["customers"] else "Aucun client identifié parmi les ventes valides.",
        "",
        "## Jours atypiques (Tukey, 3×IQR)",
        "",
        _table(anomalies.assign(gross_revenue=anomalies["gross_revenue"].map(_money),
                                upper_bound=anomalies["upper_bound"].map(_money)))
        if len(anomalies) else "Aucun jour atypique.",
        "",
    ]
    return "\n".join(out)
