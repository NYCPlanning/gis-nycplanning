"""Tests for dcpgis.validate.spatial_index.

GDAL-touching tests open the real fixture zips over local /vsizip/ paths and hand the check the
same zip's .shp bytes, so the index read and the truth read agree without any network.
"""

import struct
import threading
import zipfile

import pytest
from osgeo import gdal

from dcpgis.validate import spatial_index
from tests.conftest import STALE_NAME

# The check turns GDAL failures into an ERROR verdict only if they raise.
gdal.UseExceptions()


def _shp_bytes(zip_path) -> bytes:
    with zipfile.ZipFile(zip_path) as zf:
        (name,) = [n for n in zf.namelist() if n.lower().endswith(".shp")]
        return zf.read(name)


def _check(zip_path, load_bboxes=None) -> dict:
    # Bound step by step: osgeo hands back borrowed views, so the dataset must outlive the layer.
    dataset = gdal.OpenEx(f"/vsizip/{zip_path.as_posix()}", gdal.OF_VECTOR)
    layer = dataset.GetLayer(0)
    if load_bboxes is None:
        data = _shp_bytes(zip_path)
        load_bboxes = lambda: spatial_index.parse_shp_bboxes(data)  # noqa: E731
    return spatial_index.check_spatial_index(layer, load_bboxes)


def _without_index(zip_path, out_path, old: str, new: str):
    with zipfile.ZipFile(zip_path) as src, zipfile.ZipFile(out_path, "w") as dst:
        for info in src.infolist():
            if info.filename.lower().endswith((".sbn", ".sbx")):
                continue
            dst.writestr(info.filename.replace(old, new), src.read(info.filename))
    return out_path


# --- grid / tolerance -------------------------------------------------------------------------


def test_make_grid_covers_extent_exactly():
    cells = spatial_index.make_grid(0, 0, 3, 3, n=3)
    assert len(cells) == 9
    assert cells[0] == (0, 0, 1, 1)
    assert cells[-1] == (2, 2, 3, 3)


def test_truth_count_counts_intersecting_bboxes_and_skips_nulls():
    bboxes = [(0, 0, 1, 1), (5, 5, 6, 6), None]
    assert spatial_index.truth_count(bboxes, (0, 0, 2, 2)) == 1
    assert spatial_index.truth_count(bboxes, (0, 0, 10, 10)) == 2


def test_cells_mismatch_absorbs_boundary_noise_but_catches_real_corruption():
    # The bbox-vs-geometry artifact measured on a known-good file was off-by-one on a few
    # thousand; real corruption was a 90%+ drop. These assertions pin both regimes.
    assert not spatial_index.cells_mismatch(19403, 19404)
    assert not spatial_index.cells_mismatch(0, 2)
    assert spatial_index.cells_mismatch(1401, 19102)
    assert spatial_index.cells_mismatch(0, 100)


# --- .shp parsing -------------------------------------------------------------------------------


def _shp_record(shape_type: int, payload: bytes, content_length: "int | None" = None) -> bytes:
    """One .shp record: big-endian number + content length in 16-bit words, then content."""
    content = struct.pack("<i", shape_type) + payload
    words = len(content) // 2 if content_length is None else content_length // 2
    return struct.pack(">ii", 1, words) + content


def test_parse_shp_bboxes_matches_gdal_envelopes(shp_zip_path):
    # Cross-check the struct parser against GDAL's own geometry envelope - the same
    # verification done by hand during design, now automated.
    bboxes = spatial_index.parse_shp_bboxes(_shp_bytes(shp_zip_path))
    assert bboxes is not None and len(bboxes) == 1

    dataset = gdal.OpenEx(f"/vsizip/{shp_zip_path.as_posix()}", gdal.OF_VECTOR)
    layer = dataset.GetLayer(0)
    feature = layer.GetNextFeature()
    geometry = feature.GetGeometryRef()
    envelope = geometry.GetEnvelope()  # minx, maxx, miny, maxy
    parsed = bboxes[0]
    assert parsed is not None
    assert parsed == pytest.approx((envelope[0], envelope[2], envelope[1], envelope[3]))


