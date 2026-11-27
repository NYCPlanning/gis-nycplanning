"""Read a layer's field schema from an ArcGIS REST feature or map service.

Read-only: every request is a GET with f=json. No credentials are sent, so only public
services work for now.

Known differences from a feature class read:
- A MapServer layer lists only its visible fields, so a hidden field looks removed.
- Aliases can be set in the published map rather than on the feature class.
- REST reports no precision or scale.
- Hosted layers name geometry measure fields Shape__Area/Shape__Length.
"""

import re

import requests

_TIMEOUT_SECONDS = 30
_DEFAULT_PORTAL_URL = "https://www.arcgis.com"
_ITEM_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_LAYER_URL_PATTERN = re.compile(r"/(FeatureServer|MapServer)/\d+$", re.IGNORECASE)
_SERVICE_URL_PATTERN = re.compile(r"/(FeatureServer|MapServer)$", re.IGNORECASE)


def is_rest_url(value: object) -> bool:
    return isinstance(value, str) and value.lower().startswith(("http://", "https://"))


def is_item_id(value: object) -> bool:
    return isinstance(value, str) and _ITEM_ID_PATTERN.fullmatch(value) is not None


def _get_json(url: str) -> dict:
    try:
        response = requests.get(url, params={"f": "json"}, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ValueError(f"Could not read REST endpoint: {url}") from exc

    # ArcGIS REST reports most errors as HTTP 200 with an "error" object in the body.
    if "error" in payload:
        error = payload["error"]
        raise ValueError(f"REST endpoint returned an error for {url}: {error.get('code')} {error.get('message')}")
    return payload


def resolve_item_url(item_id: str, portal_url: str = _DEFAULT_PORTAL_URL) -> str:
    """Return the service URL of a public ArcGIS Online (or Portal) item."""
    if not is_item_id(item_id):
        raise ValueError(f"Not an ArcGIS item ID: {item_id!r}")

    item = _get_json(f"{portal_url.rstrip('/')}/sharing/rest/content/items/{item_id}")
    url = item.get("url")
    if not url:
        raise ValueError(f"Item {item_id} has no service URL (item type: {item.get('type')})")
    return url


def _resolve_layer_url(url: str, layer: str | None) -> str:
    """Return a layer URL, from either a layer URL or a service URL plus a layer name or ID."""
    url = url.rstrip("/")
    if _LAYER_URL_PATTERN.search(url):
        return url
    if not _SERVICE_URL_PATTERN.search(url):
        raise ValueError(f"Not a FeatureServer or MapServer URL: {url}")
    if layer is None:
        raise ValueError(f"A layer name or ID is required with a service URL: {url}")
    if layer.isdigit():
        return f"{url}/{layer}"

    service = _get_json(url)
    items = service.get("layers", []) + service.get("tables", [])
    matches = [item["id"] for item in items if item.get("name") == layer]
    if len(matches) != 1:
        available = sorted(item.get("name") for item in items)
        raise ValueError(f"Expected one layer named {layer!r} in {url}, found {len(matches)}. Available: {available}")
    return f"{url}/{matches[0]}"


def get_rest_layer_fields(source: str, layer: str | None = None) -> list[dict]:
    """Return a REST layer's fields as {name, type, length} dicts, in service order.

    Args:
        source: a layer URL, a service URL, or an ArcGIS Online item ID.
        layer: a layer name or numeric ID. Required with a service URL or item ID;
            ignored with a layer URL.

    Types are the literal esriFieldType* names with the prefix removed, the same
    vocabulary as the File Geodatabase reader. `length` is whatever REST reports and may
    be None; the caller fills in fixed lengths.

    REST doesn't list geometry as a field, so a Geometry row is added after the ObjectID
    field (the usual geodatabase order). Its position is a guess, which matters only
    when field order is checked.
    """
    url = resolve_item_url(source) if is_item_id(source) else source
    layer_url = _resolve_layer_url(url, layer)
    definition = _get_json(layer_url)
    if "fields" not in definition:
        raise ValueError(f"No field list at {layer_url}; is it a layer or table?")

    fields = [
        {"name": f["name"], "type": f["type"].removeprefix("esriFieldType"), "length": f.get("length")}
        for f in definition["fields"]
    ]

    if definition.get("geometryType"):
        geometry_name = (definition.get("geometryField") or {}).get("name", "Shape")
        oid_index = next((i for i, f in enumerate(fields) if f["type"] == "OID"), -1)
        fields.insert(oid_index + 1, {"name": geometry_name, "type": "Geometry", "length": None})

    return fields
