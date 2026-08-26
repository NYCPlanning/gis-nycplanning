"""Requires an arcpy-enabled interpreter (e.g. the ArcGIS Pro conda env) - collect_gis_info.py
imports arcpy at module level, same requirement as test_inspect_data.py."""

import platform
import sys

from utilities.gis_machine_troubleshooter.internal import collect_gis_info


# --- _describe() ---


class _NormalItem:
    name = "roads"
    dataSource = "db.roads"
    isBroken = False


class _ItemDataSourceRaises:
    # Group layers/basemaps have no dataSource - accessing it raises.
    name = "grouplike"
    isBroken = False

    @property
    def dataSource(self):
        raise AttributeError("no dataSource")


class _ItemIsBrokenRaises:
    name = "weird"
    dataSource = "db.weird"

    @property
    def isBroken(self):
        raise AttributeError("no isBroken")


def test_describe_normal_item():
    result = collect_gis_info._describe("Map1", "roads", _NormalItem())
    assert result == {
        "map": "Map1",
        "layer": "roads",
        "data_source": "db.roads",
        "is_broken": False,
    }


def test_describe_data_source_access_failure_falls_back_to_empty_string():
    result = collect_gis_info._describe("Map1", "grouplike", _ItemDataSourceRaises())
    assert result["data_source"] == ""
    assert result["is_broken"] is False


def test_describe_is_broken_access_failure_falls_back_to_false():
    result = collect_gis_info._describe("Map1", "weird", _ItemIsBrokenRaises())
    assert result["data_source"] == "db.weird"
    assert result["is_broken"] is False


# --- get_layer_inventory() ---


class _FakeLayer:
    def __init__(self, name, is_group=False, data_source="", is_broken=False):
        self.name = name
        self.isGroupLayer = is_group
        self.dataSource = data_source
        self.isBroken = is_broken


class _UnreadableLayer:
    # Simulates a corrupted/broken layer where even attribute access raises.
    # isGroupLayer is accessed outside _describe()'s own try/except, so raising there
    # is what reaches get_layer_inventory's per-layer isolation.
    name = "corrupt_layer"

    @property
    def isGroupLayer(self):
        raise RuntimeError("layer read fail")


class _UnreadableTable:
    # For tables there's no isGroupLayer check - the only access outside _describe()'s
    # own try/except is `table.name` itself, so that's what needs to raise here.
    @property
    def name(self):
        raise RuntimeError("table read fail")


class _FakeMap:
    def __init__(self, name, layers=None, tables=None):
        self.name = name
        self._layers = layers or []
        self._tables = tables or []

    def listLayers(self):
        return self._layers

    def listTables(self):
        return self._tables


class _FakeProject:
    def __init__(self, maps):
        self._maps = maps

    def listMaps(self):
        return self._maps


def _fake_project_factory(maps):
    def factory(aprx_path):
        return _FakeProject(maps)

    return factory


def test_get_layer_inventory_skips_group_layers_and_includes_tables(monkeypatch):
    group_layer = _FakeLayer("group1", is_group=True)
    real_layer = _FakeLayer("roads", data_source="db.roads", is_broken=False)
    map_obj = _FakeMap(
        "Map1",
        layers=[group_layer, real_layer],
        tables=[_FakeLayer("addresses", data_source="db.addresses")],
    )
    monkeypatch.setattr(
        collect_gis_info.arcpy.mp, "ArcGISProject", _fake_project_factory([map_obj])
    )

    entries = collect_gis_info.get_layer_inventory("fake.aprx")

    assert entries == [
        {
            "map": "Map1",
            "layer": "roads",
            "data_source": "db.roads",
            "is_broken": False,
        },
        {
            "map": "Map1",
            "layer": "addresses",
            "data_source": "db.addresses",
            "is_broken": False,
        },
    ]


def test_get_layer_inventory_isolates_one_broken_layer(monkeypatch):
    good_layer = _FakeLayer("roads", data_source="db.roads", is_broken=False)
    broken_layer = _UnreadableLayer()
    map_obj = _FakeMap("Map1", layers=[good_layer, broken_layer])
    monkeypatch.setattr(
        collect_gis_info.arcpy.mp, "ArcGISProject", _fake_project_factory([map_obj])
    )

    entries = collect_gis_info.get_layer_inventory("fake.aprx")

    assert len(entries) == 2
    assert entries[0] == {
        "map": "Map1",
        "layer": "roads",
        "data_source": "db.roads",
        "is_broken": False,
    }
    assert entries[1]["map"] == "Map1"
    assert entries[1]["layer"] == "<unreadable>"
    assert entries[1]["is_broken"] is True
    assert "layer read fail" in entries[1]["error"]


