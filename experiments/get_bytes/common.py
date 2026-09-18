"""Shared HTTP/zip-listing plumbing for the get_bytes tools.

Deliberately generic - nothing here is specific to PLUTO/MapPLUTO or any other single DCP
product, since these tools are expected to grow to cover other datasets over time.
"""

import io
import zipfile

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def get_zip_namelist(url: str, session: requests.Session) -> list[str] | None:
    """Peek at a remote zip's member names without downloading the whole file.

    Requests just the tail of the file (where the zip central directory lives) via a
    suffix Range request. Falls back to a full download if Range isn't honored.
    """
    try:
        resp = session.get(url, headers={"Range": "bytes=-262144"}, timeout=60)
    except requests.RequestException as exc:
        print(f"WARNING: request failed for {url}: {exc}")
        return None

    if resp.status_code not in (200, 206):
        print(f"WARNING: unexpected status {resp.status_code} for {url}")
        return None

    try:
        return zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    except zipfile.BadZipFile:
        if resp.status_code == 200:
            print(f"WARNING: could not read zip contents for {url}")
            return None

    try:
        resp = session.get(url, timeout=120)
        resp.raise_for_status()
        return zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    except (requests.RequestException, zipfile.BadZipFile) as exc:
        print(f"WARNING: could not inspect zip contents for {url}: {exc}")
        return None


class _HTTPRangeFile:
    """Minimal seekable, readable file-like object over a remote file, backed by ranged GET
    requests - just enough for zipfile.ZipFile's random-access needs (it seeks to find the
    central directory, then seeks again per-member to its local header + compressed data),
    without ever downloading the whole remote file.

    Unlike get_zip_namelist (which only fetches the zip's tail to list member names cheaply),
    reading an arbitrary member's actual bytes needs real random access, since that member's
    compressed data can live anywhere earlier in the file.
    """

    def __init__(self, url: str, session: requests.Session):
        self._url = url
        self._session = session
        self._pos = 0
        resp = session.head(url, timeout=30)
        resp.raise_for_status()
        self._size = int(resp.headers["Content-Length"])

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._size + offset
        else:
            raise ValueError(f"unsupported whence: {whence}")
        return self._pos

    def tell(self) -> int:
        return self._pos

    def seekable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        end = (
            self._size - 1
            if size is None or size < 0
            else min(self._pos + size, self._size) - 1
        )
        if end < self._pos:
            return b""
        resp = self._session.get(
            self._url, headers={"Range": f"bytes={self._pos}-{end}"}, timeout=60
        )
        resp.raise_for_status()
        data = resp.content
        self._pos += len(data)
        return data


def get_zip_member_bytes(
    url: str, member_name: str, session: requests.Session
) -> bytes | None:
    """Read one member's bytes out of a remote zip via ranged HTTP requests, without
    downloading the whole file."""
    try:
        return zipfile.ZipFile(_HTTPRangeFile(url, session)).read(member_name)
    except (requests.RequestException, zipfile.BadZipFile, KeyError, OSError) as exc:
        print(f"WARNING: could not read member {member_name!r} from {url}: {exc}")
        return None


def get_response_code(url: str, session: requests.Session) -> int | None:
    """Cheaply check a URL's HTTP status without downloading its body.

    Tries a HEAD request first; if that fails outright (some servers reject/mishandle HEAD),
    falls back to a minimal ranged GET. Returns the status code from whichever request
    actually completed - any code, 404 included, is a valid result, not a failure. None only
    if neither request could complete at all.
    """
    try:
        resp = session.head(url, timeout=30)
        return resp.status_code
    except requests.RequestException:
        pass

    try:
        resp = session.get(url, headers={"Range": "bytes=0-0"}, timeout=30)
        return resp.status_code
    except requests.RequestException as exc:
        print(f"WARNING: could not check status for {url}: {exc}")
        return None
