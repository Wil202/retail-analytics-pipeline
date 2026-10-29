"""Interface en ligne de commande.

    python -m retail_analytics.cli generate-sample
    python -m retail_analytics.cli fetch-uci [--mirror]
    python -m retail_analytics.cli check-db
    python -m retail_analytics.cli run --source sample [--dry-run]
    python -m retail_analytics.cli run --source uci [--file data/raw/online_retail_II.xlsx]
    python -m retail_analytics.cli report [--dataset uci_online_retail_ii] [--output docs/analysis_uci.md]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from retail_analytics.config import (
    DATASET_SAMPLE, DATASET_UCI, MAX_UNPARSEABLE_RATIO, MIRROR_COMMIT, MIRROR_REPO, RAW_DIR, REPORTS_DIR, SAMPLE_FILE,
    UCI_DATASET_PAGE, UCI_DOWNLOAD_URL, UCI_EXPECTED_ROWS, UCI_XLSX_NAME,
)


def cmd_generate_sample(args: argparse.Namespace) -> int:
    from retail_analytics.sample_data import write_sample

    n = write_sample(SAMPLE_FILE, seed=args.seed)
    print(f"Échantillon SYNTHÉTIQUE écrit : {SAMPLE_FILE} ({n} lignes, graine {args.seed})")
    return 0


EXIT_OK, EXIT_ENV, EXIT_DATA = 0, 2, 3  # 2 = configuration / réseau / base ; 3 = données refusées


def cmd_fetch_uci(args: argparse.Namespace) -> int:
    from retail_analytics.sources import fetch_mirror, fetch_official

    try:
        print(f"Téléchargement de {UCI_DOWNLOAD_URL} ...")
        print(f"OK (source officielle UCI) : {fetch_official()}")
        return EXIT_OK
    except Exception as exc:  # réseau indisponible, proxy, archive invalide...
        print(f"Source officielle UCI injoignable ({exc}).", file=sys.stderr)
    if not args.mirror:
        print(f"Téléchargez manuellement l'archive depuis {UCI_DATASET_PAGE} et placez {UCI_XLSX_NAME} dans "
              f"{RAW_DIR}/, ou relancez avec --mirror (copie R épinglée : {MIRROR_REPO}).", file=sys.stderr)
        return EXIT_ENV
    try:
        print(f"Repli sur le miroir {MIRROR_REPO} @ {MIRROR_COMMIT[:7]} ...")
        path = fetch_mirror()
    except Exception as exc:
        print(f"Miroir indisponible ou invalide : {exc}", file=sys.stderr)
        return EXIT_ENV
    print(f"OK (miroir, SHA-256 vérifié) : {path}")
    return EXIT_OK


def cmd_check_db(args: argparse.Namespace) -> int:
    from retail_analytics.db import check_connection, get_engine

    try:
        print(check_connection(get_engine()))
    except Exception as exc:
        print(f"Connexion PostgreSQL impossible : {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from retail_analytics.pipeline import run_pipeline

    if args.source == "sample":
        path, dataset = Path(args.file) if args.file else SAMPLE_FILE, DATASET_SAMPLE
        if not path.exists():
            print(f"{path} absent : lancez d'abord `generate-sample`.", file=sys.stderr)
            return 2
    else:
        from retail_analytics.sources import default_uci_file

        path, dataset = Path(args.file) if args.file else default_uci_file(), DATASET_UCI
        if not path.exists():
            print(f"{path} absent : lancez `fetch-uci` (ou `fetch-uci --mirror`) ou téléchargez-le depuis "
                  f"{UCI_DATASET_PAGE}.", file=sys.stderr)
            return 2
        print(f"Fichier source   : {path}")

    engine = None
    if not args.dry_run:
        from retail_analytics.db import get_engine
        engine = get_engine()

    result = run_pipeline(path, dataset, engine, dry_run=args.dry_run, export_clean=args.export_clean,
                          max_invalid_ratio=args.max_invalid_ratio, date_order=args.date_order)
    q = result.quality
    print(f"Dataset          : {dataset}{'  (DONNÉES SYNTHÉTIQUES)' if dataset == DATASET_SAMPLE else ''}")
    print(f"Lignes lues      : {result.rows}")
    if dataset == DATASET_UCI and result.rows != UCI_EXPECTED_ROWS:
        print(f"Avertissement    : {UCI_EXPECTED_ROWS} lignes attendues d'après UCI, fichier probablement différent")
    print(f"Ventes valides   : {q['rows_valid_sale']} ({q['valid_sale_ratio']:.1%})")
    print(f"Types de lignes  : {q['line_types']}")
    print(f"Doublons exacts  : {q['exact_duplicates']}")
    print(f"Rapport qualité  : {result.report_path}")
    for w in result.warnings:
        print(f"Avertissement    : {w}")
    if result.load:
        s = result.load
        print(f"PostgreSQL       : run_id={s.run_id}, nouvelles lignes raw={s.rows_new_raw}, "
              f"lignes staging upsert={s.rows_staging}")
    print(f"Durée            : {result.seconds}s")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from retail_analytics.db import get_engine
    from retail_analytics.report import build_report

    try:
        md = build_report(get_engine(), args.dataset, top_n=args.top)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    out = Path(args.output) if args.output else REPORTS_DIR / f"{args.dataset}_analysis.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"Rapport écrit : {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="retail-pipeline", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate-sample", help="génère l'échantillon synthétique reproductible")
    g.add_argument("--seed", type=int, default=42)
    g.set_defaults(func=cmd_generate_sample)

    fu = sub.add_parser("fetch-uci", help="télécharge Online Retail II depuis UCI")
    fu.add_argument("--mirror", action="store_true",
                    help="si UCI est injoignable, utiliser la copie R épinglée (SHA-256 vérifié)")
    fu.set_defaults(func=cmd_fetch_uci)
    sub.add_parser("check-db", help="teste la connexion PostgreSQL").set_defaults(func=cmd_check_db)

    r = sub.add_parser("run", help="exécute le pipeline complet")
    r.add_argument("--source", choices=["sample", "uci"], required=True)
    r.add_argument("--file", help="chemin explicite du fichier source (.csv ou .xlsx)")
    r.add_argument("--dry-run", action="store_true", help="valide et nettoie sans écrire en base")
    r.add_argument("--export-clean", action="store_true", help="écrit aussi data/processed/<dataset>_clean.csv")
    r.add_argument("--date-order", choices=["auto", "mdy", "dmy"], default="auto",
                   help="ordre jour/mois des dates « a/b/AAAA » (défaut : déduit du fichier)")
    r.add_argument("--max-invalid-ratio", type=float, default=MAX_UNPARSEABLE_RATIO,
                   help="part maximale de lignes illisibles avant arrêt (défaut 0.05)")
    r.set_defaults(func=cmd_run)

    rp = sub.add_parser("report", help="génère le rapport d'analyse Markdown depuis les marts")
    rp.add_argument("--dataset", default=DATASET_UCI, help=f"défaut : {DATASET_UCI}")
    rp.add_argument("--output", help="défaut : data/reports/<dataset>_analysis.md")
    rp.add_argument("--top", type=int, default=10)
    rp.set_defaults(func=cmd_report)
    return p


def _first_line(exc: BaseException) -> str:
    text_ = str(getattr(exc, "orig", None) or exc).strip()
    return text_.splitlines()[0] if text_ else type(exc).__name__


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée : les erreurs attendues donnent un message d'une ligne et un code de sortie, jamais une
    trace Python. Les erreurs inattendues remontent (avec trace) pour ne pas masquer un bug."""
    from sqlalchemy.exc import InterfaceError, OperationalError

    from retail_analytics.db import DatabaseNotConfigured, PipelineBusy, SchemaVersionMismatch
    from retail_analytics.validate import SchemaValidationError

    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        return args.func(args)
    except DatabaseNotConfigured as exc:
        print(f"Configuration manquante : {exc}", file=sys.stderr)
        return EXIT_ENV
    except PipelineBusy as exc:
        print(f"Chargement impossible : {exc}", file=sys.stderr)
        return EXIT_ENV
    except SchemaVersionMismatch as exc:
        print(f"Base incompatible, rien n'a été modifié : {exc}", file=sys.stderr)
        return EXIT_ENV
    except (OperationalError, InterfaceError) as exc:
        print(f"Connexion PostgreSQL impossible : {_first_line(exc)}\n"
              "Vérifiez que le serveur tourne et que DATABASE_URL (.env) est correct, puis lancez `check-db`.",
              file=sys.stderr)
        return EXIT_ENV
    except (SchemaValidationError, ValueError, UnicodeDecodeError) as exc:
        print(f"Données refusées, rien n'a été chargé : {exc}", file=sys.stderr)
        return EXIT_DATA
    except FileNotFoundError as exc:
        print(f"Fichier introuvable : {exc}", file=sys.stderr)
        return EXIT_ENV


if __name__ == "__main__":
    raise SystemExit(main())
