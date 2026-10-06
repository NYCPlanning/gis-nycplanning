"""HTTP sessions and cheap URL checks."""

import logging

import requests

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# What servers that don't implement HEAD answer, instead of failing the request.
_HEAD_UNSUPPORTED = (405, 501)


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": _USER_AGENT})
    return session


def get_response_code(url: str, session: requests.Session) -> int | None:
    """Cheaply check a URL's HTTP status without downloading its body.

    Tries a HEAD request first. If that fails outright, or the server answers 405 or 501
    because it doesn't support HEAD, falls back to a GET for the first byte only.

    Returns the status code from whichever request completed - any code, 404 included, is a
    valid result, not a failure. A server honouring the GET's Range answers 206 rather than
    200, so treat both as success. If HEAD got a 405/501 and the GET then fails outright,
    that 405/501 is returned. None only if neither request got a response at all.
    """
    head_code = None
    try:
        head_code = session.head(url, timeout=30).status_code
    except requests.RequestException:
        pass
    else:
        if head_code not in _HEAD_UNSUPPORTED:
            return head_code

    try:
        resp = session.get(url, headers={"Range": "bytes=0-0"}, timeout=30)
        return resp.status_code
    except requests.RequestException as exc:
        if head_code is not None:
            return head_code
        logger.warning(f"could not check status for {url}: {exc}")
        return None
