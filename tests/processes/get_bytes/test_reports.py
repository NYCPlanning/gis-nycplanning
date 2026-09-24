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


def test_find_incorrect_file_flags_label_filename_mismatch():
    # The real case: one zip listed under two releases, and this is the wrong one.
    entry = _entry(
        "PLUTOChangeFile26v1_00673",
        version="26v2",
        url_actual="https://x/PLUTOChangeFile26v1.zip",
    )
    (row,) = reports.find_incorrect_file(entry)
    assert row["problem"] == "incorrect_file"
    assert row["level"] == "url"
    assert row["detail"] == "labelled 26v2, file is 26v1"


def test_find_incorrect_file_ignores_formatting_differences():
    # The page writes 25v2.1 where the filename has 25v2_1, and labels betas "18v2Beta".
    dotted = _entry(
        "a", version="25v2.1", url_actual="https://x/nyc_pluto_25v2_1_arc_csv.zip"
    )
    beta = _entry(
        "b", version="18v2Beta", url_actual="https://x/nyc_mappluto_18v2_arc_shp.zip"
    )
    assert reports.find_incorrect_file(dotted) == []
    assert reports.find_incorrect_file(beta) == []


def test_find_incorrect_file_skips_versionless_filenames():
    # Reference PDFs carry no version, so there is nothing to disagree with.
    entry = _entry("pluto_readme", url_actual="https://x/pluto_readme.pdf")
    assert reports.find_incorrect_file(entry) == []


def _failed(identifier, **url_level):
    entry = _entry(identifier, **url_level)
    entry["zip_level"] = {
        "filename": f"{identifier}.zip",
        "obs_size_bytes": None,
        "objects": None,
        "error": "central directory could not be read",
    }
    return entry


def test_find_unreadable_zips_reports_a_failed_inspection():
    (row,) = reports.find_unreadable_zips(_failed("nyc_mappluto_20v1_shp"))
    assert row == {
        "identifier": "nyc_mappluto_20v1_shp",
        "level": "zip",
        "path_in_zip": "",
        "problem": "unreadable_zip",
        "detail": "central directory could not be read",
        "url": "https://x/nyc_mappluto_20v1_shp.zip",
    }


def test_find_unreadable_zips_defers_to_a_broken_link():
    # A 404 zip is always unreadable too; the url-level row already names the cause.
    entry = _failed("gone", response_code=404)
    assert reports.find_unreadable_zips(entry) == []
    assert [r["problem"] for r in reports.build_error_rows(_observed([entry]))] == ["broken_link"]


def test_find_unreadable_zips_ignores_inspected_and_uninspected_zips():
    inspected = _entry("ok")
    inspected["zip_level"] = {"objects": []}
    assert reports.find_unreadable_zips(inspected) == []
    assert reports.find_unreadable_zips(_entry("depth_zero")) == []


def test_failed_zip_raises_no_file_level_rows():
    # objects is None, not a list, so there is nothing to call "listed but unread"
    rows = reports.build_error_rows(_observed([_failed("bad")], depth=1))
    assert [(r["level"], r["problem"]) for r in rows] == [("zip", "unreadable_zip")]


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


def _corrupted(entry):
    return [
        (r["path_in_zip"], r["detail"]) for r in reports.find_corrupted_files(entry)
    ]


def test_find_corrupted_files_unparseable_table():
    # nyc_pluto_20v5_arc_csv: the header parses, then a quoting defect stops the row count.
    entry = _entry("nyc_pluto_20v5_arc_csv")
    entry["dataset_level"] = [
        _dataset("pluto_20v5.csv", "csv", row_count=None, col_count=3),
        _dataset("pluto_readme.pdf", "pdf", row_count=None, col_count=None),
    ]
    assert _corrupted(entry) == [("pluto_20v5.csv", "rows could not be parsed")]


def test_find_corrupted_files_column_count_outlier():
    # nyc_pluto_06c: one borough file has twice the columns of the other four.
    entry = _entry("nyc_pluto_06c")
    entry["dataset_level"] = [
        _dataset(f"{boro}06C.TXT", "txt", col_count=165 if boro == "BK" else 83)
        for boro in ("BK", "BX", "MN", "QN", "SI")
    ]
    assert _corrupted(entry) == [("BK06C.TXT", "165 columns; siblings have 83")]


