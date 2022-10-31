from decimal import Decimal

from attrs import field, frozen


# mypy is being weird and is making me define this in every model file
def convert_to_decimal(field) -> Decimal:
    return Decimal(str(field))


@frozen()
class Photo:
    photo_id: str
    src: str
    creation_timestamp: str
    height: Decimal = field(converter=convert_to_decimal)
    width: Decimal = field(converter=convert_to_decimal)
    hsh: str
