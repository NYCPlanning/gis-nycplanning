"""Read a remote zip's directory and individual members over ranged HTTP, without downloading
the whole archive."""

import io
import logging
import lzma
import zipfile
import zlib

import requests

logger = logging.getLogger(__name__)

# The zip central directory lives at the end of the file, so a suffix range this size is
# enough to read it for every archive seen so far without downloading the whole thing.
CENTRAL_DIRECTORY_TAIL_BYTES = 262144


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
        logger.warning(f"request failed for {url}: {exc}")
        return None

    if resp.status_code not in (200, 206):
        logger.warning(f"unexpected status {resp.status_code} for {url}")
        return None

    try:
        infolist = zipfile.ZipFile(io.BytesIO(resp.content)).infolist()
    except zipfile.BadZipFile:
        if resp.status_code == 200:
            logger.warning(f"could not read zip contents for {url}")
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
        logger.warning(f"could not inspect zip contents for {url}: {exc}")
        return None


def get_zip_namelist(url: str, session: requests.Session) -> list[str] | None:
    """Member names only, for callers that don't need sizes."""
    result = get_zip_central_directory(url, session)
    return None if result is None else [info.filename for info in result[0]]


# Deliberately not an OSError: zipfile turns OSErrors raised while it looks for the end of
# central directory into a generic "File is not a zip file", which would hide the cause.
class _RangeNotHonoredError(Exception):
    pass


class _HTTPRangeFile:
    """Minimal seekable, readable file-like object over a remote file, backed by ranged GET
    requests - enough for zipfile.ZipFile's random-access needs (one seek to find the
    central directory, another per-member to its local header + compressed data), without
    ever downloading the whole remote file.

    Unlike get_zip_central_directory (which only fetches the zip's tail), reading an arbitrary
    member's actual bytes needs real random access. Raises _RangeNotHonoredError if the
    server answers a partial read with anything other than 206.
    """

    def __init__(self, url: str, session: requests.Session):
        self._url = url
        self._session = session
        self._pos = 0
        resp = session.head(url, timeout=30)
        resp.raise_for_status()
        length = resp.headers.get("Content-Length", "")
        if not length.isdigit():
            raise OSError(f"no usable Content-Length ({length!r}) for {url}")
        self._size = int(length)

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
        # A server ignoring Range sends the whole file with a 200, which is only the bytes
        # asked for when the read covered the whole file anyway.
        if resp.status_code != 206 and not (self._pos == 0 and end == self._size - 1):
            raise _RangeNotHonoredError(
                f"server ignored Range (status {resp.status_code}) for {self._url}"
            )
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
        _RangeNotHonoredError,
        zipfile.BadZipFile,
        KeyError,
        OSError,
        # Some older archives use compression stdlib zipfile can't decode; without this the
        # failure escapes and costs the whole zip instead of just this member.
        NotImplementedError,
        # Damaged compressed data surfaces as the decompressor's own error, not BadZipFile.
        zlib.error,
        EOFError,
        lzma.LZMAError,
    ) as exc:
        logger.warning(f"could not read member {member_name!r} from {url}: {exc}")
        return None
