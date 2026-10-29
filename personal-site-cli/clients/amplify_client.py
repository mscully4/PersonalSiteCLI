from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from boto3 import Session
from boto3.dynamodb.conditions import ConditionBase, Key
from mypy_boto3_dynamodb.service_resource import Table

from exceptions import DynamoDBException


class Models:
    """
    The Amplify model names, which are also the table name prefixes
    """

    DESTINATION = "TravelDestination"
    PLACE = "TravelPlace"
    ALBUM = "TravelAlbum"
    PHOTO = "TravelPhoto"
    HOME_PHOTO = "HomePhoto"


# AppSync filters on __typename, and it does not consistently match the table
# name, so each one is recorded rather than derived
TYPENAMES = {
    Models.DESTINATION: "Destination",
    Models.PLACE: "Place",
    Models.ALBUM: "Album",
    Models.PHOTO: "TravelPhoto",
    Models.HOME_PHOTO: "HomePhoto",
}

# TravelPhoto partitions on the album, keyed by the album's full composite key
PHOTO_ALBUM_KEY_FS = "{place_id}#{album_id}"

# A GSI on TravelPhoto.placeId, added so the site can open one place's gallery
# without reading the whole table
PHOTOS_BY_PLACE_INDEX = "travelPhotosByPlaceId"

# Fields the site writes but the CLI's models do not carry.  A put rebuilds the
# whole row, so these are read back off the existing row and carried over rather
# than silently dropped by an edit
PRESERVED_FIELDS = {
    Models.DESTINATION: ("cardPhotoThumbnailSrc",),
    Models.PLACE: ("cardPhotoThumbnailSrc",),
}

# Cards are 4:3, so the photo closest to that ratio crops the least
DESIRED_RATIO = Decimal(4) / Decimal(3)


def to_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def coords(latitude: Any, longitude: Any) -> Dict[str, Decimal]:
    return {"lat": to_decimal(latitude), "lng": to_decimal(longitude)}


def aspect_ratio(photo: Dict[str, Any]) -> Optional[Decimal]:
    """
    A photo's width over its height, or None if either is missing or zero.

    The site declares width and height as strings and the CLI writes them as
    numbers, so both have to be accepted
    """
    try:
        width = to_decimal(photo["width"])
        height = to_decimal(photo["height"])
    except (KeyError, TypeError, ArithmeticError, ValueError):
        return None

    if height == 0:
        return None

    return width / height


