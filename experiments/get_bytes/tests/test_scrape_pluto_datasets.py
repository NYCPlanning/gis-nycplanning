"""Tests for scrape_pluto_datasets.py - fully offline (see conftest.block_network)."""

import csv
import json

import requests
from conftest import MockResponse, make_zip_bytes, mock_session_call

import scrape_pluto_datasets as spd

# --- pure functions -----------------------------------------------------------------


def test_normalize_dataset_name_strips_tm_symbol_and_suffix():
    assert spd.normalize_dataset_name("MapPLUTO™ - Shapefile") == "mappluto"


def test_normalize_dataset_name_multi_word():
    assert spd.normalize_dataset_name("PLUTO Change File") == "pluto_change_file"


def test_reference_doc_suffix():
    assert spd.reference_doc_suffix("View Data Dictionary") == "datadictionary"
    assert spd.reference_doc_suffix("View Read Me") == "readme"


def test_infer_type_from_label():
    assert spd.infer_type_from_label("File Geodatabase") == "fgdb"
    assert spd.infer_type_from_label("Shapefile (SHP)") == "shp"
    assert spd.infer_type_from_label("Data (CSV)") == "csv"
    assert spd.infer_type_from_label("Something else") is None


def test_infer_type_from_url():
    assert spd.infer_type_from_url("https://x/nyc_mappluto_26v2_fgdb.zip") == "fgdb"
    assert spd.infer_type_from_url("https://x/nyc_mappluto_26v2_shp.zip") == "shp"
    assert spd.infer_type_from_url("https://x/mappluto_18v1.zip") is None


def test_strip_cache_buster():
    assert spd.strip_cache_buster("https://x/file.zip?r=1") == "https://x/file.zip"
    assert spd.strip_cache_buster("https://x/file.zip") == "https://x/file.zip"


def test_infer_type_pdf_shortcut_ignores_label(monkeypatch):
    # .pdf is decided purely by extension - no request should even be attempted.
    def _boom(self, *a, **k):
        raise AssertionError("should not make a request for a .pdf URL")

    monkeypatch.setattr(requests.Session, "get", _boom)
    assert (
        spd.infer_type("anything", "https://x/readme.pdf", requests.Session()) == "pdf"
    )


def test_infer_type_from_zip_contents(monkeypatch):
    url = "https://x/some.zip"
    routes = {url: MockResponse(206, make_zip_bytes(["Foo.gdb/a00000001.gdbtable"]))}
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes))
    assert spd.infer_type_from_zip_contents(url, requests.Session()) == "fgdb"

    url2 = "https://x/some2.zip"
    routes2 = {url2: MockResponse(206, make_zip_bytes(["Borough/BXMapPLUTO.shp"]))}
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes2))
    assert spd.infer_type_from_zip_contents(url2, requests.Session()) == "shp"

    url3 = "https://x/some3.zip"
    routes3 = {url3: MockResponse(206, make_zip_bytes(["readme.txt"]))}
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes3))
    assert spd.infer_type_from_zip_contents(url3, requests.Session()) == "txt"

    url4 = "https://x/some4.zip"
    routes4 = {url4: MockResponse(206, make_zip_bytes(["readme.xml"]))}
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes4))
    assert spd.infer_type_from_zip_contents(url4, requests.Session()) == "unknown"


def test_infer_type_from_zip_contents_unlistable_zip_is_unknown(monkeypatch):
    url = "https://x/broken.zip"
    monkeypatch.setattr(
        requests.Session, "get", mock_session_call({url: MockResponse(404)})
    )
    assert spd.infer_type_from_zip_contents(url, requests.Session()) == "unknown"


# --- assign_identifiers ---------------------------------------------------------------


def test_assign_identifiers_no_collision():
    rows = [{"url": "https://x/a.zip"}, {"url": "https://x/b.zip"}]
    spd.assign_identifiers(rows)
    assert rows[0]["identifier"] == "a"
    assert rows[1]["identifier"] == "b"


def test_assign_identifiers_collision_gets_stable_distinct_suffixes():
    # Two different real releases whose URL stem collides - a real upstream data error this
    # disambiguation exists to catch (see README's "Known gaps").
    rows = [
        {"url": "https://x/nyc_mappluto_22v2_arc_shp.zip", "version": "22v2"},
        {"url": "https://x/nyc_mappluto_22v2_arc_shp.zip?r=9", "version": "22v3"},
    ]
    spd.assign_identifiers(rows)
    ids = {row["identifier"] for row in rows}
    assert len(ids) == 2
    for identifier in ids:
        assert identifier.startswith("nyc_mappluto_22v2_arc_shp_")
        suffix = identifier.rsplit("_", 1)[1]
        assert len(suffix) == 5 and suffix.isdigit()

    # deterministic - rerunning on fresh copies of the same input reproduces the same ids
    rows2 = [
        {"url": "https://x/nyc_mappluto_22v2_arc_shp.zip", "version": "22v2"},
        {"url": "https://x/nyc_mappluto_22v2_arc_shp.zip?r=9", "version": "22v3"},
    ]
    spd.assign_identifiers(rows2)
    assert [r["identifier"] for r in rows] == [r["identifier"] for r in rows2]


