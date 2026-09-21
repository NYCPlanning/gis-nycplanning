"""Tests for zip_inspect.py.

The GDAL-touching tests run against the real fixture zips over LOCAL /vsizip/ paths, never
/vsicurl/ - so they exercise real osgeo rather than a mock, without any network. Where a test
needs both halves at once (GDAL reading the layer *and* the truth parser reading the .shp
bytes over HTTP), the ranged-session mock is fed the same fixture's bytes, so the two agree.

This file is the coverage that spatial_index_report.py never had: it lived in a different
interpreter than the test suite, so none of this was reachable until the environments merged.
"""

import zipfile

import pytest
import requests

from processes.get_bytes import zip_inspect
from processes.get_bytes.common import make_session
from tests.processes.get_bytes.conftest import mock_ranged_file_session

SHP_ZIP = "shapefile_nyzd_one_row.zip"
GDB_ZIP = "geodatabase_zoning_data.zip"
FAKE_URL = "https://s-media.nyc.gov/fixture.zip"


@pytest.fixture()
def shp_zip_path(resources_path):
    return resources_path / SHP_ZIP


@pytest.fixture()
def gdb_zip_path(resources_path):
    return resources_path / GDB_ZIP


def vsi(zip_path, inner: str = "") -> str:
    path = f"/vsizip/{zip_path.as_posix()}"
    return f"{path}/{inner}" if inner else path


# --- pure helpers -------------------------------------------------------------------------


def test_extent_from_filename():
    assert zip_inspect.extent_from_filename("BKMapPLUTO") == "bk"
    assert zip_inspect.extent_from_filename("bx_pluto") == "bx"
    assert zip_inspect.extent_from_filename("MapPLUTO_25v2_clipped") == "citywide"


def test_to_windows_path_drops_empty_parts():
    assert zip_inspect.to_windows_path("a/b", "c.shp") == "a\\b\\c.shp"
    assert zip_inspect.to_windows_path("", "c.shp") == "c.shp"


def test_has_unclipped_signal():
    assert zip_inspect.has_unclipped_signal("MapPLUTO_unclipped")
    assert zip_inspect.has_unclipped_signal("water included")
    assert not zip_inspect.has_unclipped_signal("MapPLUTO_clipped")


def test_apply_mappluto_sub_dataset_internal_split():
    # A zip bundling both variants: the unclipped one is labelled, and everything else in
    # that same zip becomes the implicit clipped default.
    entries = [
        {"path_in_zip": "MapPLUTO_unclipped.shp"},
        {"path_in_zip": "MapPLUTO.shp"},
    ]
    zip_inspect.apply_mappluto_sub_dataset(entries, sibling_has_unclipped=False)
    assert [e["sub_dataset"] for e in entries] == ["unclipped", "clipped"]


def test_apply_mappluto_sub_dataset_no_evidence_anywhere_leaves_blank():
    entries = [{"path_in_zip": "MapPLUTO.shp"}]
    zip_inspect.apply_mappluto_sub_dataset(entries, sibling_has_unclipped=False)
    assert entries[0]["sub_dataset"] == ""


def test_apply_mappluto_sub_dataset_sibling_zip_is_the_unclipped_one():
    entries = [{"path_in_zip": "MapPLUTO.shp"}]
    zip_inspect.apply_mappluto_sub_dataset(entries, sibling_has_unclipped=True)
    assert entries[0]["sub_dataset"] == "clipped"


def test_find_versions_with_unclipped_sibling():
    entries = [
        {
            "identifier": "nyc_mappluto_25v2_unclipped_shp",
            "url_level": {
                "version": "25v2",
                "type": "shp",
                "url_actual": "https://x/a",
            },
        },
        {
            "identifier": "nyc_mappluto_25v2_shp",
            "url_level": {
                "version": "25v2",
                "type": "shp",
                "url_actual": "https://x/b",
            },
        },
        {
            "identifier": "mappluto_09v1",
            "url_level": {
                "version": "09v1",
                "type": "shp",
                "url_actual": "https://x/c",
            },
        },
    ]
    assert zip_inspect.find_versions_with_unclipped_sibling(entries) == {
        ("25v2", "shp")
    }


