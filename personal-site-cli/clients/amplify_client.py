from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from boto3 import Session
from boto3.dynamodb.conditions import Attr, ConditionBase, Key
from exceptions import DynamoDBException
from mypy_boto3_dynamodb.service_resource import Table


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


def to_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def coords(latitude: Any, longitude: Any) -> Dict[str, Decimal]:
    return {"lat": to_decimal(latitude), "lng": to_decimal(longitude)}


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

    def _query(self, model: str, expression: ConditionBase) -> List[Dict[str, Any]]:
        """
        Runs a query, following pagination.  A single query call stops at
        DynamoDB's 1MB page, which would silently truncate a large album
        """
        table = self._table(model)
        items: List[Dict[str, Any]] = []
        kwargs: Dict[str, Any] = {"KeyConditionExpression": expression}

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

    def _put(self, model: str, item: Dict[str, Any]) -> None:
        now = timestamp()
        item = {
            **item,
            "__typename": TYPENAMES[model],
            "createdAt": item.get("createdAt", now),
            "updatedAt": now,
        }

        resp = self._table(model).put_item(Item=item)
        if resp["ResponseMetadata"]["HTTPStatusCode"] != 200:
            raise DynamoDBException(f"Put operation failed: {resp}")

    def _delete(self, model: str, key: Dict[str, str]) -> None:
        resp = self._table(model).delete_item(Key=key)
        if resp["ResponseMetadata"]["HTTPStatusCode"] != 200:
            raise DynamoDBException(f"Delete operation failed: {resp}")

    # -- Destinations ----------------------------------------------------
    def get_destinations(self) -> List[Dict[str, Any]]:
        return self._scan(Models.DESTINATION)

    def put_destination(self, item: Dict[str, Any]) -> None:
        self._put(Models.DESTINATION, item)

    def delete_destination(self, destination_id: str) -> None:
        self._delete(Models.DESTINATION, {"destinationId": destination_id})

    # -- Places ----------------------------------------------------------
    def get_places(self, destination_id: str) -> List[Dict[str, Any]]:
        return self._query(Models.PLACE, Key("destinationId").eq(destination_id))

    def put_place(self, item: Dict[str, Any]) -> None:
        self._put(Models.PLACE, item)

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
        TravelPhoto partitions on a key that is unique per photo, so there is no
        query path by place.  The site has the same constraint and lists the
        whole table, so this scans with a filter
        """
        table = self._table(Models.PHOTO)
        items: List[Dict[str, Any]] = []
        kwargs: Dict[str, Any] = {"FilterExpression": Attr("placeId").eq(place_id)}

        while True:
            resp = table.scan(**kwargs)
            items += resp["Items"]

            if "LastEvaluatedKey" not in resp:
                return items

            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

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
