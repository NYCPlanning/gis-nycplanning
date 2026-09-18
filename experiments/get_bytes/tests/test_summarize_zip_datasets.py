"""Tests for summarize_zip_datasets.py.

Two tiers: pure-logic unit tests (no I/O at all), and GDAL-integration tests against small
real local fixture zips via plain local /vsizip/ paths - never /vsicurl/, so fully offline
(see conftest.block_network) without needing to mock GDAL itself.
"""

import requests
from conftest import make_zip_bytes, mock_ranged_file_session

import summarize_zip_datasets as szd

# --- pure-logic unit tests ------------------------------------------------------------


def test_has_unclipped_signal():
    assert szd.has_unclipped_signal("MapPLUTO25v2_unclipped.gdb")
    assert szd.has_unclipped_signal("water included version")
    assert szd.has_unclipped_signal("Bronx\\WI\\BXMapPLUTO.shp")
    assert not szd.has_unclipped_signal("MapPLUTO25v2.gdb")
    # "wi" requires a word boundary on both sides - an underscore is a word character, so it
    # does *not* bound "wi" the way a path separator or space does. Documented here as
    # intentional regex behavior, not a gap: no real filename observed uses "_WI" as its only
    # unclipped signal.
    assert not szd.has_unclipped_signal("BXMapPLUTO_WI.shp")


def test_extent_from_filename_borough_codes():
    assert szd.extent_from_filename("BKMapPLUTO") == "bk"
    assert szd.extent_from_filename("bx_pluto") == "bx"
    assert szd.extent_from_filename("QNMapPLUTO") == "qn"


def test_extent_from_filename_citywide_default():
    assert szd.extent_from_filename("MapPLUTO_25v2_clipped") == "citywide"
    assert szd.extent_from_filename("NOT_MAPPED_LOTS") == "citywide"


def test_extent_from_filename_boundary_case_is_intentional():
    # The regex only requires the 2-letter prefix be followed by '_' or an uppercase letter -
    # a name that merely *starts with* a borough code still matches by design, since every
    # real borough-coded PLUTO filename observed follows exactly this shape (BXMapPLUTO,
    # bx_pluto, ...). Documented here as intended behavior, not a gap.
    assert szd.extent_from_filename("BXsomethingelse") == "bx"


def test_to_windows_path():
    assert szd.to_windows_path("Bronx", "BXMapPLUTO.shp") == "Bronx\\BXMapPLUTO.shp"
    assert szd.to_windows_path("", "BXMapPLUTO.shp") == "BXMapPLUTO.shp"


def test_discover_gdb_folders():
    names = [
        "MapPLUTO25v2.gdb/a00000001.gdbtable",
        "MapPLUTO25v2.gdb/a00000002.gdbtable",
        "MapPLUTO25v2_unclipped.gdb/a00000001.gdbtable",
        "pluto_readme.pdf",
    ]
    assert szd.discover_gdb_folders(names) == [
        "MapPLUTO25v2.gdb",
        "MapPLUTO25v2_unclipped.gdb",
    ]


def test_discover_loose_dirs_requires_shp_or_dbf():
    # The bug this regression-tests: a PDF-only top-level entry alongside a .gdb folder must
    # NOT produce a loose dir - GDAL can never open it as a Shapefile datasource.
    names = [
        "MapPLUTO26v2.gdb/a00000001.gdbtable",
        "pluto_readme.pdf",
        "pluto_datadictionary.pdf",
    ]
    assert szd.discover_loose_dirs(names) == []


def test_discover_loose_dirs_finds_shp_and_lone_dbf():
    names = [
        "Bronx/BXMapPLUTO.shp",
        "Bronx/BXMapPLUTO.dbf",
        "Bronx/bx_pluto.dbf",  # standalone table, no matching .shp
        "Bronx/BXMapPLUTO.prj",  # sidecar - not itself a dataset
    ]
    assert szd.discover_loose_dirs(names) == ["Bronx"]


