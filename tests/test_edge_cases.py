"""Cas limites de lecture et de nettoyage (défauts D3 à D8 du rapport QA, docs/qa_report.md).

Chaque test décrit le comportement attendu ; il a été écrit AVANT la correction et échouait sur la v0.2.
"""

from pathlib import Path

import pandas as pd
import pytest

from conftest import make_raw, sale
from retail_analytics.extract import extract_file
from retail_analytics.transform import clean, infer_slash_date_order, parse_dates
from retail_analytics.validate import validate_schema

HEADER = "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"


def _csv(tmp_path: Path, body: str, name="f.csv", encoding="utf-8") -> Path:
    p = tmp_path / name
    p.write_bytes((HEADER + body).encode(encoding))
    return p


# ---------------------------------------------------------------- D3 : fichier vide
def test_zero_byte_file_gives_clear_error(tmp_path):
    p = tmp_path / "vide.csv"
    p.write_bytes(b"")
    with pytest.raises(ValueError, match="vide"):
        extract_file(p)


def test_header_only_file_is_rejected_by_schema(tmp_path):
    p = tmp_path / "entete.csv"
    p.write_text(HEADER)
    res = extract_file(p)
    assert not validate_schema(res.data).ok


# ---------------------------------------------------------------- D4 : mauvais séparateur
def test_semicolon_separator_error_mentions_separator(tmp_path):
    p = tmp_path / "pv.csv"
    p.write_text(HEADER.replace(",", ";") + "1;A;x;1;2010-12-01 08:26:00;1;1;UK\n")
    res = extract_file(p)
    v = validate_schema(res.data, res.unknown_columns)
    assert not v.ok and "séparateur" in " ".join(v.errors)


# ---------------------------------------------------------------- D5 : encodage Windows
def test_cp1252_csv_is_read_with_warning(tmp_path):
    p = _csv(tmp_path, "536365,85123A,CAFÉ CRÈME,6,12/1/2010 8:26,2.55,17850,France\n", encoding="cp1252")
    res = extract_file(p)
    assert res.data.loc[0, "description"] == "CAFÉ CRÈME"
    assert any("cp1252" in w for w in res.warnings)


# ---------------------------------------------------------------- D6 / D7 : formats de date
def test_us_date_with_seconds_is_parsed():
    s = parse_dates(pd.Series(["12/1/2010 08:26:00", "12/13/2010 8:26"]))
    assert s.tolist() == [pd.Timestamp("2010-12-01 08:26"), pd.Timestamp("2010-12-13 08:26")]


def test_day_first_dates_are_detected_not_swapped():
    s = parse_dates(pd.Series(["01/12/2010 08:26", "25/12/2010 09:00"]))
    assert s.tolist() == [pd.Timestamp("2010-12-01 08:26"), pd.Timestamp("2010-12-25 09:00")]


def test_slash_order_inference():
    assert infer_slash_date_order(pd.Series(["12/13/2010 8:26", "1/2/2010 8:00"])) == "mdy"
    assert infer_slash_date_order(pd.Series(["13/12/2010 8:26", "1/2/2010 8:00"])) == "dmy"
    assert infer_slash_date_order(pd.Series(["1/2/2010 8:00"])) == "ambiguous"
    assert infer_slash_date_order(pd.Series(["13/1/2010 8:00", "1/13/2010 8:00"])) == "mixed"
    assert infer_slash_date_order(pd.Series(["2010-12-01 08:26:00", None])) is None


def test_ambiguous_dates_produce_a_warning():
    out = clean(make_raw([sale(date="01/02/2010 08:00")]))
    assert any("ambigu" in w for w in out.attrs["warnings"])


def test_explicit_date_order_overrides_inference():
    out = clean(make_raw([sale(date="01/02/2010 08:00")]), date_order="dmy")
    assert out.loc[0, "invoice_date"] == pd.Timestamp("2010-02-01 08:00")
    assert not out.attrs["warnings"]


def test_mixed_date_orders_are_flagged_invalid_not_guessed():
    out = clean(make_raw([sale(date="13/01/2010 08:00"), sale(date="01/13/2010 08:00")]))
    assert out["line_type"].eq("invalid").all()
    assert out["invalid_reason"].eq("bad_date").all()


# ---------------------------------------------------------------- D8 : dates aberrantes
def test_out_of_range_dates_are_invalid():
    out = clean(make_raw([sale(date="2099-01-01 08:00:00"), sale(date="1900-01-01 08:00:00"),
                          sale(date="2010-12-01 08:00:00")]))
    assert out["invalid_reason"].tolist()[:2] == ["date_out_of_range", "date_out_of_range"]
    assert out["line_type"].tolist() == ["invalid", "invalid", "sale"]
    assert out["invoice_date"].notna().all()  # la date lue est conservée pour audit


# ---------------------------------------------------------------- non-régression : NA texte
def test_text_na_is_a_value_not_a_missing_value(tmp_path):
    p = _csv(tmp_path, "1,A,NA,6,2010-12-01 08:26:00,2.55,1,NA\n")
    out = clean(extract_file(p).data)
    assert out.loc[0, "country"] == "NA" and out.loc[0, "description"] == "NA"