# --- discovery ------------------------------------------------------------------------------


def test_discovery_partitions_a_realistic_namelist():
    names = [
        "MapPLUTO.gdb/a00000001.gdbtable",
        "MapPLUTO.gdb/a00000002.gdbtable",
        "Bronx/BXMapPLUTO.shp",
        "Bronx/BXMapPLUTO.dbf",
        "standalone_table.dbf",
        "notes.csv",
        "readme.txt",
        "pluto_datadictionary.pdf",
        "inner.zip",
        "MapPLUTO.gdb/skipme.csv",
    ]
    assert zip_inspect.discover_gdb_folders(names) == ["MapPLUTO.gdb"]
    assert zip_inspect.discover_loose_dirs(names) == ["", "Bronx"]
    assert zip_inspect.discover_nested_zips(names) == ["inner.zip"]
    # .gdb-internal and nested-zip members are excluded from every suffix-based scan
    assert zip_inspect.discover_tabular_files(names) == ["notes.csv", "readme.txt"]
    assert zip_inspect.discover_pdf_files(names) == ["pluto_datadictionary.pdf"]


def test_discover_loose_dirs_ignores_pdf_only_directory():
    # GDAL's Shapefile driver can never identify a directory of PDFs, so there is no point
    # asking it to try - this gate is what stops a doomed open attempt per zip root.
    assert zip_inspect.discover_loose_dirs(["docs/readme.pdf"]) == []


# --- grid / tolerance -------------------------------------------------------------------------


def test_make_grid_covers_extent_exactly():
    cells = zip_inspect.make_grid(0, 0, 3, 3, n=3)
    assert len(cells) == 9
    assert cells[0] == (0, 0, 1, 1)
    assert cells[-1] == (2, 2, 3, 3)


def test_truth_count_counts_intersecting_bboxes_and_skips_nulls():
    bboxes = [(0, 0, 1, 1), (5, 5, 6, 6), None]
    assert zip_inspect.truth_count(bboxes, (0, 0, 2, 2)) == 1
    assert zip_inspect.truth_count(bboxes, (0, 0, 10, 10)) == 2


def test_cells_mismatch_absorbs_boundary_noise_but_catches_real_corruption():
    # The bbox-vs-geometry artifact measured on a known-good file was off-by-one on a few
    # thousand; real corruption was a 90%+ drop. These assertions pin both regimes.
    assert not zip_inspect.cells_mismatch(19403, 19404)
    assert not zip_inspect.cells_mismatch(0, 2)
    assert zip_inspect.cells_mismatch(1401, 19102)
    assert zip_inspect.cells_mismatch(0, 100)


# --- zip_level ----------------------------------------------------------------------------------


def test_build_derived_file_list_synthesizes_missing_directory_entries():
    infolist = [zipfile.ZipInfo("a/b/c.shp"), zipfile.ZipInfo("top.txt")]
    for info in infolist:
        info.file_size = 10
    listing = zip_inspect.build_derived_file_list(infolist)

    assert {e["path"]: e["type"] for e in listing} == {
        "a/": "directory",
        "a/b/": "directory",
        "a/b/c.shp": "file",
        "top.txt": "file",
    }
    assert all(e["size_bytes"] == 10 for e in listing if e["type"] == "file")


def test_build_derived_file_list_keeps_explicit_directory_entries():
    explicit_dir = zipfile.ZipInfo("empty_folder/")
    listing = zip_inspect.build_derived_file_list([explicit_dir])
    assert listing == [{"path": "empty_folder/", "type": "directory"}]


