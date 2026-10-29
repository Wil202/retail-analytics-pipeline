"""KPI calculés en Pandas, comparés à des valeurs calculées à la main sur tiny_rows (voir conftest)."""

from datetime import date

from conftest import make_raw
from retail_analytics.kpis import compute_kpis
from retail_analytics.transform import clean

# Calcul manuel : ventes valides = 5.00 + 10.00 + 10.00 + 24.00 = 49.00 (doublon exclu),
# annulation = 1 x 8.00, commandes 500001/500002/500003, clients 20001/20002, unités 2+1+4+3.
EXPECTED = {
    "gross_revenue": 49.00,
    "cancelled_amount": 8.00,
    "net_revenue": 41.00,
    "orders": 3,
    "customers": 2,
    "units": 10,
    "avg_order_value": 16.33,
    "revenue_share_without_customer": 0.2041,
}


def test_kpis_match_hand_computation(tiny_rows):
    assert compute_kpis(clean(make_raw(tiny_rows))) == EXPECTED


def test_kpis_date_filter(tiny_rows):
    k = compute_kpis(clean(make_raw(tiny_rows)), start=date(2024, 2, 1), end=date(2024, 2, 29))
    assert k["gross_revenue"] == 34.00 and k["orders"] == 2 and k["cancelled_amount"] == 8.00


def test_kpis_country_filter(tiny_rows):
    k = compute_kpis(clean(make_raw(tiny_rows)), countries=("France",))
    assert k == {**k, "gross_revenue": 15.00, "orders": 1, "customers": 1, "cancelled_amount": 0.0}


def test_kpis_empty_result_has_no_division_error(tiny_rows):
    k = compute_kpis(clean(make_raw(tiny_rows)), countries=("Japan",))
    assert k["orders"] == 0 and k["avg_order_value"] is None and k["revenue_share_without_customer"] is None
