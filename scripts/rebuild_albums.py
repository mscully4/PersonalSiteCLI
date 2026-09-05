#! /usr/bin/env python3
"""
Recreates missing Immich albums from the photos already recorded in DynamoDB.

Some places have album records whose titles match nothing in Immich, usually
because the album was never recreated there.  The photos themselves are almost
always still in the library, just not gathered into an album.  Every photo
record stores the capture time it was imported with, so the assets can be found
by timestamp and collected into a new album.

The album is created with exactly the stored title, so relink_albums.py then
matches it as an exact match.  This script therefore only writes to Immich; run
relink_albums.py afterwards to repoint the DynamoDB records.

Immich zeroes the sub second part of fileCreatedAt, so a burst can put several
assets on one timestamp.  By default one asset is taken per stored photo, which
keeps the album the same size as the original.  --include-bursts takes every
asset sharing a timestamp instead.

Dry run by default; pass --apply to create albums.
"""

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(SCRIPT_DIR), "personal-site-cli"))
sys.path.insert(0, SCRIPT_DIR)

import boto3  # noqa: E402

from clients import DDBClient, ImmichClient, Namespaces, TravelEntities  # noqa: E402
from conf.config import Config  # noqa: E402
from relink_albums import match_album  # noqa: E402

ALBUM_PK = f"{Namespaces.TRAVEL}#{TravelEntities.ALBUM}"
PHOTO_PK = f"{Namespaces.TRAVEL}#{TravelEntities.PHOTO}"


def normalize(timestamp: str) -> str:
    """
    Truncates a stored timestamp to whole seconds in UTC.

    Records written at different times carry different precision, some with
    fractional seconds and some without, while Immich always reports whole
    seconds
    """
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def all_image_assets(immich: ImmichClient) -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []
    page = 1
    while page:
        result = immich._post_json(
            "/search/metadata", {"type": "IMAGE", "size": 1000, "page": page}
        )["assets"]
        assets += result["items"]
        next_page = result.get("nextPage")
        page = int(next_page) if next_page else 0
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="create albums (default: dry run)")
    parser.add_argument(
        "--include-bursts",
        action="store_true",
        help="include every asset sharing a timestamp, not one per stored photo",
    )
    parser.add_argument(
        "--top-up",
        action="store_true",
        help="also add missing assets to albums that exist but are under-populated",
    )
    parser.add_argument("--limit", type=int, help="stop after this many albums")
    parser.add_argument("--report", default="album_rebuild_report.csv")
    args = parser.parse_args()

    config = Config.from_env_file(".env")
    # The old single table is in a different region from the Amplify tables
    legacy = dict(config.boto3_session_kwargs())
    if config.legacy_aws_region_name:
        legacy["region_name"] = config.legacy_aws_region_name
    ddb = DDBClient(boto3.Session(**legacy), config.aws_table_name)
    immich = ImmichClient(config.immich_base_url, config.immich_api_key)
    immich.ping()

    immich_albums = immich.get_albums()
    exact = {a["albumName"].strip(): a["id"] for a in immich_albums}
    names = list(exact)

    index: Dict[str, List[str]] = {}
    for asset in all_image_assets(immich):
        index.setdefault(immich.asset_timestamp(asset), []).append(asset["id"])

    # Only rebuild albums that relink_albums.py could not match at all.  An
    # album it matches fuzzily already exists under a slightly different name,
    # and recreating it would leave two near-identical albums in Immich
    missing = []
    for record in ddb.get_equals(ALBUM_PK):
        matched, _, _ = match_album(record["title"].strip(), names, exact)
        if matched is None:
            missing.append(record)
    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"album records with no Immich album: {len(missing)}")
    print(f"library timestamps indexed        : {len(index)}\n")

    rows = []
    created = skipped_empty = skipped_unresolved = 0
    seen_titles: Set[str] = set()

    for record in missing:
        title = record["title"].strip()
        photos = ddb.get_begins_with(PHOTO_PK, record["place_id"])
        if not photos or title in seen_titles:
            skipped_empty += 1
            continue
        seen_titles.add(title)

        stamps = sorted(normalize(p["creation_timestamp"]) for p in photos)

        if args.include_bursts:
            asset_ids = list({i for s in stamps for i in index.get(s, [])})
        else:
            # One distinct asset per stored photo, so the rebuilt album is the
            # same size as the original rather than inflated by burst frames
            used: Set[str] = set()
            asset_ids = []
            for stamp in stamps:
                for asset_id in sorted(index.get(stamp, [])):
                    if asset_id not in used:
                        used.add(asset_id)
                        asset_ids.append(asset_id)
                        break

        resolved = sum(1 for s in stamps if s in index)
        rows.append(
            {
                "stored_title": title,
                "place_id": record["place_id"],
                "ddb_photos": len(stamps),
                "timestamps_resolved": resolved,
                "assets_selected": len(asset_ids),
                "action": "create" if asset_ids else "skip-unresolved",
            }
        )

        if not asset_ids:
            skipped_unresolved += 1
            continue

        print(f"  {title!r}: {len(stamps)} photos -> {len(asset_ids)} assets")

        if args.apply:
            immich._post_json("/albums", {"albumName": title, "assetIds": asset_ids})
            created += 1

        if args.limit and len(rows) >= args.limit:
            break

    if args.top_up:
        print("\ntopping up under-populated albums")
        topped = added_total = 0
        for record in ddb.get_equals(ALBUM_PK):
            album_id, _, _ = match_album(record["title"].strip(), names, exact)
            if album_id is None:
                continue

            photos = ddb.get_begins_with(PHOTO_PK, record["place_id"])
            if not photos:
                continue

            held = {a["id"] for a in immich.get_album_photos(album_id)}
            held_stamps = {immich.asset_timestamp(a) for a in immich.get_album_photos(album_id)}

            # An asset counts as missing when the site has a photo at that
            # second and the album holds nothing at that second
            add: List[str] = []
            for photo in photos:
                stamp = normalize(photo["creation_timestamp"])
                if stamp in held_stamps:
                    continue
                for asset_id in sorted(index.get(stamp, [])):
                    if asset_id not in held and asset_id not in add:
                        add.append(asset_id)
                        break

            if not add:
                continue

            print(
                f"  {record['title'].strip()!r}: +{len(add)} assets "
                f"(album had {len(held)}, site has {len(photos)})"
            )
            rows.append(
                {
                    "stored_title": record["title"].strip(),
                    "place_id": record["place_id"],
                    "ddb_photos": len(photos),
                    "timestamps_resolved": len(add),
                    "assets_selected": len(add),
                    "action": "top-up",
                }
            )
            topped += 1
            added_total += len(add)

            if args.apply:
                immich._request("PUT", f"/albums/{album_id}/assets", json={"ids": add})

        print(f"  albums topped up: {topped}   assets added: {added_total}")

    if rows:
        with open(args.report, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    print(f"\n  would create      : {sum(1 for r in rows if r['action'] == 'create')}")
    print(f"  created           : {created}")
    print(f"  skipped, no photos: {skipped_empty}")
    print(f"  skipped, no assets: {skipped_unresolved}")
    print(f"\nreport written to {args.report}")
    if not args.apply:
        print("\nDry run only. Re-run with --apply to create the albums,")
        print("then run relink_albums.py --apply to repoint the records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