def test_assign_identifiers_retries_on_forced_hash_collision(monkeypatch):
    # Force two different URLs to hash to the exact same suffix, to exercise the linear-probe
    # retry loop deterministically rather than hoping real URLs happen to collide.
    import hashlib

    class _FakeDigest:
        def hexdigest(self):
            return "42"

    monkeypatch.setattr(hashlib, "md5", lambda *_a, **_k: _FakeDigest())

    rows = [{"url": "https://x/dup.zip?a=1"}, {"url": "https://x/dup.zip?a=2"}]
    spd.assign_identifiers(rows)

    suffix0 = int(rows[0]["identifier"].rsplit("_", 1)[1])
    suffix1 = int(rows[1]["identifier"].rsplit("_", 1)[1])
    assert suffix1 == suffix0 + 1


def test_assign_identifiers_three_way_collision_uses_linear_probe():
    rows = [{"url": f"https://x/dup.zip?v={i}"} for i in range(3)]
    spd.assign_identifiers(rows)
    ids = [row["identifier"] for row in rows]
    assert len(set(ids)) == 3
    for identifier in ids:
        assert identifier.startswith("dup_")


# --- parse_recent_release / parse_archive, from real-shaped fixtures -----------------


def test_parse_recent_release(mocked_responses_path):
    html_fragment = (mocked_responses_path / "recent_release_fragment.html").read_text()
    rows = spd.parse_recent_release(html_fragment, requests.Session())

    by_url = {row["url"]: row for row in rows}
    download = by_url[
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/nyc_mappluto_26v2_shp.zip"
    ]
    assert download["dataset_name"] == "mappluto"
    assert download["type"] == "shp"
    assert download["version"] == "26v2"

    reference = by_url[
        "https://s-media.nyc.gov/agencies/dcp/assets/files/pdf/data-tools/bytes/pluto_datadictionary.pdf"
    ]
    assert reference["dataset_name"] == "mappluto_datadictionary"
    assert reference["type"] == "pdf"


def test_parse_recent_release_no_recent_release_section_returns_empty():
    assert (
        spd.parse_recent_release(
            "<html><body>nothing here</body></html>", requests.Session()
        )
        == []
    )


def test_parse_recent_release_skips_sub_section_without_h3():
    html = '<div id="recent-release"><div class="sub-section"><p>no heading</p></div></div>'
    assert spd.parse_recent_release(html, requests.Session()) == []


def test_parse_recent_release_skips_non_zip_pdf_links():
    html = """
    <div id="recent-release">
      <div class="sub-section">
        <h3>MapPLUTO</h3>
        <table><tr><td><a class="download" href="https://x/view-rest-service">View REST</a></td></tr></table>
      </div>
    </div>
    """
    assert spd.parse_recent_release(html, requests.Session()) == []


def test_parse_recent_release_version_comes_from_label_not_url():
    # The page-level "Latest Release" label is the only version signal that exists in this
    # section (confirmed by inspecting the real page - no per-dataset label exists there), so
    # it must win even when a download URL visibly embeds a different version.
    html = """
    <p>Latest Release: 26v2</p>
    <div id="recent-release">
      <div class="sub-section">
        <h3>MapPLUTO</h3>
        <table><tr><td><a class="download" href="https://x/nyc_mappluto_25v4_shp.zip">Download</a></td></tr></table>
      </div>
    </div>
    """
    rows = spd.parse_recent_release(html, requests.Session())
    assert rows[0]["version"] == "26v2"