def test_discover_loose_dirs_ignores_gdb_and_nested_zip_members():
    names = ["Foo.gdb/x.shp", "outer/nested.zip"]
    assert szd.discover_loose_dirs(names) == []


def test_discover_nested_zips():
    names = [
        "Bronx16V2.zip",
        "Brooklyn16V2.zip",
        "MapPLUTO.gdb/a.gdbtable",
        "readme.pdf",
    ]
    assert szd.discover_nested_zips(names) == ["Bronx16V2.zip", "Brooklyn16V2.zip"]


def test_discover_tabular_files():
    names = [
        "MapPLUTO26v2.gdb/a00000001.gdbtable",
        "data.csv",
        "notes.txt",
        "Bronx/BXMapPLUTO.shp",
        "nested.zip",
        "pluto_readme.pdf",
    ]
    assert szd.discover_tabular_files(names) == ["data.csv", "notes.txt"]


def test_discover_tabular_files_skips_gdb_and_nested_zip_members():
    names = ["Foo.gdb/data.csv", "outer/nested.zip"]
    assert szd.discover_tabular_files(names) == []


def test_find_versions_with_unclipped_sibling():
    source_rows = [
        {
            "version": "26v2",
            "type": "fgdb",
            "identifier": "nyc_mappluto_26v2_fgdb",
            "url": "https://x/a.zip",
        },
        {
            "version": "26v2",
            "type": "fgdb",
            "identifier": "nyc_mappluto_26v2_unclipped_fgdb",
            "url": "https://x/b.zip",
        },
        {
            "version": "09v1",
            "type": "shp",
            "identifier": "mappluto_09v1",
            "url": "https://x/c.zip",
        },
    ]
    assert szd.find_versions_with_unclipped_sibling(source_rows) == {("26v2", "fgdb")}


def _row(path_in_zip: str) -> dict:
    return {"path_in_zip": path_in_zip, "sub_dataset": None}


def test_apply_mappluto_sub_dataset_own_path_signal():
    rows = [_row("MapPLUTO25v2_unclipped.gdb\\MapPLUTO_25v2_unclipped")]
    szd.apply_mappluto_sub_dataset(rows, sibling_has_unclipped=False)
    assert rows[0]["sub_dataset"] == "unclipped"


def test_apply_mappluto_sub_dataset_zip_internal_split():
    # Reproduces the nyc_mappluto_18v1_1_arc_fgdb bug: a pre-2019 zip that already bundles
    # both variants internally must classify the non-unclipped row as "clipped", not "".
    rows = [
        _row("MapPLUTO_18v1_1.gdb\\MapPLUTO"),
        _row("MapPLUTO_18v1_1_unclipped.gdb\\MapPLUTO_UNCLIPPED"),
    ]
    szd.apply_mappluto_sub_dataset(rows, sibling_has_unclipped=False)
    assert rows[0]["sub_dataset"] == "clipped"
    assert rows[1]["sub_dataset"] == "unclipped"


def test_apply_mappluto_sub_dataset_sibling_signal():
    # Reproduces the modern nyc_mappluto_26v2_fgdb / _unclipped_fgdb split-across-rows case:
    # nothing inside *this* zip mentions unclipped, but a sibling row does.
    rows = [_row("MapPLUTO26v2.gdb\\MapPLUTO_26v2_clipped")]
    szd.apply_mappluto_sub_dataset(rows, sibling_has_unclipped=True)
    assert rows[0]["sub_dataset"] == "clipped"


def test_apply_mappluto_sub_dataset_no_evidence():
    # Reproduces mappluto_09v1: no unclipped signal anywhere, internal or sibling - this
    # vintage predates the concept entirely.
    rows = [_row("MapPLUTO_09v1\\Bronx\\BXMapPLUTO.shp")]
    szd.apply_mappluto_sub_dataset(rows, sibling_has_unclipped=False)
    assert rows[0]["sub_dataset"] == ""


