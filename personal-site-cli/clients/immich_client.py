import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import requests
from exceptions import ImmichException
from rapidfuzz import fuzz, process, utils


class ImmichClient(object):
    """
    A client for an Immich server.

    Mirrors the method names of the Google Photos client it replaced so the
    CLIs read the same way
    """

    IMAGE_TYPE = "IMAGE"
    DEFAULT_TIMEOUT_SECONDS = 60
    SEARCH_PAGE_SIZE = 1000

    def __init__(self, base_url: str, api_key: str, timeout: int = DEFAULT_TIMEOUT_SECONDS):
        self.base_url = self.normalize_base_url(base_url)
        self._api_key = api_key
        self._timeout = timeout

        # requests Sessions are not documented as thread safe and photos are
        # downloaded from a pool of threads, so each thread gets its own
        self._thread_local = threading.local()

    @staticmethod
    def asset_timestamp(asset: Dict[str, Any]) -> str:
        """
        Formats an asset's capture time as a UTC instant.

        Immich serves ISO 8601 with an offset while the existing records use
        a trailing Z, so normalize to keep the column sortable as a string
        """
        parsed = datetime.fromisoformat(asset["fileCreatedAt"])
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def normalize_base_url(base_url: str) -> str:
        """
        Immich serves its API under /api.  Accept a URL with or without that
        suffix so both forms work in the .env file
        """
        normalized = base_url.strip().rstrip("/")
        if not normalized.endswith("/api"):
            normalized = f"{normalized}/api"
        return normalized

    @property
    def _session(self) -> requests.Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update({"x-api-key": self._api_key, "Accept": "application/json"})
            self._thread_local.session = session
        return session

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url}{path}"

        try:
            resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
        except requests.RequestException as e:
            raise ImmichException(f"{method} {url} failed: {e}") from e

        if not resp.ok:
            raise ImmichException(f"{method} {url} returned {resp.status_code}: {resp.text[:200]}")

        return resp

    def _get_json(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params=params or None).json()

    def _post_json(self, path: str, body: Dict[str, Any]) -> Any:
        return self._request("POST", path, json=body).json()

    def ping(self) -> None:
        """
        Verifies the server is reachable and the API key is accepted, raising
        if either is not the case
        """
        self._get_json("/server/ping")
        self._get_json("/server/about")

    def get_albums(self) -> List[Dict[str, Any]]:
        """
        A method for retrieving all the Immich albums for a user
        """
        return self._get_json("/albums")

    def get_album_info(self, album_id: str) -> Dict[str, Any]:
        """
        A method for retrieving album metadata given an album id
        """
        return self._get_json(f"/albums/{album_id}")

    def get_album_photos(self, album_id: str) -> List[Dict[str, Any]]:
        """
        A method for retrieving all the image assets in an album.

        Immich 2.x embeds the assets in the album response.  3.x dropped that
        field, so fall back to the search endpoint rather than silently
        returning nothing after a server upgrade
        """
        album = self.get_album_info(album_id)
        assets = album.get("assets")

        if assets is None:
            assets = self._search_album_assets(album_id)

        # Albums can hold videos and other media that Pillow cannot open
        return [asset for asset in assets if asset.get("type") == self.IMAGE_TYPE]

    def _search_album_assets(self, album_id: str) -> List[Dict[str, Any]]:
        """
        A method for paging through an album's assets via the search endpoint
        """
        assets: List[Dict[str, Any]] = []
        page = 1

        while page:
            resp = self._post_json(
                "/search/metadata",
                {
                    "albumIds": [album_id],
                    "type": self.IMAGE_TYPE,
                    "withExif": True,
                    "size": self.SEARCH_PAGE_SIZE,
                    "page": page,
                },
            )
            results = resp["assets"]
            assets += results["items"]

            next_page = results.get("nextPage")
            page = int(next_page) if next_page else 0

        return assets

    def get_album_suggestions(
        self, albums: List[Dict[str, Any]], entry: str, n: int = 5
    ) -> List[Tuple[str, str]]:
        """
        A method for calculating the closest matching existing album names given a text entry
        """
        names = [album["albumName"] for album in albums]

        # default_process lowercases and strips non alphanumerics from both the
        # entry and each album name, so the "--" separator does not skew scoring
        matches = process.extract(
            entry,
            names,
            scorer=fuzz.token_set_ratio,
            processor=utils.default_process,
            limit=n,
        )

        return [(albums[i]["albumName"], albums[i]["id"]) for _, _, i in matches]

    def download_asset(self, asset_id: str) -> bytes:
        """
        A method for downloading the original file for an asset
        """
        return self._request("GET", f"/assets/{asset_id}/original").content