def test_build_zip_level_is_pure_and_flags_lock_files():
    infolist = [
        zipfile.ZipInfo("MapPLUTO.gdb/a00000001.gdbtable"),
        zipfile.ZipInfo("MapPLUTO.gdb/_gdb.DCP-DELL.sr.lock"),
        zipfile.ZipInfo("inner.zip"),
    ]
    for info in infolist:
        info.file_size = 1

    zip_level = zip_inspect.build_zip_level(
        "https://x/nyc_mappluto_19v1_arc_fgdb.zip", infolist, 12345
    )
    assert zip_level["filename"] == "nyc_mappluto_19v1_arc_fgdb.zip"
    assert zip_level["obs_size_bytes"] == 12345
    assert zip_level["has_lock_files"] is True
    assert zip_level["nested_zip_paths"] == ["inner.zip"]


def test_build_zip_level_no_lock_files():
    info = zipfile.ZipInfo("clean.shp")
    info.file_size = 1
    assert (
        zip_inspect.build_zip_level("https://x/a.zip", [info], 1)["has_lock_files"]
        is False
    )


# --- tabular ---------------------------------------------------------------------------------------


def test_read_tabular_entry_counts_rows_and_columns(monkeypatch):
    zip_bytes = _zip_with("data.csv", b"a,b,c\n1,2,3\n4,5,6\n")
    _install_ranged(monkeypatch, zip_bytes)

    entry = zip_inspect.read_tabular_entry(FAKE_URL, "data.csv", make_session())
    assert entry is not None
    assert entry["type"] == "csv"
    assert entry["row_count"] == 2  # header excluded
    assert entry["col_count"] == 3
    assert entry["encoding"] == "utf-8"


def test_read_tabular_entry_records_fallback_encoding(monkeypatch):
    # 0x92 is a cp1252 smart quote and invalid UTF-8 - real older PLUTO files contain these.
    zip_bytes = _zip_with("old.csv", b"owner\nO\x92Brien\n")
    _install_ranged(monkeypatch, zip_bytes)

    entry = zip_inspect.read_tabular_entry(FAKE_URL, "old.csv", make_session())
    assert entry is not None
    assert entry["encoding"] == "cp1252"
    assert entry["row_count"] == 1


def test_read_tabular_entry_txt_type_and_empty_content(monkeypatch, capsys):
    zip_bytes = _zip_with("empty.txt", b"   ")
    _install_ranged(monkeypatch, zip_bytes)

    entry = zip_inspect.read_tabular_entry(FAKE_URL, "empty.txt", make_session())
    assert entry is not None
    assert entry["type"] == "txt"
    assert entry["row_count"] is None
    assert entry["col_count"] is None
    assert "is empty" in capsys.readouterr().out


def test_read_tabular_entry_missing_member_returns_none(monkeypatch):
    _install_ranged(monkeypatch, _zip_with("other.csv", b"a\n1\n"))
    assert zip_inspect.read_tabular_entry(FAKE_URL, "gone.csv", make_session()) is None


def _zip_with(name: str, content: bytes) -> bytes:
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, content)
    return buf.getvalue()


def _install_ranged(monkeypatch, zip_bytes: bytes) -> None:
    get, head = mock_ranged_file_session(zip_bytes)
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "head", head)


# --- GDAL integration, against real local fixtures ----------------------------------------------


def test_layers_from_vsi_shapefile_directory(shp_zip_path):
    entries = zip_inspect.layers_from_vsi(
        vsi(shp_zip_path), "", None, FAKE_URL, None, check_index=False
    )
    assert len(entries) == 1
    entry = entries[0]
    assert entry["type"] == "shp"
    assert entry["path_in_zip"] == "shapefile_nyzd_one_row.shp"
    assert entry["row_count"] == 1
    assert entry["col_count"] > 0
    assert entry["encoding"] is None


