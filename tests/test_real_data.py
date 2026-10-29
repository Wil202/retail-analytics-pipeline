"""Contrôles sur le VRAI dataset (opt-in : RUN_REAL_DATA=1 et fichier présent dans data/raw/).

Valeurs de référence : page UCI (nombre d'instances, période) et profil du fichier vérifié le 2026-10-20.
"""

import os

import pytest

from retail_analytics.sources import default_uci_file
from retail_analytics.config import UCI_EXPECTED_ROWS
from retail_analytics.extract import extract_file
from retail_analytics.transform import clean
from retail_analytics.validate import quality_report

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_DATA") != "1" or not default_uci_file().exists(),
    reason="RUN_REAL_DATA=1 et data/raw/ (online_retail_II.xlsx ou onlineretail2.rda) requis",
)


@pytest.fixture(scope="module")
def quality():
    return quality_report(clean(extract_file(default_uci_file()).data))


def test_row_count_matches_uci(quality):
    assert quality["rows_total"] == UCI_EXPECTED_ROWS


def test_period_matches_uci(quality):
    assert quality["date_min"].startswith("2009-12-01")
    assert quality["date_max"].startswith("2011-12-09")


def test_known_quality_issues_are_detected(quality):
    assert quality["line_types"]["invalid"] == 0
    assert quality["exact_duplicates"] > 30_000
    assert quality["line_types"]["cancellation"] > 19_000
    assert 0.9 < quality["valid_sale_ratio"] < 0.97
