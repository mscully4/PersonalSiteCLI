#! /usr/bin/env python3

import asyncio
import os

import boto3

from cli import PersonalSiteCLI
from clients import DDBClient, GoogleMapsClient, GooglePhotosClient, S3Client
from conf.config import Config

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


async def main():
    # Retrieving keys from config file
    config_path = os.path.join(ROOT_DIR + "/conf/config.yaml")
    assert os.path.exists(config_path)

    config = Config(config_path)

    # Instantiating Google Photos class
    GOOGLE_PHOTOS_SCOPES = ["https://www.googleapis.com/auth/photoslibrary.readonly"]
    google_photos_client = GooglePhotosClient(config.config["GOOGLE"], GOOGLE_PHOTOS_SCOPES)

    # Instantiating Google Maps class
    google_maps_client = GoogleMapsClient(api_key=config.config["GOOGLE"]["api_key"])

    session = boto3.Session(region_name=config.config["AWS"]["region_name"])
    s3_client = S3Client(
        session,
        bucket_name=config.config["AWS"]["photos_bucket"],
    )

    ddb_client = DDBClient(session, config.config["AWS"]["table_name"])

    cli = PersonalSiteCLI(
        google_maps_client=google_maps_client,
        google_photos_client=google_photos_client,
        s3_client=s3_client,
        ddb_client=ddb_client,
    )
    await cli.run()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
