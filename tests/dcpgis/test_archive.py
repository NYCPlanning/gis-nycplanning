"""Tests for dcpgis.archive - pure functions over member names, no I/O."""

import zipfile

from dcpgis import archive

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
    assert archive.discover_gdb_folders(names) == ["MapPLUTO.gdb"]
    assert archive.discover_loose_dirs(names) == ["", "Bronx"]
    assert archive.discover_nested_zips(names) == ["inner.zip"]
    # .gdb-internal and nested-zip members are excluded from every suffix-based scan
    assert archive.discover_tabular_files(names) == ["notes.csv", "readme.txt"]
    assert archive.discover_pdf_files(names) == ["pluto_datadictionary.pdf"]


def test_discover_loose_dirs_ignores_pdf_only_directory():
    # GDAL's Shapefile driver can never identify a directory of PDFs, so there is no point
    # asking it to try - this gate is what stops a doomed open attempt per zip root.
    assert archive.discover_loose_dirs(["docs/readme.pdf"]) == []


# --- object inventory -------------------------------------------------------------------------


def _infolist(*entries) -> list[zipfile.ZipInfo]:
    """(path, size) pairs as ZipInfos; a trailing slash makes a directory entry."""
    out = []
    for path, size in entries:
        info = zipfile.ZipInfo(path)
        info.file_size = size
        out.append(info)
    return out


def test_object_inventory_rolls_a_shapefile_up_and_records_its_extensions():
    infolist = _infolist(
        ("MapPLUTO.shp", 100),
        ("MapPLUTO.dbf", 20),
        ("MapPLUTO.prj", 1),
        ("MapPLUTO.shp.xml", 5),
        ("readme.pdf", 7),
    )
    objects = archive.build_object_inventory(infolist, {}, set())

    shapefile = next(o for o in objects if o["kind"] == "shapefile")
    assert shapefile["path"] == "MapPLUTO.shp"
    assert shapefile["size_bytes"] == 126  # every sidecar, not just the .shp
    # .shp.xml groups with its shapefile rather than looking like a lone .xml
    assert shapefile["parts"] == [".dbf", ".prj", ".shp", ".shp.xml"]
    assert {"path": "readme.pdf", "kind": "file", "size_bytes": 7} in objects


def test_object_inventory_collapses_a_gdb_and_attaches_its_contents():
    infolist = _infolist(
        ("MapPLUTO.gdb/", 0),
        ("MapPLUTO.gdb/a00000001.gdbtable", 40),
        ("MapPLUTO.gdb/a00000001.gdbtablx", 60),
    )
    contents = [{"name": "MapPLUTO_Clipped", "kind": "feature_class"}]
    (gdb,) = archive.build_object_inventory(infolist, {"MapPLUTO.gdb": contents}, set())

    assert gdb["path"] == "MapPLUTO.gdb"
    assert gdb["size_bytes"] == 100
    # system files are not worth counting, let alone listing
    assert "member_count" not in gdb
    assert gdb["contents"] == contents


def test_object_inventory_lists_lock_files_individually_not_inside_the_gdb():
    infolist = _infolist(
        ("MapPLUTO.gdb/a00000001.gdbtable", 40),
        ("MapPLUTO.gdb/_gdb.DCP-DELL.sr.lock", 0),
        ("MapPLUTO.gdb/MapPLUTO_Clipped.DCP-DELL.sr.lock", 0),
    )
    objects = archive.build_object_inventory(infolist, {}, set())

    locks = [o["path"] for o in objects if o["kind"] == "lock"]
    assert locks == [
        "MapPLUTO.gdb/MapPLUTO_Clipped.DCP-DELL.sr.lock",
        "MapPLUTO.gdb/_gdb.DCP-DELL.sr.lock",
    ]
    gdb = next(o for o in objects if o["kind"] == "gdb")
    assert gdb["size_bytes"] == 40  # locks are not counted into their container


def test_object_inventory_unreadable_gdb_reports_null_contents():
    # "could not open this" must not read as "this gdb is empty".
    infolist = _infolist(("MapPLUTO.gdb/a00000001.gdbtable", 40))
    (gdb,) = archive.build_object_inventory(infolist, {}, {"MapPLUTO.gdb"})
    assert gdb["contents"] is None

    (readable,) = archive.build_object_inventory(infolist, {}, set())
    assert readable["contents"] == []


def test_object_inventory_classifies_the_remaining_kinds():
    infolist = _infolist(
        ("data.csv", 3),
        ("notes.txt", 4),
        ("lookup.dbf", 5),
        ("inner.zip", 6),
        ("map.pdf", 7),
    )
    objects = archive.build_object_inventory(infolist, {}, set())
    kinds = {o["path"]: o["kind"] for o in objects}
    assert kinds == {
        "data.csv": "table",
        "notes.txt": "table",
        "lookup.dbf": "table",  # standalone, with no .shp sharing its basename
        "inner.zip": "zip",
        "map.pdf": "file",
    }
