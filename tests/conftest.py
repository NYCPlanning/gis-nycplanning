"""Fixtures and helpers shared across the test tree.

No third-party HTTP-mocking library is used - these suites rely on hand-rolled
unittest.mock/monkeypatch fakes rather than requests-mock/responses/vcrpy, following the
sibling data-engineering repo's convention rather than adding a dependency for it.
"""

import io
import json
import socket
import zipfile
from pathlib import Path

import pytest
import requests

RESOURCES = Path(__file__).parent / "resources"

SHP_ZIP = "shapefile_nyzd_one_row.zip"
STALE_NAME = "shapefile_nyzd_stale_index"


@pytest.fixture()
def resources_path():
    return RESOURCES


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Fail loudly if any test opens a real socket - a self-enforcing guarantee that no suite
    reaches a live server, on top of every HTTP-touching test mocking
    requests.Session.get/.head explicitly.

    Does not catch GDAL's own C-extension socket usage, which is why the GDAL-touching tests
    are local-fixture-only rather than relying on this guard.
    """

    def _blocked(*args, **kwargs):
        raise RuntimeError("network access is blocked in tests")

    monkeypatch.setattr(socket, "socket", _blocked)


# --- HTTP fakes -------------------------------------------------------------------------------


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
    remote_zip._HTTPRangeFile, which zipfile.ZipFile drives to find the central directory and
    then a member's local header + compressed data) gets back correct slices.
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


# --- shapefile fixtures -----------------------------------------------------------------------


@pytest.fixture()
def shp_zip_path(resources_path):
    return resources_path / SHP_ZIP


# Fractions of a grid cell, chosen to keep every square clear of a cell edge so no feature
# is double-counted by the bbox-based truth pass.
STALE_OFFSETS = ((0.15, 0.15), (0.35, 0.35), (0.55, 0.55), (0.75, 0.75), (0.35, 0.75))
STALE_SQUARE_SIZE = 10.0


def _square(x: float, y: float, size: float):
    from osgeo import ogr

    corners = ((x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y))
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for corner in corners:
        ring.AddPoint_2D(*corner)
    polygon = ogr.Geometry(ogr.wkbPolygon)
    polygon.AddGeometry(ring)
    return polygon


def _build_stale_index_zip(shp_zip_path, tmp_path):
    """A shapefile carrying a real .sbn/.sbx that describes an earlier version of itself.

    Reuses the checked-in fixture's genuine ESRI-written index rather than synthesizing or
    byte-corrupting one, so the archive fails the same way the upstream ones do: features
    were added and the index was never rebuilt. Feature 0 is the original polygon, so the
    index's single entry stays truthful and the layer extent is unchanged - what makes this
    INCONSISTENT is purely the 45 features the index has never heard of.

    osgeo is imported here rather than at module scope so suites that never build this
    fixture don't need GDAL.
    """
    from osgeo import gdal, ogr

    source = gdal.OpenEx(f"/vsizip/{shp_zip_path.as_posix()}", gdal.OF_VECTOR)
    source_layer = source.GetLayer(0)
    # Bound step by step, not chained: osgeo hands back borrowed views, so a chained call
    # lets the owner be collected and the next call gets a dangling proxy.
    source_feature = source_layer.GetNextFeature()
    original = source_feature.GetGeometryRef().Clone()
    source_srs = source_layer.GetSpatialRef()
    minx, maxx, miny, maxy = source_layer.GetExtent()

    work = tmp_path / "stale"
    work.mkdir()
    dataset = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(
        str(work / f"{STALE_NAME}.shp")
    )
    layer = dataset.CreateLayer(STALE_NAME, source_srs, ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("ZONEDIST", ogr.OFTString))

    def add(geometry):
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(geometry)
        layer.CreateFeature(feature)

    add(original)
    width, height = (maxx - minx) / 3, (maxy - miny) / 3
    for row in range(3):
        for col in range(3):
            for fx, fy in STALE_OFFSETS:
                x = minx + (col + fx) * width
                y = miny + (row + fy) * height
                add(_square(x, y, STALE_SQUARE_SIZE))
    dataset = None  # flush to disk before zipping

    with zipfile.ZipFile(shp_zip_path) as source_zip:
        for suffix in (".sbn", ".sbx"):
            member = f"{shp_zip_path.stem}{suffix}"
            (work / f"{STALE_NAME}{suffix}").write_bytes(source_zip.read(member))

    zip_path = tmp_path / f"{STALE_NAME}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as out:
        for member in sorted(work.iterdir()):
            out.write(member, member.name)
    return zip_path


@pytest.fixture()
def stale_index_zip_path(shp_zip_path, tmp_path):
    return _build_stale_index_zip(shp_zip_path, tmp_path)
