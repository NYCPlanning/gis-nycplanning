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

    def __init__(self, status_code: int, content: bytes = b""):
        self.status_code = status_code
        self.content = content

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


def make_zip_bytes(names: list[str]) -> bytes:
    """Small in-memory zip with empty-content members - for tests that only need
    get_zip_namelist's namelist() output, not real spatial content."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in names:
            zf.writestr(name, b"")
    return buf.getvalue()


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
