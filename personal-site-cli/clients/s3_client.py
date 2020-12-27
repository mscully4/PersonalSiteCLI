import botocore


class S3Client:
    IMAGE_DIRECTORY = "images"

    def __init__(self, session, bucket_name, region):
        self._s3_resource = session.resource("s3")
        self.bucket_name = bucket_name
        self.region = region
        self.base_url = "https://{}.s3.{}.amazonaws.com".format(
            self.bucket_name, self.region
        )

    def generate_s3_path_for_image(
        self, destination_id: str, place_id: str, file_name: str
    ):
        return (
            f"{self.IMAGE_DIRECTORY}/{destination_id}/{place_id}/{file_name}".replace(
                " ", "_"
            )
        )

    def write_image_to_s3(self, file_name, img, **kwargs):
        resp = self._s3_resource.Object(self.bucket_name, file_name).put(
            Body=img, **kwargs
        )
        assert resp["ResponseMetadata"]["HTTPStatusCode"], "Upload Failed"
        return f"{self.base_url}/{file_name}"

    def does_image_exist(self, file_name):
        try:
            self._s3_resource.Object(self.bucket_name, file_name).load()
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            else:
                return True
        else:
            return True


# def upload_file(file_name, bucket, object_name=None):
#     """Upload a file to an S3 bucket

#     :param file_name: File to upload
#     :param bucket: Bucket to upload to
#     :param object_name: S3 object name. If not specified then file_name is used
#     :return: True if file was uploaded, else False
#     """

#     # If S3 object_name was not specified, use file_name
#     if object_name is None:
#         object_name = file_name

#     # Upload the file
#     s3_client = boto3.client('s3')
#     try:
#         response = s3_client.upload_file(file_name, bucket, object_name)
#     except Exception as e:
#         print(e)
#         return False
#     return True

# def read_file(file_name, bucket):
#     s3 = boto3.resource('s3')
#     obj = s3.Object(bucket, file_name)
#     return obj.get()['Body'].read()
