#! /usr/bin/env python3
"""
Repoints TRAVEL#ALBUM records at Immich albums.

Every album record written by the Google Photos version of the CLI stores a
Google Photos album id.  Immich uses UUIDs, so "Add Photos" cannot find the
album any more.  This matches the stored album titles against Immich album
names and rewrites album_id.

The sort key embeds album_id, so a relink is a put of the new record followed
by a delete of the old one, not an update in place.

Dry run by default; pass --apply to write.
"""

import argparse
import csv
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "personal-site-cli"),
)

import boto3  # noqa: E402
from rapidfuzz import fuzz, process, utils  # noqa: E402

from clients import DDBClient, ImmichClient, Namespaces, TravelEntities  # noqa: E402
from conf.config import Config  # noqa: E402

ALBUM_PK = f"{Namespaces.TRAVEL}#{TravelEntities.ALBUM}"
ALBUM_SK_FS = "{place_id}#{album_id}"

# Scoring uses fuzz.ratio, NOT token_set_ratio.  token_set_ratio returns 100
# whenever one token set is a subset of the other, so "Yellowstone" scored a
# perfect match against all 16 "Yellowstone -- <place>" albums.  fuzz.ratio is
# length sensitive and scores those below 60.
#
# A match must clear this score and beat the runner up by this margin.  False
# negatives are cheap here (a human relinks the album by hand) while a false
# positive silently attaches the wrong photos to a place
MIN_SCORE = 95.0
MIN_MARGIN = 5.0


def match_album(
    title: str, immich_names: List[str], exact: Dict[str, str]
) -> Tuple[Optional[str], str, float]:
    """
    Returns (immich_album_id, how, score) for a stored album title
    """
    if title in exact:
        return exact[title], "exact", 100.0

    results = process.extract(
        title, immich_names, scorer=fuzz.ratio, processor=utils.default_process, limit=2
    )
    if not results:
        return None, "no-candidates", 0.0

    best_name, best_score, _ = results[0]
    runner_up = results[1][1] if len(results) > 1 else 0.0

    if best_score < MIN_SCORE:
        return None, "below-threshold", best_score
    if best_score - runner_up < MIN_MARGIN:
        return None, "ambiguous", best_score

    return exact[best_name], "fuzzy", best_score


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--report", default="album_relink_report.csv", help="CSV report path")
    args = parser.parse_args()

    config = Config.from_env_file(".env")
    session = boto3.Session(**config.boto3_session_kwargs())
    ddb = DDBClient(session, config.aws_table_name)
    immich = ImmichClient(config.immich_base_url, config.immich_api_key)
    immich.ping()

    immich_albums = immich.get_albums()
    exact = {a["albumName"].strip(): a["id"] for a in immich_albums}
    names = list(exact)
    by_id = {a["id"]: a for a in immich_albums}

    records: List[Dict[str, Any]] = ddb.get_equals(ALBUM_PK)
    print(f"album records: {len(records)}   immich albums: {len(immich_albums)}")
    print(f"mode: {'APPLY' if args.apply else 'DRY RUN'}\n")

    counts = {"exact": 0, "fuzzy": 0, "already-linked": 0, "unmatched": 0, "written": 0}
    rows = []

    for record in records:
        title = record["title"].strip()
        old_id = record["album_id"]
        closest = None
        new_id, how, score = match_album(title, names, exact)

        if new_id is None:
            closest = process.extractOne(
                title, names, scorer=fuzz.ratio, processor=utils.default_process
            )
            if closest:
                score = closest[1]

        if new_id is not None and new_id == old_id:
            how, counts["already-linked"] = "already-linked", counts["already-linked"] + 1
        elif new_id is None:
            counts["unmatched"] += 1
        else:
            counts[how] += 1

        matched_album = by_id.get(new_id or "", {})
        if new_id is None and closest:
            matched_album = {"albumName": f"(closest) {closest[0]}"}
        rows.append(
            {
                "match": how,
                "score": f"{score:.1f}",
                "stored_title": title,
                "immich_album_name": matched_album.get("albumName", ""),
                "immich_asset_count": matched_album.get("assetCount", ""),
                "place_id": record["place_id"],
                "old_album_id": old_id,
                "new_album_id": new_id or "",
            }
        )

        if not args.apply or new_id is None or new_id == old_id:
            continue

        updated = dict(record, album_id=new_id)
        # Put the new record before removing the old one, so a failure between
        # the two leaves the album linked twice rather than not at all
        ddb.put(ALBUM_PK, ALBUM_SK_FS.format(place_id=record["place_id"], album_id=new_id), updated)
        ddb.delete(ALBUM_PK, ALBUM_SK_FS.format(place_id=record["place_id"], album_id=old_id))
        counts["written"] += 1

    with open(args.report, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    for key, value in counts.items():
        print(f"  {key:15}: {value}")
    print(f"\nreport written to {args.report}")

    if not args.apply:
        print("\nDry run only. Re-run with --apply to write these changes.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
