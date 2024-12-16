from attr import frozen


@frozen(auto_attribs=True)
class GoogleWebConfig:
    client_id: str
    project_id: str
    auth_uri: str
    token_uri: str
    auth_provider_x509_cert_url: str
    client_secret: str


@frozen(auto_attribs=True)
class GoogleConfig:
    api_key: str
    scope: str
    web: GoogleWebConfig


@frozen(auto_attribs=True)
class AWSConfig:
    region_name: str
    photos_bucket: str
    table_name: str


@frozen(auto_attribs=True)
class Config:
    google: GoogleConfig
    aws: AWSConfig
