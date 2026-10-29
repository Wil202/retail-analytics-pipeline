import pandas as pd

from conftest import make_raw, sale
from retail_analytics.transform import clean, parse_customer_id, parse_dates


def test_no_row_is_ever_dropped(tiny_rows):
    raw = make_raw(tiny_rows)
    assert len(clean(raw)) == len(raw)


def test_line_type_classification(tiny_rows):
    out = clean(make_raw(tiny_rows))
    assert out["line_type"].tolist() == [
        "sale", "sale", "sale", "sale", "sale",
        "cancellation", "non_product", "stock_adjustment", "zero_price", "invalid",
    ]


def test_exact_duplicate_flags_only_later_occurrences(tiny_rows):
    out = clean(make_raw(tiny_rows))
    assert out["is_duplicate"].tolist()[:3] == [False, False, True]
    assert int(out["is_duplicate"].sum()) == 1
    assert int(out["is_valid_sale"].sum()) == 4


def test_near_duplicate_is_not_a_duplicate():
    out = clean(make_raw([sale(qty="2"), sale(qty="3")]))
    assert not out["is_duplicate"].any()


def test_missing_values_are_kept_and_flagged():
    out = clean(make_raw([sale(customer=None, desc=None), sale(customer="  ")]))
    assert out["customer_id"].isna().all()
    assert (~out["has_customer"]).all()
    assert out.loc[0, "has_description"] == False  # noqa: E712
    assert out["line_type"].eq("sale").all()  # client manquant != ligne invalide


def test_invalid_values_get_a_reason():
    out = clean(make_raw([
        sale(qty="abc"), sale(date="31/31/2024"), sale(price="free"), sale(code=None),
        sale(invoice=None), sale(qty="1.5"),
    ]))
    assert out["line_type"].eq("invalid").all()
    assert out["invalid_reason"].tolist() == [
        "bad_quantity", "bad_date", "bad_price", "missing_stock_code", "missing_invoice", "bad_quantity",
    ]
    assert not out["is_valid_sale"].any()


def test_priority_bad_debt_and_cancellation_over_other_rules():
    out = clean(make_raw([
        sale(invoice="A506401", code="B", qty="1", price="-11062.06", customer=None),
        sale(invoice="c500010", qty="-2"),  # minuscule normalisée
        sale(invoice="C500011", code="POST", qty="-1", price="18"),
    ]))
    assert out["line_type"].tolist() == ["bad_debt_adjustment", "cancellation", "cancellation"]
    assert out["is_product_code"].tolist() == [False, True, False]


def test_non_product_codes():
    codes = ["POST", "DOT", "M", "m", "BANK CHARGES", "AMAZONFEE", "ADJUST2", "TEST001", "gift_0001_10", "CRUK"]
    out = clean(make_raw([sale(code=c) for c in codes]))
    assert out["line_type"].eq("non_product").all()
    assert out["is_product_code"].eq(False).all()
    # Les codes produits « normaux », y compris avec suffixe lettre, restent des ventes
    out2 = clean(make_raw([sale(code="85123A"), sale(code="47566"), sale(code="DCGS0003")]))
    assert out2["line_type"].eq("sale").all()


def test_line_amount_and_types():
    out = clean(make_raw([sale(qty="3", price="2.55")]))
    assert out.loc[0, "line_amount"] == 7.65
    assert out.loc[0, "quantity"] == 3
    assert out.loc[0, "invoice_date"] == pd.Timestamp("2024-03-01 10:00:00")


def test_text_is_trimmed_and_whitespace_collapsed():
    out = clean(make_raw([sale(desc="  WHITE   HANGING  HEART ", country=" France ")]))
    assert out.loc[0, "description"] == "WHITE HANGING HEART"
    assert out.loc[0, "country"] == "France"


def test_parse_customer_id_handles_float_strings():
    s = parse_customer_id(pd.Series(["12345", "12345.0", None, "abc", "12345.5"]))
    assert s.tolist()[:2] == ["12345", "12345"]
    assert s.iloc[2:].isna().all()


def test_parse_dates_supports_iso_and_us_formats():
    s = parse_dates(pd.Series(["2010-12-01 08:26:00", "12/1/2010 8:26", "garbage", None]))
    assert s.iloc[0] == s.iloc[1] == pd.Timestamp("2010-12-01 08:26")
    assert s.iloc[2:].isna().all()


def test_cleaning_is_deterministic(tiny_rows):
    a, b = clean(make_raw(tiny_rows)), clean(make_raw(tiny_rows))
    pd.testing.assert_frame_equal(a, b)
    assert a["row_hash"].is_unique is False  # le doublon a la même empreinte
