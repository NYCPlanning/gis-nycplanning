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
