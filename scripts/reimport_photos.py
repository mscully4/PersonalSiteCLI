#! /usr/bin/env python3
"""
Re-imports photos from Immich into the Amplify tables the site reads.

The existing rows were written from Google Photos and cannot be deduplicated
against Immich: the stored hash is an md5 of the rescaled image, Google served
a recompressed copy, and the images are now WebP rather than PNG.  The bytes
differ, so the hashes, the S3 keys and the photo ids all differ, and a plain
"Add Photos" would add everything a second time.

Photos are imported before the superseded rows are deleted, so a failure part
way through leaves a place showing duplicates rather than nothing.  Re-running
is safe: once a place holds Immich era rows their hashes match and the import
skips them.

Requires relink_albums.py to have run first, otherwise the stored album id is
still a Google Photos id and Immich cannot resolve it.

Dry run by default; pass --apply to write.
"""

import argparse
import collections
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(SCRIPT_DIR), "personal-site-cli"))

import boto3  # noqa: E402

from cli.travel_cli import TravelCLI  # noqa: E402
from clients import (  # noqa: E402
    AmplifyClient,
    GoogleMapsClient,
    ImmichClient,
    S3Client,
    destination_kwargs,
    place_kwargs,
)
from conf.config import Config  # noqa: E402
from models.travel import Destination, Place  # noqa: E402

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return {"__decimal__": str(o)}
        return super().default(o)


def write_backup(directory: str, place: Place, rows: List[Dict[str, Any]]) -> None:
    """
    Saves a place's rows before they are deleted.  The first backup is kept, so
    re-running cannot overwrite the pre-migration state
    """
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{place.place_id}.json")
    if os.path.exists(path):
        return

    with open(path, "w") as handle:
        json.dump(
            {
                "place_id": place.place_id,
                "place_name": place.name,
                "destination_id": place.destination_id,
                "backed_up_at": datetime.now(timezone.utc).isoformat(),
                "model": "TravelPhoto",
                "rows": rows,
            },
            handle,
            cls=DecimalEncoder,
            indent=2,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--place-id", help="re-import a single place")
    selection.add_argument("--destination-id", help="re-import every place in a destination")
    selection.add_argument("--all", action="store_true", help="re-import every place")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--limit", type=int, help="stop after this many places")
    parser.add_argument("--backup-dir", default="amplify_backups")
    parser.add_argument(
        "--max-loss",
        type=int,
        default=0,
        help="skip a place when the Immich album holds this many fewer photos than "
        "the site currently shows (default 0)",
    )
    args = parser.parse_args()

    config = Config.from_env_file(".env")
    session = boto3.Session(**config.boto3_session_kwargs())
    amplify = AmplifyClient(session, config.amplify_table_suffix)
    s3 = S3Client(session, config.aws_photos_bucket, config.image_base_url)
    immich = ImmichClient(config.immich_base_url, config.immich_api_key)
    immich.ping()

    travel = TravelCLI(GoogleMapsClient(config.google_maps_api_key), immich, s3, amplify)
    travel.quiet = True

    destinations = {d["destinationId"]: d for d in amplify.get_destinations()}
    albums = {a["placeId"]: a for a in amplify.get_all_albums()}

    # One scan up front rather than one per place: the photo table has no query
    # path by place, so each lookup would otherwise be a full scan
    by_place: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for row in amplify.get_all_photos():
        by_place[row["placeId"]].append(row)

    places: List[Place] = []
    for destination_id in destinations:
        if args.destination_id and destination_id != args.destination_id:
            continue
        for raw in amplify.get_places(destination_id):
            if args.place_id and raw["placeId"] != args.place_id:
                continue
            places.append(Place(**place_kwargs(raw)))

    if args.limit:
        places = places[: args.limit]

    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}   places selected: {len(places)}")
    print(f"backups: {os.path.abspath(args.backup_dir)}\n")

    stats = collections.Counter()
    started = time.time()

    for index, place in enumerate(places, start=1):
        album = albums.get(place.place_id)
        if album is None:
            stats["skipped_no_album"] += 1
            continue

        if not UUID_RE.match(album["albumId"]):
            print(f"  [{index}/{len(places)}] {place.name}: album not relinked -- SKIPPED")
            stats["skipped_not_relinked"] += 1
            continue

        try:
            assets = immich.get_album_photos(album["albumId"])
        except Exception as e:  # noqa: BLE001 - report and continue the batch
            print(f"  [{index}/{len(places)}] {place.name}: immich error {e} -- SKIPPED")
            stats["failed"] += 1
            continue

        rows = by_place.get(place.place_id, [])

        # The Amplify rows carry no capture time, so the guard compares counts
        # rather than working out exactly which photos would disappear
        shortfall = max(0, len(rows) - len(assets))
        if shortfall > args.max_loss:
            print(
                f"  [{index}/{len(places)}] {place.name}: album holds {len(assets)} but the "
                f"site shows {len(rows)} -- SKIPPED"
            )
            stats["skipped_would_lose"] += 1
            continue

        print(
            f"  [{index}/{len(places)}] {place.name}: {len(assets)} in immich, "
            f"replacing {len(rows)} existing"
        )

        if not args.apply:
            continue

        destination = Destination(**destination_kwargs(destinations[place.destination_id]))

        try:
            travel._process_photos(destination, place, existing={r["hsh"] for r in rows})
        except Exception as e:  # noqa: BLE001
            print(f"      import failed: {e} -- existing rows left untouched")
            stats["failed"] += 1
            continue

        stats["imported"] += len(assets)

        if rows:
            write_backup(args.backup_dir, place, rows)
            stats["backed_up"] += 1

        # Delete only rows the import did not just rewrite.  photoId is the
        # Immich asset id, so a second run would otherwise remove what it wrote
        imported_ids = {asset["id"] for asset in assets}
        for row in rows:
            if row["photoId"] in imported_ids:
                continue
            amplify.delete_photo(row["albumId"], row["photoId"])
            stats["removed"] += 1

    print(f"\nelapsed: {time.time() - started:.1f}s")
    for key in (
        "imported",
        "removed",
        "backed_up",
        "skipped_no_album",
        "skipped_not_relinked",
        "skipped_would_lose",
        "failed",
    ):
        print(f"  {key:22}: {stats[key]}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