def closest_to_four_thirds(photos: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Picks the photo whose aspect ratio is nearest 4:3, lowest photoId winning a
    tie.

    This is the same rule the site's scripts/backfillCardPhotos.ts applies, and
    the two have to agree or a re-run of the backfill would churn every row the
    CLI wrote.  Nearest-to-4:3 alone was not enough to make them agree: most of
    the library is 2048x1536, which is exactly 4:3, so ties are the norm and the
    winner came down to the order rows happened to arrive in.  Comparing the
    stored choices against a fresh run found 262 of 334 places differing, every
    one of them a tie rather than a worse photo.  Sorting on (distance, photoId)
    settles it the same way on both sides and makes the choice idempotent.

    Photos with an unusable width or height are ignored
    """
    usable = [(ratio, photo) for photo in photos if (ratio := aspect_ratio(photo)) is not None]
    if not usable:
        return None

    return min(usable, key=lambda pair: (abs(DESIRED_RATIO - pair[0]), pair[1].get("photoId", "")))[
        1
    ]


def timestamp() -> str:
    """
    An Amplify style ISO 8601 timestamp, e.g. 2025-01-14T20:41:03.726Z
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class AmplifyClient:
    """
    A client for the DynamoDB tables behind the site's AppSync API.

    Amplify uses a table per model with its own key schema rather than the
    single table the CLI previously wrote to, so this exposes one pair of
    methods per entity instead of generic put and delete
    """

    def __init__(self, session: Session, table_suffix: str):
        self._session = session
        self._suffix = table_suffix
        self._tables: Dict[str, Table] = {}

    def _table(self, model: str) -> Table:
        if model not in self._tables:
            resource = self._session.resource("dynamodb")
            self._tables[model] = resource.Table(f"{model}{self._suffix}")
        return self._tables[model]

    def _query(
        self, model: str, expression: ConditionBase, index: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Runs a query, following pagination.  A single query call stops at
        DynamoDB's 1MB page, which would silently truncate a large album
        """
        table = self._table(model)
        items: List[Dict[str, Any]] = []
        kwargs: Dict[str, Any] = {"KeyConditionExpression": expression}

        if index is not None:
            kwargs["IndexName"] = index

        while True:
            resp = table.query(**kwargs)
            items += resp["Items"]

            if "LastEvaluatedKey" not in resp:
                return items

            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def _scan(self, model: str) -> List[Dict[str, Any]]:
        table = self._table(model)
        items: List[Dict[str, Any]] = []
        kwargs: Dict[str, Any] = {}

        while True:
            resp = table.scan(**kwargs)
            items += resp["Items"]

            if "LastEvaluatedKey" not in resp:
                return items

            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def _put(self, model: str, item: Dict[str, Any], key: Optional[Dict[str, str]] = None) -> None:
        now = timestamp()
        existing = self._get(model, key) if key else None

        if existing:
            # An edit rebuilds the row from a CLI model, which does not carry
            # every field the site stores, so the absent ones are carried over
            # from the row being replaced rather than dropped
            carried = {
                field: existing[field]
                for field in PRESERVED_FIELDS.get(model, ())
                if field not in item and field in existing
            }
            item = {
                **carried,
                **item,
                "createdAt": item.get("createdAt", existing.get("createdAt", now)),
            }

        item = {
            **item,
            "__typename": TYPENAMES[model],
            "createdAt": item.get("createdAt", now),
            "updatedAt": now,
        }

        resp = self._table(model).put_item(Item=item)
        if resp["ResponseMetadata"]["HTTPStatusCode"] != 200:
            raise DynamoDBException(f"Put operation failed: {resp}")

    def _get(self, model: str, key: Dict[str, str]) -> Optional[Dict[str, Any]]:
        return self._table(model).get_item(Key=key).get("Item")

    def _set_field(self, model: str, key: Dict[str, str], field: str, value: Any) -> None:
        resp = self._table(model).update_item(
            Key=key,
            UpdateExpression="SET #field = :value, #updatedAt = :now",
            ExpressionAttributeNames={"#field": field, "#updatedAt": "updatedAt"},
            ExpressionAttributeValues={":value": value, ":now": timestamp()},
        )
        if resp["ResponseMetadata"]["HTTPStatusCode"] != 200:
            raise DynamoDBException(f"Update operation failed: {resp}")

    def _delete(self, model: str, key: Dict[str, str]) -> None:
        resp = self._table(model).delete_item(Key=key)
        if resp["ResponseMetadata"]["HTTPStatusCode"] != 200:
            raise DynamoDBException(f"Delete operation failed: {resp}")

    # -- Destinations ----------------------------------------------------
    def get_destinations(self) -> List[Dict[str, Any]]:
        return self._scan(Models.DESTINATION)

    def put_destination(self, item: Dict[str, Any]) -> None:
        self._put(Models.DESTINATION, item, key={"destinationId": item["destinationId"]})

    def update_destination_card_photo(self, destination_id: str, thumbnail_src: str) -> None:
        self._set_field(
            Models.DESTINATION,
            {"destinationId": destination_id},
            "cardPhotoThumbnailSrc",
            thumbnail_src,
        )

    def delete_destination(self, destination_id: str) -> None:
        self._delete(Models.DESTINATION, {"destinationId": destination_id})

    # -- Places ----------------------------------------------------------
    def get_places(self, destination_id: str) -> List[Dict[str, Any]]:
        return self._query(Models.PLACE, Key("destinationId").eq(destination_id))

    def put_place(self, item: Dict[str, Any]) -> None:
        key = {"destinationId": item["destinationId"], "placeId": item["placeId"]}
        self._put(Models.PLACE, item, key=key)

    def update_place_card_photo(
        self, destination_id: str, place_id: str, thumbnail_src: str
    ) -> None:
        self._set_field(
            Models.PLACE,
            {"destinationId": destination_id, "placeId": place_id},
            "cardPhotoThumbnailSrc",
            thumbnail_src,
        )

    def delete_place(self, destination_id: str, place_id: str) -> None:
        self._delete(Models.PLACE, {"destinationId": destination_id, "placeId": place_id})

    # -- Albums ----------------------------------------------------------
    def get_albums(self, place_id: str) -> List[Dict[str, Any]]:
        return self._query(Models.ALBUM, Key("placeId").eq(place_id))

    def get_all_albums(self) -> List[Dict[str, Any]]:
        return self._scan(Models.ALBUM)

    def put_album(self, item: Dict[str, Any]) -> None:
        self._put(Models.ALBUM, item)

    def delete_album(self, place_id: str, album_id: str) -> None:
        self._delete(Models.ALBUM, {"placeId": place_id, "albumId": album_id})

    # -- Travel photos ---------------------------------------------------
    @staticmethod
    def photo_album_key(place_id: str, album_id: str) -> str:
        return PHOTO_ALBUM_KEY_FS.format(place_id=place_id, album_id=album_id)

    def get_photos(self, place_id: str, album_id: str) -> List[Dict[str, Any]]:
        key = self.photo_album_key(place_id, album_id)
        return self._query(Models.PHOTO, Key("albumId").eq(key))

    def get_photos_for_place(self, place_id: str) -> List[Dict[str, Any]]:
        """
        TravelPhoto partitions on a key that is unique per photo, so a place's
        photos are read through the placeId GSI the site added for its galleries.
        This used to scan the whole table with a filter, which read all 9,973
        rows to find the handful belonging to one place
        """
        return self._query(Models.PHOTO, Key("placeId").eq(place_id), index=PHOTOS_BY_PLACE_INDEX)

    def get_all_photos(self) -> List[Dict[str, Any]]:
        return self._scan(Models.PHOTO)

    def put_photo(self, item: Dict[str, Any]) -> None:
        self._put(Models.PHOTO, item)

    def delete_photo(self, album_key: str, photo_id: str) -> None:
        self._delete(Models.PHOTO, {"albumId": album_key, "photoId": photo_id})

    # -- Home photos -----------------------------------------------------
    def get_home_photos(self) -> List[Dict[str, Any]]:
        return self._scan(Models.HOME_PHOTO)

    def put_home_photo(self, item: Dict[str, Any]) -> None:
        self._put(Models.HOME_PHOTO, item)

    def delete_home_photo(self, photo_id: str) -> None:
        self._delete(Models.HOME_PHOTO, {"photoId": photo_id})

    # -- Convenience -----------------------------------------------------
    def get_album(self, place_id: str) -> Optional[Dict[str, Any]]:
        albums = self.get_albums(place_id)
        return albums[0] if albums else None

    # -- Card photos -----------------------------------------------------
    #
    # The travel view reads a representative thumbnail off the place and the
    # destination rather than choosing one from the photo table at runtime, so
    # anything that changes a place's photos has to rewrite these or the card
    # falls back to a placeholder, or keeps pointing at a deleted photo

    def refresh_place_card_photo(
        self, destination_id: str, place_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Recomputes a place's card photo from the photos it currently holds, and
        returns the photo chosen, or None when the place has no usable photos
        """
        best = closest_to_four_thirds(self.get_photos_for_place(place_id))
        if best is None:
            return None

        self.update_place_card_photo(destination_id, place_id, best["thumbnailSrc"])
        return best

    def refresh_destination_card_photo(self, destination_id: str) -> Optional[Dict[str, Any]]:
        """
        Rolls the card photos of a destination's places up to the destination,
        which is how the site's scripts/backfillCardPhotos.ts built the
        existing rows
        """
        candidates = [
            best
            for place in self.get_places(destination_id)
            if (best := closest_to_four_thirds(self.get_photos_for_place(place["placeId"])))
            is not None
        ]

        best = closest_to_four_thirds(candidates)
        if best is None:
            return None

        self.update_destination_card_photo(destination_id, best["thumbnailSrc"])
        return best


# -- Model conversion ----------------------------------------------------
#
# The CLI's models use snake_case and separate latitude and longitude, while
# Amplify expects camelCase and a coords map.  Amplify also requires the
# __typename, createdAt and updatedAt fields, which _put adds.


def destination_item(destination: Any) -> Dict[str, Any]:
    return {
        "destinationId": destination.place_id,
        "placeId": destination.place_id,
        "name": destination.name,
        "country": destination.country,
        "countryCode": destination.country_code,
        "coords": coords(destination.latitude, destination.longitude),
    }


def destination_kwargs(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "place_id": item["destinationId"],
        "name": item["name"],
        "country": item.get("country", ""),
        "country_code": item.get("countryCode", ""),
        "latitude": item["coords"]["lat"],
        "longitude": item["coords"]["lng"],
    }


def place_item(place: Any) -> Dict[str, Any]:
    return {
        "destinationId": place.destination_id,
        "placeId": place.place_id,
        "name": place.name,
        "address": place.address,
        "city": place.city,
        "state": place.state,
        "country": place.country,
        "coords": coords(place.latitude, place.longitude),
    }


def place_kwargs(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "place_id": item["placeId"],
        "destination_id": item["destinationId"],
        "name": item["name"],
        "address": item.get("address", ""),
        "city": item.get("city", ""),
        "state": item.get("state", ""),
        "country": item.get("country", ""),
        "zip_code": "",
        "latitude": item["coords"]["lat"],
        "longitude": item["coords"]["lng"],
    }


def album_item(album: Any) -> Dict[str, Any]:
    return {
        "placeId": album.place_id,
        "albumId": album.album_id,
        "destinationId": album.destination_id,
        "title": album.title,
    }


def album_kwargs(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "album_id": item["albumId"],
        "place_id": item["placeId"],
        "destination_id": item["destinationId"],
        "title": item["title"],
    }


def photo_item(photo: Any) -> Dict[str, Any]:
    """
    The site lists every photo and groups them by placeId, so albumId only has
    to make the primary key unique.  It carries the same {placeId}#{photoId}
    composite the existing rows use
    """
    return {
        "albumId": PHOTO_ALBUM_KEY_FS.format(place_id=photo.place_id, album_id=photo.photo_id),
        "photoId": photo.photo_id,
        "placeId": photo.place_id,
        "destinationId": photo.destination_id,
        "src": photo.src,
        "thumbnailSrc": photo.thumbnail_src,
        "width": to_decimal(photo.width),
        "height": to_decimal(photo.height),
        "hsh": photo.hsh,
    }


def home_photo_item(photo: Any) -> Dict[str, Any]:
    return {
        "photoId": photo.photo_id,
        "src": photo.src,
        "width": to_decimal(photo.width),
        "height": to_decimal(photo.height),
        "hsh": photo.hsh,
    }
