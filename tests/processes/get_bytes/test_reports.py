"""Tests for reports.py - pure functions over the observed JSON, no network anywhere."""

import csv

from processes.get_bytes import reports


def _entry(identifier, **url_level):
    """An observed entry with url_level defaults, for tests that only care about one field."""
    defaults = {
        "dataset_name": "mappluto",
        "type": "shp",
        "version": "26v2",
        "url_actual": f"https://x/{identifier}.zip",
        "response_code": 200,
        "product": "pluto",
    }
    return {
        "identifier": identifier,
        "url_level": {**defaults, **url_level},
        "zip_level": None,
        "dataset_level": [],
    }


def _observed(entries, depth=0):
    return {
        "input_url": "https://x/datasets/some-page",
        "page": "some-page",
        "initiated_timestamp": "20260918T120000Z",
        "depth": depth,
        "entries": entries,
    }


# --- url report ------------------------------------------------------------------------


def test_build_url_rows_matches_legacy_column_shape():
    observed = _observed([_entry("a", version="18v1")])
    assert reports.build_url_rows(observed) == [
        {
            "identifier": "a",
            "dataset_name": "mappluto",
            "type": "shp",
            "version": "18v1",
            "url": "https://x/a.zip",
            "response_code": 200,
        }
    ]


# --- problem rules ---------------------------------------------------------------------


def test_find_broken_links_flags_only_real_failures():
    assert reports.find_broken_links(_entry("ok", response_code=200)) == []
    assert reports.find_broken_links(_entry("partial", response_code=206)) == []
    # Never got a code at all - the request itself failed, which is not the same claim as
    # "the server said this is missing", so it isn't reported as a broken link.
    assert reports.find_broken_links(_entry("unknown", response_code=None)) == []

    (row,) = reports.find_broken_links(_entry("missing", response_code=404))
    assert row == {
        "identifier": "missing",
        "level": "url",
        "path_in_zip": "",
        "problem": "broken_link",
        "detail": "404",
        "url": "https://x/missing.zip",
    }


def test_find_duplicate_identifier():
    assert reports.find_duplicate_identifier(_entry("nyc_mappluto_25v2_arc_shp")) == []
    (row,) = reports.find_duplicate_identifier(_entry("PLUTOChangeFile26v1_00673"))
    assert row["problem"] == "duplicate_identifier"
    assert row["level"] == "url"


def test_find_extra_zip_nesting():
    assert reports.find_extra_zip_nesting(_entry("fine", type="shp")) == []
    (row,) = reports.find_extra_zip_nesting(_entry("mappluto_16v2", type="unknown"))
    assert row["problem"] == "extra_zip_nesting"
    assert row["level"] == "zip"


def test_find_lock_files_is_one_row_per_lock_file():
    # One row each, naming the file. The count follows the locks, not the datasets - three
    # datasets alongside two locks still yields two rows.
    entry = _entry("mappluto_19v1")
    entry["zip_level"] = {
        "objects": [
            {"path": "MapPLUTO.gdb", "kind": "gdb"},
            {"path": "MapPLUTO.gdb/_gdb.DCP-DELL.sr.lock", "kind": "lock"},
            {"path": "MapPLUTO_unclipped.gdb/_gdb.DCP-DELL.sr.lock", "kind": "lock"},
        ]
    }
    entry["dataset_level"] = [
        {"path_in_zip": "a.shp"},
        {"path_in_zip": "b.shp"},
        {"path_in_zip": "c.shp"},
    ]
    rows = reports.find_lock_files(entry)
    assert [r["path_in_zip"] for r in rows] == [
        "MapPLUTO.gdb/_gdb.DCP-DELL.sr.lock",
        "MapPLUTO_unclipped.gdb/_gdb.DCP-DELL.sr.lock",
    ]
    assert all(r["problem"] == "has_lock_files" and r["level"] == "zip" for r in rows)


