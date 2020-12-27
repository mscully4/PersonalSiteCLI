from attr import asdict
from attrs import frozen, asdict


@frozen()
class Album:
    album_id: str
    destination_id: str
    place_id: str
    cover_photo_id: str
    cover_photo_url: str
    title: str

    def asdict(self):
        return asdict(self)
