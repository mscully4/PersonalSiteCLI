#! /usr/bin/env python3

import os
import asyncio
import boto3

from conf.config import Config
from clients import GooglePhotosClient, GoogleMapsClient, S3Client, DDBClient
from cli import PersonalSiteCLI

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))


async def main():
    # Retrieving keys from config file
    config_path = os.path.join(ROOT_DIR + "/conf/config.yaml")
    assert os.path.exists(config_path)

    config = Config(config_path)

    # Instantiating Google Photos class
    GOOGLE_PHOTOS_SCOPES = ["https://www.googleapis.com/auth/photoslibrary.readonly"]
    google_photos_client = GooglePhotosClient(
        config.config["GOOGLE"], GOOGLE_PHOTOS_SCOPES
    )

    # Instantiating Google Maps class
    google_maps_client = GoogleMapsClient(api_key=config.config["GOOGLE"]["api_key"])

    session = boto3.Session(region_name="us-west-2")
    s3_client = S3Client(
        session,
        bucket_name=config.config["S3"]["bucket"],
        region=config.config["S3"].get("region"),
    )

    ddb_client = DDBClient(session, config.config["DYNAMO"]["table_name"])

    cli = PersonalSiteCLI(
        google_maps_client=google_maps_client,
        google_photos_client=google_photos_client,
        s3_client=s3_client,
        ddb_client=ddb_client,
    )
    await cli.run()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
