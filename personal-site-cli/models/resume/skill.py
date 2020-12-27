from attrs import asdict, frozen


@frozen()
class Skill:
    id: str
    name: str
    logo_url: str

    def asdict(self):
        return asdict(self)
