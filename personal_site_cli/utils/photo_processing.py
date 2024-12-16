import hashlib as hl
import io

import requests
from PIL import Image

THUMBNAIL_MAX_SIZE = 512
PHOTO_MAX_SIZE = 2048
IMAGE_TYPE = "png"


def download_image(url: str) -> Image.Image:
    r: requests.Response = requests.get(url)
    r.raw.decode_content = True  # handle spurious Content-Encoding

    # Save the file contents to a variable
    content = r.content

    return Image.open(io.BytesIO(content))


def save_image_to_buffer(image: Image.Image, image_format=IMAGE_TYPE) -> io.BytesIO:
    """
    Writes a Pillow Image to a buffer and returns the buffer
    """
    buffer = io.BytesIO()
    # Save the image back out to a buffer and repoint the buffer back to the beginning
    image.save(buffer, image_format)
    buffer.seek(0)
    return buffer


def rescale_image(image: Image.Image, max_size: int) -> Image.Image:
    """
    Change the size of an Image such that neither the height, nor
    the width of the image are larger than the specified max
    """
    width, height = image.size
    ratio = width / height

    if width <= max_size and height <= max_size:
        pass
    elif ratio > 1:
        image = image.resize((max_size, int(max_size / ratio)))
    elif ratio < 1:
        image = image.resize((int(max_size * ratio), max_size))

    return image


def hash_buffer_md5(buffer: io.BytesIO) -> str:
    """
    Compute the md5 hash of a buffer
    """
    md5 = hl.md5(buffer.getbuffer())
    return md5.hexdigest()
