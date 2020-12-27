from attrs import asdict, frozen


@frozen()
class Job:
    id: str
    company: str
    role: str
    started: str
    ended: str
    logo_url: str

    def asdict(self):
        return asdict(self)
