"""Shared pytest fixtures/helpers for the get_bytes test suite.

No third-party HTTP-mocking library is used - this repo's own test suite
(tests/utilities/python) and the sibling data-engineering repo's test suite both rely on
hand-rolled unittest.mock/monkeypatch fakes rather than requests-mock/responses/vcrpy, and
this suite follows the same convention rather than adding a new dependency for it.
"""

import io
import json
import socket
import zipfile
from pathlib import Path

import pytest
import requests

RESOURCES = Path(__file__).parent / "resources"
MOCKED_RESPONSES = RESOURCES / "mocked_responses"


@pytest.fixture()
def resources_path():
    return RESOURCES


@pytest.fixture()
def mocked_responses_path():
    return MOCKED_RESPONSES


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Fail loudly if any test tries to open a real socket - a self-enforcing guarantee that
    this suite never reaches s-media.nyc.gov, on top of every HTTP-touching test explicitly
    mocking requests.Session.get/.head below.

    Does not catch GDAL/pyogrio's own C-extension socket usage (same caveat noted for the
    equivalent guard in the data-engineering repo) - the GDAL-touching tests in
    test_summarize_zip_datasets.py are local-fixture-only for exactly this reason, not
    reliant on this guard.
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
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return json.loads(self.content)


def mock_session_call(
    routes: dict[str, "MockResponse | list[MockResponse] | Exception"],
):
    """Returns a callable for monkeypatching requests.Session.get/.head.

    `routes` maps an exact URL to what that call should produce:
    - a single MockResponse: returned on every call for that URL.
    - a list of MockResponse: returned in order, one per successive call (matches
      get_zip_namelist's ranged-then-full-GET two-call fallback shape); the last entry
      repeats for any further calls.
    - an Exception instance: raised when that URL is requested.

    A URL with no route at all raises requests.RequestException, mirroring what a real
    connection failure looks like to calling code.
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
    """Small in-memory zip. Members default to empty content (enough for tests that only need
    get_zip_namelist's namelist() output) - pass `content` to give specific members real bytes
    (e.g. for get_zip_member_bytes tests that need to actually read a member back)."""
    content = content or {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, content.get(name, b""))
    return buf.getvalue()


def mock_ranged_file_session(full_bytes: bytes):
    """Returns (get, head) callables for monkeypatching requests.Session.get/.head, simulating
    a real ranged-HTTP file server backed by in-memory bytes.

    Unlike mock_session_call's fixed-response-per-call model, this actually honors the Range
    header's byte offsets, so a caller doing real random-access reads against it (e.g.
    common._HTTPRangeFile, which zipfile.ZipFile drives to find the central directory and then
    a specific member's local header + compressed data) gets back correct slices.
    """

    def _get(self, url, *args, **kwargs):
        range_header = kwargs.get("headers", {}).get("Range")
        if range_header is None:
            return MockResponse(200, full_bytes)
        start, end = range_header.removeprefix("bytes=").split("-")
        return MockResponse(206, full_bytes[int(start) : int(end) + 1])

    def _head(self, url, *args, **kwargs):
        return MockResponse(200, headers={"Content-Length": str(len(full_bytes))})

    return _get, _head


@pytest.fixture()
def nested_zip_path(tmp_path, resources_path):
    """A zip-of-zips fixture built at test time by wrapping the real shapefile fixture inside
    an outer zip - mirrors the real mappluto_16v2/17v1 zip-of-per-borough-zips shape, without
    checking in another binary blob for something fully derivable from an existing fixture.
    """
    inner_name = "shapefile_nyzd_one_row.zip"
    inner_bytes = (resources_path / inner_name).read_bytes()
    outer_path = tmp_path / "nested.zip"
    with zipfile.ZipFile(outer_path, "w") as zf:
        zf.writestr(inner_name, inner_bytes)
    return outer_path