def test_find_corrupted_files_column_counts_need_a_clear_majority():
    agreeing = _entry("agree")
    agreeing["dataset_level"] = [
        _dataset(f"{b}06C.TXT", "txt", col_count=83) for b in ("BK", "BX", "MN")
    ]
    pair = _entry("pair")
    pair["dataset_level"] = [
        _dataset("BK06C.TXT", "txt", col_count=165),
        _dataset("BX06C.TXT", "txt", col_count=83),
    ]
    split = _entry("split")
    split["dataset_level"] = [
        _dataset(f"{boro}06C.TXT", "txt", col_count=cols)
        for boro, cols in (("BK", 83), ("BX", 83), ("MN", 90), ("QN", 90))
    ]
    assert _corrupted(agreeing) == []
    assert _corrupted(pair) == []  # with two, there is no telling which one is wrong
    assert _corrupted(split) == []  # nor with an even split


def test_find_corrupted_files_spatial_index_check_that_could_not_run():
    # The .shp could be listed but not read back, so its index was never verified - that must
    # not pass as clean.
    entry = _entry("nyc_mappluto_20v1_shp")
    entry["dataset_level"] = [
        _dataset("MapPLUTO.shp", "shp") | {"spatial_index": {"present": None, "status": "ERROR"}},
        _dataset("BXMapPLUTO.shp", "shp") | {"spatial_index": {"present": True, "status": "CONSISTENT"}},
        _dataset("MNMapPLUTO.shp", "shp") | {"spatial_index": {"present": False, "status": None}},
    ]
    assert _corrupted(entry) == [("MapPLUTO.shp", "spatial index could not be checked")]
    # an index check that errored is not evidence the index itself is corrupt
    assert reports.find_corrupted_spatial_indexes(entry) == []


def test_find_corrupted_files_listed_but_unread():
    # nyc_pluto_25v1_arc_csv: the CSV is in the central directory but could never be read.
    entry = _entry("nyc_pluto_25v1_arc_csv")
    entry["zip_level"] = {
        "objects": [
            {"path": "pluto_25v1.csv", "kind": "table"},
            {"path": "Bronx/BXMapPLUTO.shp", "kind": "shapefile"},
            {"path": "MapPLUTO.gdb", "kind": "gdb", "contents": [{"name": "MapPLUTO"}]},
            {"path": "Broken.gdb", "kind": "gdb", "contents": None},
            {"path": "pluto_readme.pdf", "kind": "file"},
        ]
    }
    entry["dataset_level"] = [
        _dataset("Bronx\\BXMapPLUTO.shp", "shp"),
        _dataset("MapPLUTO.gdb\\MapPLUTO", "gdb_fc"),
    ]
    assert _corrupted(entry) == [
        ("pluto_25v1.csv", "listed in the zip but could not be read"),
        ("Broken.gdb", "listed in the zip but could not be read"),
    ]


# --- aggregate -------------------------------------------------------------------------


def test_build_error_rows_is_empty_for_clean_data():
    # The long format's whole point: clean input shrinks this report to nothing rather than
    # padding it with all-false rows per identifier.
    observed = _observed([_entry("clean_one"), _entry("clean_two")])
    assert reports.build_error_rows(observed) == []


def test_build_error_rows_at_depth_zero_finds_only_url_level_problems():
    # zip_level is null and dataset_level empty at depth 0, so the zip/file rules find
    # nothing without needing any explicit depth branching.
    wrong = _entry(
        "wrong_00673", version="26v2", url_actual="https://x/PLUTOChangeFile26v1.zip"
    )
    observed = _observed([_entry("gone", response_code=404), wrong], depth=0)
    rows = reports.build_error_rows(observed)
    assert {(r["identifier"], r["problem"]) for r in rows} == {
        ("gone", "broken_link"),
        ("wrong_00673", "incorrect_file"),
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
