"""Tests for common.py - fully offline (see conftest.block_network)."""

import pytest
import requests
from conftest import (
    MockResponse,
    make_zip_bytes,
    mock_ranged_file_session,
    mock_session_call,
)

from common import (
    _HTTPRangeFile,
    get_response_code,
    get_zip_member_bytes,
    get_zip_namelist,
    make_session,
)

URL = "https://s-media.nyc.gov/example.zip"


def test_make_session_sets_user_agent():
    session = make_session()
    assert session.headers.get("User-Agent")


def test_get_zip_namelist_ranged_success(monkeypatch):
    routes = {URL: MockResponse(206, make_zip_bytes(["a.shp", "a.dbf"]))}
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes))

    assert get_zip_namelist(URL, make_session()) == ["a.shp", "a.dbf"]


def test_get_zip_namelist_unexpected_status_returns_none(monkeypatch, capsys):
    routes = {URL: MockResponse(404)}
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes))

    assert get_zip_namelist(URL, make_session()) is None
    assert "unexpected status 404" in capsys.readouterr().out


def test_get_zip_namelist_ranged_200_corrupt_returns_none_without_fallback(monkeypatch):
    # A ranged request answered with status 200 means the server ignored Range and sent the
    # *whole* file - if that whole file still isn't a valid zip, retrying can't help.
    routes = {URL: MockResponse(200, b"not a zip")}
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes))

    assert get_zip_namelist(URL, make_session()) is None


def test_get_zip_namelist_ranged_206_corrupt_falls_back_to_full_get(monkeypatch):
    # A 206 means Range *was* honored - the tail alone may not parse as a standalone zip even
    # though the real file is fine, so a corrupt 206 response should trigger a full re-fetch.
    routes = {
        URL: [
            MockResponse(206, b"not a zip"),
            MockResponse(200, make_zip_bytes(["b.gdb/a00000001.gdbtable"])),
        ]
    }
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes))

    assert get_zip_namelist(URL, make_session()) == ["b.gdb/a00000001.gdbtable"]


def test_get_zip_namelist_fallback_get_also_fails_returns_none(monkeypatch):
    routes = {
        URL: [
            MockResponse(206, b"not a zip"),
            requests.RequestException("connection reset"),
        ]
    }
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes))

    assert get_zip_namelist(URL, make_session()) is None


def test_get_zip_namelist_request_exception_returns_none(monkeypatch, capsys):
    routes = {URL: requests.RequestException("boom")}
    monkeypatch.setattr(requests.Session, "get", mock_session_call(routes))

    assert get_zip_namelist(URL, make_session()) is None
    assert "request failed" in capsys.readouterr().out


def test_get_response_code_head_200(monkeypatch):
    monkeypatch.setattr(
        requests.Session, "head", mock_session_call({URL: MockResponse(200)})
    )
    assert get_response_code(URL, make_session()) == 200


def test_get_response_code_head_404_no_get_fallback(monkeypatch):
    # A completed HEAD request is not a failure, even with a 404 - no GET should be attempted.
    monkeypatch.setattr(
        requests.Session, "head", mock_session_call({URL: MockResponse(404)})
    )
    assert get_response_code(URL, make_session()) == 404


def test_get_response_code_head_fails_falls_back_to_get(monkeypatch):
    monkeypatch.setattr(
        requests.Session,
        "head",
        mock_session_call({URL: requests.RequestException("HEAD not allowed")}),
    )
    monkeypatch.setattr(
        requests.Session, "get", mock_session_call({URL: MockResponse(200)})
    )
    assert get_response_code(URL, make_session()) == 200


def test_get_response_code_both_fail_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(
        requests.Session,
        "head",
        mock_session_call({URL: requests.RequestException("HEAD not allowed")}),
    )
    monkeypatch.setattr(
        requests.Session,
        "get",
        mock_session_call({URL: requests.RequestException("connection reset")}),
    )
    assert get_response_code(URL, make_session()) is None
    assert "could not check status" in capsys.readouterr().out


def test_get_zip_member_bytes_reads_real_member_via_ranged_requests(monkeypatch):
    zip_bytes = make_zip_bytes(
        ["a.shp", "data.csv"], content={"data.csv": b"col1,col2\n1,2\n3,4\n"}
    )
    get, head = mock_ranged_file_session(zip_bytes)
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "head", head)

    assert (
        get_zip_member_bytes(URL, "data.csv", make_session())
        == b"col1,col2\n1,2\n3,4\n"
    )


def test_get_zip_member_bytes_missing_member_returns_none(monkeypatch, capsys):
    zip_bytes = make_zip_bytes(["a.shp"])
    get, head = mock_ranged_file_session(zip_bytes)
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "head", head)

    assert get_zip_member_bytes(URL, "missing.csv", make_session()) is None
    assert "could not read member" in capsys.readouterr().out


def test_get_zip_member_bytes_head_failure_returns_none(monkeypatch, capsys):
    monkeypatch.setattr(
        requests.Session,
        "head",
        mock_session_call({URL: requests.RequestException("HEAD not allowed")}),
    )

    assert get_zip_member_bytes(URL, "data.csv", make_session()) is None
    assert "could not read member" in capsys.readouterr().out


def test_http_range_file_seek_whence_variants(monkeypatch):
    # Direct unit tests against _HTTPRangeFile's own seek/read logic, rather than relying on
    # zipfile happening to exercise every whence value - zipfile only calls whence=1 (SEEK_CUR)
    # to skip a member's local-header "extra field" when one is present, which plain zips
    # written by zipfile.writestr (as this suite's fixtures are) don't include, so real zip
    # I/O alone wouldn't reach that branch.
    get, head = mock_ranged_file_session(b"0123456789")
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "head", head)

    f = _HTTPRangeFile(URL, make_session())
    assert f.tell() == 0

    f.seek(4)  # SEEK_SET (default whence)
    assert f.tell() == 4

    f.seek(2, 1)  # SEEK_CUR
    assert f.tell() == 6

    f.seek(-1, 2)  # SEEK_END
    assert f.tell() == 9

    with pytest.raises(ValueError):
        f.seek(0, 99)


def test_http_range_file_read_past_end_returns_empty(monkeypatch):
    get, head = mock_ranged_file_session(b"0123456789")
    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(requests.Session, "head", head)

    f = _HTTPRangeFile(URL, make_session())
    f.seek(10)  # exactly at EOF (10-byte file)
    assert f.read(5) == b""
