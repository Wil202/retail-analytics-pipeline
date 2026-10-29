"""Chargement idempotent dans PostgreSQL.

Garanties :
- raw     : INSERT ... ON CONFLICT DO NOTHING sur (dataset, sha256 du fichier, feuille, ligne)
            => recharger le même fichier n'ajoute aucune ligne.
- staging : upsert sur la même clé => un changement de règle de nettoyage met à jour les lignes existantes.
- marts   : reconstruits depuis la version ACTIVE du dataset (meta.dataset_current)
            => une nouvelle version du fichier remplace l'ancienne dans les analyses, sans doublon ni suppression.
Tout se fait dans une seule transaction : en cas d'erreur, rien n'est modifié et l'exécution est marquée 'failed'.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import Engine, text

from retail_analytics import __version__
from retail_analytics.db import build_marts, copy_dataframe, init_schema, pipeline_lock
from retail_analytics.extract import CANONICAL_COLUMNS

RAW_COLUMNS = ["dataset", "file_sha256", "source_file", "source_sheet", "source_row", *CANONICAL_COLUMNS]
STAGING_COLUMNS = [
    "dataset", "file_sha256", "source_sheet", "source_row",
    "invoice", "stock_code", "description", "quantity", "invoice_date", "unit_price", "customer_id", "country",
    "line_amount", "line_type", "invalid_reason", "is_product_code", "has_customer", "has_description",
    "row_hash", "is_duplicate", "is_valid_sale",
]
_KEY = ["dataset", "file_sha256", "source_sheet", "source_row"]
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadStats:
    run_id: int
    rows_extracted: int
    rows_new_raw: int
    rows_staging: int


def _start_run(engine: Engine, dataset: str, source_file: str, sha: str, n: int) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text("""INSERT INTO meta.load_runs (dataset, source_file, file_sha256, rows_extracted, pipeline_version)
                    VALUES (:d, :f, :s, :n, :v) RETURNING run_id"""),
            {"d": dataset, "f": source_file, "s": sha, "n": n, "v": __version__},
        ).scalar_one()


def _fail_run(engine: Engine, run_id: int, error: Exception) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE meta.load_runs SET status='failed', finished_at=now(), error_message=:e WHERE run_id=:r"),
            {"e": f"{type(error).__name__}: {error}"[:2000], "r": run_id},
        )


def _close_interrupted_runs(engine: Engine) -> int:
    """Sous verrou, aucun autre chargement n'est actif : un run encore 'running' a été interrompu (processus tué,
    coupure). On le marque 'failed' au lieu de le laisser « en cours » indéfiniment."""
    with engine.begin() as conn:
        return conn.execute(text(
            "UPDATE meta.load_runs SET status = 'failed', finished_at = now(), "
            "error_message = 'interrompu : exécution arrêtée avant la fin (détecté au chargement suivant)' "
            "WHERE status = 'running'")).rowcount


def load_to_postgres(
    engine: Engine,
    raw: pd.DataFrame,
    clean: pd.DataFrame,
    *,
    dataset: str,
    source_file: str,
    file_sha256: str,
    quality: dict,
) -> LoadStats:
    if len(raw) != len(clean):
        raise ValueError("raw et clean doivent avoir le même nombre de lignes (aucune suppression autorisée)")
    with pipeline_lock(engine):
        init_schema(engine)
        _close_interrupted_runs(engine)
        return _load_locked(engine, raw, clean, dataset=dataset, source_file=source_file,
                            file_sha256=file_sha256, quality=quality)


def _load_locked(engine: Engine, raw: pd.DataFrame, clean: pd.DataFrame, *, dataset: str, source_file: str,
                 file_sha256: str, quality: dict) -> LoadStats:
    run_id = _start_run(engine, dataset, source_file, file_sha256, len(raw))

    raw_df = raw.assign(dataset=dataset)[RAW_COLUMNS]
    stg_df = clean.assign(dataset=dataset)[STAGING_COLUMNS]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in STAGING_COLUMNS if c not in _KEY)
    key = ", ".join(_KEY)
    try:
        with engine.begin() as conn:
            # Tables temporaires de même type que les cibles, sans contraintes (run_id ajouté à l'insertion).
            conn.exec_driver_sql(
                f"CREATE TEMP TABLE tmp_raw ON COMMIT DROP AS SELECT {', '.join(RAW_COLUMNS)} "
                "FROM raw.sales_lines WITH NO DATA"
            )
            conn.exec_driver_sql(
                f"CREATE TEMP TABLE tmp_stg ON COMMIT DROP AS SELECT {', '.join(STAGING_COLUMNS)} "
                "FROM staging.sales_lines WITH NO DATA"
            )
            copy_dataframe(conn, "tmp_raw", raw_df)
            copy_dataframe(conn, "tmp_stg", stg_df)
            new_raw = conn.execute(
                text(f"""INSERT INTO raw.sales_lines ({", ".join(RAW_COLUMNS)}, run_id)
                         SELECT {", ".join(RAW_COLUMNS)}, :r FROM tmp_raw
                         ON CONFLICT ({key}) DO NOTHING"""),
                {"r": run_id},
            ).rowcount
            staged = conn.execute(
                text(f"""INSERT INTO staging.sales_lines ({", ".join(STAGING_COLUMNS)}, run_id)
                         SELECT {", ".join(STAGING_COLUMNS)}, :r FROM tmp_stg
                         ON CONFLICT ({key}) DO UPDATE SET {set_clause}, run_id = EXCLUDED.run_id"""),
                {"r": run_id},
            ).rowcount
            conn.execute(
                text("""INSERT INTO meta.dataset_current (dataset, file_sha256, run_id) VALUES (:d, :s, :r)
                        ON CONFLICT (dataset) DO UPDATE
                        SET file_sha256 = EXCLUDED.file_sha256, run_id = EXCLUDED.run_id, activated_at = now()"""),
                {"d": dataset, "s": file_sha256, "r": run_id},
            )
            build_marts(conn)
            conn.execute(
                text("""UPDATE meta.load_runs SET status='success', finished_at=now(), rows_new_raw=:nr,
                        rows_staging=:ns, quality_report=CAST(:q AS JSONB) WHERE run_id=:r"""),
                {"nr": new_raw, "ns": staged, "q": json.dumps(quality, default=str), "r": run_id},
            )
    except Exception as exc:
        try:
            _fail_run(engine, run_id, exc)
        except Exception as record_exc:  # ne jamais masquer l'erreur d'origine
            log.error("Impossible d'enregistrer l'échec du run %s : %s", run_id, record_exc)
        raise
    return LoadStats(run_id=run_id, rows_extracted=len(raw), rows_new_raw=new_raw, rows_staging=staged)
