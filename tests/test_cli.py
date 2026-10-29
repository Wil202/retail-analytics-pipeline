import pytest

from retail_analytics import cli


def test_dry_run_on_sample_needs_no_database(capsys, monkeypatch, tmp_path):
    from functools import partial

    from retail_analytics import pipeline

    # Rapport écrit dans un dossier temporaire plutôt que dans data/reports/.
    monkeypatch.setattr(pipeline, "run_pipeline", partial(pipeline.run_pipeline, reports_dir=tmp_path))
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:1/none")  # ne doit pas être utilisé
    assert cli.main(["run", "--source", "sample", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DONNÉES SYNTHÉTIQUES" in out and "Ventes valides" in out and "PostgreSQL" not in out
    assert (tmp_path / "synthetic_sample_quality.json").exists()


def test_missing_uci_file_gives_clear_message(capsys, tmp_path):
    assert cli.main(["run", "--source", "uci", "--file", str(tmp_path / "absent.xlsx"), "--dry-run"]) == 2
    assert "archive.ics.uci.edu" in capsys.readouterr().err


def test_check_db_reports_unreachable_server(capsys, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:1/none")
    assert cli.main(["check-db"]) == 2
    assert "impossible" in capsys.readouterr().err


def test_parser_rejects_unknown_source():
    with pytest.raises(SystemExit):
        cli.main(["run", "--source", "ftp"])
