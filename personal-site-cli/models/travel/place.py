from attr import asdict
from attrs import frozen, field, asdict
from decimal import Decimal


@frozen()
class Place:
    name: str
    place_id: str
    address: str
    city: str
    state: str
    country: str
    zip_code: str
    latitude: Decimal = field(converter=lambda x: Decimal(str(x)))
    longitude: Decimal = field(converter=lambda x: Decimal(str(x)))
    destination_id: str

    def asdict(self):
        return asdict(self)
