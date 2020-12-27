from attrs import asdict, frozen


@frozen()
class Album:
    album_id: str
    destination_id: str
    place_id: str
    title: str

    def asdict(self):
        return asdict(self)