def test_layers_from_vsi_gdb_reports_feature_classes_not_raw_files(gdb_zip_path):
    entries = zip_inspect.layers_from_vsi(
        vsi(gdb_zip_path, "geodatabase_zoning_data.gdb"),
        "geodatabase_zoning_data.gdb",
        "geodatabase_zoning_data.gdb",
        FAKE_URL,
        None,
        check_index=False,
    )
    assert entries, "expected at least one layer in the gdb fixture"
    assert all(e["type"] in ("gdb_fc", "gdb_tb") for e in entries)
    # The point of the GDAL-aware view: a .gdb appears as named layers, not a00000001.gdbtable
    assert all(".gdbtable" not in e["path_in_zip"] for e in entries)
    assert all(
        e["path_in_zip"].startswith("geodatabase_zoning_data.gdb\\") for e in entries
    )


def test_layers_from_vsi_one_bad_layer_keeps_the_others(monkeypatch, shp_zip_path):
    # Regression: GDAL defers opening each .shp in a directory datasource, so a corrupt member
    # raises at GetLayer. That used to escape this function and cost the caller the entire
    # zip - confirmed against nyc_mappluto_20v1_arc_shp, which the baseline has rows for.
    real_open = zip_inspect.gdal.OpenEx

    class _TwoLayers:
        def __init__(self, inner):
            self._inner = inner

        def GetLayerCount(self):
            return 2

        def GetLayer(self, i):
            if i == 0:
                raise RuntimeError("Failed to open file MapPLUTO_UNCLIPPED.shp")
            return self._inner.GetLayer(0)

    monkeypatch.setattr(
        zip_inspect.gdal, "OpenEx", lambda *a, **k: _TwoLayers(real_open(*a, **k))
    )

    entries = zip_inspect.layers_from_vsi(
        vsi(shp_zip_path), "", None, FAKE_URL, None, check_index=False
    )
    assert len(entries) == 1, "the readable layer should survive its neighbour failing"
    assert entries[0]["path_in_zip"] == "shapefile_nyzd_one_row.shp"


def test_layers_from_vsi_layer_count_failure_returns_empty(
    monkeypatch, shp_zip_path, capsys
):
    class _Unscannable:
        def GetLayerCount(self):
            raise RuntimeError("cpl_unzOpenCurrentFile() failed")

    monkeypatch.setattr(zip_inspect.gdal, "OpenEx", lambda *a, **k: _Unscannable())
    assert (
        zip_inspect.layers_from_vsi(
            vsi(shp_zip_path), "", None, FAKE_URL, None, check_index=False
        )
        == []
    )
    assert "could not list layers" in capsys.readouterr().out


def test_layers_from_vsi_unopenable_path_warns_and_returns_empty(tmp_path, capsys):
    bogus = tmp_path / "not_a_zip.zip"
    bogus.write_bytes(b"definitely not a zip")
    assert (
        zip_inspect.layers_from_vsi(
            vsi(bogus), "", None, FAKE_URL, None, check_index=False
        )
        == []
    )
    assert "could not open" in capsys.readouterr().out


def test_spatial_index_check_on_real_fixture_with_sbn(monkeypatch, shp_zip_path):
    # The fixture genuinely ships .sbn/.sbx, so this exercises the full present=True path:
    # GDAL reads the layer locally while the truth parser reads the same bytes over the
    # mocked ranged session.
    _install_ranged(monkeypatch, shp_zip_path.read_bytes())

    entries = zip_inspect.layers_from_vsi(
        vsi(shp_zip_path), "", None, FAKE_URL, make_session(), check_index=True
    )
    index = entries[0]["spatial_index"]
    assert index["present"] is True
    assert index["status"] == "CONSISTENT"