# --- GDAL-integration tests, against small real local fixture zips (no network) -------


def test_read_layer_rows_shapefile_fixture(resources_path):
    zip_path = (resources_path / "shapefile_nyzd_one_row.zip").as_posix()
    vsi_path = f"/vsizip/{zip_path}"

    rows = szd.read_layer_rows(vsi_path, "test_id", "mappluto", "", None)

    assert len(rows) == 1
    row = rows[0]
    assert row["identifier"] == "test_id"
    assert row["product"] == "pluto"
    assert row["dataset"] == "mappluto"
    assert row["spatial"] is True
    assert row["row_count"] == 1
    assert row["path_in_zip"] == "shapefile_nyzd_one_row.shp"
    assert row["extent"] == "citywide"


def test_read_layer_rows_gdb_fixture(resources_path):
    zip_path = (resources_path / "geodatabase_zoning_data.zip").as_posix()
    gdb_path = "geodatabase_zoning_data.gdb"
    vsi_path = f"/vsizip/{zip_path}/{gdb_path}"

    rows = szd.read_layer_rows(vsi_path, "test_id", "mappluto", gdb_path, gdb_path)

    assert len(rows) == 1
    row = rows[0]
    assert row["spatial"] is True
    assert row["row_count"] == 1
    assert row["path_in_zip"] == f"{gdb_path}\\nyzd_one_row"


def test_read_layer_rows_nested_zip_fixture(nested_zip_path):
    # Local nested-vsizip requires curly braces at both levels (unlike the plain double
    # /vsizip//vsizip//vsicurl/... form used for real remote URLs in discover_zip) - confirmed
    # empirically before writing this test.
    outer_posix = nested_zip_path.as_posix()
    level1 = f"/vsizip/{{{outer_posix}}}/shapefile_nyzd_one_row.zip"
    level2 = f"/vsizip/{{{level1}}}"

    rows = szd.read_layer_rows(level2, "test_id", "mappluto", "", None)

    assert len(rows) == 1
    assert rows[0]["spatial"] is True
    assert rows[0]["row_count"] == 1


def test_read_layer_rows_unopenable_path_warns_and_returns_empty(capsys):
    rows = szd.read_layer_rows(
        "/vsizip/does/not/exist.zip", "test_id", "mappluto", "", None
    )
    assert rows == []
    assert "WARNING: could not list layers" in capsys.readouterr().out


def test_read_layer_rows_skips_layer_whose_info_fails(
    monkeypatch, resources_path, capsys
):
    # list_layers succeeds, but read_info fails for one specific layer - that layer should be
    # skipped with a warning, not abort the whole zip.
    import pyogrio

    zip_path = (resources_path / "shapefile_nyzd_one_row.zip").as_posix()
    vsi_path = f"/vsizip/{zip_path}"

    def fake_read_info(path, layer=None):
        raise RuntimeError("simulated read_info failure")

    monkeypatch.setattr(pyogrio, "read_info", fake_read_info)

    rows = szd.read_layer_rows(vsi_path, "test_id", "mappluto", "", None)

    assert rows == []
    assert "WARNING: could not read layer" in capsys.readouterr().out


# --- discover_zip orchestration (get_zip_namelist/read_layer_rows stubbed out) ---------


