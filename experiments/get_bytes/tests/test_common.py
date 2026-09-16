"""Tests for common.py - fully offline (see conftest.block_network)."""

import requests
from conftest import MockResponse, make_zip_bytes, mock_session_call

from common import get_response_code, get_zip_namelist, make_session

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
