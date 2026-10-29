"""Dashboard Streamlit. Toutes les valeurs viennent de PostgreSQL via retail_analytics.kpis.

Lancement : streamlit run dashboard/app.py
"""

from __future__ import annotations

import altair as alt
import streamlit as st
from sqlalchemy.exc import InterfaceError, OperationalError

from retail_analytics import kpis
from retail_analytics.config import DATASET_SAMPLE
from retail_analytics.db import get_engine
from retail_analytics.validate import UNSPECIFIED_COUNTRIES

st.set_page_config(page_title="Retail Analytics", page_icon="📊", layout="wide")


@st.cache_resource
def engine():
    return get_engine()


@st.cache_data(ttl=3600, show_spinner=False)
def cached(fn_name: str, version: int, *args, **kwargs):
    """Résultat mis en cache par (fonction, n° de run actif, arguments). Un nouveau chargement change le n° de
    run, donc la clé : le dashboard ne montre jamais les chiffres d'une version remplacée."""
    return getattr(kpis, fn_name)(engine(), *args, **kwargs)


def money(v: float | None) -> str:
    return "—" if v is None else f"£{v:,.0f}".replace(",", " ")


def main() -> None:
    st.title("Retail Analytics — ventes en ligne")

    try:
        datasets = kpis.available_datasets(engine())  # non mis en cache : requête légère, source de vérité
    except Exception as exc:  # base absente, schéma non créé...
        st.error(f"Impossible de lire PostgreSQL : {exc}")
        st.info("Vérifiez .env puis lancez : `python -m retail_analytics.cli run --source sample`")
        st.stop()
    if datasets.empty:
        st.warning("Aucun dataset chargé. Lancez d'abord le pipeline (voir README).")
        st.stop()

    # ------------------------------------------------------------------ filtres
    with st.sidebar:
        st.header("Filtres")
        # Données réelles d'abord ; l'échantillon synthétique, réservé à la démo hors ligne, en dernier.
        names = sorted(datasets["dataset"].tolist(), key=lambda d: (d == DATASET_SAMPLE, d))
        dataset = st.selectbox("Dataset", names)
        version = int(datasets.set_index("dataset").loc[dataset, "run_id"])
        lo, hi = cached("date_bounds", version, dataset)
        if lo is None:
            st.warning("Ce dataset ne contient ni vente valide ni annulation.")
            st.stop()
        period = st.date_input("Période", value=(lo, hi), min_value=lo, max_value=hi)
        if isinstance(period, tuple) and len(period) == 2:
            start, end = period
        else:  # sélection en cours (une seule date) : on filtre ce jour plutôt que d'ignorer le choix
            start = end = period[0] if isinstance(period, tuple) and period else (period or lo)
            st.caption(f"Une seule date choisie : affichage du {start:%d/%m/%Y}. Choisissez une date de fin "
                       "pour une période.")
        countries = st.multiselect("Pays (vide = tous)", cached("list_countries", version, dataset))
        top_n = st.slider("Taille des classements", 5, 25, 10)
        # Par défaut au CA NET : au CA brut, deux commandes géantes intégralement annulées placent à tort deux
        # produits dans le top 10 (voir docs/findings.md).
        rank_by = st.radio("Classer les produits par", list(kpis.PRODUCT_RANKINGS),
                           index=list(kpis.PRODUCT_RANKINGS).index("net_revenue"),
                           format_func={"gross_revenue": "CA brut", "net_revenue": "CA net des annulations",
                                        "units": "Unités"}.get)
        run = datasets.set_index("dataset").loc[dataset]
        st.caption(f"Source : {run['source_file']} · run #{run['run_id']} · {run['rows_extracted']} lignes")

    if dataset == DATASET_SAMPLE:
        st.warning("⚠️ Données **synthétiques** générées pour la démonstration : ces chiffres ne décrivent "
                   "aucune entreprise réelle.")

    f = kpis.Filters(dataset=dataset, start=start, end=end, countries=tuple(countries))
    k = cached("kpis", version, f)
    if k["orders"] == 0:
        extra = f" (annulations sur la période : {money(k['cancelled_amount'])})" if k["cancelled_amount"] else ""
        st.info(f"Aucune vente pour ces filtres{extra}. Élargissez la période ou la sélection de pays.")
        st.stop()

    # ------------------------------------------------------------------ indicateurs
    c = st.columns(4)
    c[0].metric("CA brut", money(k["gross_revenue"]))
    c[1].metric("CA net des annulations", money(k["net_revenue"]),
                help=f"CA brut moins {money(k['cancelled_amount'])} d'annulations (factures « C »).")
    c[2].metric("Commandes", f"{k['orders']:,}".replace(",", " "))
    c[3].metric("Panier moyen", money(k["avg_order_value"]))
    c = st.columns(4)
    c[0].metric("Clients identifiés", f"{k['customers']:,}".replace(",", " "))
    c[1].metric("Unités vendues", f"{k['units']:,}".replace(",", " "))
    share = k["revenue_share_without_customer"]
    c[2].metric("CA sans client identifié", "—" if share is None else f"{share:.1%}")
    c[3].metric("Marge", "non calculable", help="Le dataset ne contient aucun coût d'achat.")

    # ------------------------------------------------------------------ évolution
    st.subheader("Évolution mensuelle")
    monthly = cached("monthly_trend", version, f)
    metric = st.radio("Mesure", ["gross_revenue", "net_revenue", "orders", "customers"], horizontal=True,
                      format_func={"gross_revenue": "CA brut", "net_revenue": "CA net", "orders": "Commandes",
                                   "customers": "Clients"}.get)
    st.altair_chart(
        alt.Chart(monthly).mark_line(point=True).encode(
            x=alt.X("yearmonth(invoice_month):T", title="Mois", axis=alt.Axis(format="%b %Y")),
            y=alt.Y(f"{metric}:Q", title=None),
            tooltip=[alt.Tooltip("yearmonth(invoice_month):T", title="Mois", format="%B %Y"),
                     alt.Tooltip("gross_revenue:Q", title="CA brut (£)", format=",.0f"),
                     alt.Tooltip("cancelled_amount:Q", title="Annulé (£)", format=",.0f"),
                     alt.Tooltip("net_revenue:Q", title="CA net (£)", format=",.0f"),
                     alt.Tooltip("orders:Q", title="Commandes"), alt.Tooltip("customers:Q", title="Clients")],
        ).properties(height=300),
        width="stretch",
    )
    st.caption(f"Clients = clients identifiés distincts du mois (non additifs d'un mois à l'autre). "
               f"Période affichée : {start:%d/%m/%Y} → {end:%d/%m/%Y} ; le premier et le dernier mois peuvent être "
               f"incomplets.")

    # ------------------------------------------------------------------ classements
    left, right = st.columns(2)
    with left:
        st.subheader(f"Top {top_n} produits")
        prods = cached("top_products", version, f, n=top_n, by=rank_by)
        if prods.empty:
            st.info("Aucun produit.")
        else:
            st.altair_chart(
                alt.Chart(prods).mark_bar().encode(
                    x=alt.X(f"{rank_by}:Q", title=None),
                    y=alt.Y("product_name:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
                    tooltip=[alt.Tooltip("stock_code", title="Code"), alt.Tooltip("product_name", title="Produit"),
                             alt.Tooltip("gross_revenue:Q", title="CA brut (£)", format=",.0f"),
                             alt.Tooltip("cancelled_amount:Q", title="Annulé (£)", format=",.0f"),
                             alt.Tooltip("net_revenue:Q", title="CA net (£)", format=",.0f"),
                             alt.Tooltip("units", title="Unités"), alt.Tooltip("orders", title="Commandes")],
                ).properties(height=28 * len(prods)),
                width="stretch",
            )
    with right:
        st.subheader("Classement des pays")
        ctry = cached("country_ranking", version, f, n=top_n)
        if ctry.empty:
            st.info("Aucun pays.")
        else:
            ctry = ctry.assign(revenue_share=ctry["gross_revenue"] / k["gross_revenue"])
            st.dataframe(
                ctry, hide_index=True, width="stretch",
                column_config={
                    "country": st.column_config.TextColumn("Pays"),
                    "orders": st.column_config.NumberColumn("Cmd."),
                    "customers": st.column_config.NumberColumn("Clients"),
                    "gross_revenue": st.column_config.NumberColumn("CA brut (£)", format="%.0f"),
                    "revenue_share": st.column_config.NumberColumn("Part", format="percent"),
                },
            )
            if ctry["country"].isin(UNSPECIFIED_COUNTRIES).any():
                st.caption("« Unspecified » = pays non renseigné dans la source, pas un marché.")

    # ------------------------------------------------------------------ qualité & anomalies
    st.subheader("Qualité des données (version active, sans filtre)")
    q = cached("quality_breakdown", version, dataset)
    total = int(q["lines"].sum()) if not q.empty else 0
    if total:
        summary = q.groupby("line_type", as_index=False)["lines"].sum().sort_values("lines", ascending=False)
        dup = int(q.loc[q["is_duplicate"], "lines"].sum())
        a, b = st.columns([2, 1])
        a.dataframe(summary.assign(part=summary["lines"] / total), hide_index=True, width="stretch",
                    column_config={"line_type": st.column_config.TextColumn("Type de ligne"),
                                   "lines": st.column_config.NumberColumn("Lignes"),
                                   "part": st.column_config.NumberColumn("Part", format="percent")})
        b.metric("Lignes totales", f"{total:,}".replace(",", " "))
        b.metric("Doublons exacts (exclus)", f"{dup:,}".replace(",", " "))
        st.caption("Aucune ligne n'est supprimée : les lignes non « sale » ou dupliquées sont seulement exclues "
                   "des KPI. Détail des règles : docs/data_quality.md.")

    st.subheader("Jours atypiques (règle de Tukey, 3×IQR)")
    an = cached("anomalies", version, dataset)
    if an.empty:
        st.info("Aucun jour atypique détecté.")
    else:
        st.dataframe(an, hide_index=True, width="stretch", column_config={
            "invoice_day": st.column_config.DateColumn("Jour", format="DD/MM/YYYY"),
            "gross_revenue": st.column_config.NumberColumn("CA brut (£)", format="%.0f"),
            "orders": st.column_config.NumberColumn("Commandes"),
            "lower_bound": st.column_config.NumberColumn("Seuil bas (£)", format="%.0f"),
            "upper_bound": st.column_config.NumberColumn("Seuil haut (£)", format="%.0f"),
            "direction": st.column_config.TextColumn("Sens"),
        })


try:
    main()
except (OperationalError, InterfaceError) as exc:  # base coupée PENDANT la session
    st.error(f"Connexion PostgreSQL perdue : {str(getattr(exc, 'orig', exc)).splitlines()[0]}")
    st.info("Relancez la page une fois la base disponible.")