def test_parse_archive(monkeypatch, mocked_responses_path):
    entries = json.loads((mocked_responses_path / "archive_entries.json").read_text())

    # infer_type is called with the *unstripped* link (before the cache-buster is dropped),
    # so mocked routes must be keyed on the raw link text from the fixture.
    routes = {
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/mappluto_18v1.zip": MockResponse(
            206, make_zip_bytes(["MapPLUTO18v1.gdb/a00000001.gdbtable"])
        ),
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/mappluto_17v1_1.zip?r=2": MockResponse(
            206, make_zip_bytes(["Bronx/BXMapPLUTO.shp"])
        ),
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/change/PLUTOChangeFile18v1.zip": MockResponse(
            206, make_zip_bytes(["PLUTOChangeFile18v1.csv"])
        ),
    }
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes))

    rows = spd.parse_archive(entries, requests.Session())
    by_url = {row["url"]: row for row in rows}

    mappluto_18v1 = by_url[
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/mappluto_18v1.zip"
    ]
    assert mappluto_18v1 == {
        "dataset_name": "mappluto",
        "type": "fgdb",
        "version": "18v1",
        "url": "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/mappluto_18v1.zip",
    }

    # cache-buster stripped from the stored url, even though the request used the raw link
    mappluto_17v1_1 = by_url[
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/mappluto_17v1_1.zip"
    ]
    assert mappluto_17v1_1["type"] == "shp"
    assert mappluto_17v1_1["version"] == "17v1.1"

    change_file = by_url[
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/change/PLUTOChangeFile18v1.zip"
    ]
    assert change_file["dataset_name"] == "pluto_change_file"
    assert change_file["type"] == "csv"


def test_parse_archive_version_comes_from_label_not_url(monkeypatch):
    # Mirrors the real PLUTOChangeFile26v1.zip case documented in README's Known Gaps: NYC's
    # own archive page links a "26v2" release label to a file whose name says "26v1" - the
    # label must still win, per-release, regardless of what the URL embeds.
    entries = [
        {
            "dataset": "PLUTO Change File",
            "releases": [
                {"text": "26v2", "link": "https://x/PLUTOChangeFile26v1.zip"},
            ],
        }
    ]
    routes = {
        "https://x/PLUTOChangeFile26v1.zip": MockResponse(
            206, make_zip_bytes(["a.csv"])
        )
    }
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes))

    rows = spd.parse_archive(entries, requests.Session())
    assert rows[0]["version"] == "26v2"


# --- main(), end-to-end through the CSV file -----------------------------------------


def test_main_writes_expected_csv(monkeypatch, tmp_path, mocked_responses_path):
    html_fragment = (mocked_responses_path / "recent_release_fragment.html").read_text()

    routes = {
        spd.CONTENT_API_URL: MockResponse(
            200, json.dumps({"description": html_fragment}).encode()
        ),
        spd.ARCHIVE_JSON_URL: MockResponse(
            200, (mocked_responses_path / "archive_entries.json").read_bytes()
        ),
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/mappluto_18v1.zip": MockResponse(
            206, make_zip_bytes(["MapPLUTO18v1.gdb/a00000001.gdbtable"])
        ),
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/mappluto_17v1_1.zip?r=2": MockResponse(
            206, make_zip_bytes(["Bronx/BXMapPLUTO.shp"])
        ),
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/change/PLUTOChangeFile18v1.zip": MockResponse(
            206, make_zip_bytes(["PLUTOChangeFile18v1.csv"])
        ),
    }
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes))

    # response_code is checked for every row via a HEAD request - one row routed to 200,
    # one to 404 (simulating a dead archive link, like the real nyc_mappluto_23v1_arc_fgdb.zip
    # case), the rest left unmocked (-> None -> blank in the CSV).
    head_routes = {
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/nyc_mappluto_26v2_shp.zip": MockResponse(
            200
        ),
        "https://s-media.nyc.gov/agencies/dcp/assets/files/zip/data-tools/bytes/mappluto/mappluto_18v1.zip": MockResponse(
            404
        ),
    }
    monkeypatch.setattr(requests.Session, "head", mock_session_call(head_routes))

    output_csv = tmp_path / "pluto_datasets.csv"
    monkeypatch.setattr(spd, "OUTPUT_CSV", output_csv)

    spd.main()

    with output_csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_identifier = {row["identifier"]: row for row in rows}
    assert set(by_identifier) == {
        "nyc_mappluto_26v2_shp",
        "pluto_datadictionary",
        "mappluto_18v1",
        "mappluto_17v1_1",
        "PLUTOChangeFile18v1",
    }
    assert by_identifier["nyc_mappluto_26v2_shp"]["type"] == "shp"
    assert by_identifier["mappluto_18v1"]["type"] == "fgdb"
    assert by_identifier["mappluto_17v1_1"]["type"] == "shp"
    assert by_identifier["PLUTOChangeFile18v1"]["dataset_name"] == "pluto_change_file"
    assert by_identifier["nyc_mappluto_26v2_shp"]["response_code"] == "200"
    assert by_identifier["mappluto_18v1"]["response_code"] == "404"
    assert by_identifier["pluto_datadictionary"]["response_code"] == ""