def test_find_lock_files_absent_or_none():
    assert reports.find_lock_files(_entry("no_zip_level")) == []
    entry = _entry("clean")
    entry["zip_level"] = {"objects": [{"path": "a.shp", "kind": "shapefile"}]}
    assert reports.find_lock_files(entry) == []


def test_find_corrupted_spatial_indexes_one_row_per_affected_layer():
    entry = _entry("mappluto_14v2")
    entry["dataset_level"] = [
        {
            "path_in_zip": "Manhattan\\MNMapPLUTO.shp",
            "spatial_index": {"present": True, "status": "INCONSISTENT"},
        },
        {
            "path_in_zip": "Bronx\\BXMapPLUTO.shp",
            "spatial_index": {"present": True, "status": "CONSISTENT"},
        },
        # no index at all, and a tabular entry with no spatial_index key - neither is a problem
        {
            "path_in_zip": "Queens\\QNMapPLUTO.shp",
            "spatial_index": {"present": False, "status": None},
        },
        {"path_in_zip": "notes.csv"},
    ]
    rows = reports.find_corrupted_spatial_indexes(entry)
    assert [r["path_in_zip"] for r in rows] == ["Manhattan\\MNMapPLUTO.shp"]
    assert rows[0]["level"] == "file"


# --- aggregate -------------------------------------------------------------------------


def test_build_error_rows_is_empty_for_clean_data():
    # The long format's whole point: clean input shrinks this report to nothing rather than
    # padding it with all-false rows per identifier.
    observed = _observed([_entry("clean_one"), _entry("clean_two")])
    assert reports.build_error_rows(observed) == []


def test_build_error_rows_at_depth_zero_finds_only_url_level_problems():
    # zip_level is null and dataset_level empty at depth 0, so the zip/file rules find
    # nothing without needing any explicit depth branching.
    observed = _observed(
        [_entry("gone", response_code=404), _entry("dup_00673")], depth=0
    )
    rows = reports.build_error_rows(observed)
    assert {(r["identifier"], r["problem"]) for r in rows} == {
        ("gone", "broken_link"),
        ("dup_00673", "duplicate_identifier"),
    }
    assert all(r["level"] == "url" for r in rows)


def test_build_error_rows_sorted_and_carries_url():
    observed = _observed(
        [_entry("zzz", response_code=404), _entry("aaa", response_code=500)]
    )
    rows = reports.build_error_rows(observed)
    assert [r["identifier"] for r in rows] == ["aaa", "zzz"]
    assert rows[0]["url"] == "https://x/aaa.zip"


# --- dataset report ----------------------------------------------------------------------


def _dataset(path_in_zip, type_, sub_dataset="", row_count=1, col_count=1):
    return {
        "dataset": "mappluto",
        "sub_dataset": sub_dataset,
        "path_in_zip": path_in_zip,
        "geog_extent": "citywide",
        "type": type_,
        "row_count": row_count,
        "col_count": col_count,
    }


def test_build_dataset_rows_derives_spatial_from_type():
    entry = _entry("nyc_mappluto_26v2_fgdb")
    entry["zip_level"] = {"objects": [{"path": "a.shp", "kind": "shapefile"}]}
    entry["dataset_level"] = [
        _dataset("MapPLUTO.gdb\\MapPLUTO", "gdb_fc", "unclipped", 857932, 94),
        _dataset("MapPLUTO.gdb\\NOT_MAPPED_LOTS", "gdb_tb", row_count=412),
        _dataset("notes.csv", "csv", row_count=9),
    ]
    rows = reports.build_dataset_rows(_observed([entry], depth=1))

    assert [r["spatial"] for r in rows] == [True, False, False]
    assert rows[0]["extent"] == "citywide"  # geog_extent is renamed on the way out
    assert rows[0]["column_count"] == 94  # and col_count
    assert all(r["product"] == "pluto" for r in rows)
    assert all(r["has_lock_files"] is False for r in rows)


