from pydantic.dataclasses import dataclass
from pydantic import field_validator
from decimal import Decimal
from pydantic import BaseModel


def _convert_to_decimal(field) -> Decimal:
    return Decimal(str(field))


@dataclass(frozen=True)
class Album(BaseModel):
    album_id: str
    destination_id: str
    place_id: str
    title: str


@dataclass(frozen=True)
class Destination(BaseModel):
    place_id: str
    name: str
    country: str
    country_code: str
    latitude: float
    longitude: float
    type: str = ""

    _normalize_latitude = field_validator('latitude')(_convert_to_decimal)
    _normalize_longitude = field_validator('longitude')(_convert_to_decimal)


@dataclass(frozen=True)
class Place(BaseModel):
    name: str
    place_id: str
    address: str
    city: str
    state: str
    country: str
    zip_code: str
    latitude: float
    longitude: float
    destination_id: str

    _normalize_latitude = field_validator('latitude')(_convert_to_decimal)
    _normalize_longitude = field_validator('longitude')(_convert_to_decimal)

@dataclass(frozen=True)
class Photo(BaseModel):
    photo_id: str
    src: str
    place_id: str
    creation_timestamp: str
    destination_id: str
    height: float
    width: float
    hsh: str
    thumbnail_src: str

    _normalize_height = field_validator('height')(_convert_to_decimal)
    _normalize_width = field_validator('width')(_convert_to_decimal)
