from PIL import Image
import requests
import io
import hashlib as hl

import sys, os

sys.path.insert(1, os.path.join(sys.path[0], "../../../"))
# from utils.constants import COVER_PHOTO_MAX_SIZE, IMAGE_MAX_SIZE

PHOTO_MAX_SIZE = 2048
COVER_PHOTO_MAX_SIZE = 256
IMAGE_TYPE = "png"


def download(url):
    r = requests.get(url + "=d")
    r.raw.decode_content = True  # handle spurious Content-Encoding

    # Save the file contents to a variable
    content = r.content

    return Image.open(io.BytesIO(content))

    # image = self._rescale(
    #     image,
    #     max_size=(COVER_PHOTO_MAX_SIZE if self.is_cover_image else IMAGE_MAX_SIZE),
    # )
    # self.width, self.height = image.size
    # self._hash = self._hash_function(content)

    # # Save the image back out to a buffer and repoint the buffer back to the beginning
    # image.save(self._buffer, "PNG")
    # self._buffer.seek(0)


def save_image_to_buffer(image, image_format="PNG"):
    buffer = io.BytesIO()
    # # Save the image back out to a buffer and repoint the buffer back to the beginning
    image.save(buffer, image_format)
    buffer.seek(0)
    return buffer


def rescale_image(image: Image, max_size: int):
    width, height = image.size
    ratio = width / height

    if width <= max_size and height <= max_size:
        pass
    elif ratio > 1:
        image = image.resize((max_size, int(max_size / ratio)))
    elif ratio < 1:
        image = image.resize((int(max_size * ratio), max_size))

    return image


def hash_buffer_md5(buffer: io.BytesIO):
    md5 = hl.md5(buffer.getbuffer())
    return md5.hexdigest()


# def write(self, s3, overwrite_if_exists=False):
#     # TODO check that buffer isn't empty and hash has been compute
#     file_name = self._hash + ".png"

#     if self.is_cover_image:
#         file_path = (
#             f"cover-photos/{self.destination_id}/{self.place_id}/{file_name}".replace(
#                 " ", "_"
#             )
#         )
#     else:
#         file_path = f"images/{self.destination_id}/{self.place_id}/{file_name}".replace(
#             " ", "_"
#         )

#     self.s3_url = f"{s3.base_url}/{file_path}"
#     if overwrite_if_exists or not s3.does_image_exist(file_path):
#         s3.write_image_to_s3(
#             file_path, self._buffer, ACL="public-read", ContentType="image/png"
#         )
#     return self.s3_url
