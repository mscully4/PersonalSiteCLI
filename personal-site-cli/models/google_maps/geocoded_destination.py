from attrs import asdict, frozen


@frozen(auto_attribs=True)
class GeocodedDestination:
    name: str
    country: str
    country_code: str
    latitude: int
    longitude: int

    def asdict(self):
        return asdict(self)
