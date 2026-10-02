"""HTTP sessions and cheap URL checks."""

import logging

import requests

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def get_response_code(url: str, session: requests.Session) -> int | None:
    """Cheaply check a URL's HTTP status without downloading its body.

    Tries a HEAD request first; if that fails outright, falls back to a minimal ranged GET.
    Returns the status code from whichever request actually completed - any code, 404 included,
    is a valid result, not a failure. None only if neither request could complete at all.
    """
    try:
        resp = session.head(url, timeout=30)
        return resp.status_code
    except requests.RequestException:
        pass

    try:
        resp = session.get(url, headers={"Range": "bytes=0-0"}, timeout=30)
        return resp.status_code
    except requests.RequestException as exc:
        logger.warning(f"could not check status for {url}: {exc}")
        return None
