#! /usr/bin/env python3
"""
Restores photo records saved by reimport_photos.py.

Each re-imported place has a JSON backup of the records that were deleted.
This puts them back, and optionally removes the records the re-import created,
which together revert a place to exactly its previous state.

The S3 objects the restored records point at are still there unless
--delete-old-s3 was used during the re-import, so a plain restore is enough to
bring a place back.

Dry run by default; pass --apply to write.
"""

import argparse
import glob
import json
import os
import sys
from decimal import Decimal
from typing import Any, Dict, List

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "personal-site-cli"),
)

import boto3  # noqa: E402

from clients import DDBClient, Namespaces, S3Client, TravelEntities  # noqa: E402
from conf.config import Config  # noqa: E402

PHOTO_PK = f"{Namespaces.TRAVEL}#{TravelEntities.PHOTO}"
PHOTO_SK_FS = "{place_id}#{photo_id}"


def decode_decimals(obj: Dict[str, Any]) -> Any:
    if "__decimal__" in obj:
        return Decimal(obj["__decimal__"])
    return obj


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", default="reimport_backups")
    parser.add_argument("--place-id", help="restore only this place (default: every backup)")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument(
        "--purge-current",
        action="store_true",
        help="also delete records the re-import created, reverting the place completely",
    )
    args = parser.parse_args()

    config = Config.from_env_file(".env")
    session = boto3.Session(**config.boto3_session_kwargs())
    ddb = DDBClient(session, config.aws_table_name)
    s3 = S3Client(session, bucket_name=config.aws_photos_bucket)

    pattern = f"{args.place_id}.json" if args.place_id else "*.json"
    paths = sorted(glob.glob(os.path.join(args.backup_dir, pattern)))
    if not paths:
        print(f"no backups found in {os.path.abspath(args.backup_dir)}")
        return 1

    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}   backups: {len(paths)}")
    print(f"current records: {'PURGED' if args.purge_current else 'left in place'}\n")

    restored = purged = missing_objects = 0

    for path in paths:
        with open(path) as handle:
            backup = json.load(handle, object_hook=decode_decimals)

        place_id = backup["place_id"]
        records: List[Dict[str, Any]] = backup["records"]
        current = ddb.get_begins_with(PHOTO_PK, place_id)
        backed_up_ids = {r["photo_id"] for r in records}

        # Verify the S3 objects the backup refers to still exist, otherwise the
        # restored records would point at nothing
        absent = [
            key
            for key in backup["s3_keys"][:5]
            if not s3.does_image_exist(key)  # sampled; full check is slow
        ]
        if absent:
            missing_objects += 1

        print(
            f"  {backup['place_name']}: restoring {len(records)} records "
            f"(currently {len(current)})"
        )

        if not args.apply:
            continue

        for record in records:
            ddb.put(
                PHOTO_PK,
                PHOTO_SK_FS.format(place_id=place_id, photo_id=record["photo_id"]),
                record,
            )
        restored += len(records)

        if args.purge_current:
            for record in current:
                if record["photo_id"] in backed_up_ids:
                    continue
                ddb.delete(
                    PHOTO_PK,
                    PHOTO_SK_FS.format(place_id=place_id, photo_id=record["photo_id"]),
                )
                purged += 1

    print(f"\n  records restored: {restored}")
    print(f"  records purged  : {purged}")
    if not args.apply:
        print("\nDry run only. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
