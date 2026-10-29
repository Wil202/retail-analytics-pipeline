import pytest

from conftest import make_raw, sale
from retail_analytics.transform import clean
from retail_analytics.validate import (
    SchemaValidationError, quality_report, validate_parse_ratio, validate_schema,
)


def test_schema_ok(tiny_rows):
    assert validate_schema(make_raw(tiny_rows)).ok


def test_schema_missing_columns_is_fatal(tiny_rows):
    raw = make_raw(tiny_rows).drop(columns=["unit_price", "country"])
    res = validate_schema(raw)
    assert not res.ok
    with pytest.raises(SchemaValidationError, match="unit_price"):
        res.raise_if_failed()


def test_schema_empty_is_fatal():
    assert not validate_schema(make_raw([])).ok


def test_unknown_columns_are_only_a_warning(tiny_rows):
    res = validate_schema(make_raw(tiny_rows), unknown_columns=["Extra"])
    assert res.ok and res.warnings


def test_parse_ratio_threshold():
    rows = [sale()] * 9 + [sale(qty="bad")]
    assert not validate_parse_ratio(clean(make_raw(rows)), max_ratio=0.05).ok  # 10 % > 5 %
    assert validate_parse_ratio(clean(make_raw(rows)), max_ratio=0.2).ok


def test_quality_report_counts(tiny_rows):
    q = quality_report(clean(make_raw(tiny_rows)))
    assert q["rows_total"] == 10
    assert q["rows_valid_sale"] == 4
    assert q["exact_duplicates"] == 1
    assert q["cancellation_lines"] == 1
    assert q["cancellation_invoices"] == 1
    assert q["line_types"]["invalid"] == 1
    assert q["missing_values"]["customer_id"] == 2
    assert q["valid_sales_without_customer"] == 1
    assert q["negative_quantity_lines"] == 2
    assert q["invalid_reasons"] == {"bad_quantity": 1}
    assert q["date_min"].startswith("2024-01-10")
    assert sum(q["line_types"].values()) == q["rows_total"]


def test_quality_report_is_json_serialisable(tiny_rows):
    import json
    json.dumps(quality_report(clean(make_raw(tiny_rows))))


def test_quality_report_on_all_invalid_rows():
    q = quality_report(clean(make_raw([sale(qty="x"), sale(date="?")])))
    assert q["rows_valid_sale"] == 0 and q["valid_sale_ratio"] == 0.0
    assert isinstance(q["stock_codes_with_several_descriptions"], int)
    assert q["date_max"].startswith("2024-03-01")  # la 1re ligne a une date lisible malgré sa quantité invalide
