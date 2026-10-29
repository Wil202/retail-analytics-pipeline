"""Orchestration : extract -> validate (schéma) -> clean -> validate (lisibilité) -> rapport qualité -> load."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine

from retail_analytics.config import MAX_UNPARSEABLE_RATIO, PROCESSED_DIR, REPORTS_DIR
from retail_analytics.extract import extract_file
from retail_analytics.load import LoadStats, load_to_postgres
from retail_analytics.transform import clean
from retail_analytics.validate import quality_report, validate_parse_ratio, validate_schema

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    dataset: str
    rows: int
    quality: dict
    warnings: list[str]
    report_path: Path
    load: LoadStats | None
    seconds: float


def run_pipeline(
    path: str | Path,
    dataset: str,
    engine: Engine | None = None,
    *,
    dry_run: bool = False,
    export_clean: bool = False,
    reports_dir: Path = REPORTS_DIR,
    max_invalid_ratio: float = MAX_UNPARSEABLE_RATIO,
    date_order: str = "auto",
) -> PipelineResult:
    t0 = time.perf_counter()
    path = Path(path)
    log.info("Extraction de %s", path)
    extracted = extract_file(path)
    schema = validate_schema(extracted.data, extracted.unknown_columns)
    schema.raise_if_failed()

    log.info("Nettoyage de %d lignes", len(extracted.data))
    cleaned = clean(extracted.data, date_order=date_order)
    parse = validate_parse_ratio(cleaned, max_invalid_ratio)
    parse.raise_if_failed()

    quality = quality_report(cleaned)
    warnings = extracted.warnings + schema.warnings + cleaned.attrs.get("warnings", []) + parse.warnings
    quality.update({"dataset": dataset, "source_file": extracted.source_file, "file_sha256": extracted.file_sha256,
                    "warnings": warnings})
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{dataset}_quality.json"
    report_path.write_text(json.dumps(quality, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    if export_clean:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        cleaned.to_csv(PROCESSED_DIR / f"{dataset}_clean.csv", index=False)

    stats = None
    if not dry_run:
        if engine is None:
            raise ValueError("engine requis hors mode --dry-run")
        log.info("Chargement PostgreSQL (dataset=%s)", dataset)
        stats = load_to_postgres(
            engine, extracted.data, cleaned, dataset=dataset, source_file=extracted.source_file,
            file_sha256=extracted.file_sha256, quality=quality,
        )
    return PipelineResult(
        dataset=dataset, rows=len(cleaned), quality=quality, warnings=warnings,
        report_path=report_path, load=stats, seconds=round(time.perf_counter() - t0, 2),
    )
