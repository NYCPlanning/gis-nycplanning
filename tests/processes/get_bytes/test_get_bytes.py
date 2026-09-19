"""End-to-end tests for get_bytes.py at depth 0 - fully offline.

main() is covered here rather than excluded as a thin wrapper, because at depth 0 it is
nothing but file I/O and pure assembly over already-mocked HTTP: there is no GDAL and no
unmockable surface, so the whole path from CLI args to written files is testable.
"""

import csv
import json
from pathlib import Path

import requests

from processes.get_bytes import get_bytes
from tests.processes.get_bytes.conftest import (
    MockResponse,
    make_zip_bytes,
    mock_session_call,
)

PAGE_URL = "https://www.nyc.gov/content/planning/pages/resources/datasets/some-page"
CONTENT_API = (
    "https://apps.nyc.gov/content-api/v1/content/planning/resources/datasets/some-page"
)
ARCHIVE_JSON = "https://www.nyc.gov/assets/planning/json/content/resources/dataset-archives/some-page.json"

MAPPLUTO_18V1 = "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/mappluto_18v1.zip"
MAPPLUTO_17V1_1_RAW = "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/mappluto_17v1_1.zip?r=2"
CHANGE_FILE = "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/change/PLUTOChangeFile18v1.zip"
RECENT_SHP = "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/nyc_mappluto_26v2_shp.zip"


def _install_routes(monkeypatch, mocked_responses_path):
    html_fragment = (mocked_responses_path / "recent_release_fragment.html").read_text()
    get_routes = {
        CONTENT_API: MockResponse(
            200, json.dumps({"description": html_fragment}).encode()
        ),
        ARCHIVE_JSON: MockResponse(
            200, (mocked_responses_path / "archive_entries.json").read_bytes()
        ),
        MAPPLUTO_18V1: MockResponse(
            206, make_zip_bytes(["MapPLUTO18v1.gdb/a00000001.gdbtable"])
        ),
        MAPPLUTO_17V1_1_RAW: MockResponse(
            206, make_zip_bytes(["Bronx/BXMapPLUTO.shp"])
        ),
        CHANGE_FILE: MockResponse(206, make_zip_bytes(["PLUTOChangeFile18v1.csv"])),
    }
    monkeypatch.setattr(requests.Session, "get", mock_session_call(get_routes))

    # One row routed to 200 and one to 404 (mirroring the real dead-archive-link case); the
    # rest are left unmocked, so they come back None and land blank in the CSV.
    head_routes = {RECENT_SHP: MockResponse(200), MAPPLUTO_18V1: MockResponse(404)}
    monkeypatch.setattr(requests.Session, "head", mock_session_call(head_routes))


def test_main_depth_zero_writes_json_and_two_csvs(
    monkeypatch, tmp_path, mocked_responses_path
):
    _install_routes(monkeypatch, mocked_responses_path)

    get_bytes.main([PAGE_URL, "--output-dir", str(tmp_path)])

    written = sorted(p.name.split("_some-page_")[0] for p in tmp_path.iterdir())
    assert written == ["error_summary", "observed_report", "url_report"], (
        "depth 0 should not emit a dataset report"
    )


def test_main_depth_zero_observed_json_shape(
    monkeypatch, tmp_path, mocked_responses_path
):
    _install_routes(monkeypatch, mocked_responses_path)

    get_bytes.main([PAGE_URL, "--output-dir", str(tmp_path)])

    observed = json.loads(
        next(tmp_path.glob("observed_report_*.json")).read_text(encoding="utf-8")
    )
    assert observed["input_url"] == PAGE_URL
    assert observed["page"] == "some-page"
    assert observed["depth"] == 0
    assert observed["initiated_timestamp"].endswith("Z")

    by_identifier = {e["identifier"]: e for e in observed["entries"]}
    assert set(by_identifier) == {
        "nyc_mappluto_26v2_shp",
        "pluto_datadictionary",
        "mappluto_18v1",
        "mappluto_17v1_1",
        "PLUTOChangeFile18v1",
    }

    entry = by_identifier["mappluto_18v1"]
    assert entry["url_level"] == {
        "dataset_name": "mappluto",
        "type": "fgdb",
        "version": "18v1",
        "url_actual": MAPPLUTO_18V1,
        "response_code": 404,
        "product": "pluto",
    }
    # depth 0 leaves the deeper levels explicitly empty rather than omitting the keys, so
    # consumers can tell "not inspected" apart from "inspected and found nothing".
    assert entry["zip_level"] is None
    assert entry["dataset_level"] == []

    # `spatial` is derived at report time, never persisted
    assert "spatial" not in json.dumps(observed)


def test_main_depth_zero_url_report_matches_legacy_columns(
    monkeypatch, tmp_path, mocked_responses_path
):
    _install_routes(monkeypatch, mocked_responses_path)

    get_bytes.main([PAGE_URL, "--output-dir", str(tmp_path)])

    url_csv = next(tmp_path.glob("url_report_*.csv"))
    with url_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == [
            "identifier",
            "dataset_name",
            "type",
            "version",
            "url",
            "response_code",
        ]
        rows = {row["identifier"]: row for row in reader}

    assert rows["nyc_mappluto_26v2_shp"]["type"] == "shp"
    assert rows["mappluto_18v1"]["type"] == "fgdb"
    assert rows["mappluto_17v1_1"]["type"] == "shp"
    assert rows["PLUTOChangeFile18v1"]["dataset_name"] == "pluto_change_file"
    assert rows["nyc_mappluto_26v2_shp"]["response_code"] == "200"
    assert rows["mappluto_18v1"]["response_code"] == "404"
    assert rows["pluto_datadictionary"]["response_code"] == ""
    # cache-buster stripped from the stored url
    assert rows["mappluto_17v1_1"]["url"] == MAPPLUTO_17V1_1_RAW.removesuffix("?r=2")


def test_main_depth_zero_error_summary_catches_the_404(
    monkeypatch, tmp_path, mocked_responses_path
):
    _install_routes(monkeypatch, mocked_responses_path)

    get_bytes.main([PAGE_URL, "--output-dir", str(tmp_path)])

    error_csv = next(tmp_path.glob("error_summary_*.csv"))
    with error_csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert rows == [
        {
            "identifier": "mappluto_18v1",
            "level": "url",
            "path_in_zip": "",
            "problem": "broken_link",
            "detail": "404",
            "url": MAPPLUTO_18V1,
        }
    ]


def test_parse_args_defaults_to_depth_zero_and_cwd():
    args = get_bytes.parse_args([PAGE_URL])
    assert args.depth == 0
    assert args.url == PAGE_URL
    assert args.output_dir == Path.cwd()


def test_parse_args_output_dir_tracks_cwd_at_call_time(tmp_path, monkeypatch):
    # The default must not be frozen at import, or a caller running from elsewhere would
    # silently get reports wherever the module happened to be first imported.
    monkeypatch.chdir(tmp_path)
    assert get_bytes.parse_args([PAGE_URL]).output_dir == tmp_path


def test_parse_args_accepts_depth_one():
    assert get_bytes.parse_args([PAGE_URL, "--depth", "1"]).depth == 1