def test_get_layer_inventory_isolates_one_broken_table(monkeypatch):
    good_layer = _FakeLayer("roads", data_source="db.roads")
    broken_table = _UnreadableTable()
    map_obj = _FakeMap("Map1", layers=[good_layer], tables=[broken_table])
    monkeypatch.setattr(
        collect_gis_info.arcpy.mp, "ArcGISProject", _fake_project_factory([map_obj])
    )

    entries = collect_gis_info.get_layer_inventory("fake.aprx")

    assert len(entries) == 2
    assert entries[0]["layer"] == "roads"
    assert entries[1]["layer"] == "<unreadable>"
    assert entries[1]["is_broken"] is True


# --- get_signed_in_account() ---


def test_get_signed_in_account_no_portal_url(monkeypatch):
    monkeypatch.setattr(collect_gis_info.arcpy, "GetActivePortalURL", lambda: "")
    assert collect_gis_info.get_signed_in_account() == "Not signed in"


def test_get_signed_in_account_returns_username(monkeypatch):
    monkeypatch.setattr(
        collect_gis_info.arcpy,
        "GetActivePortalURL",
        lambda: "https://portal.example.com",
    )
    monkeypatch.setattr(
        collect_gis_info.arcpy,
        "GetPortalDescription",
        lambda url: {"user": {"username": "jrosacker"}},
    )
    assert collect_gis_info.get_signed_in_account() == "jrosacker"


def test_get_signed_in_account_unknown_when_user_missing(monkeypatch):
    monkeypatch.setattr(
        collect_gis_info.arcpy,
        "GetActivePortalURL",
        lambda: "https://portal.example.com",
    )
    monkeypatch.setattr(collect_gis_info.arcpy, "GetPortalDescription", lambda url: {})
    assert collect_gis_info.get_signed_in_account() == "Unknown"


# --- main() ---
# Patches the module's own get_signed_in_account/get_layer_inventory rather than arcpy
# internals, so these stay focused on main()'s field-isolation orchestration.


def test_main_happy_path(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["collect_gis_info.py", "good.aprx"])
    monkeypatch.setattr(collect_gis_info, "get_signed_in_account", lambda: "jrosacker")
    monkeypatch.setattr(
        collect_gis_info.arcpy, "GetInstallInfo", lambda: {"Version": "3.2"}
    )
    layers = [
        {"map": "Map1", "layer": "roads", "data_source": "db.roads", "is_broken": False}
    ]
    monkeypatch.setattr(collect_gis_info, "get_layer_inventory", lambda path: layers)

    result = collect_gis_info.main()

    assert result == {
        "aprx_path": "good.aprx",
        "signed_in_account": "jrosacker",
        "software_version": "3.2",
        "python_version": platform.python_version(),
        "layers": layers,
    }


def test_main_isolates_signed_in_account_failure(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["collect_gis_info.py"])

    def raise_signed_in():
        raise RuntimeError("boom - not signed in properly")

    monkeypatch.setattr(collect_gis_info, "get_signed_in_account", raise_signed_in)
    monkeypatch.setattr(
        collect_gis_info.arcpy, "GetInstallInfo", lambda: {"Version": "3.2"}
    )

    result = collect_gis_info.main()

    assert result["signed_in_account"] == "Error: boom - not signed in properly"
    assert result["software_version"] == "3.2"
    assert result["python_version"] == platform.python_version()
    assert result["layers"] == []


def test_main_isolates_software_version_failure(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["collect_gis_info.py"])
    monkeypatch.setattr(collect_gis_info, "get_signed_in_account", lambda: "jrosacker")

    def raise_install_info():
        raise RuntimeError("no license")

    monkeypatch.setattr(collect_gis_info.arcpy, "GetInstallInfo", raise_install_info)

    result = collect_gis_info.main()

    assert result["software_version"] == "Error: no license"
    assert result["signed_in_account"] == "jrosacker"


def test_main_isolates_layers_error_when_project_fails_to_open(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["collect_gis_info.py", "bad.aprx"])
    monkeypatch.setattr(collect_gis_info, "get_signed_in_account", lambda: "jrosacker")
    monkeypatch.setattr(
        collect_gis_info.arcpy, "GetInstallInfo", lambda: {"Version": "3.2"}
    )

    def raise_layers(path):
        raise RuntimeError("cannot open corrupt aprx")

    monkeypatch.setattr(collect_gis_info, "get_layer_inventory", raise_layers)

    result = collect_gis_info.main()

    assert result["layers"] == []
    assert result["layers_error"] == "Failed to open project: cannot open corrupt aprx"
    assert result["signed_in_account"] == "jrosacker"


def test_main_skips_layer_inventory_when_no_aprx_path(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["collect_gis_info.py"])
    monkeypatch.setattr(collect_gis_info, "get_signed_in_account", lambda: "jrosacker")
    monkeypatch.setattr(
        collect_gis_info.arcpy, "GetInstallInfo", lambda: {"Version": "3.2"}
    )
    calls = []

    def spy(path):
        calls.append(path)
        return []

    monkeypatch.setattr(collect_gis_info, "get_layer_inventory", spy)

    result = collect_gis_info.main()

    assert result["layers"] == []
    assert calls == []
