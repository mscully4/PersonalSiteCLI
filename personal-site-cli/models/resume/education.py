from attrs import asdict, frozen


@frozen()
class Education:
    id: str
    school: str
    level: str
    year: str
    major: str
    gpa: float
    logo_url: str

    def asdict(self):
        return asdict(self)
