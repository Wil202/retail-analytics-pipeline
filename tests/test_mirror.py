"""Source de repli : lecture .rda et vérification stricte de l'empreinte du miroir."""

import hashlib

import pandas as pd
import pytest

from conftest import UCI_HEADER, sale
from retail_analytics import sources
from retail_analytics.config import MIRROR_FILE_NAME, UCI_XLSX_NAME
from retail_analytics.extract import extract_file
from retail_analytics.transform import clean

pyreadr = pytest.importorskip("pyreadr")


def _rda(tmp_path):
    """Fichier .rda aux types du miroir réel : Quantity/CustomerID en float, dates en datetime."""
    df = pd.DataFrame([sale(), sale(invoice="C500002", qty="-1", customer=None)],
                      columns=["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price",
                               "CustomerID", "Country"])
    df["Quantity"] = df["Quantity"].astype(float)
    df["Price"] = df["Price"].astype(float)
    df["CustomerID"] = pd.to_numeric(df["CustomerID"])
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    path = tmp_path / "x.rda"
    pyreadr.write_rdata(str(path), df, df_name="onlineretail2")
    return path


def test_rda_is_read_and_cleaned_like_the_official_file(tmp_path):
    raw = extract_file(_rda(tmp_path)).data
    assert raw["source_sheet"].tolist() == ["onlineretail2"] * 2
    out = clean(raw)
    assert out["customer_id"].tolist()[0] == "20001"  # 20001.0 -> "20001"
    assert out["quantity"].tolist() == [2, -1]  # 2.0 -> 2
    assert out["invoice_date"].iloc[0] == pd.Timestamp("2024-03-01 10:00")
    assert out["line_type"].tolist() == ["sale", "cancellation"]
    assert UCI_HEADER[0] == "Invoice"


def _serve(tmp_path, content: bytes):
    src = tmp_path / "remote.bin"
    src.write_bytes(content)
    return src.as_uri(), hashlib.sha256(content).hexdigest()


def test_fetch_mirror_accepts_expected_checksum(tmp_path):
    url, sha = _serve(tmp_path, b"donnees")
    dest = tmp_path / "raw"
    path = sources.fetch_mirror(dest, url=url, expected_sha256=sha)
    assert path.name == MIRROR_FILE_NAME and path.read_bytes() == b"donnees"
    assert sources.fetch_mirror(dest, url="file:///inexistant", expected_sha256=sha) == path  # déjà présent : pas de 2e téléchargement


def test_fetch_mirror_rejects_tampered_file(tmp_path):
    url, _ = _serve(tmp_path, b"fichier modifie")
    dest = tmp_path / "raw"
    with pytest.raises(ValueError, match="SHA-256"):
        sources.fetch_mirror(dest, url=url, expected_sha256="0" * 64)
    assert list(dest.iterdir()) == []  # rien n'est conservé


def test_default_uci_file_prefers_official_source(tmp_path):
    assert sources.default_uci_file(tmp_path).name == UCI_XLSX_NAME  # rien de présent : on indique le fichier officiel
    (tmp_path / MIRROR_FILE_NAME).write_bytes(b"x")
    assert sources.default_uci_file(tmp_path).name == MIRROR_FILE_NAME
    (tmp_path / UCI_XLSX_NAME).write_bytes(b"x")
    assert sources.default_uci_file(tmp_path).name == UCI_XLSX_NAME


def test_failed_download_leaves_no_partial_file(tmp_path):
    dest = tmp_path / "x.bin"
    with pytest.raises(OSError):  # urllib.error.URLError hérite d'OSError
        sources.download((tmp_path / "absent.bin").as_uri(), dest)
    assert not dest.exists()


def test_unzip_extracts_only_the_expected_file(tmp_path):
    import zipfile

    archive = tmp_path / "a.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(f"nested/{UCI_XLSX_NAME}", b"xlsx")
        zf.writestr("../evil.txt", b"x")
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    out = sources.unzip_uci_archive(archive, raw_dir)
    assert out == raw_dir / UCI_XLSX_NAME and out.read_bytes() == b"xlsx"
    assert not (tmp_path / "evil.txt").exists()  # un membre au chemin « ../ » n'est jamais extrait
    with zipfile.ZipFile(tmp_path / "b.zip", "w") as zf:
        zf.writestr("other.xlsx", b"x")
    with pytest.raises(FileNotFoundError):
        sources.unzip_uci_archive(tmp_path / "b.zip", tmp_path)


def test_fetch_official_is_a_noop_when_file_present(tmp_path):
    (tmp_path / UCI_XLSX_NAME).write_bytes(b"x")
    assert sources.fetch_official(tmp_path, url="file:///inexistant") == tmp_path / UCI_XLSX_NAME
