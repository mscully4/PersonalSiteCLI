from decimal import Decimal

from attrs import asdict, field, frozen


# mypy is being weird and is making me define this in every model file
def convert_to_decimal(field) -> Decimal:
    return Decimal(str(field))


@frozen(auto_attribs=True)
class Destination:
    place_id: str
    name: str
    country: str
    country_code: str
    latitude: Decimal = field(converter=convert_to_decimal)
    longitude: Decimal = field(converter=convert_to_decimal)
    type: str = field(default="")

    def asdict(self):
        return asdict(self)
