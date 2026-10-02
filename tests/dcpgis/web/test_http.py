"""Tests for dcpgis.web.http - fully offline (see conftest.block_network)."""

import requests

from dcpgis.web.http import get_response_code, make_session
from tests.conftest import MockResponse, mock_session_call

URL = "https://s-media.nyc.gov/example.zip"


def test_make_session_sets_user_agent():
    session = make_session()
    assert session.headers.get("User-Agent")


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


def test_get_response_code_both_fail_returns_none(monkeypatch, caplog):
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
    assert "could not check status" in caplog.text
