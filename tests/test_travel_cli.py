"""
The ingest path, with Immich and S3 replaced by fakes.

The point of these is ordering rather than photo processing: a place's card
photo has to be written after its photos are, or the card keeps pointing at
whatever it pointed at before.
"""

from io import BytesIO

from conftest import make_destination, make_place, seed_destination, seed_place, stored_place
from PIL import Image

from cli.travel_cli import TravelCLI
from clients.amplify_client import album_item
from models.travel import Album


class FakeImmich:
    """
    Serves images of the sizes a test asks for.  The CLI hashes what it
    downloads, so the bytes have to differ per asset or the second photo looks
    like a duplicate of the first and is skipped
    """

    def __init__(self, assets):
        self._assets = assets

    def get_album_photos(self, album_id):
        return [{"id": asset_id} for asset_id, _, _ in self._assets]

    def download_asset(self, asset_id):
        width, height = next((w, h) for id_, w, h in self._assets if id_ == asset_id)
        image = Image.new("RGB", (width, height), color=(len(asset_id) * 20 % 256, 120, 200))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def asset_timestamp(self, asset):
        return "2025-01-01T00:00:00.000Z"


class FakeS3:
    def __init__(self):
        self.written = []

    def generate_s3_path_for_image(self, destination_id, place_id, file_name):
        return f"images/{destination_id}/{place_id}/{file_name}"

    def generate_s3_path_for_thumbnail(self, destination_id, place_id, file_name):
        return f"thumbnails/{destination_id}/{place_id}/{file_name}"

    def write_image_to_s3(self, path, buffer, **kwargs):
        self.written.append(path)
        return f"https://cdn.example/{path}"


def build_cli(amplify, assets):
    cli = TravelCLI(
        google_maps_client=None,
        immich_client=FakeImmich(assets),
        s3_client=FakeS3(),
        amplify_client=amplify,
    )
    cli.quiet = True
    return cli


def seed_album(amplify, place):
    amplify.put_album(
        album_item(
            Album(
                album_id="album-1",
                place_id=place.place_id,
                destination_id=place.destination_id,
                title="An Album",
            )
        )
    )


def test_ingesting_photos_writes_the_place_card_photo(amplify):
    """
    The bug this covers: a place added from here on rendered the noImages
    placeholder on its card, because nothing wrote cardPhotoThumbnailSrc, even
    though its gallery worked
    """
    destination, place = make_destination(), make_place()
    seed_destination(amplify, destination)
    seed_place(amplify, place)
    seed_album(amplify, place)

    cli = build_cli(amplify, [("asset-one", 1920, 1080), ("asset-twotwo", 2048, 1536)])
    cli._process_photos(destination, place)

    photos = amplify.get_photos_for_place("place-1")
    assert len(photos) == 2

    card = stored_place(amplify, "dest-1", "place-1")["cardPhotoThumbnailSrc"]
    four_thirds = next(p for p in photos if int(p["width"]) * 3 == int(p["height"]) * 4)
    assert card == four_thirds["thumbnailSrc"]


def test_a_second_ingest_does_not_change_the_card(amplify):
    destination, place = make_destination(), make_place()
    seed_destination(amplify, destination)
    seed_place(amplify, place)
    seed_album(amplify, place)

    cli = build_cli(amplify, [("asset-one", 1920, 1080), ("asset-twotwo", 2048, 1536)])
    cli._process_photos(destination, place)
    first = stored_place(amplify, "dest-1", "place-1")["cardPhotoThumbnailSrc"]

    cli._process_photos(destination, place)
    assert stored_place(amplify, "dest-1", "place-1")["cardPhotoThumbnailSrc"] == first


def test_the_card_photo_is_one_of_the_place_s_own_photos(amplify):
    destination, place = make_destination(), make_place()
    seed_destination(amplify, destination)
    seed_place(amplify, place)
    seed_album(amplify, place)

    cli = build_cli(amplify, [("asset-one", 2048, 1536)])
    cli._process_photos(destination, place)

    card = stored_place(amplify, "dest-1", "place-1")["cardPhotoThumbnailSrc"]
    assert card in {p["thumbnailSrc"] for p in amplify.get_photos_for_place("place-1")}
    assert card.startswith("https://cdn.example/thumbnails/")