def test_build_dataset_rows_classifies_items_and_scopes_sub_dataset():
    # The inference stamps the clip label on everything sharing a zip with MapPLUTO; only the
    # MapPLUTO layer itself should keep it.
    entry = _entry("nyc_mappluto_25v1_arc_fgdb")
    entry["zip_level"] = {"objects": []}
    entry["dataset_level"] = [
        _dataset("MapPLUTO25v1.gdb\\MapPLUTO_25v1_clipped", "gdb_fc", "clipped"),
        _dataset("pluto_datadictionary.pdf", "pdf", "clipped", None, None),
        _dataset("MapPLUTO25v1.gdb\\NOT_MAPPED_LOTS", "gdb_tb", "clipped"),
    ]
    rows = reports.build_dataset_rows(_observed([entry], depth=1))

    assert [(r["item"], r["sub_dataset"]) for r in rows] == [
        ("mappluto", "clipped"),
        ("pluto_datadictionary", ""),
        ("not_classified", ""),
    ]
    assert [r["type"] for r in rows] == ["gdb_fc", "pdf", "gdb_tb"]


def test_build_dataset_rows_dataset_name_comes_from_url_level():
    # url_level is the page's own name for the dataset; dataset_level's copy is only a stamp.
    entry = _entry("PLUTOChangeFile25v4", dataset_name="pluto_change_file")
    entry["zip_level"] = {"objects": []}
    entry["dataset_level"] = [_dataset("pluto_changes_applied.csv", "csv")]
    (row,) = reports.build_dataset_rows(_observed([entry], depth=1))

    assert row["dataset_name"] == "pluto_change_file"
    assert row["item"] == "pluto_changes_applied"


def test_build_dataset_rows_empty_at_depth_zero():
    assert reports.build_dataset_rows(_observed([_entry("a")])) == []


# --- writers ------------------------------------------------------------------------------


def test_writers_name_files_by_page_and_timestamp(tmp_path):
    observed = _observed([_entry("a", response_code=404)])

    url_path = reports.write_url_report(observed, tmp_path)
    error_path = reports.write_error_summary(observed, tmp_path)

    assert url_path.name == "url_report_some-page_20260918T120000Z.csv"
    assert error_path.name == "error_summary_some-page_20260918T120000Z.csv"

    with error_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows == [
        {
            "identifier": "a",
            "level": "url",
            "path_in_zip": "",
            "problem": "broken_link",
            "detail": "404",
            "url": "https://x/a.zip",
        }
    ]


def test_write_url_report_creates_missing_output_dir(tmp_path):
    out_dir = tmp_path / "does" / "not" / "exist"
    path = reports.write_url_report(_observed([_entry("a")]), out_dir)
    assert path.exists()


def test_write_dataset_report_column_order(tmp_path):
    entry = _entry("nyc_mappluto_26v2_shp")
    entry["zip_level"] = {"objects": [{"path": "a.shp", "kind": "shapefile"}]}
    entry["dataset_level"] = [
        {
            "dataset": "mappluto",
            "sub_dataset": "clipped",
            "path_in_zip": "Bronx\\BXMapPLUTO.shp",
            "geog_extent": "bx",
            "type": "shp",
            "row_count": 89684,
            "col_count": 86,
            "spatial_index": {"present": True, "status": "INCONSISTENT"},
        }
    ]
    path = reports.write_dataset_report(_observed([entry], depth=1), tmp_path)

    assert path.name == "dataset_report_some-page_20260918T120000Z.csv"
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == [
            "identifier",
            "product",
            "dataset_name",
            "item",
            "sub_dataset",
            "extent",
            "spatial",
            "row_count",
            "column_count",
            "type",
            "path_in_zip",
            "has_lock_files",
        ]
        rows = list(reader)

    assert rows[0]["item"] == "mappluto"
    assert rows[0]["sub_dataset"] == "clipped"
    assert rows[0]["spatial"] == "True"
    assert rows[0]["extent"] == "bx"
    assert rows[0]["row_count"] == "89684"
    assert rows[0]["column_count"] == "86"
    assert "spatial_index" not in rows[0]  # stays JSON-only
