#! /usr/bin/env python3

import asyncio
import os

import boto3

from personal_site_cli.cli import PersonalSiteCLI
from personal_site_cli.clients import DDBClient, GoogleMapsClient, GooglePhotosClient, S3Client
from personal_site_cli.utils.config import get_config

GOOGLE_PHOTOS_SCOPES = ["https://www.googleapis.com/auth/photoslibrary.readonly"]


def main() -> None:
    config = get_config()

    # Instantiating Google Photos class
    google_photos_client = GooglePhotosClient(config.config["google"], GOOGLE_PHOTOS_SCOPES)

    # Instantiating Google Maps class
    google_maps_client = GoogleMapsClient(api_key=config.config["google"]["api_key"])

    session = boto3.Session(region_name=config.config["aws"]["region_name"])
    s3_client = S3Client(
        session,
        bucket_name=config.config["aws"]["photos_bucket"],
    )

    ddb_client = DDBClient(session, config.config["aws"]["table_name"])

    cli = PersonalSiteCLI(
        google_maps_client=google_maps_client,
        google_photos_client=google_photos_client,
        s3_client=s3_client,
        ddb_client=ddb_client,
    )

    asyncio.get_event_loop().run_until_complete(run(cli))



async def run(cli: PersonalSiteCLI) -> None:
    await cli.run()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
