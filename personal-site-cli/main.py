#! /usr/bin/env python3

import os

import boto3

from cli import PersonalSiteCLI
from clients import AmplifyClient, GoogleMapsClient, ImmichClient, S3Client
from conf.config import Config

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    config = Config.from_env_file(os.path.join(ROOT_DIR, ".env"))

    immich_client = ImmichClient(config.immich_base_url, config.immich_api_key)

    # Fail here rather than part way through a photo upload
    immich_client.ping()

    google_maps_client = GoogleMapsClient(api_key=config.google_maps_api_key)

    session = boto3.Session(**config.boto3_session_kwargs())
    s3_client = S3Client(
        session, bucket_name=config.aws_photos_bucket, base_url=config.image_base_url
    )
    amplify_client = AmplifyClient(session, config.amplify_table_suffix)

    cli = PersonalSiteCLI(
        google_maps_client=google_maps_client,
        immich_client=immich_client,
        s3_client=s3_client,
        amplify_client=amplify_client,
    )
    cli.run()


if __name__ == "__main__":
    main()
