"""Accès PostgreSQL : moteur SQLAlchemy, exécution des scripts SQL, COPY rapide."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection

from retail_analytics.config import SQL_DIR, get_settings


class DatabaseNotConfigured(RuntimeError):
    pass


class PipelineBusy(RuntimeError):
    """Un autre chargement détient le verrou depuis plus longtemps que PIPELINE_LOCK_TIMEOUT."""


class SchemaVersionMismatch(RuntimeError):
    """La base a été créée par une version incompatible du schéma."""


# Version du schéma persistant (raw / staging / meta). À incrémenter à toute modification de table de
# sql/01_schema.sql, avec une note de migration dans docs/architecture.md. Les marts, eux, sont reconstruits
# à chaque chargement et ne sont pas concernés.
SCHEMA_VERSION = 1
DEFAULT_CONNECT_TIMEOUT_S = 10
DEFAULT_LOCK_TIMEOUT_S = 900  # un chargement réel dure ~2 min ; au-delà de 15 min d'attente, on abandonne
# Clé arbitraire mais fixe du verrou consultatif PostgreSQL qui sérialise les chargements.
PIPELINE_LOCK_KEY = 74_201_001


def get_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    if not url:
        raise DatabaseNotConfigured(
            "DATABASE_URL absent : copiez .env.example en .env et renseignez la connexion PostgreSQL."
        )
    # Délai de connexion borné : sans lui, un hôte injoignable bloque le pipeline plusieurs minutes.
    timeout = int(os.getenv("DB_CONNECT_TIMEOUT", DEFAULT_CONNECT_TIMEOUT_S))
    connect_args = {"connect_timeout": timeout} if url.startswith("postgresql") else {}
    return create_engine(url, pool_pre_ping=True, future=True, connect_args=connect_args)


def check_connection(engine: Engine) -> str:
    with engine.connect() as conn:
        return conn.execute(text("SELECT version()")).scalar_one()


def run_sql_file(conn: Connection, path: Path) -> None:
    """Exécute un script SQL complet (plusieurs instructions, sans paramètres) sur la connexion donnée."""
    if not path.exists():
        raise FileNotFoundError(
            f"Script SQL introuvable : {path}. Le projet doit être installé en mode éditable (pip install -e .) "
            "depuis le dépôt, car les fichiers sql/ ne sont pas inclus dans le paquet."
        )
    conn.exec_driver_sql(path.read_text(encoding="utf-8"))


@contextmanager
def pipeline_lock(engine: Engine) -> Iterator[None]:
    """Verrou consultatif de session : un seul chargement à la fois par base. Les autres attendent, au plus
    PIPELINE_LOCK_TIMEOUT secondes, puis échouent avec un message clair au lieu d'attendre indéfiniment."""
    from sqlalchemy.exc import OperationalError

    timeout_s = int(os.getenv("PIPELINE_LOCK_TIMEOUT", DEFAULT_LOCK_TIMEOUT_S))
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"SET lock_timeout = '{timeout_s}s'")  # entier validé ci-dessus
        try:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": PIPELINE_LOCK_KEY})
        except OperationalError as exc:
            if getattr(getattr(exc, "orig", None), "sqlstate", None) == "55P03":  # lock_not_available
                raise PipelineBusy(
                    f"un autre chargement est en cours depuis plus de {timeout_s} s sur cette base. Attendez sa "
                    "fin, ou vérifiez qu'aucun processus n'est bloqué (pg_stat_activity)."
                ) from exc
            raise
        conn.exec_driver_sql("SET lock_timeout = 0")
        try:
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": PIPELINE_LOCK_KEY})


def _installed_schema_version(conn: Connection) -> int | None:
    if conn.execute(text("SELECT to_regclass('meta.schema_info')")).scalar() is None:
        return None
    return conn.execute(text("SELECT version FROM meta.schema_info")).scalar()


def init_schema(engine: Engine) -> None:
    """Crée le schéma s'il n'existe pas. Refuse une base créée par une version incompatible : sans ce contrôle,
    CREATE TABLE IF NOT EXISTS laisserait l'ancienne table en place et l'erreur surviendrait plus tard, obscure."""
    with engine.begin() as conn:
        installed = _installed_schema_version(conn)
        if installed is not None and installed != SCHEMA_VERSION:
            raise SchemaVersionMismatch(
                f"la base contient le schéma v{installed}, ce code attend la v{SCHEMA_VERSION}. Utilisez une base "
                "vide (ou supprimez les schémas raw, staging, marts, meta) puis rechargez les fichiers sources."
            )
        run_sql_file(conn, SQL_DIR / "01_schema.sql")


def build_marts(conn: Connection) -> None:
    run_sql_file(conn, SQL_DIR / "02_marts.sql")


def _python_rows(df: pd.DataFrame) -> Iterable[tuple]:
    """Convertit un DataFrame en tuples Python natifs (NA/NaT -> None) pour COPY."""
    obj = df.astype(object).where(df.notna(), None)
    for row in obj.itertuples(index=False, name=None):
        yield tuple(v.to_pydatetime() if isinstance(v, pd.Timestamp) else v for v in row)


def copy_dataframe(conn: Connection, table: str, df: pd.DataFrame) -> int:
    """COPY ... FROM STDIN dans la transaction courante (beaucoup plus rapide que INSERT ligne à ligne)."""
    cols = ", ".join(df.columns)
    cursor = conn.connection.cursor()
    with cursor.copy(f"COPY {table} ({cols}) FROM STDIN") as copy:
        for row in _python_rows(df):
            copy.write_row(row)
    return len(df)
