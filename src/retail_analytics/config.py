"""Configuration centralisée, lue depuis les variables d'environnement (et un .env local optionnel)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = DATA_DIR / "reports"
SAMPLE_FILE = DATA_DIR / "sample" / "online_retail_sample.csv"
SQL_DIR = PROJECT_ROOT / "sql"

# Source officielle (vérifiée le 2026-10-20) : UCI Machine Learning Repository, licence CC BY 4.0.
UCI_DATASET_PAGE = "https://archive.ics.uci.edu/dataset/502/online+retail+ii"
UCI_DOWNLOAD_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
UCI_DOI = "10.24432/C5CG6D"
UCI_XLSX_NAME = "online_retail_II.xlsx"
UCI_EXPECTED_ROWS = 1_067_371  # nombre d'instances annoncé par la page UCI

# Source de repli : package R « onlineretail2 » (A. Quadros), qui redistribue le même dataset avec
# l'autorisation du donateur (usage non commercial). Épinglé par commit + SHA-256 : un fichier modifié
# en amont est refusé. Vérifié le 2026-10-20 : 1 067 371 lignes, 2009-12-01 07:45 -> 2011-12-09 12:50.
MIRROR_REPO = "https://github.com/allanvc/onlineretail2"
MIRROR_COMMIT = "35b2729b7bb4c46831cb4fb4efde29edd3a8dd7e"
MIRROR_FILE_NAME = "onlineretail2.rda"
MIRROR_URL = f"https://raw.githubusercontent.com/allanvc/onlineretail2/{MIRROR_COMMIT}/data/{MIRROR_FILE_NAME}"
MIRROR_SHA256 = "be2480b1fcb1fa123f90d731f63ab3cf44f6c97cba0a38eabee93759d411c6f7"

DATASET_UCI = "uci_online_retail_ii"
DATASET_SAMPLE = "synthetic_sample"

# Seuil au-delà duquel le pipeline refuse de charger : trop de lignes illisibles = problème de format,
# pas de qualité de données.
MAX_UNPARSEABLE_RATIO = 0.05


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    test_database_url: str | None


def _build_url_from_parts() -> str | None:
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    if not user or not password:
        return None
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "retail")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return Settings(
        database_url=os.getenv("DATABASE_URL") or _build_url_from_parts(),
        test_database_url=os.getenv("TEST_DATABASE_URL"),
    )
