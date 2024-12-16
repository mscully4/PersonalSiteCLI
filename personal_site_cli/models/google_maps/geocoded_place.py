from attrs import asdict, frozen


@frozen(auto_attribs=True)
class GeocodedPlace:
    place_id: str
    address: str
    state: str
    country: str
    zip_code: str
    latitude: float
    longitude: float

    def asdict(self):
        return asdict(self)
