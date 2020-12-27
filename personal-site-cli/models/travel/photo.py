import pprint
from decimal import Decimal
from PIL import Image
import requests
import io
import hashlib as hl

import sys, os

sys.path.insert(1, os.path.join(sys.path[0], "../../../"))
# from utils.constants import COVER_PHOTO_MAX_SIZE, IMAGE_MAX_SIZE

from attr import asdict
from attrs import frozen, field, asdict
from decimal import Decimal


@frozen()
class Photo:
    photo_id: str
    src: str
    place_id: str
    creation_timestamp: str
    is_cover_image: bool
    destination_id: str
    height: Decimal = field(converter=lambda x: Decimal(str(x)))
    width: Decimal = field(converter=lambda x: Decimal(str(x)))

    def asdict(self):
        return asdict(self)

    @classmethod
    def from_barf(cls, barf):
        return cls()
