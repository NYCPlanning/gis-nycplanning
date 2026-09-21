"""Shared HTTP/zip plumbing for the get_bytes tool.

Product agnostic - nothing here is specific to any single DCP product.
"""

import io
import zipfile

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# The zip central directory lives at the end of the file, so a suffix range this size is
# enough to read it for every archive seen so far without downloading the whole thing.
CENTRAL_DIRECTORY_TAIL_BYTES = 262144


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _total_size_from_content_range(resp: requests.Response) -> int | None:
    """Total file size out of a 206's `Content-Range: bytes X-Y/TOTAL` header."""
    total = resp.headers.get("Content-Range", "").rpartition("/")[2]
    return int(total) if total.isdigit() else None


def get_zip_central_directory(
    url: str, session: requests.Session
) -> tuple[list[zipfile.ZipInfo], int | None] | None:
    """Read a remote zip's central directory without downloading the whole file.

    Returns (infolist, total_size_bytes). Prefer this over get_zip_namelist: the infolist
    carries each member's uncompressed `file_size`, and the total size comes free from the
    same response's Content-Range headers.

    Requests just the tail of the file via a suffix Range request, falling back to a full
    download if Range isn't honored. total_size is None only when the server answers 206
    without a usable Content-Range.
    """
    try:
        resp = session.get(
            url, headers={"Range": f"bytes=-{CENTRAL_DIRECTORY_TAIL_BYTES}"}, timeout=60
        )
    except requests.RequestException as exc:
        print(f"WARNING: request failed for {url}: {exc}")
        return None

    if resp.status_code not in (200, 206):
        print(f"WARNING: unexpected status {resp.status_code} for {url}")
        return None

    try:
        infolist = zipfile.ZipFile(io.BytesIO(resp.content)).infolist()
    except zipfile.BadZipFile:
        if resp.status_code == 200:
            print(f"WARNING: could not read zip contents for {url}")
            return None
    else:
        total = (
            len(resp.content)
            if resp.status_code == 200
            else _total_size_from_content_range(resp)
        )
        return infolist, total

    try:
        resp = session.get(url, timeout=120)
        resp.raise_for_status()
        return zipfile.ZipFile(io.BytesIO(resp.content)).infolist(), len(resp.content)
    except (requests.RequestException, zipfile.BadZipFile) as exc:
        print(f"WARNING: could not inspect zip contents for {url}: {exc}")
        return None


def get_zip_namelist(url: str, session: requests.Session) -> list[str] | None:
    """Member names only, for callers that don't need sizes."""
    result = get_zip_central_directory(url, session)
    return None if result is None else [info.filename for info in result[0]]


class _HTTPRangeFile:
    """Minimal seekable, readable file-like object over a remote file, backed by ranged GET
    requests - enough for zipfile.ZipFile's random-access needs (one seek to find the
    central directory, another per-member to its local header + compressed data), without 
    ever downloading the whole remote file.

    Unlike get_zip_central_directory (which only fetches the zip's tail), reading an arbitrary
    member's actual bytes needs real random access.
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
    except (
        requests.RequestException,
        zipfile.BadZipFile,
        KeyError,
        OSError,
        # Some older archives use compression stdlib zipfile can't decode; without this the
        # failure escapes and costs the whole zip instead of just this member.
        NotImplementedError,
    ) as exc:
        print(f"WARNING: could not read member {member_name!r} from {url}: {exc}")
        return None


def get_response_code(url: str, session: requests.Session) -> int | None:
    """Cheaply check a URL's HTTP status without downloading its body.

    Tries a HEAD request first; if that fails outright, falls back to a minimal ranged GET. 
    Returns the status code from whichever request actually completed - any code, 404 included, 
    is a valid result, not a failure. None only if neither request could complete at all.
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
