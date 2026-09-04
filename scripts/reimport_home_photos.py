#! /usr/bin/env python3
"""
Re-imports the home page photos from Immich.

The home page records were written by the Google Photos version of the CLI and
store PNGs.  Running "Update Photos" in the CLI alone would not replace them:
the sort key is the image hash, and re-encoding to WebP changes it, so the old
records would sit alongside the new ones and the page would show everything
twice.

This imports from Immich and then removes the records still holding the old
format, so the page ends up with exactly the current album.

Home records do not store an album id, so the album is chosen by name and
defaults to the one the existing photos came from.

Dry run by default; pass --apply to write.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "personal-site-cli"),
)

import boto3  # noqa: E402

from cli.home_cli import HomeCLI  # noqa: E402
from clients import AmplifyClient, ImmichClient, S3Client  # noqa: E402
from conf.config import Config  # noqa: E402
from utils.photo_processing import IMAGE_TYPE  # noqa: E402


class DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return {"__decimal__": str(o)}
        return super().default(o)


def normalize(timestamp: str) -> str:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--album", default="Home", help="Immich album name (default: Home)")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument(
        "--max-loss",
        type=int,
        default=0,
        help="allow this many photos on the page to be dropped because the album "
        "no longer holds them (default 0)",
    )
    parser.add_argument("--backup-dir", default="amplify_backups")
    args = parser.parse_args()

    config = Config.from_env_file(".env")
    session = boto3.Session(**config.boto3_session_kwargs())
    amplify = AmplifyClient(session, config.amplify_table_suffix)
    s3 = S3Client(session, config.aws_photos_bucket, config.image_base_url)
    immich = ImmichClient(config.immich_base_url, config.immich_api_key)
    immich.ping()

    albums = {a["albumName"].strip(): a for a in immich.get_albums()}
    if args.album not in albums:
        print(f"no Immich album named {args.album!r}")
        return 1

    album = albums[args.album]
    assets = immich.get_album_photos(album["id"])
    existing: List[Dict[str, Any]] = amplify.get_home_photos()
    stale = [r for r in existing if not r["src"].endswith(f".{IMAGE_TYPE}")]

    # The Amplify rows carry no capture time, so the guard compares counts
    lost = max(0, len(existing) - len(assets))

    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"album           : {args.album!r} ({len(assets)} images)")
    print(f"page now        : {len(existing)} photos, {len(stale)} in the old format")
    print(f"would be dropped: {lost} (on the page, not in the album)\n")

    if lost > args.max_loss:
        print(f"refusing: {lost} photos would be lost, --max-loss is {args.max_loss}")
        return 1

    if not args.apply:
        print("Dry run only. Re-run with --apply to write.")
        return 0

    os.makedirs(args.backup_dir, exist_ok=True)
    path = os.path.join(args.backup_dir, "HOME.json")
    if not os.path.exists(path):
        with open(path, "w") as handle:
            json.dump(
                {
                    "model": "HomePhoto",
                    "backed_up_at": datetime.now(timezone.utc).isoformat(),
                    "rows": existing,
                },
                handle,
                cls=DecimalEncoder,
                indent=2,
            )
        print(f"backed up {len(existing)} rows to {path}")

    home = HomeCLI(immich, s3, amplify)
    home._process_photos(album["id"])

    # The sort key is the image hash, so the newly written records cannot
    # collide with the old ones.  Remove whatever is still in the old format
    for record in stale:
        amplify.delete_home_photo(record["photoId"])
    print(f"\nremoved {len(stale)} old format rows")

    remaining = amplify.get_home_photos()
    print(f"home page now: {len(remaining)} photos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
