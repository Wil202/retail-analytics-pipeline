"""Acquisition du dataset Online Retail II : source officielle UCI, puis miroir épinglé en repli.

Ce module ne fait que télécharger et vérifier des fichiers ; il ne lit pas leur contenu (voir extract.py).
"""

from __future__ import annotations

import shutil
import urllib.request
import zipfile
from pathlib import Path

from retail_analytics.config import (
    MIRROR_FILE_NAME, MIRROR_SHA256, MIRROR_URL, RAW_DIR, UCI_DOWNLOAD_URL, UCI_XLSX_NAME,
)
from retail_analytics.extract import file_sha256

DOWNLOAD_TIMEOUT_S = 60


def download(url: str, dest: Path, timeout: float = DOWNLOAD_TIMEOUT_S) -> None:
    """Téléchargement avec délai (urlretrieve n'en a pas : un serveur muet bloquerait indéfiniment).
    Aucun fichier partiel n'est laissé en cas d'échec."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp, dest.open("wb") as out:  # noqa: S310
            shutil.copyfileobj(resp, out, length=1 << 20)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def unzip_uci_archive(zip_path: Path, dest_dir: Path) -> Path:
    """Extrait online_retail_II.xlsx de l'archive UCI (seul ce fichier, vers un chemin contrôlé)."""
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if Path(m).name == UCI_XLSX_NAME]
        if not members:
            raise FileNotFoundError(f"{UCI_XLSX_NAME} absent de l'archive {zip_path}")
        target = dest_dir / UCI_XLSX_NAME
        with zf.open(members[0]) as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1 << 20)
    return target


def fetch_official(dest_dir: Path = RAW_DIR, url: str = UCI_DOWNLOAD_URL) -> Path:
    """Télécharge l'archive UCI et en extrait le .xlsx. Ne fait rien si le fichier est déjà présent."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / UCI_XLSX_NAME
    if target.exists():
        return target
    zip_path = dest_dir / "online_retail_ii.zip"
    download(url, zip_path)
    return unzip_uci_archive(zip_path, dest_dir)


def fetch_mirror(dest_dir: Path = RAW_DIR, url: str = MIRROR_URL, expected_sha256: str = MIRROR_SHA256) -> Path:
    """Télécharge le miroir épinglé et refuse tout fichier dont l'empreinte diffère."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / MIRROR_FILE_NAME
    if target.exists() and file_sha256(target) == expected_sha256:
        return target
    tmp = dest_dir / (MIRROR_FILE_NAME + ".part")
    download(url, tmp)
    actual = file_sha256(tmp)
    if actual != expected_sha256:
        tmp.unlink()
        raise ValueError(f"SHA-256 inattendu pour {url} : {actual} (attendu {expected_sha256})")
    tmp.replace(target)
    return target


def default_uci_file(raw_dir: Path = RAW_DIR) -> Path:
    """Fichier officiel s'il est présent (ou si rien n'est présent, pour le message d'erreur), sinon le miroir."""
    official, mirror = raw_dir / UCI_XLSX_NAME, raw_dir / MIRROR_FILE_NAME
    return mirror if mirror.exists() and not official.exists() else official
