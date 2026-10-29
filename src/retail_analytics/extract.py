"""Extraction : lecture du fichier source SANS transformation métier.

Toutes les valeurs sont conservées sous forme de texte (couche « raw ») avec leur provenance
(fichier, feuille, numéro de ligne, empreinte SHA-256 du fichier). Les types et règles métier
sont appliqués plus tard (transform.py), ce qui permet de rejouer le nettoyage sans relire la source.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


# Colonnes canoniques du projet.
CANONICAL_COLUMNS = [
    "invoice",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "unit_price",
    "customer_id",
    "country",
]

# Le fichier UCI (xlsx) et ses copies CSV circulant en ligne utilisent des noms différents :
# on accepte les variantes connues, après normalisation (minuscules, sans espaces ni « _ »).
COLUMN_ALIASES = {
    "invoice": "invoice",
    "invoiceno": "invoice",
    "stockcode": "stock_code",
    "description": "description",
    "quantity": "quantity",
    "invoicedate": "invoice_date",
    "price": "unit_price",
    "unitprice": "unit_price",
    "customerid": "customer_id",
    "country": "country",
}

METADATA_COLUMNS = ["source_file", "source_sheet", "source_row", "file_sha256"]


@dataclass(frozen=True)
class ExtractResult:
    data: pd.DataFrame  # colonnes canoniques (texte) + métadonnées de provenance
    file_sha256: str
    source_file: str
    unknown_columns: list[str]
    warnings: list[str] = field(default_factory=list)


def _normalize_name(name: object) -> str:
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def normalize_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Renomme les colonnes vers le schéma canonique. Retourne (df, colonnes inconnues ignorées)."""
    mapping: dict[str, str] = {}
    unknown: list[str] = []
    for col in df.columns:
        target = COLUMN_ALIASES.get(_normalize_name(col))
        if target is None:
            unknown.append(str(col))
        elif target in mapping.values():
            raise ValueError(f"Colonne en double après normalisation : {col!r} -> {target!r}")
        else:
            mapping[col] = target
    out = df.rename(columns=mapping)
    return out[[c for c in CANONICAL_COLUMNS if c in out.columns]], unknown


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _to_text(series: pd.Series) -> pd.Series:
    """Convertit en texte en préservant les valeurs manquantes (None) et les dates au format ISO."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.strftime("%Y-%m-%d %H:%M:%S").astype(object).where(series.notna(), None)

    def conv(v: object) -> object:
        if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
            return None
        if isinstance(v, pd.Timestamp):
            return v.strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(v, "isoformat") and not isinstance(v, str):  # datetime.datetime
            return v.isoformat(sep=" ")
        s = str(v)
        return s if s.strip() != "" else None

    return series.map(conv).astype(object)


CSV_ENCODINGS = ("utf-8-sig", "cp1252")  # cp1252 : encodage des CSV exportés par Excel sous Windows


def _read_csv(path: Path, warnings: list[str]) -> pd.DataFrame:
    for i, enc in enumerate(CSV_ENCODINGS):
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], encoding=enc)
        except UnicodeDecodeError:
            continue
        if i > 0:
            warnings.append(f"{path.name} n'est pas en UTF-8 : lu en {enc}")
        return df
    raise ValueError(f"Encodage de {path.name} non reconnu (essayés : {', '.join(CSV_ENCODINGS)})")


def _read_frames(path: Path, warnings: list[str]) -> list[tuple[str, pd.DataFrame]]:
    suffix = path.suffix.lower()
    if path.stat().st_size == 0:
        raise ValueError(f"Fichier vide : {path}")
    if suffix == ".csv":
        try:
            return [("csv", _read_csv(path, warnings))]
        except pd.errors.EmptyDataError as exc:
            raise ValueError(f"Fichier vide ou sans en-tête : {path}") from exc
    if suffix in {".xlsx", ".xls"}:
        sheets = pd.read_excel(path, sheet_name=None, dtype=object)
        return list(sheets.items())
    if suffix in {".rda", ".rdata", ".rds"}:  # miroir R du dataset (voir config.MIRROR_*)
        try:
            import pyreadr
        except ImportError as exc:
            raise ImportError("Lecture .rda : installez pyreadr (pip install pyreadr)") from exc
        return list(pyreadr.read_r(str(path)).items())
    raise ValueError(f"Format non supporté : {path.suffix} (attendu .csv, .xlsx ou .rda)")


def extract_file(path: str | Path) -> ExtractResult:
    """Lit un fichier .csv ou .xlsx (toutes les feuilles) et renvoie la couche brute en texte."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    sha = file_sha256(path)
    parts: list[pd.DataFrame] = []
    unknown_all: list[str] = []
    warnings: list[str] = []
    for sheet, frame in _read_frames(path, warnings):
        frame, unknown = normalize_columns(frame)
        unknown_all.extend(u for u in unknown if u not in unknown_all)
        frame = frame.apply(_to_text) if len(frame) else frame.astype(object)
        frame["source_file"] = path.name
        frame["source_sheet"] = str(sheet)
        frame["source_row"] = range(2, len(frame) + 2)  # n° de ligne tel que vu dans le fichier (en-tête = 1)
        frame["file_sha256"] = sha
        parts.append(frame)
    data = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=CANONICAL_COLUMNS)
    return ExtractResult(data=data, file_sha256=sha, source_file=path.name, unknown_columns=unknown_all,
                         warnings=warnings)