def test_spatial_index_absent_reports_present_false(
    monkeypatch, tmp_path, shp_zip_path
):
    # Same fixture with .sbn/.sbx stripped - the NOT_APPLICABLE case, which should report
    # present=False and no status rather than a verdict it cannot justify.
    stripped = tmp_path / "no_index.zip"
    with zipfile.ZipFile(shp_zip_path) as src, zipfile.ZipFile(stripped, "w") as dst:
        for info in src.infolist():
            if info.filename.lower().endswith((".sbn", ".sbx")):
                continue
            dst.writestr(
                info.filename.replace("shapefile_nyzd_one_row", "noidx"),
                src.read(info.filename),
            )

    _install_ranged(monkeypatch, stripped.read_bytes())
    entries = zip_inspect.layers_from_vsi(
        vsi(stripped), "", None, FAKE_URL, make_session(), check_index=True
    )
    index = entries[0]["spatial_index"]
    assert index["present"] is False
    assert index["status"] is None


def test_gdb_layers_get_no_spatial_index_key(gdb_zip_path):
    # .gdb uses .spx, a different mechanism this check does not cover - the key should be
    # absent entirely rather than present-and-null, so consumers cannot misread it.
    entries = zip_inspect.layers_from_vsi(
        vsi(gdb_zip_path, "geodatabase_zoning_data.gdb"),
        "geodatabase_zoning_data.gdb",
        "geodatabase_zoning_data.gdb",
        FAKE_URL,
        None,
        check_index=True,
    )
    assert all("spatial_index" not in e for e in entries)


def test_read_shp_bboxes_matches_gdal_envelopes(monkeypatch, shp_zip_path):
    # Cross-check the struct parser against GDAL's own geometry envelope - the same
    # verification done by hand during design, now automated.
    from osgeo import gdal

    _install_ranged(monkeypatch, shp_zip_path.read_bytes())
    bboxes = zip_inspect.read_shp_bboxes(
        FAKE_URL, "shapefile_nyzd_one_row.shp", make_session()
    )
    assert bboxes is not None and len(bboxes) == 1

    # Each step is bound to a name rather than chained: osgeo hands back borrowed views, so
    # a chained call lets the owner be collected and the next call gets a dangling proxy.
    dataset = gdal.OpenEx(vsi(shp_zip_path), gdal.OF_VECTOR)
    layer = dataset.GetLayer(0)
    feature = layer.GetNextFeature()
    geometry = feature.GetGeometryRef()
    envelope = geometry.GetEnvelope()  # minx, maxx, miny, maxy
    parsed = bboxes[0]
    assert parsed is not None
    assert parsed == pytest.approx((envelope[0], envelope[2], envelope[1], envelope[3]))


def test_read_shp_bboxes_missing_member_returns_none(monkeypatch, shp_zip_path):
    _install_ranged(monkeypatch, shp_zip_path.read_bytes())
    assert zip_inspect.read_shp_bboxes(FAKE_URL, "gone.shp", make_session()) is None


# --- orchestration ----------------------------------------------------------------------------
#
# layers_from_vsi is stubbed in these: it builds /vsizip//vsicurl/ paths that real GDAL would
# fetch over the network, and GDAL's own curl bypasses the block_network guard. Stubbing it
# leaves the part that is actually under test here - which discovery feeds what, and how the
# pieces are assembled - running for real.


def _stub_layers(monkeypatch, entries_by_prefix: dict):
    calls = []

    def _fake(vsi_path, path_prefix, gdb_path, url, session, check_index):
        calls.append({"vsi_path": vsi_path, "gdb_path": gdb_path})
        return [dict(e) for e in entries_by_prefix.get(path_prefix, [])]

    monkeypatch.setattr(zip_inspect, "layers_from_vsi", _fake)
    return calls


def _layer(path_in_zip: str, type_: str = "shp") -> dict:
    return {
        "dataset": None,
        "sub_dataset": "",
        "path_in_zip": path_in_zip,
        "geog_extent": "citywide",
        "type": type_,
        "encoding": None,
        "row_count": 1,
        "col_count": 1,
    }