def test_discover_zip_orchestration(monkeypatch):
    names = [
        "Foo.gdb/a00000001.gdbtable",
        "Bronx/BXMapPLUTO.shp",
        "Bronx/BXMapPLUTO.dbf",
        "nested.zip",
    ]
    monkeypatch.setattr(szd, "get_zip_namelist", lambda url, session: names)

    calls = []

    def fake_read_layer_rows(
        vsi_path, identifier, dataset_name, path_prefix_for_display, layer_path_key
    ):
        calls.append(vsi_path)
        return [{"identifier": identifier, "path_in_zip": f"{vsi_path}-row"}]

    monkeypatch.setattr(szd, "read_layer_rows", fake_read_layer_rows)

    rows = szd.discover_zip(
        "https://x/some.zip", "some_id", "mappluto", False, session=object()
    )

    vsi_prefix = "/vsizip//vsicurl/https://x/some.zip"
    assert f"{vsi_prefix}/Foo.gdb" in calls
    assert f"{vsi_prefix}/Bronx" in calls
    assert f"/vsizip/{vsi_prefix}/nested.zip" in calls
    assert len(rows) == 3
    # apply_mappluto_sub_dataset ran over the combined result - no unclipped signal anywhere
    assert all(r["sub_dataset"] == "" for r in rows)


def test_discover_zip_threads_sibling_flag_into_sub_dataset(monkeypatch):
    monkeypatch.setattr(
        szd, "get_zip_namelist", lambda url, session: ["Foo.gdb/a.gdbtable"]
    )
    monkeypatch.setattr(
        szd,
        "read_layer_rows",
        lambda *a: [{"identifier": a[1], "path_in_zip": "Foo.gdb\\MapPLUTO"}],
    )

    rows = szd.discover_zip(
        "https://x/some.zip", "some_id", "mappluto", True, session=object()
    )

    assert rows[0]["sub_dataset"] == "clipped"


def test_discover_zip_returns_empty_when_namelist_unavailable(monkeypatch):
    monkeypatch.setattr(szd, "get_zip_namelist", lambda url, session: None)
    assert (
        szd.discover_zip(
            "https://x/some.zip", "some_id", "mappluto", False, session=object()
        )
        == []
    )


def test_discover_zip_includes_tabular_rows(monkeypatch):
    monkeypatch.setattr(szd, "get_zip_namelist", lambda url, session: ["data.csv"])
    monkeypatch.setattr(szd, "read_layer_rows", lambda *a: [])
    monkeypatch.setattr(
        szd,
        "read_tabular_row",
        lambda url, identifier, dataset_name, member_name, session: {
            "identifier": identifier,
            "path_in_zip": member_name,
        },
    )

    rows = szd.discover_zip(
        "https://x/some.zip", "some_id", "pluto", False, session=object()
    )

    assert rows == [
        {"identifier": "some_id", "path_in_zip": "data.csv", "sub_dataset": ""}
    ]


def test_discover_zip_skips_unreadable_tabular_file(monkeypatch):
    monkeypatch.setattr(
        szd, "get_zip_namelist", lambda url, session: ["good.csv", "bad.csv"]
    )
    monkeypatch.setattr(szd, "read_layer_rows", lambda *a: [])

    def fake_read_tabular_row(url, identifier, dataset_name, member_name, session):
        if member_name == "bad.csv":
            return None
        return {"identifier": identifier, "path_in_zip": member_name}

    monkeypatch.setattr(szd, "read_tabular_row", fake_read_tabular_row)

    rows = szd.discover_zip(
        "https://x/some.zip", "some_id", "pluto", False, session=object()
    )

    assert [r["path_in_zip"] for r in rows] == ["good.csv"]


# --- read_tabular_row (ranged-HTTP + stdlib csv, no GDAL/VSI involved) -----------------


URL = "https://s-media.nyc.gov/example.zip"


def test_read_tabular_row_reads_csv(monkeypatch):
    # dataset_name deliberately "pluto_change_file", not "mappluto" - regression test for the
    # bug where product/dataset were hardcoded to "mappluto" for every tabular row regardless
    # of the source row's real dataset_name (confirmed against real data: every csv/txt-typed
    # pluto_datasets.csv row is actually "pluto" or "pluto_change_file", never "mappluto").
    # Also distinguishes product ("pluto", the fixed umbrella product) from dataset (the
    # varying dataset_name) - a dataset_name of "pluto" alone can't tell the two apart.
    zip_bytes = make_zip_bytes(
        ["data.csv"], content={"data.csv": b"col1,col2\n1,2\n3,4\n5,6\n"}
    )
    get, head = mock_ranged_file_session(zip_bytes)
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "head", head)

    row = szd.read_tabular_row(
        URL, "test_id", "pluto_change_file", "data.csv", requests.Session()
    )

    assert row == {
        "identifier": "test_id",
        "product": "pluto",
        "dataset": "pluto_change_file",
        "extent": "citywide",
        "spatial": False,
        "row_count": 3,
        "path_in_zip": "data.csv",
    }


