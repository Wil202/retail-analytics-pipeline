"""Validation du schéma (bloquante) et profil de qualité (documenté, non bloquant).

- validate_schema : la source a-t-elle la bonne forme ? Sinon on arrête tout.
- validate_parse_ratio : trop de lignes illisibles => format inattendu => on arrête.
- quality_report : mesure les problèmes de qualité (manquants, doublons, annulations...) sans rien supprimer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from retail_analytics.config import MAX_UNPARSEABLE_RATIO
from retail_analytics.extract import CANONICAL_COLUMNS
from retail_analytics.transform import LINE_TYPES

# customer_id et description peuvent manquer dans le dataset réel : ils sont requis comme COLONNES,
# pas comme valeurs.
REQUIRED_COLUMNS = CANONICAL_COLUMNS
UNSPECIFIED_COUNTRIES = ("Unspecified",)


class SchemaValidationError(ValueError):
    """La source ne respecte pas le schéma attendu."""


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_if_failed(self) -> None:
        if self.errors:
            raise SchemaValidationError("; ".join(self.errors))


def validate_schema(raw: pd.DataFrame, unknown_columns: list[str] | None = None) -> ValidationResult:
    result = ValidationResult()
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        msg = f"colonnes manquantes : {missing}"
        if unknown_columns and len(unknown_columns) == 1 and any(sep in unknown_columns[0] for sep in ";\t|"):
            msg += (f" — une seule colonne lue ({unknown_columns[0][:60]!r}) : séparateur probablement différent "
                    "de la virgule (« ; » ou tabulation). Convertissez le fichier en CSV séparé par des virgules")
        result.errors.append(msg)
    if len(raw) == 0:
        result.errors.append("aucune ligne de données")
    if unknown_columns:
        result.warnings.append(f"colonnes ignorées : {unknown_columns}")
    return result


def validate_parse_ratio(clean: pd.DataFrame, max_ratio: float = MAX_UNPARSEABLE_RATIO) -> ValidationResult:
    result = ValidationResult()
    if len(clean) == 0:
        return result
    ratio = float((clean["line_type"] == "invalid").mean())
    if ratio > max_ratio:
        result.errors.append(
            f"{ratio:.1%} de lignes illisibles (seuil {max_ratio:.0%}) : format de source probablement inattendu"
        )
    elif ratio > 0:
        result.warnings.append(f"{ratio:.2%} de lignes illisibles, conservées avec line_type='invalid'")
    return result


def _count(mask: pd.Series) -> int:
    return int(mask.sum())


def quality_report(clean: pd.DataFrame) -> dict:
    """Profil de qualité calculé sur la couche nettoyée. Toutes les valeurs proviennent des données."""
    n = len(clean)
    line_types = clean["line_type"].value_counts().reindex(LINE_TYPES, fill_value=0)
    raw_missing = {
        col: _count(clean[col].isna()) for col in ["invoice", "stock_code", "description", "quantity",
                                                    "invoice_date", "unit_price", "customer_id", "country"]
    }
    valid = clean[clean["is_valid_sale"]]
    dates = clean["invoice_date"].dropna()
    report = {
        "rows_total": n,
        "rows_valid_sale": len(valid),
        "valid_sale_ratio": round(len(valid) / n, 4) if n else 0.0,
        "line_types": {k: int(v) for k, v in line_types.items()},
        "missing_values": raw_missing,
        "invalid_reasons": {k: int(v) for k, v in clean["invalid_reason"].value_counts().items()},
        "exact_duplicates": _count(clean["is_duplicate"]),
        "cancellation_lines": int(line_types["cancellation"]),
        "cancellation_invoices": int(clean.loc[clean["line_type"] == "cancellation", "invoice"].nunique()),
        "negative_quantity_lines": _count(clean["quantity"].fillna(0) < 0),
        "non_positive_price_lines": _count(clean["unit_price"].fillna(1) <= 0),
        "valid_sales_without_customer": _count(~valid["has_customer"]),
        "date_min": dates.min().isoformat() if len(dates) else None,
        "date_max": dates.max().isoformat() if len(dates) else None,
        "distinct_countries": int(clean["country"].nunique()),
        # « Unspecified » est une valeur de la source signifiant « pays inconnu » : comptée comme un pays dans les
        # classements, elle est mesurée ici pour que le lecteur ne la prenne pas pour un vrai marché.
        "unspecified_country_lines": _count(clean["country"].isin(UNSPECIFIED_COUNTRIES)),
        "distinct_stock_codes": int(clean["stock_code"].nunique()),
        "stock_codes_with_several_descriptions": int(
            (valid.dropna(subset=["description"]).groupby("stock_code")["description"].nunique() > 1).sum()
        ),
    }
    return report
