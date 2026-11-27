import pytest
import requests

from dcpgis.utils import inspect_data, rest_schema

SERVICE_URL = "https://services.example.com/arcgis/rest/services/demo/FeatureServer"
ITEM_ID = "0123456789abcdef0123456789abcdef"

# Shaped like the public DTM service's responses: no "geometryField" key, Date fields
# report length 8, other non-string types report no length.
SERVICE_JSON = {"layers": [{"id": 0, "name": "TAX_LOT_POLYGON"}], "tables": [{"id": 2, "name": "CONDO"}]}
LAYER_JSON = {
    "id": 0,
    "name": "TAX_LOT_POLYGON",
    "geometryType": "esriGeometryPolygon",
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID", "length": None},
        {"name": "BBL", "type": "esriFieldTypeString", "length": 10},
        {"name": "LOT", "type": "esriFieldTypeSmallInteger", "length": None},
        {"name": "CREATED_DATE", "type": "esriFieldTypeDate", "length": 8},
        {"name": "Shape__Area", "type": "esriFieldTypeDouble", "length": None},
    ],
}
TABLE_JSON = {
    "id": 2,
    "name": "CONDO",
    "fields": [
        {"name": "OBJECTID", "type": "esriFieldTypeOID", "length": None},
        {"name": "CONDO_NUM", "type": "esriFieldTypeString", "length": 4},
    ],
}
ROUTES = {
    SERVICE_URL: SERVICE_JSON,
    f"{SERVICE_URL}/0": LAYER_JSON,
    f"{SERVICE_URL}/2": TABLE_JSON,
    f"https://www.arcgis.com/sharing/rest/content/items/{ITEM_ID}": {"type": "Feature Service", "url": SERVICE_URL},
}
EXPECTED_LAYER_ROWS = [
    ["OBJECTID", "OID", 4],
    ["Shape", "Geometry", 0],
    ["BBL", "String", 10],
    ["LOT", "SmallInteger", 2],
    ["CREATED_DATE", "Date", 8],
    ["Shape__Area", "Double", 8],
]


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload, self.status_code = payload, status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


@pytest.fixture
def requests_made(monkeypatch):
    made = []

    def fake_get(url, params=None, timeout=None):
        made.append((url, params))
        return _FakeResponse(ROUTES.get(url, {"error": {"code": 400, "message": "Invalid URL"}}))

    monkeypatch.setattr(rest_schema.requests, "get", fake_get)
    return made


def _rows(schema):
    return schema.values.tolist()


def test_layer_url(requests_made):
    assert _rows(inspect_data.get_dataset_schema(f"{SERVICE_URL}/0")) == EXPECTED_LAYER_ROWS


@pytest.mark.parametrize("layer", ["TAX_LOT_POLYGON", "0"])
def test_service_url_with_layer_name_or_id(requests_made, layer):
    assert _rows(inspect_data.get_dataset_schema(SERVICE_URL, layer=layer)) == EXPECTED_LAYER_ROWS


def test_item_id_with_layer_name(requests_made):
    assert _rows(inspect_data.get_dataset_schema(ITEM_ID, layer="TAX_LOT_POLYGON")) == EXPECTED_LAYER_ROWS


def test_table_has_no_geometry_row(requests_made):
    schema = inspect_data.get_dataset_schema(SERVICE_URL, layer="CONDO")
    assert _rows(schema) == [["OBJECTID", "OID", 4], ["CONDO_NUM", "String", 4]]


def test_load_reference_schema_accepts_url(requests_made):
    assert _rows(inspect_data.load_reference_schema(f"{SERVICE_URL}/0")) == EXPECTED_LAYER_ROWS


def test_every_request_is_read_only_json(requests_made):
    inspect_data.get_dataset_schema(ITEM_ID, layer="TAX_LOT_POLYGON")
    assert requests_made and all(params == {"f": "json"} for _, params in requests_made)


def test_error_in_response_body_raises(requests_made):
    with pytest.raises(ValueError, match="returned an error"):
        inspect_data.get_dataset_schema(f"{SERVICE_URL}/9")


def test_connection_failure_raises(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.ConnectionError("unreachable")

    monkeypatch.setattr(rest_schema.requests, "get", fail)
    with pytest.raises(ValueError, match="Could not read REST endpoint"):
        inspect_data.get_dataset_schema(f"{SERVICE_URL}/0")


def test_service_url_without_layer_raises(requests_made):
    with pytest.raises(ValueError, match="layer name or ID is required"):
        inspect_data.get_dataset_schema(SERVICE_URL)


def test_unknown_layer_name_lists_available(requests_made):
    with pytest.raises(ValueError, match="Available: \\['CONDO', 'TAX_LOT_POLYGON'\\]"):
        inspect_data.get_dataset_schema(SERVICE_URL, layer="SUB_LOT")
