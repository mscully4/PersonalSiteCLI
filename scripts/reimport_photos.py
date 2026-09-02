#! /usr/bin/env python3
"""
Re-imports a place's photos from Immich, replacing the Google Photos era
records.

Photos imported from Google Photos cannot be deduplicated against Immich: the
stored hash is an md5 of the rescaled PNG, and Google served a recompressed
copy while Immich holds the true original.  The bytes differ, so the hashes,
the S3 keys and the photo ids all differ.  A plain "Add Photos" would therefore
add every photo a second time rather than skipping it.

This imports from Immich first and only then deletes the superseded records, so
a failure part way through leaves the place showing duplicates rather than
nothing.  Re-running is safe: once a place holds Immich era records their
hashes match and the import skips them.

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
from typing import Any, Dict, List, Set, Tuple

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "personal-site-cli"),
)

import boto3  # noqa: E402

from cli.travel_cli import TravelCLI  # noqa: E402
from clients import (  # noqa: E402
    DDBClient,
    GoogleMapsClient,
    ImmichClient,
    Namespaces,
    S3Client,
    TravelEntities,
)
from conf.config import Config  # noqa: E402
from models.travel import Destination, Place  # noqa: E402

DESTINATION_PK = f"{Namespaces.TRAVEL}#{TravelEntities.DESTINATION}"
PLACE_PK = f"{Namespaces.TRAVEL}#{TravelEntities.PLACE}"
PHOTO_PK = f"{Namespaces.TRAVEL}#{TravelEntities.PHOTO}"
ALBUM_PK = f"{Namespaces.TRAVEL}#{TravelEntities.ALBUM}"
PHOTO_SK_FS = "{place_id}#{photo_id}"

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class DecimalEncoder(json.JSONEncoder):
    """
    DynamoDB returns numbers as Decimal, which json cannot serialise.  Tag them
    so a restore can put back the exact same types
    """

    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return {"__decimal__": str(o)}
        return super().default(o)


def write_backup(
    directory: str, place: Place, records: List[Dict[str, Any]], keys: Set[str]
) -> str:
    """
    Writes a place's current photo records to disk before they are deleted.

    Without this a re-import is one way: the S3 objects survive but the records
    pointing at them are gone
    """
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{place.place_id}.json")

    # Never overwrite an existing backup.  The first one captures the state
    # before any re-import ran, which is the one worth being able to return to
    if os.path.exists(path):
        return path

    with open(path, "w") as handle:
        json.dump(
            {
                "place_id": place.place_id,
                "place_name": place.name,
                "destination_id": place.destination_id,
                "backed_up_at": datetime.now(timezone.utc).isoformat(),
                "pk": PHOTO_PK,
                "sk_format": PHOTO_SK_FS,
                "records": records,
                "s3_keys": sorted(keys),
            },
            handle,
            cls=DecimalEncoder,
            indent=2,
        )
    return path


def normalize(timestamp: str) -> str:
    """
    Truncates a stored timestamp to whole seconds in UTC, matching what Immich
    reports.  Records written at different times carry different precision
    """
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def photos_lost(
    immich: ImmichClient, records: List[Dict[str, Any]], assets: List[Dict[str, Any]]
) -> int:
    """
    Counts photos currently on the site that the Immich album does not hold.

    Some Immich albums were never fully populated, so a re-import would silently
    drop photos the site is serving today
    """
    stored = collections.Counter(normalize(r["creation_timestamp"]) for r in records)
    available = collections.Counter(immich.asset_timestamp(a) for a in assets)
    return sum((stored - available).values())


def s3_key(url: str, bucket_base: str) -> str:
    return url[len(bucket_base) + 1 :] if url.startswith(bucket_base) else ""


def old_records(ddb: DDBClient, place_id: str, bucket_base: str) -> Tuple[List[str], Set[str]]:
    """
    Returns the photo ids and S3 keys currently recorded for a place
    """
    records: List[Dict[str, Any]] = ddb.get_begins_with(PHOTO_PK, place_id)
    photo_ids = [r["photo_id"] for r in records]
    keys = {
        key
        for r in records
        for key in (s3_key(r["src"], bucket_base), s3_key(r["thumbnail_src"], bucket_base))
        if key
    }
    return photo_ids, keys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--place-id", help="re-import a single place")
    selection.add_argument("--destination-id", help="re-import every place in a destination")
    selection.add_argument("--all", action="store_true", help="re-import every place")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--limit", type=int, help="stop after this many places")
    parser.add_argument(
        "--backup-dir",
        default="reimport_backups",
        help="directory to write the superseded records to before deleting them",
    )
    parser.add_argument(
        "--max-loss",
        type=int,
        default=0,
        help="skip a place if re-importing would drop more than this many photos that "
        "are on the site but absent from the Immich album (default 0)",
    )
    parser.add_argument(
        "--delete-old-s3",
        action="store_true",
        help="delete the superseded S3 objects too (irreversible; they are orphaned otherwise)",
    )
    args = parser.parse_args()

    config = Config.from_env_file(".env")
    session = boto3.Session(**config.boto3_session_kwargs())
    ddb = DDBClient(session, config.aws_table_name)
    s3 = S3Client(session, bucket_name=config.aws_photos_bucket)
    immich = ImmichClient(config.immich_base_url, config.immich_api_key)
    immich.ping()

    travel = TravelCLI(GoogleMapsClient(config.google_maps_api_key), immich, s3, ddb)
    travel.quiet = True

    destinations = {d["place_id"]: Destination(**d) for d in ddb.get_equals(DESTINATION_PK)}
    albums = {a["place_id"]: a for a in ddb.get_equals(ALBUM_PK)}

    places: List[Place] = []
    for destination in destinations.values():
        if args.destination_id and destination.place_id != args.destination_id:
            continue
        for raw in ddb.get_begins_with(PLACE_PK, destination.place_id):
            place = Place(**raw)
            if args.place_id and place.place_id != args.place_id:
                continue
            places.append(place)

    if args.limit:
        places = places[: args.limit]

    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}   places selected: {len(places)}")
    print(f"backups: {os.path.abspath(args.backup_dir)}")
    print(f"old S3 objects: {'DELETED' if args.delete_old_s3 else 'left in place (orphaned)'}\n")

    stats = {
        "imported": 0,
        "removed": 0,
        "skipped_no_album": 0,
        "skipped_not_relinked": 0,
        "skipped_would_lose": 0,
        "backed_up": 0,
        "failed": 0,
        "s3_deleted": 0,
    }
    started = time.time()

    for index, place in enumerate(places, start=1):
        album = albums.get(place.place_id)
        if album is None:
            stats["skipped_no_album"] += 1
            continue

        if not UUID_RE.match(album["album_id"]):
            print(
                f"  [{index}/{len(places)}] {place.name}: album not relinked, run "
                "relink_albums.py first -- SKIPPED"
            )
            stats["skipped_not_relinked"] += 1
            continue

        try:
            assets = immich.get_album_photos(album["album_id"])
        except Exception as e:  # noqa: BLE001 - report and continue the batch
            print(f"  [{index}/{len(places)}] {place.name}: immich error {e} -- SKIPPED")
            stats["failed"] += 1
            continue

        records = ddb.get_begins_with(PHOTO_PK, place.place_id)
        lost = photos_lost(immich, records, assets)
        if lost > args.max_loss:
            print(
                f"  [{index}/{len(places)}] {place.name}: would DROP {lost} photos "
                f"(site {len(records)} -> immich {len(assets)}) -- SKIPPED"
            )
            stats["skipped_would_lose"] += 1
            continue

        photo_ids, keys = old_records(ddb, place.place_id, s3.base_url)
        print(
            f"  [{index}/{len(places)}] {place.name}: {len(assets)} in immich, "
            f"replacing {len(photo_ids)} existing ({len(keys)} S3 objects)"
        )

        if not args.apply:
            continue

        try:
            # Import first: the place keeps serving its old photos until this
            # succeeds, and the new records use different sort keys
            travel._process_photos(destinations[place.destination_id], place)
        except Exception as e:  # noqa: BLE001
            print(f"      import failed: {e} -- old records left untouched")
            stats["failed"] += 1
            continue

        stats["imported"] += len(assets)

        # Save the records about to be deleted so the place can be restored
        if records:
            write_backup(args.backup_dir, place, records, keys)
            stats["backed_up"] += 1

        # Delete only records the import did not just rewrite.  photo_id is the
        # Immich asset id, so re-running over an already imported place gives
        # the new records the same sort keys as the old ones, and deleting by
        # the old id list would remove exactly what was just written
        imported_ids = {asset["id"] for asset in assets}
        superseded = [pid for pid in photo_ids if pid not in imported_ids]

        for photo_id in superseded:
            ddb.delete(PHOTO_PK, PHOTO_SK_FS.format(place_id=place.place_id, photo_id=photo_id))
        stats["removed"] += len(superseded)

        if args.delete_old_s3 and keys:
            bucket = session.resource("s3").Bucket(config.aws_photos_bucket)
            ordered = list(keys)
            for start in range(0, len(ordered), 1000):
                bucket.delete_objects(
                    Delete={"Objects": [{"Key": k} for k in ordered[start : start + 1000]]}
                )
            stats["s3_deleted"] += len(ordered)

    print(f"\nelapsed: {time.time() - started:.1f}s")
    for key, value in stats.items():
        print(f"  {key:22}: {value}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to write.")
        print("Suggested order: relink_albums.py --apply, then this with --limit 1 --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
