"""
The client's reads and writes, against tables built with the same key schemas
and placeId index as the deployed ones.
"""

from clients.amplify_client import destination_item, place_item
from conftest import (
    make_destination,
    make_place,
    photo,
    seed_destination,
    seed_photos,
    seed_place,
    stored_destination,
    stored_place,
)

# -- Reading a place's photos -------------------------------------------


def test_photos_are_read_by_place_through_the_index(amplify):
    seed_photos(
        amplify,
        [
            photo("a", place_id="place-1"),
            photo("b", place_id="place-1"),
            photo("c", place_id="place-2"),
        ],
    )

    found = {row["photoId"] for row in amplify.get_photos_for_place("place-1")}
    assert found == {"a", "b"}


def test_a_place_with_no_photos_reads_as_empty(amplify):
    seed_photos(amplify, [photo("a", place_id="place-1")])
    assert amplify.get_photos_for_place("place-2") == []


def test_photos_carry_their_dimensions_through_the_index(amplify):
    """
    The index projects every attribute.  A KEYS_ONLY projection would still
    return the right rows but without width and height, and the card photo
    would silently stop being chosen
    """
    seed_photos(amplify, [photo("a", place_id="place-1", width=2048, height=1536)])

    row = amplify.get_photos_for_place("place-1")[0]
    assert row["width"] == 2048
    assert row["height"] == 1536
    assert row["thumbnailSrc"] == "thumb/a"


# -- Card photos ---------------------------------------------------------


def test_refreshing_a_place_writes_the_chosen_thumbnail(amplify):
    place = make_place()
    seed_place(amplify, place)
    seed_photos(
        amplify,
        [
            photo("a", width=1920, height=1080),
            photo("b", width=2048, height=1536),
        ],
    )

    chosen = amplify.refresh_place_card_photo("dest-1", "place-1")

    assert chosen["photoId"] == "b"
    assert stored_place(amplify, "dest-1", "place-1")["cardPhotoThumbnailSrc"] == "thumb/b"


def test_refreshing_a_place_with_no_photos_leaves_the_row_alone(amplify):
    seed_place(amplify, make_place())

    assert amplify.refresh_place_card_photo("dest-1", "place-1") is None
    assert "cardPhotoThumbnailSrc" not in stored_place(amplify, "dest-1", "place-1")


def test_refreshing_is_idempotent(amplify):
    seed_place(amplify, make_place())
    seed_photos(amplify, [photo("a"), photo("b", width=2048, height=1536)])

    first = amplify.refresh_place_card_photo("dest-1", "place-1")
    second = amplify.refresh_place_card_photo("dest-1", "place-1")
    assert first["photoId"] == second["photoId"]


def test_a_destination_rolls_up_the_best_of_its_places(amplify):
    seed_destination(amplify, make_destination())
    seed_place(amplify, make_place(place_id="place-1"))
    seed_place(amplify, make_place(place_id="place-2"))
    seed_photos(
        amplify,
        [
            photo("a", place_id="place-1", width=1920, height=1080),
            photo("b", place_id="place-2", width=2048, height=1536),
        ],
    )

    chosen = amplify.refresh_destination_card_photo("dest-1")

    assert chosen["photoId"] == "b"
    assert stored_destination(amplify, "dest-1")["cardPhotoThumbnailSrc"] == "thumb/b"


def test_the_rollup_skips_places_that_have_no_photos(amplify):
    seed_destination(amplify, make_destination())
    seed_place(amplify, make_place(place_id="place-1"))
    seed_place(amplify, make_place(place_id="place-2"))
    seed_photos(amplify, [photo("a", place_id="place-1", width=2048, height=1536)])

    assert amplify.refresh_destination_card_photo("dest-1")["photoId"] == "a"


def test_a_destination_whose_places_have_no_photos_is_left_alone(amplify):
    seed_destination(amplify, make_destination())
    seed_place(amplify, make_place())

    assert amplify.refresh_destination_card_photo("dest-1") is None
    assert "cardPhotoThumbnailSrc" not in stored_destination(amplify, "dest-1")


def test_the_rollup_only_considers_its_own_destination(amplify):
    seed_destination(amplify, make_destination(destination_id="dest-1"))
    seed_place(amplify, make_place(place_id="place-1", destination_id="dest-1"))
    seed_place(amplify, make_place(place_id="place-2", destination_id="dest-2"))
    seed_photos(
        amplify,
        [
            photo("a", place_id="place-1", destination_id="dest-1", width=1920, height=1080),
            photo("b", place_id="place-2", destination_id="dest-2", width=2048, height=1536),
        ],
    )

    assert amplify.refresh_destination_card_photo("dest-1")["photoId"] == "a"


# -- Editing a row the CLI models cannot fully describe -------------------


def test_editing_a_place_keeps_its_card_photo(amplify):
    """
    place_item rebuilds the whole row from a Place, which carries no
    cardPhotoThumbnailSrc, so a rename would otherwise drop it
    """
    place = make_place()
    seed_place(amplify, place)
    seed_photos(amplify, [photo("a", width=2048, height=1536)])
    amplify.refresh_place_card_photo("dest-1", "place-1")

    from models.travel import Place

    amplify.put_place(place_item(Place(**{**place.asdict(), "name": "Renamed"})))

    after = stored_place(amplify, "dest-1", "place-1")
    assert after["name"] == "Renamed"
    assert after["cardPhotoThumbnailSrc"] == "thumb/a"


def test_editing_a_place_keeps_its_original_created_at(amplify):
    place = make_place()
    seed_place(amplify, place)
    created_at = stored_place(amplify, "dest-1", "place-1")["createdAt"]

    from models.travel import Place

    amplify.put_place(place_item(Place(**{**place.asdict(), "name": "Renamed"})))

    assert stored_place(amplify, "dest-1", "place-1")["createdAt"] == created_at


def test_editing_a_destination_keeps_its_card_photo(amplify):
    destination = make_destination()
    seed_destination(amplify, destination)
    seed_place(amplify, make_place())
    seed_photos(amplify, [photo("a", width=2048, height=1536)])
    amplify.refresh_destination_card_photo("dest-1")

    from models.travel import Destination

    amplify.put_destination(
        destination_item(Destination(**{**destination.asdict(), "name": "Renamed"}))
    )

    after = stored_destination(amplify, "dest-1")
    assert after["name"] == "Renamed"
    assert after["cardPhotoThumbnailSrc"] == "thumb/a"


def test_a_new_place_is_written_with_what_appsync_expects(amplify):
    seed_place(amplify, make_place())

    row = stored_place(amplify, "dest-1", "place-1")
    assert row["__typename"] == "Place"
    assert row["createdAt"] and row["updatedAt"]
    assert "cardPhotoThumbnailSrc" not in row


def test_an_edit_moves_updated_at(amplify):
    place = make_place()
    seed_place(amplify, place)
    before = stored_place(amplify, "dest-1", "place-1")["updatedAt"]

    from models.travel import Place

    amplify.put_place(place_item(Place(**{**place.asdict(), "name": "Renamed"})))

    assert stored_place(amplify, "dest-1", "place-1")["updatedAt"] >= before
