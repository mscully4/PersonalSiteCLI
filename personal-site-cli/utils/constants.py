import pprint

APP_NAME = "Personal Site CLI"
COVER_PHOTO_MAX_SIZE = 256
IMAGE_MAX_SIZE = 2048


class Dot:
    """This helper class provides property access (the "dot notation")
    to the json object, backed by the original object stored in the _raw
    field.
    """

    def __init__(self, raw):
        self._raw = raw

    def __getattr__(self, key):
        if key in self._raw:
            return self._raw[key]
        else:
            return super().__getattribute__(key)

    def __repr__(self):
        return "{name}({raw})".format(
            name=self.__class__.__name__,
            raw=pprint.pformat(self._raw, indent=4),
        )
