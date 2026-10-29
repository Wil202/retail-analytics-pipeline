import pandas as pd
import pytest

from conftest import UCI_HEADER, sale, write_csv
from retail_analytics.extract import CANONICAL_COLUMNS, extract_file, file_sha256, normalize_columns


def test_normalize_accepts_uci_xlsx_names():
    df = pd.DataFrame(columns=UCI_HEADER)
    out, unknown = normalize_columns(df)
    assert list(out.columns) == CANONICAL_COLUMNS
    assert unknown == []


def test_normalize_accepts_legacy_csv_names_and_reports_unknown():
    df = pd.DataFrame(columns=["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate",
                               "UnitPrice", "CustomerID", "Country", "Extra"])
    out, unknown = normalize_columns(df)
    assert list(out.columns) == CANONICAL_COLUMNS
    assert unknown == ["Extra"]


def test_normalize_rejects_ambiguous_columns():
    with pytest.raises(ValueError, match="double"):
        normalize_columns(pd.DataFrame(columns=["Price", "UnitPrice"]))


def test_extract_csv_keeps_text_missing_values_and_provenance(tmp_path):
    path = write_csv(tmp_path / "s.csv", [sale(customer=None), sale(invoice="500002", qty="007")])
    res = extract_file(path)
    df = res.data
    assert len(df) == 2
    assert df.loc[0, "customer_id"] is None or pd.isna(df.loc[0, "customer_id"])
    assert df.loc[1, "quantity"] == "007"  # texte brut conservé tel quel
    assert df["source_row"].tolist() == [2, 3]
    assert (df["file_sha256"] == file_sha256(path)).all()
    assert res.source_file == "s.csv"


def test_extract_xlsx_reads_all_sheets_and_formats_dates(tmp_path):
    path = tmp_path / "s.xlsx"
    a = pd.DataFrame([sale()], columns=UCI_HEADER)
    a["InvoiceDate"] = pd.to_datetime(a["InvoiceDate"])
    a["Customer ID"] = 20001.0  # comme dans le vrai fichier (float)
    with pd.ExcelWriter(path) as w:
        a.to_excel(w, sheet_name="Year 2009-2010", index=False)
        a.assign(Invoice="500009").to_excel(w, sheet_name="Year 2010-2011", index=False)
    df = extract_file(path).data
    assert sorted(df["source_sheet"].unique()) == ["Year 2009-2010", "Year 2010-2011"]
    assert df.loc[0, "invoice_date"] == "2024-03-01 10:00:00"


def test_extract_rejects_unknown_format(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{}")
    with pytest.raises(ValueError, match="Format"):
        extract_file(p)


def test_sha_changes_with_content(tmp_path):
    a = write_csv(tmp_path / "a.csv", [sale()])
    b = write_csv(tmp_path / "b.csv", [sale(qty="3")])
    assert file_sha256(a) != file_sha256(b)