def test_build_dataset_level_dispatches_each_discovery_kind(monkeypatch):
    names = [
        "MapPLUTO.gdb/a00000001.gdbtable",
        "Bronx/BXMapPLUTO.shp",
        "inner.zip",
        "notes.csv",
        "readme.pdf",
    ]
    calls = _stub_layers(
        monkeypatch,
        {
            "MapPLUTO.gdb": [_layer("MapPLUTO.gdb\\MapPLUTO", "gdb_fc")],
            "Bronx": [_layer("Bronx\\BXMapPLUTO.shp")],
            "inner.zip": [_layer("inner.zip\\Inner.shp")],
        },
    )
    _install_ranged(monkeypatch, _zip_with("notes.csv", b"a,b\n1,2\n"))

    entries = zip_inspect.build_dataset_level(
        FAKE_URL, names, "mappluto", False, make_session()
    )

    # the gdb open is the only one flagged as a gdb; the nested zip is opened via a second
    # /vsizip/ wrapper rather than byte-extracted
    assert [c["gdb_path"] for c in calls] == ["MapPLUTO.gdb", None, None]
    assert any(c["vsi_path"].startswith("/vsizip//vsizip//vsicurl/") for c in calls)

    by_type = {e["type"] for e in entries}
    assert by_type == {"gdb_fc", "shp", "csv", "pdf"}
    # dataset_name is stamped onto every entry regardless of which path produced it
    assert all(e["dataset"] == "mappluto" for e in entries)


def test_build_dataset_level_pdf_entry_has_no_counts(monkeypatch):
    _stub_layers(monkeypatch, {})
    entries = zip_inspect.build_dataset_level(
        FAKE_URL, ["pluto_datadictionary.pdf"], "mappluto", False, make_session()
    )
    assert len(entries) == 1
    assert entries[0]["type"] == "pdf"
    assert entries[0]["row_count"] is None
    assert entries[0]["col_count"] is None
    assert "spatial_index" not in entries[0]


def test_build_dataset_level_applies_sub_dataset_across_the_whole_zip(monkeypatch):
    _stub_layers(
        monkeypatch,
        {
            "": [
                _layer("MapPLUTO_unclipped.shp"),
                _layer("MapPLUTO.shp"),
            ]
        },
    )
    entries = zip_inspect.build_dataset_level(
        FAKE_URL, ["MapPLUTO_unclipped.shp", "MapPLUTO.shp"], "mappluto", False, None
    )
    assert {e["path_in_zip"]: e["sub_dataset"] for e in entries} == {
        "MapPLUTO_unclipped.shp": "unclipped",
        "MapPLUTO.shp": "clipped",
    }


def test_inspect_zip_shares_one_central_directory_fetch(monkeypatch):
    zip_bytes = _zip_with("notes.csv", b"a,b\n1,2\n3,4\n")
    _install_ranged(monkeypatch, zip_bytes)
    _stub_layers(monkeypatch, {})

    zip_level, dataset_level = zip_inspect.inspect_zip(
        FAKE_URL, "pluto", False, make_session()
    )

    assert zip_level is not None
    assert zip_level["filename"] == "fixture.zip"
    assert zip_level["obs_size_bytes"] == len(zip_bytes)
    assert [e["path"] for e in zip_level["derived_file_list"]] == ["notes.csv"]
    assert [e["type"] for e in dataset_level] == ["csv"]
    assert dataset_level[0]["row_count"] == 2


def test_inspect_zip_unreadable_archive_returns_nothing(monkeypatch, capsys):
    monkeypatch.setattr(
        requests.Session,
        "get",
        lambda self, *a, **k: (_ for _ in ()).throw(
            requests.RequestException("connection reset")
        ),
    )
    zip_level, dataset_level = zip_inspect.inspect_zip(
        FAKE_URL, "pluto", False, make_session()
    )
    assert zip_level is None
    assert dataset_level == []
