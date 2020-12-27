from io import BytesIO
from xmlrpc.client import boolean

import botocore
from boto3 import Session
from mypy_boto3_s3.service_resource import S3ServiceResource
from mypy_boto3_s3.type_defs import PutObjectOutputTypeDef


class S3Client:
    IMAGE_DIRECTORY = "images"
    THUMBNAIL_DIRECTORY = "thumbnails"

    def __init__(self, session: Session, bucket_name: str):
        self._s3_resource: S3ServiceResource = session.resource("s3")
        self.bucket_name = bucket_name
        self.region = session.region_name
        self.base_url = "https://{}.s3.{}.amazonaws.com".format(self.bucket_name, self.region)

    def generate_s3_path_for_image(self, destination_id: str, place_id: str, file_name: str) -> str:
        return f"{self.IMAGE_DIRECTORY}/{destination_id}/{place_id}/{file_name}".replace(" ", "_")

    def generate_s3_path_for_thumbnail(
        self, destination_id: str, place_id: str, file_name: str
    ) -> str:
        return f"{self.THUMBNAIL_DIRECTORY}/{destination_id}/{place_id}/{file_name}".replace(
            " ", "_"
        )

    def write_image_to_s3(self, file_name: str, img: BytesIO, **kwargs) -> str:
        resp: PutObjectOutputTypeDef = self._s3_resource.Object(self.bucket_name, file_name).put(
            Body=img, **kwargs
        )
        assert resp["ResponseMetadata"]["HTTPStatusCode"], "Image Upload Failed"
        return f"{self.base_url}/{file_name}"

    def does_image_exist(self, file_name: str) -> boolean:
        try:
            self._s3_resource.Object(self.bucket_name, file_name).load()
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
        finally:
            return True
