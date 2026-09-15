"""End-to-end tests for get_bytes.py at depth 0 - fully offline.

main() is covered here rather than excluded as a thin wrapper, because at depth 0 it is
nothing but file I/O and pure assembly over already-mocked HTTP: there is no GDAL and no
unmockable surface, so the whole path from CLI args to written files is testable.
"""

import csv
import json
import zlib
from pathlib import Path

import pytest
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
            "version": "18v1",
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


def test_parse_args_resume_writes_beside_the_resumed_report(tmp_path, monkeypatch):
    # Run from anywhere else, a resume must still rewrite the report it started from rather
    # than leaving a second, diverging copy in cwd.
    report = tmp_path / "runs" / "observed_report_p_20260919T000000Z.json"
    monkeypatch.chdir(tmp_path)
    args = get_bytes.parse_args(["--resume", str(report)])
    assert args.output_dir == report.parent
    assert get_bytes.observed_path({"page": "p", "initiated_timestamp": "20260919T000000Z"}, args.output_dir) == report


def test_parse_args_resume_implies_depth_one(tmp_path):
    assert get_bytes.parse_args(["--resume", str(tmp_path / "r.json")]).depth == 1


def test_parse_args_resume_rejects_depth_zero(tmp_path):
    # Depth 0 has nothing to resume; silently running it would drop the inspection entirely.
    with pytest.raises(SystemExit):
        get_bytes.parse_args(["--resume", str(tmp_path / "r.json"), "--depth", "0"])


def test_parse_args_explicit_output_dir_wins_over_resume(tmp_path):
    out = tmp_path / "elsewhere"
    args = get_bytes.parse_args(["--resume", str(tmp_path / "r.json"), "--output-dir", str(out)])
    assert args.output_dir == out


# --- depth 1 orchestration ------------------------------------------------------------------
#
# inspect_zip is stubbed: it needs real GDAL against remote paths, which is covered in
# test_zip_inspect.py. What matters here is the wiring - which entries get inspected, how
# results land on them, and that one bad archive cannot abort the run.


def _entry(identifier, type_="shp", version="26v2"):
    return {
        "identifier": identifier,
        "url_level": {
            "dataset_name": "mappluto",
            "type": type_,
            "version": version,
            "url_actual": f"https://x/{identifier}.zip",
            "response_code": 200,
            "product": "pluto",
        },
        "zip_level": None,
        "dataset_level": [],
    }


def _stub_inspect(monkeypatch, result=None, raises=None):
    from processes.get_bytes import zip_inspect

    inspected = []

    def _fake(url, dataset_name, sibling_has_unclipped, session, check_index=True):
        inspected.append({"url": url, "sibling": sibling_has_unclipped})
        if raises is not None:
            raise raises
        return result if result is not None else ({"objects": []}, [])

    monkeypatch.setattr(zip_inspect, "inspect_zip", _fake)
    monkeypatch.setattr(zip_inspect, "configure_gdal", lambda: None)
    return inspected


def test_depth_one_skips_out_of_scope_types(monkeypatch):
    observed = {
        "entries": [
            _entry("a_shp", "shp"),
            _entry("b_fgdb", "fgdb"),
            _entry("c_csv", "csv"),
            _entry("d_txt", "txt"),
            _entry("e_pdf", "pdf"),
            _entry("f_unknown", "unknown"),
        ]
    }
    inspected = _stub_inspect(monkeypatch)

    get_bytes.add_zip_and_dataset_levels(observed, session=None)

    # pdf has no archive to open; unknown is the zip-of-zips case GDAL cannot reach
    assert [i["url"].rsplit("/", 1)[1] for i in inspected] == [
        "a_shp.zip",
        "b_fgdb.zip",
        "c_csv.zip",
        "d_txt.zip",
    ]
    assert observed["entries"][4]["zip_level"] is None
    assert observed["entries"][5]["zip_level"] is None


def test_depth_one_attaches_results_to_the_entry(monkeypatch):
    observed = {"entries": [_entry("a_shp")]}
    zip_level = {"objects": [{"path": "a.lock", "kind": "lock"}], "obs_size_bytes": 99}
    dataset_level = [{"type": "shp", "path_in_zip": "a.shp"}]
    _stub_inspect(monkeypatch, result=(zip_level, dataset_level))

    get_bytes.add_zip_and_dataset_levels(observed, session=None)

    assert observed["entries"][0]["zip_level"] == zip_level
    assert observed["entries"][0]["dataset_level"] == dataset_level


