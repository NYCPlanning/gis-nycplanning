"""Shared fixtures/helpers for the get_bytes test suite.

No third-party HTTP-mocking library is used - this repo's own tests/utilities suite and the
sibling data-engineering repo both rely on hand-rolled unittest.mock/monkeypatch fakes rather
than requests-mock/responses/vcrpy, and this suite follows the same convention rather than
adding a dependency for it.

`resources_path` is deliberately not redefined here - it comes from the top-level
tests/conftest.py and points at tests/resources, the single shared fixture root.
"""

import io
import json
import socket
import zipfile

import pytest
import requests


@pytest.fixture()
def mocked_responses_path(resources_path):
    return resources_path / "mocked_responses"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Fail loudly if any test opens a real socket - a self-enforcing guarantee that this
    suite never reaches nyc.gov, on top of every HTTP-touching test mocking
    requests.Session.get/.head explicitly.

    Does not catch GDAL's own C-extension socket usage, which is why the GDAL-touching tests
    are local-fixture-only rather than relying on this guard.
    """

    def _blocked(*args, **kwargs):
        raise RuntimeError("network access is blocked in tests")

    monkeypatch.setattr(socket, "socket", _blocked)


class MockResponse:
    """Minimal stand-in for requests.Response - only what this codebase's HTTP calls use."""

    def __init__(
        self, status_code: int, content: bytes = b"", headers: dict | None = None
    ):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            # Deliberately a duck-typed stand-in, not a real Response - calling code only
            # ever reads .status_code/.content/.headers off it.
            raise requests.HTTPError(f"{self.status_code} error", response=self)  # type: ignore[arg-type]

    def json(self):
        return json.loads(self.content)


def ranged_zip_response(
    zip_bytes: bytes, total_size: int | None = None
) -> MockResponse:
    """A 206 carrying a zip tail, with the Content-Range header a real server would send.

    get_zip_central_directory reads the total file size out of that header, so tests for it
    need the header present - a bare MockResponse(206, ...) exercises the missing-header path
    instead, which is also covered deliberately.
    """
    total = len(zip_bytes) if total_size is None else total_size
    return MockResponse(
        206,
        zip_bytes,
        headers={"Content-Range": f"bytes 0-{len(zip_bytes) - 1}/{total}"},
    )


def mock_session_call(
    routes: dict[str, "MockResponse | list[MockResponse] | Exception"],
):
    """Returns a callable for monkeypatching requests.Session.get/.head.

    `routes` maps an exact URL to what that call should produce:
    - a single MockResponse: returned on every call for that URL.
    - a list of MockResponse: returned in order, one per successive call (matches
      get_zip_central_directory's ranged-then-full-GET fallback shape); the last entry
      repeats for any further calls.
    - an Exception instance: raised when that URL is requested.

    A URL with no route raises requests.RequestException, mirroring what a real connection
    failure looks like to calling code.
    """
    call_counts: dict[str, int] = {}

    def _call(self, url, *args, **kwargs):
        if url not in routes:
            raise requests.RequestException(f"no mocked route for {url}")
        route = routes[url]
        if isinstance(route, list):
            i = call_counts.get(url, 0)
            call_counts[url] = i + 1
            route = route[min(i, len(route) - 1)]
        if isinstance(route, Exception):
            raise route
        return route

    return _call


def make_zip_bytes(names: list[str], content: dict[str, bytes] | None = None) -> bytes:
    """Small in-memory zip. Members default to empty content - pass `content` to give
    specific members real bytes (e.g. for get_zip_member_bytes tests that read one back)."""
    content = content or {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, content.get(name, b""))
    return buf.getvalue()


def mock_ranged_file_session(full_bytes: bytes):
    """Returns (get, head) callables for monkeypatching requests.Session.get/.head,
    simulating a real ranged-HTTP file server backed by in-memory bytes.

    Unlike mock_session_call's fixed-response-per-call model, this honors the Range header's
    byte offsets, so a caller doing real random-access reads against it (e.g.
    common._HTTPRangeFile, which zipfile.ZipFile drives to find the central directory and then
    a member's local header + compressed data) gets back correct slices.
    """
    size = len(full_bytes)

    def _get(self, url, *args, **kwargs):
        range_header = kwargs.get("headers", {}).get("Range")
        if range_header is None:
            return MockResponse(200, full_bytes)
        start, _, end = range_header.removeprefix("bytes=").partition("-")
        if not start:  # suffix range, e.g. "bytes=-262144"
            chunk = full_bytes[-int(end) :]
            first = size - len(chunk)
        else:
            chunk = full_bytes[int(start) : int(end) + 1]
            first = int(start)
        return MockResponse(
            206,
            chunk,
            headers={"Content-Range": f"bytes {first}-{first + len(chunk) - 1}/{size}"},
        )

    def _head(self, url, *args, **kwargs):
        return MockResponse(200, headers={"Content-Length": str(size)})

    return _get, _head


@pytest.fixture()
def nested_zip_path(tmp_path, resources_path):
    """A zip-of-zips built at test time by wrapping the real shapefile fixture in an outer
    zip - mirrors the real mappluto_16v2/17v1 shape without checking in another binary blob
    for something fully derivable from an existing fixture.
    """
    inner_name = "shapefile_nyzd_one_row.zip"
    inner_bytes = (resources_path / inner_name).read_bytes()
    outer_path = tmp_path / "nested.zip"
    with zipfile.ZipFile(outer_path, "w") as zf:
        zf.writestr(inner_name, inner_bytes)
    return outer_path
