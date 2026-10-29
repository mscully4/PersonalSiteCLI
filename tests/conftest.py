"""
Shared fixtures.

The source lives in ./personal-site-cli, whose name is not a valid Python
identifier, and its modules import each other as top level names, so the
directory goes on sys.path rather than being imported as a package.
"""

import os
import sys
from typing import Any, Dict, List, Optional

import pytest

SOURCE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "personal-site-cli"
)
sys.path.insert(0, SOURCE_DIR)

TABLE_SUFFIX = "-test"


@pytest.fixture(autouse=True)
def fake_aws_credentials(monkeypatch):
    """
    Nothing here may reach a real account.  moto only intercepts calls that
    have credentials to sign with, so a developer running these with a real
    profile exported would otherwise hit their own tables
    """
    for key in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-2")


@pytest.fixture
def dynamodb(fake_aws_credentials):
    """
    The three tables the card photos touch, with the key schemas and the
    placeId index the deployed tables actually have
    """
    from moto import mock_aws

    with mock_aws():
        import boto3

        client = boto3.client("dynamodb", region_name="us-east-2")

        client.create_table(
            TableName=f"TravelDestination{TABLE_SUFFIX}",
            KeySchema=[{"AttributeName": "destinationId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "destinationId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName=f"TravelPlace{TABLE_SUFFIX}",
            KeySchema=[
                {"AttributeName": "destinationId", "KeyType": "HASH"},
                {"AttributeName": "placeId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "destinationId", "AttributeType": "S"},
                {"AttributeName": "placeId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName=f"TravelPhoto{TABLE_SUFFIX}",
            KeySchema=[
                {"AttributeName": "albumId", "KeyType": "HASH"},
                {"AttributeName": "photoId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "albumId", "AttributeType": "S"},
                {"AttributeName": "photoId", "AttributeType": "S"},
                {"AttributeName": "placeId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "travelPhotosByPlaceId",
                    "KeySchema": [{"AttributeName": "placeId", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        client.create_table(
            TableName=f"TravelAlbum{TABLE_SUFFIX}",
            KeySchema=[
                {"AttributeName": "placeId", "KeyType": "HASH"},
                {"AttributeName": "albumId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "placeId", "AttributeType": "S"},
                {"AttributeName": "albumId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield client


@pytest.fixture
def amplify(dynamodb):
    import boto3

    from clients.amplify_client import AmplifyClient

    return AmplifyClient(boto3.Session(region_name="us-east-2"), TABLE_SUFFIX)


def photo(
    photo_id: str,
    place_id: str = "place-1",
    destination_id: str = "dest-1",
    width: Any = 1200,
    height: Any = 900,
) -> Dict[str, Any]:
    """
    A TravelPhoto row.  width and height are deliberately loose: the site
    declares them as strings and the CLI writes them as numbers
    """
    return {
        "albumId": f"{place_id}#{photo_id}",
        "photoId": photo_id,
        "placeId": place_id,
        "destinationId": destination_id,
        "src": f"src/{photo_id}",
        "thumbnailSrc": f"thumb/{photo_id}",
        "width": width,
        "height": height,
        "hsh": photo_id,
    }


def make_place(place_id: str = "place-1", destination_id: str = "dest-1", name: str = "A Place"):
    from models.travel import Place

    return Place(
        name=name,
        place_id=place_id,
        address="1 Street",
        city="City",
        state="State",
        country="Country",
        zip_code="",
        latitude=1.5,
        longitude=2.5,
        destination_id=destination_id,
    )


def make_destination(destination_id: str = "dest-1", name: str = "A Destination"):
    from models.travel import Destination

    return Destination(
        place_id=destination_id,
        name=name,
        country="Country",
        country_code="CC",
        latitude=1.5,
        longitude=2.5,
    )


def seed_place(amplify, place) -> None:
    from clients.amplify_client import place_item

    amplify.put_place(place_item(place))


def seed_destination(amplify, destination) -> None:
    from clients.amplify_client import destination_item

    amplify.put_destination(destination_item(destination))


def stored_place(amplify, destination_id: str, place_id: str) -> Optional[Dict[str, Any]]:
    return amplify._get("TravelPlace", {"destinationId": destination_id, "placeId": place_id})


def stored_destination(amplify, destination_id: str) -> Optional[Dict[str, Any]]:
    return amplify._get("TravelDestination", {"destinationId": destination_id})


def seed_photos(amplify, photos: List[Dict[str, Any]]) -> None:
    for row in photos:
        amplify.put_photo(row)
