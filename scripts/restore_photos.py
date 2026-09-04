#! /usr/bin/env python3
"""
Restores TravelPhoto rows saved by reimport_photos.py.

Each re-imported place has a JSON backup of the rows that were deleted.  This
puts them back, and optionally removes the rows the re-import created, which
together revert a place to exactly its previous state.

The S3 objects the restored rows point at are still there, so a plain restore
is enough to bring a place back.

Dry run by default; pass --apply to write.
"""

import argparse
import glob
import json
import os
import sys
from decimal import Decimal
from typing import Any, Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(SCRIPT_DIR), "personal-site-cli"))

import boto3  # noqa: E402

from clients import AmplifyClient  # noqa: E402
from conf.config import Config  # noqa: E402


def decode_decimals(obj: Dict[str, Any]) -> Any:
    if "__decimal__" in obj:
        return Decimal(obj["__decimal__"])
    return obj


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", default="amplify_backups")
    parser.add_argument("--place-id", help="restore only this place (default: every backup)")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument(
        "--purge-current",
        action="store_true",
        help="also delete rows the re-import created, reverting the place completely",
    )
    args = parser.parse_args()

    config = Config.from_env_file(".env")
    amplify = AmplifyClient(
        boto3.Session(**config.boto3_session_kwargs()), config.amplify_table_suffix
    )

    pattern = f"{args.place_id}.json" if args.place_id else "*.json"
    paths = sorted(glob.glob(os.path.join(args.backup_dir, pattern)))
    if not paths:
        print(f"no backups found in {os.path.abspath(args.backup_dir)}")
        return 1

    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}   backups: {len(paths)}")
    print(f"current rows: {'PURGED' if args.purge_current else 'left in place'}\n")

    # One scan up front; the photo table has no query path by place
    current: Dict[str, List[Dict[str, Any]]] = {}
    for row in amplify.get_all_photos():
        current.setdefault(row["placeId"], []).append(row)

    restored = purged = skipped = 0

    for path in paths:
        with open(path) as handle:
            backup = json.load(handle, object_hook=decode_decimals)

        if backup.get("model") != "TravelPhoto":
            print(f"  {os.path.basename(path)}: not an Amplify backup -- SKIPPED")
            skipped += 1
            continue

        place_id = backup["place_id"]
        rows: List[Dict[str, Any]] = backup["rows"]
        live = current.get(place_id, [])
        backed_up_ids = {r["photoId"] for r in rows}

        print(f"  {backup['place_name']}: restoring {len(rows)} rows (currently {len(live)})")

        if not args.apply:
            continue

        for row in rows:
            amplify.put_photo(row)
        restored += len(rows)

        if args.purge_current:
            for row in live:
                if row["photoId"] in backed_up_ids:
                    continue
                amplify.delete_photo(row["albumId"], row["photoId"])
                purged += 1

    print(f"\n  rows restored: {restored}")
    print(f"  rows purged  : {purged}")
    print(f"  files skipped: {skipped}")
    if not args.apply:
        print("\nDry run only. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
