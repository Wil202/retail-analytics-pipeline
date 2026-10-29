"""Nettoyage et typage avec Pandas.

Principe : AUCUNE ligne n'est supprimée. Chaque ligne brute produit exactement une ligne nettoyée,
enrichie de types corrects et d'indicateurs (line_type, is_duplicate, ...). Les analyses filtrent
ensuite explicitement sur ces indicateurs, ce qui rend chaque exclusion traçable et réversible.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

# Codes article qui ne sont pas des produits (frais de port, remises, frais bancaires, tests...).
# Identifiés dans Online Retail II ; liste documentée dans docs/data_quality.md.
NON_PRODUCT_PATTERN = (
    r"^(?:POST|DOT|M|C2|D|S|B|CRUK|PADS|BANK CHARGES|AMAZONFEE|ADJUST\d*|TEST\d+|GIFT_\d+_\d+)$"
)

# Ordre de priorité de la classification (première règle qui s'applique).
LINE_TYPES = [
    "invalid",                # champ obligatoire manquant ou illisible
    "bad_debt_adjustment",    # factures « A... » : ajustements comptables de créances
    "cancellation",           # factures « C... » : annulations / retours
    "non_product",            # frais de port, remises, frais bancaires...
    "stock_adjustment",       # quantité <= 0 hors annulation (casse, perte, correction d'inventaire)
    "zero_price",             # prix <= 0 hors cas ci-dessus (échantillons, cadeaux, corrections)
    "sale",                   # vente exploitable
]

BUSINESS_KEY = ["invoice", "stock_code", "description", "quantity", "invoice_date", "unit_price", "customer_id", "country"]

# Bornes de plausibilité : une date hors de [2000-01-01 ; maintenant + 1 jour] est lisible mais aberrante
# (date système erronée, numéro de série Excel mal converti...). Elle est conservée, marquée invalid.
MIN_PLAUSIBLE_DATE = pd.Timestamp("2000-01-01")
MAX_FUTURE_TOLERANCE = timedelta(days=1)

DATE_ORDERS = ("auto", "mdy", "dmy")
_SLASH = r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})"
_SLASH_FORMATS = {
    "mdy": ["%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"],
    "dmy": ["%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y"],
}


def _clean_text(s: pd.Series) -> pd.Series:
    out = s.astype("string").str.strip()
    out = out.str.replace(r"\s+", " ", regex=True)
    return out.mask(out == "")


def parse_customer_id(s: pd.Series) -> pd.Series:
    """'12345', '12345.0' -> '12345' ; vide / non numérique -> <NA>."""
    num = pd.to_numeric(_clean_text(s), errors="coerce")
    whole = num.where(num.notna() & (num == num.round()))
    return whole.astype("Int64").astype("string")


def infer_slash_date_order(s: pd.Series) -> str | None:
    """Ordre des dates « a/b/AAAA » d'une colonne : 'mdy', 'dmy', 'ambiguous' (a et b toujours <= 12),
    'mixed' (les deux ordres prouvés dans le même fichier) ou None (aucune date de ce type).

    La décision est prise sur TOUTE la colonne : une ligne isolée ne peut pas être devinée de façon fiable.
    """
    txt = _clean_text(s)
    txt = txt[txt.str.contains("/", regex=False, na=False)]  # filtre rapide : les dates ISO n'ont pas de « / »
    parts = txt.str.extract(_SLASH).dropna().astype(int)
    if parts.empty:
        return None
    first_gt_12, second_gt_12 = bool((parts[0] > 12).any()), bool((parts[1] > 12).any())
    if first_gt_12 and second_gt_12:
        return "mixed"
    if first_gt_12:
        return "dmy"
    if second_gt_12:
        return "mdy"
    return "ambiguous"


def parse_dates(s: pd.Series, order: str = "auto") -> pd.Series:
    """ISO 8601 (xlsx, .rda, échantillon) puis « a/b/AAAA hh:mm[:ss] » des copies CSV.

    order='auto' déduit l'ordre jour/mois de la colonne ; si ce n'est pas déductible (« ambiguous »), l'ordre
    US des copies CSV publiques d'Online Retail est utilisé et clean() émet un avertissement. En cas d'ordres
    mélangés (« mixed »), les dates à barres obliques ne sont PAS devinées : elles restent illisibles (NaT).
    """
    if order not in DATE_ORDERS:
        raise ValueError(f"order doit valoir l'une de {DATE_ORDERS}")
    return _parse_dates(s, _resolve_order(order, s))


def _resolve_order(order: str, s: pd.Series, inferred: str | None = "unknown") -> str | None:
    """Ordre effectif ('mdy', 'dmy') ou None (pas de date « a/b/AAAA » à interpréter, ou ordres mélangés)."""
    if order != "auto":
        return order
    if inferred == "unknown":
        inferred = infer_slash_date_order(s)
    if inferred in (None, "mixed"):
        return None
    return "mdy" if inferred == "ambiguous" else inferred


def _parse_dates(s: pd.Series, order: str | None) -> pd.Series:
    txt = _clean_text(s)
    out = pd.to_datetime(txt, format="ISO8601", errors="coerce")
    if order is None:
        return out
    slash = txt.str.match(_SLASH).fillna(False).astype(bool)
    for fmt in _SLASH_FORMATS[order]:
        todo = slash & out.isna()
        if not todo.any():
            break
        out = out.mask(todo, pd.to_datetime(txt.where(todo), format=fmt, errors="coerce"))
    return out


def _row_hash(df: pd.DataFrame) -> pd.Series:
    """Empreinte déterministe des colonnes métier (vectorisée, rapide sur ~1 M lignes)."""
    as_text = df[BUSINESS_KEY].astype("string").fillna("\x00")
    hashed = pd.util.hash_pandas_object(as_text, index=False)
    return hashed.map(lambda v: f"{v:016x}").astype("string")


def clean(raw: pd.DataFrame, date_order: str = "auto") -> pd.DataFrame:
    """Transforme la couche brute (texte) en couche nettoyée typée et annotée.

    Les avertissements (ex. ordre des dates non déductible) sont renvoyés dans ``df.attrs["warnings"]``.
    """
    warnings: list[str] = []
    df = pd.DataFrame(index=raw.index)
    for col in ["source_file", "source_sheet", "source_row", "file_sha256"]:
        if col in raw:
            df[col] = raw[col]

    df["invoice"] = _clean_text(raw["invoice"]).str.upper()
    df["stock_code"] = _clean_text(raw["stock_code"]).str.upper()
    df["description"] = _clean_text(raw["description"])
    df["quantity"] = pd.to_numeric(_clean_text(raw["quantity"]), errors="coerce")
    if date_order not in DATE_ORDERS:
        raise ValueError(f"date_order doit valoir l'une de {DATE_ORDERS}")
    inferred = infer_slash_date_order(raw["invoice_date"]) if date_order == "auto" else None
    if date_order == "auto":
        if inferred == "ambiguous":
            warnings.append("dates « a/b/AAAA » ambiguës (jour et mois <= 12 partout) : ordre mois/jour supposé ; "
                            "forcez-le avec --date-order dmy|mdy si nécessaire")
        elif inferred == "mixed":
            warnings.append("dates « a/b/AAAA » aux ordres jour/mois mélangés : non interprétées (line_type=invalid)")
    df["invoice_date"] = _parse_dates(raw["invoice_date"], _resolve_order(date_order, raw["invoice_date"], inferred))
    df["unit_price"] = pd.to_numeric(_clean_text(raw["unit_price"]), errors="coerce").round(4)
    df["customer_id"] = parse_customer_id(raw["customer_id"])
    df["country"] = _clean_text(raw["country"])

    # Quantité non entière = donnée invalide (le dataset ne contient que des unités).
    non_integer_qty = df["quantity"].notna() & (df["quantity"] != df["quantity"].round())
    df["quantity"] = df["quantity"].where(~non_integer_qty).astype("Int64")

    issues = pd.Series("", index=df.index, dtype="string")
    for col, label in [
        ("invoice", "missing_invoice"),
        ("stock_code", "missing_stock_code"),
        ("quantity", "bad_quantity"),
        ("invoice_date", "bad_date"),
        ("unit_price", "bad_price"),
    ]:
        issues = issues.mask(df[col].isna() & (issues == ""), label)
    out_of_range = df["invoice_date"].notna() & (
        (df["invoice_date"] < MIN_PLAUSIBLE_DATE) | (df["invoice_date"] > pd.Timestamp.now() + MAX_FUTURE_TOLERANCE)
    )
    issues = issues.mask(out_of_range & (issues == ""), "date_out_of_range")
    df["invalid_reason"] = issues.mask(issues == "")

    df["line_amount"] = (df["quantity"].astype("Float64") * df["unit_price"]).round(2)
    df["has_customer"] = df["customer_id"].notna()
    df["has_description"] = df["description"].notna()

    inv = df["invoice"].fillna("")
    code = df["stock_code"].fillna("")
    line_type = pd.Series("sale", index=df.index, dtype="string")
    # Application dans l'ordre inverse de priorité : la règle la plus prioritaire écrase les autres.
    line_type = line_type.mask(df["unit_price"].fillna(0) <= 0, "zero_price")
    line_type = line_type.mask(df["quantity"].fillna(0) <= 0, "stock_adjustment")
    df["is_product_code"] = ~code.str.fullmatch(NON_PRODUCT_PATTERN) & df["stock_code"].notna()
    line_type = line_type.mask(~df["is_product_code"], "non_product")
    line_type = line_type.mask(inv.str.startswith("C"), "cancellation")
    line_type = line_type.mask(inv.str.startswith("A"), "bad_debt_adjustment")
    line_type = line_type.mask(df["invalid_reason"].notna(), "invalid")
    df["line_type"] = line_type

    # Doublons exacts : toutes les colonnes métier identiques. La 1re occurrence est conservée comme
    # « originale », les suivantes sont marquées is_duplicate=True (jamais supprimées).
    # La comparaison porte sur les valeurs elles-mêmes, pas sur l'empreinte : aucun faux doublon par collision.
    df["row_hash"] = _row_hash(df)
    df["is_duplicate"] = df.duplicated(subset=BUSINESS_KEY, keep="first")
    df["is_valid_sale"] = (df["line_type"] == "sale") & ~df["is_duplicate"]
    df.attrs["warnings"] = warnings
    return df
