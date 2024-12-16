from decimal import Decimal

from attrs import asdict, field, frozen


# mypy is being weird and is making me define this in every model file
def convert_to_decimal(field) -> Decimal:
    return Decimal(str(field))


@frozen(auto_attribs=True)
class Place:
    name: str
    place_id: str
    address: str
    city: str
    state: str
    country: str
    zip_code: str
    latitude: Decimal = field(converter=convert_to_decimal)
    longitude: Decimal = field(converter=convert_to_decimal)
    destination_id: str

    def asdict(self):
        return asdict(self)