def test_parse_shp_bboxes_points_become_degenerate_boxes():
    # Point records store x, y where other types store a bbox - read as one, they would
    # yield garbage and throw the truth count off.
    records = (
        _shp_record(1, struct.pack("<dd", 5.0, 7.0))
        + _shp_record(11, struct.pack("<dddd", 1.0, 2.0, 3.0, 4.0))  # PointZ: x, y, z, m
        + _shp_record(0, b"")
        + _shp_record(5, struct.pack("<dddd", 0.0, 0.0, 9.0, 9.0) + b"\x00" * 8)
    )
    assert spatial_index.parse_shp_bboxes(b"\x00" * 100 + records) == [
        (5.0, 7.0, 5.0, 7.0),
        (1.0, 2.0, 1.0, 2.0),
        None,
        (0.0, 0.0, 9.0, 9.0),
    ]


@pytest.mark.parametrize("content_length", [0, -8, -1000])
def test_parse_shp_bboxes_corrupt_record_length_returns_none(caplog, content_length):
    # A length this small would stop the read position advancing, so the parser would spin
    # forever. The thread is only there so a regression fails instead of hanging the suite.
    data = b"\x00" * 100 + _shp_record(5, struct.pack("<dddd", 0.0, 0.0, 1.0, 1.0), content_length)
    result: list = []
    worker = threading.Thread(
        target=lambda: result.append(spatial_index.parse_shp_bboxes(data, label="x.shp")), daemon=True
    )
    worker.start()
    worker.join(timeout=5)

    assert not worker.is_alive(), "parse_shp_bboxes did not terminate"
    assert result == [None]
    assert "malformed .shp record length" in caplog.text
    assert "x.shp" in caplog.text


def test_parse_shp_bboxes_truncated_record_returns_none(caplog):
    # A record whose header promises more bytes than the file holds.
    data = b"\x00" * 100 + struct.pack(">ii", 1, 10) + struct.pack("<i", 5)
    assert spatial_index.parse_shp_bboxes(data) is None
    assert "malformed .shp record in" in caplog.text


# --- the check, through real GDAL -------------------------------------------------------------


def test_check_spatial_index_consistent_on_real_fixture(shp_zip_path):
    # The fixture genuinely ships .sbn/.sbx, so this exercises the full present=True path.
    assert _check(shp_zip_path) == {"present": True, "status": "CONSISTENT"}


def test_check_spatial_index_absent_skips_the_truth_read(tmp_path, shp_zip_path):
    # Same fixture with .sbn/.sbx stripped: no verdict it cannot justify, and no truth read,
    # since that read is the expensive part.
    stripped = _without_index(shp_zip_path, tmp_path / "no_index.zip", "shapefile_nyzd_one_row", "noidx")

    def _must_not_load():
        raise AssertionError("truth bboxes loaded for a layer with no index")

    assert _check(stripped, _must_not_load) == {"present": False, "status": None}


def test_check_spatial_index_inconsistent_against_a_real_stale_sbn(stale_index_zip_path):
    # The index reports itself usable, so only the comparison against the .shp's own bboxes
    # catches it.
    assert _check(stale_index_zip_path) == {"present": True, "status": "INCONSISTENT"}


def test_stale_verdict_comes_from_the_index_not_the_geometry(stale_index_zip_path, tmp_path):
    # Control for the test above: identical features, index removed. Were the INCONSISTENT
    # verdict an artifact of the grid or the truth parser, it would survive this.
    control = _without_index(stale_index_zip_path, tmp_path / "control.zip", STALE_NAME, "control")
    assert _check(control) == {"present": False, "status": None}


def test_check_spatial_index_unreadable_truth_is_an_error(shp_zip_path):
    assert _check(shp_zip_path, lambda: None) == {"present": True, "status": "ERROR"}


def test_check_spatial_index_gdal_failure_is_an_error(caplog):
    class _Unreadable:
        def TestCapability(self, name):
            return True

        def GetExtent(self):
            raise RuntimeError("cpl_unzOpenCurrentFile() failed")

    result = spatial_index.check_spatial_index(_Unreadable(), lambda: [], label="Broken.shp")
    assert result == {"present": None, "status": "ERROR"}
    assert "spatial index check failed for Broken.shp" in caplog.text
