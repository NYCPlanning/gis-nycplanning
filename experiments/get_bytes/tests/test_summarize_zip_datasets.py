"""Tests for summarize_zip_datasets.py.

Two tiers: pure-logic unit tests (no I/O at all), and GDAL-integration tests against small
real local fixture zips via plain local /vsizip/ paths - never /vsicurl/, so fully offline
(see conftest.block_network) without needing to mock GDAL itself.
"""

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

    rows = szd.read_layer_rows(vsi_path, "test_id", "", None)

    assert len(rows) == 1
    row = rows[0]
    assert row["identifier"] == "test_id"
    assert row["spatial"] is True
    assert row["row_count"] == 1
    assert row["path_in_zip"] == "shapefile_nyzd_one_row.shp"
    assert row["extent"] == "citywide"


def test_read_layer_rows_gdb_fixture(resources_path):
    zip_path = (resources_path / "geodatabase_zoning_data.zip").as_posix()
    gdb_path = "geodatabase_zoning_data.gdb"
    vsi_path = f"/vsizip/{zip_path}/{gdb_path}"

    rows = szd.read_layer_rows(vsi_path, "test_id", gdb_path, gdb_path)

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

    rows = szd.read_layer_rows(level2, "test_id", "", None)

    assert len(rows) == 1
    assert rows[0]["spatial"] is True
    assert rows[0]["row_count"] == 1


def test_read_layer_rows_unopenable_path_warns_and_returns_empty(capsys):
    rows = szd.read_layer_rows("/vsizip/does/not/exist.zip", "test_id", "", None)
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

    rows = szd.read_layer_rows(vsi_path, "test_id", "", None)

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
        vsi_path, identifier, path_prefix_for_display, layer_path_key
    ):
        calls.append(vsi_path)
        return [{"identifier": identifier, "path_in_zip": f"{vsi_path}-row"}]

    monkeypatch.setattr(szd, "read_layer_rows", fake_read_layer_rows)

    rows = szd.discover_zip("https://x/some.zip", "some_id", False, session=object())

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

    rows = szd.discover_zip("https://x/some.zip", "some_id", True, session=object())

    assert rows[0]["sub_dataset"] == "clipped"


def test_discover_zip_returns_empty_when_namelist_unavailable(monkeypatch):
    monkeypatch.setattr(szd, "get_zip_namelist", lambda url, session: None)
    assert (
        szd.discover_zip("https://x/some.zip", "some_id", False, session=object()) == []
    )