def test_read_tabular_row_borough_prefixed_extent(monkeypatch):
    zip_bytes = make_zip_bytes(
        ["Bronx/bx_pluto_extra.csv"],
        content={"Bronx/bx_pluto_extra.csv": b"a,b\n1,2\n"},
    )
    get, head = mock_ranged_file_session(zip_bytes)
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "head", head)

    row = szd.read_tabular_row(
        URL, "test_id", "pluto", "Bronx/bx_pluto_extra.csv", requests.Session()
    )

    assert row["extent"] == "bx"
    assert row["path_in_zip"] == "Bronx\\bx_pluto_extra.csv"


def test_read_tabular_row_missing_member_returns_none(monkeypatch):
    zip_bytes = make_zip_bytes(["other.csv"])
    get, head = mock_ranged_file_session(zip_bytes)
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "head", head)

    assert (
        szd.read_tabular_row(URL, "test_id", "pluto", "data.csv", requests.Session())
        is None
    )


def test_read_tabular_row_cp1252_fallback(monkeypatch):
    # Reproduces real failures found against nyc_pluto_20v5_arc_csv/nyc_pluto_07c: older
    # PLUTO tabular releases were authored on Windows and contain legacy single-byte
    # characters (e.g. em dash, cp1252 byte 0x97) that aren't valid UTF-8, but decode fine
    # as cp1252.
    content = "col1,col2\n1,em—dash\n".encode("cp1252")
    zip_bytes = make_zip_bytes(["data.csv"], content={"data.csv": content})
    get, head = mock_ranged_file_session(zip_bytes)
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "head", head)

    row = szd.read_tabular_row(URL, "test_id", "pluto", "data.csv", requests.Session())

    assert row["row_count"] == 1


def test_read_tabular_row_latin1_fallback_for_bytes_undefined_in_cp1252(monkeypatch):
    # Reproduces real failures found against nyc_pluto_20v5_arc_csv/nyc_pluto_07c even
    # AFTER adding the cp1252 fallback: both files contain byte values (0x90, 0x81) that
    # are undefined in cp1252 itself (confirmed empirically), so cp1252 alone isn't enough -
    # latin-1 maps every byte 0x00-0xFF and is tried last as the guaranteed-to-decode case.
    content = b"col1,col2\n1,\x90weird\x81byte\n"
    zip_bytes = make_zip_bytes(["data.csv"], content={"data.csv": content})
    get, head = mock_ranged_file_session(zip_bytes)
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "head", head)

    row = szd.read_tabular_row(URL, "test_id", "pluto", "data.csv", requests.Session())

    assert row["row_count"] == 1


def test_read_tabular_row_unparseable_content_warns_and_returns_row_with_no_count(
    monkeypatch, capsys
):
    # latin-1 decodes any byte sequence, so the only way every attempt can still fail is a
    # genuine structural problem, not an encoding one - a zero-byte member is EmptyDataError
    # under every encoding. The file is still listed (partial visibility), just with
    # row_count left blank.
    zip_bytes = make_zip_bytes(["data.csv"], content={"data.csv": b""})
    get, head = mock_ranged_file_session(zip_bytes)
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "head", head)

    row = szd.read_tabular_row(URL, "test_id", "pluto", "data.csv", requests.Session())

    assert row["row_count"] is None
    assert "could not parse" in capsys.readouterr().out
