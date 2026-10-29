from retail_analytics.config import SAMPLE_FILE
from retail_analytics.extract import extract_file
from retail_analytics.sample_data import (
    N_CANCELLATIONS, N_DUPLICATES, N_INVALID, N_STOCK_ADJ, N_ZERO_PRICE, generate_rows, write_sample,
)
from retail_analytics.transform import clean
from retail_analytics.validate import quality_report


def test_generation_is_deterministic():
    assert generate_rows(42) == generate_rows(42)
    assert generate_rows(42) != generate_rows(7)


def test_committed_sample_matches_generator(tmp_path):
    """Le CSV versionné doit être exactement celui que produit le générateur (reproductibilité)."""
    fresh = tmp_path / "s.csv"
    write_sample(fresh, seed=42)
    assert fresh.read_bytes() == SAMPLE_FILE.read_bytes()


def test_injected_anomalies_are_detected(tmp_path):
    path = tmp_path / "s.csv"
    write_sample(path)
    q = quality_report(clean(extract_file(path).data))
    assert q["exact_duplicates"] == N_DUPLICATES
    assert q["line_types"]["cancellation"] == N_CANCELLATIONS
    assert q["line_types"]["stock_adjustment"] == N_STOCK_ADJ
    assert q["line_types"]["zero_price"] == N_ZERO_PRICE
    assert q["line_types"]["invalid"] == N_INVALID
    assert q["line_types"]["bad_debt_adjustment"] == 1
    assert q["missing_values"]["customer_id"] > 0
