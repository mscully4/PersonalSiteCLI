from attr import asdict
from attrs import frozen, field, asdict
from decimal import Decimal


# @attr.s(auto_attribs=True, frozen=True)
@frozen()
class Destination:
    place_id: str
    name: str
    country: str
    country_code: str
    latitude: Decimal = field(converter=lambda x: Decimal(str(x)))
    longitude: Decimal = field(converter=lambda x: Decimal(str(x)))
    type: str

    def asdict(self):
        return asdict(self)