def test_depth_one_passes_unclipped_sibling_signal(monkeypatch):
    # The clipped zip needs to know its unclipped counterpart exists as a separate entry,
    # which is only knowable by looking across all entries, not at one in isolation.
    observed = {
        "entries": [
            _entry("nyc_mappluto_26v2_unclipped_shp"),
            _entry("nyc_mappluto_26v2_shp"),
        ]
    }
    inspected = _stub_inspect(monkeypatch)

    get_bytes.add_zip_and_dataset_levels(observed, session=None)
    assert [i["sibling"] for i in inspected] == [True, True]


def test_depth_one_flushes_progress_to_disk(monkeypatch, tmp_path):
    # An hour-long run that writes nothing until the end loses everything on a crash.
    observed = {
        "page": "p",
        "initiated_timestamp": "20260919T000000Z",
        "entries": [_entry(f"z{i}_shp") for i in range(12)],
    }
    _stub_inspect(monkeypatch, result=({"objects": []}, []))

    get_bytes.add_zip_and_dataset_levels(observed, session=None, out_dir=tmp_path)

    written = json.loads(
        get_bytes.observed_path(observed, tmp_path).read_text(encoding="utf-8")
    )
    assert len(written["entries"]) == 12


def test_depth_one_skips_entries_already_inspected(monkeypatch):
    # The resume contract: depth 0 sets zip_level to None explicitly, so a populated
    # zip_level is the marker for "already done".
    observed = {
        "entries": [
            _entry("done_shp") | {"zip_level": {"objects": []}},
            _entry("pending_shp"),
        ]
    }
    inspected = _stub_inspect(monkeypatch)

    get_bytes.add_zip_and_dataset_levels(observed, session=None)

    assert [i["url"].rsplit("/", 1)[1] for i in inspected] == ["pending_shp.zip"]


def test_load_observed_keeps_timestamp_so_resume_rewrites_one_file(tmp_path):
    source = tmp_path / "observed_report_p_20260919T000000Z.json"
    source.write_text(
        json.dumps(
            {
                "page": "p",
                "initiated_timestamp": "20260919T000000Z",
                "depth": 0,
                "entries": [_entry("a_shp")],
            }
        ),
        encoding="utf-8",
    )

    observed = get_bytes.load_observed(source, depth=1)
    assert observed["depth"] == 1
    assert observed["initiated_timestamp"] == "20260919T000000Z"
    assert get_bytes.observed_path(observed, tmp_path) == source


def test_write_observed_is_atomic(tmp_path):
    # temp-then-rename: a crash mid-write must not truncate the file a resume depends on
    observed = {
        "page": "p",
        "initiated_timestamp": "20260919T000000Z",
        "entries": [],
    }
    path = get_bytes.write_observed(observed, tmp_path)
    assert path.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_parse_args_requires_url_unless_resuming(tmp_path):
    with pytest.raises(SystemExit):
        get_bytes.parse_args([])
    args = get_bytes.parse_args(["--resume", str(tmp_path / "r.json"), "--depth", "1"])
    assert args.url is None
    assert args.depth == 1


@pytest.mark.parametrize(
    "error",
    [
        OSError("malformed central directory"),
        # not an OSError or RuntimeError - damaged DEFLATE data in a member GDAL is reading
        zlib.error("Error -3 while decompressing data: invalid block type"),
    ],
)
def test_depth_one_one_bad_archive_does_not_abort_the_run(monkeypatch, capsys, error):
    observed = {"entries": [_entry("bad_shp"), _entry("also_bad_shp")]}
    _stub_inspect(monkeypatch, raises=error)

    get_bytes.add_zip_and_dataset_levels(observed, session=None)

    # both were attempted and both recorded as failed, rather than the first killing the run
    for entry in observed["entries"]:
        assert entry["zip_level"]["error"] == f"{type(error).__name__}: {error}"
        assert entry["zip_level"]["objects"] is None
        assert entry["dataset_level"] == []
    assert capsys.readouterr().out.count("WARNING: failed inspecting") == 2


def test_depth_one_resume_retries_failed_entries(monkeypatch):
    # A failure may be transient (a network blip), so resume gives it another go - while a
    # cleanly inspected entry is still skipped.
    observed = {
        "entries": [
            _entry("done_shp") | {"zip_level": {"objects": []}},
            _entry("failed_shp") | {"zip_level": {"objects": None, "error": "OSError: reset"}},
        ]
    }
    inspected = _stub_inspect(monkeypatch, result=({"objects": []}, [{"type": "shp"}]))

    get_bytes.add_zip_and_dataset_levels(observed, session=None)

    assert [i["url"].rsplit("/", 1)[1] for i in inspected] == ["failed_shp.zip"]
    assert "error" not in observed["entries"][1]["zip_level"]
    assert observed["entries"][1]["dataset_level"] == [{"type": "shp"}]
