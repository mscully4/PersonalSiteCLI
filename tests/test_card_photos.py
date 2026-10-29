"""
The rule that chooses the photo the site renders on a card.

This has to agree with closestToFourThirds in the site's
scripts/backfillCardPhotos.ts.  If the two ever disagree, a backfill re-run
rewrites every row the CLI wrote and vice versa, so the cases here are the
contract between them rather than incidental behaviour.
"""

import pytest

from clients.amplify_client import aspect_ratio, closest_to_four_thirds
from conftest import photo


def test_picks_an_exact_four_thirds_photo():
    photos = [
        photo("a", width=1920, height=1080),
        photo("b", width=2048, height=1536),
        photo("c", width=1000, height=1000),
    ]
    assert closest_to_four_thirds(photos)["photoId"] == "b"


def test_picks_the_nearest_when_none_are_exact():
    photos = [
        photo("a", width=1920, height=1080),
        photo("b", width=1000, height=1000),
        photo("c", width=1300, height=1000),
    ]
    assert closest_to_four_thirds(photos)["photoId"] == "c"


def test_portrait_and_landscape_are_compared_on_distance_not_direction():
    # 3:4 is as far from 4:3 as 16:9 is close, so the nearer landscape wins
    photos = [photo("a", width=1536, height=2048), photo("b", width=1600, height=1200)]
    assert closest_to_four_thirds(photos)["photoId"] == "b"


def test_a_tie_is_broken_by_the_lowest_photo_id():
    photos = [photo("c", width=2048, height=1536), photo("a", width=800, height=600)]
    assert closest_to_four_thirds(photos)["photoId"] == "a"


def test_the_choice_does_not_depend_on_the_order_photos_arrive_in():
    """
    The regression that matters.  Most of the library is exactly 4:3, so ties
    are the norm, and the CLI reads a place's photos through a GSI while the
    backfill reads them from a table scan.  Those two orders differ, so without
    the tie-break the same set of photos yields different winners
    """
    photos = [
        photo("d", width=2048, height=1536),
        photo("b", width=1600, height=1200),
        photo("c", width=800, height=600),
        photo("a", width=1024, height=768),
    ]

    chosen = closest_to_four_thirds(photos)["photoId"]
    assert chosen == "a"
    assert closest_to_four_thirds(list(reversed(photos)))["photoId"] == chosen
    assert closest_to_four_thirds(photos[2:] + photos[:2])["photoId"] == chosen


def test_string_dimensions_compare_the_same_as_numbers():
    """
    The site declares width and height as strings and the CLI writes them as
    numbers, so both turn up in the table
    """
    as_numbers = [photo("a", width=1920, height=1080), photo("b", width=2048, height=1536)]
    as_strings = [photo("a", width="1920", height="1080"), photo("b", width="2048", height="1536")]

    assert closest_to_four_thirds(as_numbers)["photoId"] == "b"
    assert closest_to_four_thirds(as_strings)["photoId"] == "b"


def test_unusable_photos_are_ignored_rather_than_crashing():
    photos = [
        photo("a", width=1000, height=0),
        photo("b", width="not a number", height="600"),
        photo("c", width=2048, height=1536),
    ]
    assert closest_to_four_thirds(photos)["photoId"] == "c"


def test_a_photo_missing_its_dimensions_is_ignored():
    missing = photo("a")
    del missing["width"]
    assert closest_to_four_thirds([missing, photo("b")])["photoId"] == "b"


def test_no_usable_photos_yields_nothing():
    assert closest_to_four_thirds([]) is None
    assert closest_to_four_thirds([photo("a", width=100, height=0)]) is None


def test_aspect_ratio_rejects_what_it_cannot_divide():
    assert float(aspect_ratio(photo("a", width=1200, height=900))) == pytest.approx(4 / 3)
    assert float(aspect_ratio(photo("a", width=1920, height=1080))) == pytest.approx(16 / 9)
    assert aspect_ratio(photo("a", width=1200, height=0)) is None
    assert aspect_ratio({"photoId": "a"}) is None
    assert aspect_ratio(photo("a", width=None, height=900)) is None
