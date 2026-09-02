import os
from pathlib import Path
from typing import Any, Dict

from attrs import frozen
from exceptions import ConfigException

# Keys that the CLI cannot start without
REQUIRED_KEYS = (
    "IMMICH_BASE_URL",
    "IMMICH_API_KEY",
    "GOOGLE_MAPS_API_KEY",
    "AWS_REGION_NAME",
    "AWS_PHOTOS_BUCKET",
    "AWS_TABLE_NAME",
)


def parse_env_file(path: Path) -> Dict[str, str]:
    """
    Parses a .env style file into a dictionary.  Blank lines and comments are
    skipped, an optional leading "export " is stripped and surrounding quotes
    are removed from values
    """
    values: Dict[str, str] = {}

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].lstrip()

        key, separator, value = line.partition("=")
        if not separator:
            continue

        key = key.strip()
        value = value.strip()

        # Strip a matched pair of surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        values[key] = value

    return values


@frozen(auto_attribs=True)
class Config:
    """
    The CLI's configuration, read from a .env file.

    Values in the .env file take precedence over the surrounding environment.
    That ordering is deliberate: it keeps the CLI working when the shell has a
    stale AWS_PROFILE (or similar) exported.  A key absent from the .env file
    still falls back to the environment, so CI can supply values without a file
    """

    immich_base_url: str
    immich_api_key: str
    google_maps_api_key: str
    aws_region_name: str
    aws_photos_bucket: str
    aws_table_name: str
    aws_profile: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    @classmethod
    def from_env_file(cls, path: str) -> "Config":
        """
        Builds a Config from a .env file, raising if any required key is absent
        """
        env_path = Path(path)
        if not env_path.exists():
            raise ConfigException(
                f"No configuration file found at {env_path}.  "
                "Copy .env.example to .env and fill it in"
            )

        values = parse_env_file(env_path)

        def lookup(key: str) -> str:
            value = values.get(key, "").strip()
            return value if value else os.environ.get(key, "").strip()

        resolved = {key: lookup(key) for key in REQUIRED_KEYS}

        missing = sorted(key for key, value in resolved.items() if not value)
        if missing:
            raise ConfigException(
                "Missing required configuration in {}: {}".format(env_path, ", ".join(missing))
            )

        return cls(
            immich_base_url=resolved["IMMICH_BASE_URL"],
            immich_api_key=resolved["IMMICH_API_KEY"],
            google_maps_api_key=resolved["GOOGLE_MAPS_API_KEY"],
            aws_region_name=resolved["AWS_REGION_NAME"],
            aws_photos_bucket=resolved["AWS_PHOTOS_BUCKET"],
            aws_table_name=resolved["AWS_TABLE_NAME"],
            aws_profile=lookup("AWS_PROFILE"),
            aws_access_key_id=lookup("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=lookup("AWS_SECRET_ACCESS_KEY"),
        )

    def boto3_session_kwargs(self) -> Dict[str, Any]:
        """
        Builds the keyword arguments for a boto3 Session.

        Static credentials win over a named profile, but supplying both is
        treated as a mistake rather than resolved silently.  Supplying neither
        is valid and leaves boto3 to use its default credential chain
        """
        has_key = bool(self.aws_access_key_id)
        has_secret = bool(self.aws_secret_access_key)

        if has_key != has_secret:
            raise ConfigException(
                "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set together"
            )

        if has_key and self.aws_profile:
            raise ConfigException(
                "Set either AWS_PROFILE or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, not both"
            )

        kwargs: Dict[str, Any] = {"region_name": self.aws_region_name}

        if has_key:
            kwargs["aws_access_key_id"] = self.aws_access_key_id
            kwargs["aws_secret_access_key"] = self.aws_secret_access_key
        elif self.aws_profile:
            kwargs["profile_name"] = self.aws_profile

        return kwargs
