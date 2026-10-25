import argparse
import pathlib
import sys

from app import catalogue, certification
from app.db import init_db


def main():
    p = argparse.ArgumentParser(description="Certify destinations and write evidence files.")
    p.add_argument("--import-csv", help="CSV of destinations to import first")
    p.add_argument("--destination", type=int, action="append", help="destination id (repeatable)")
    p.add_argument("--all", action="store_true", help="certify every enabled destination")
    args = p.parse_args()

    init_db()
    if args.import_csv:
        print("import:", catalogue.import_csv(pathlib.Path(args.import_csv).read_text()))
    ids = args.destination or ([d["id"] for d in catalogue.list_destinations() if d["enabled"]] if args.all else [])
    failed = False
    for dest_id in ids:
        ev = certification.certify(dest_id)
        print(f"dest {dest_id} [{ev['connector_key']}] {ev['result'].upper()} "
              f"in {ev['total_seconds']}s -> {ev['evidence_path']}")
        failed = failed or ev["result"] != "passed"
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()