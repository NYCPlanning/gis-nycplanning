"""Tests for error_report.py - fully offline, pure-logic (no network, no HTTP mocking needed
at all - this script never touches the network, so the usual mock_session_call/MockResponse
machinery the other test files use doesn't apply here)."""

import csv

import error_report as er


def test_find_broken_links():
    source_rows = [
        {"identifier": "good_one", "response_code": "200"},
        {"identifier": "also_good", "response_code": "206"},
        {"identifier": "missing", "response_code": "404"},
        {"identifier": "never_completed", "response_code": ""},
    ]
    rows = er.find_broken_links(source_rows)
    assert rows == [
        {
            "identifier": "missing",
            "level": "url",
            "path_in_zip": "",
            "problem": "broken_link",
            "detail": "404",
        }
    ]


def test_find_duplicate_identifiers():
    source_rows = [
        {"identifier": "PLUTOChangeFile26v1_00673"},
        {"identifier": "PLUTOChangeFile26v1_00674"},
        {"identifier": "nyc_mappluto_25v2_arc_shp"},
    ]
    rows = er.find_duplicate_identifiers(source_rows)
    assert {r["identifier"] for r in rows} == {
        "PLUTOChangeFile26v1_00673",
        "PLUTOChangeFile26v1_00674",
    }
    assert all(
        r["level"] == "url" and r["problem"] == "duplicate_identifier" for r in rows
    )


def test_find_extra_zip_nesting():
    source_rows = [
        {"identifier": "mappluto_16v2", "type": "unknown"},
        {"identifier": "mappluto_17v1", "type": "unknown"},
        {"identifier": "mappluto_18v1", "type": "shp"},
    ]
    rows = er.find_extra_zip_nesting(source_rows)
    assert {r["identifier"] for r in rows} == {"mappluto_16v2", "mappluto_17v1"}
    assert all(
        r["level"] == "zip" and r["problem"] == "extra_zip_nesting" for r in rows
    )


def test_find_lock_files_dedupes_per_identifier():
    # has_lock_files is a whole-zip fact repeated across every dataset row that zip
    # produced (the same shape summarize_zip_datasets.py writes it in) - confirm this
    # collapses back down to one problem row per affected identifier, not one per dataset row.
    zip_content_rows = [
        {"identifier": "mappluto_09v1", "has_lock_files": "True"},
        {"identifier": "mappluto_09v1", "has_lock_files": "True"},
        {"identifier": "mappluto_09v1", "has_lock_files": "True"},
        {"identifier": "mappluto_10v1", "has_lock_files": "False"},
    ]
    rows = er.find_lock_files(zip_content_rows)
    assert rows == [
        {
            "identifier": "mappluto_09v1",
            "level": "zip",
            "path_in_zip": "",
            "problem": "has_lock_files",
            "detail": "",
        }
    ]


def test_find_corrupted_spatial_indexes():
    spatial_index_rows = [
        {
            "identifier": "mappluto_14v2",
            "path_in_zip": "Manhattan\\MNMapPLUTO.shp",
            "verdict": "INCONSISTENT",
        },
        {
            "identifier": "mappluto_09v1",
            "path_in_zip": "Manhattan\\MNMapPLUTO.shp",
            "verdict": "CONSISTENT",
        },
    ]
    rows = er.find_corrupted_spatial_indexes(spatial_index_rows)
    assert rows == [
        {
            "identifier": "mappluto_14v2",
            "level": "file",
            "path_in_zip": "Manhattan\\MNMapPLUTO.shp",
            "problem": "corrupted_spatial_index",
            "detail": "",
        }
    ]


def test_main_produces_zero_rows_for_clean_data(tmp_path, monkeypatch, capsys):
    # The long format's whole point: a fully clean dataset should shrink this report to
    # nothing, not pad it with all-false/blank rows for every identifier.
    datasets_csv = tmp_path / "pluto_datasets.csv"
    datasets_csv.write_text(
        "identifier,response_code,type,url\n"
        "clean_one,200,shp,https://example.com/clean_one.zip\n",
        encoding="utf-8",
    )
    zip_contents_csv = tmp_path / "zip_contents.csv"
    zip_contents_csv.write_text(
        "identifier,has_lock_files\nclean_one,False\n", encoding="utf-8"
    )
    output_csv = tmp_path / "error_report.csv"

    monkeypatch.setattr(er, "DATASETS_CSV", datasets_csv)
    monkeypatch.setattr(er, "ZIP_CONTENTS_CSV", zip_contents_csv)
    monkeypatch.setattr(er, "SPATIAL_INDEX_CSV", tmp_path / "spatial_index_results.csv")
    monkeypatch.setattr(er, "OUTPUT_CSV", output_csv)

    er.main()

    # Path.read_text() normalizes line endings, so this compares against \n even though the
    # csv module itself writes \r\n (open(..., newline="") in main() preserves that correctly).
    assert (
        output_csv.read_text(encoding="utf-8")
        == "identifier,level,path_in_zip,problem,detail,url\n"
    )
    assert "not found - skipping corrupted_spatial_index" in capsys.readouterr().out


def test_main_tolerates_missing_spatial_index_csv_but_includes_it_when_present(
    tmp_path, monkeypatch
):
    datasets_csv = tmp_path / "pluto_datasets.csv"
    datasets_csv.write_text(
        "identifier,response_code,type,url\n"
        "some_id,200,shp,https://example.com/some_id.zip\n",
        encoding="utf-8",
    )
    zip_contents_csv = tmp_path / "zip_contents.csv"
    zip_contents_csv.write_text(
        "identifier,has_lock_files\nsome_id,False\n", encoding="utf-8"
    )
    spatial_index_csv = tmp_path / "spatial_index_results.csv"
    spatial_index_csv.write_text(
        "identifier,path_in_zip,verdict\nsome_id,Manhattan\\MNMapPLUTO.shp,INCONSISTENT\n",
        encoding="utf-8",
    )
    output_csv = tmp_path / "error_report.csv"

    monkeypatch.setattr(er, "DATASETS_CSV", datasets_csv)
    monkeypatch.setattr(er, "ZIP_CONTENTS_CSV", zip_contents_csv)
    monkeypatch.setattr(er, "SPATIAL_INDEX_CSV", spatial_index_csv)
    monkeypatch.setattr(er, "OUTPUT_CSV", output_csv)

    er.main()

    with output_csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows == [
        {
            "identifier": "some_id",
            "url": "https://example.com/some_id.zip",
            "level": "file",
            "path_in_zip": "Manhattan\\MNMapPLUTO.shp",
            "problem": "corrupted_spatial_index",
            "detail": "",
        }
    ]
