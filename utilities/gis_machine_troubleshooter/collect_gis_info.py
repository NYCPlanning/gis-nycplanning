"""
Title: Collect GIS-level diagnostic info for the machine troubleshooter
Purpose:
    Runs under the default ArcGIS Pro conda env (arcpy only, no repo package
    dependencies - this script must work standalone on any user's machine).
    Prints a single JSON object to stdout for run_troubleshooter.ps1 to parse.
Usage:
    python collect_gis_info.py [aprx_path]
    aprx_path is optional - project/layer info is skipped when omitted.
Author: J Rosacker
Date: 2025-08-24
"""
import json
import platform
import sys

import arcpy


def get_signed_in_account() -> str:
    portal_url = arcpy.GetActivePortalURL()
    if not portal_url:
        return "Not signed in"
    description = arcpy.GetPortalDescription(portal_url)
    return description.get("user", {}).get("username", "Unknown")


def _describe(map_name: str, name: str, item) -> dict:
    try:
        data_source = item.dataSource
    except Exception:
        # Group layers, basemaps, and similar have no dataSource
        data_source = ""
    try:
        is_broken = item.isBroken
    except Exception:
        is_broken = False
    return {
        "map": map_name,
        "layer": name,
        "data_source": data_source,
        "is_broken": is_broken,
    }


def get_layer_inventory(aprx_path: str) -> list:
    entries = []
    aprx = arcpy.mp.ArcGISProject(aprx_path)
    for map_obj in aprx.listMaps():
        for layer in map_obj.listLayers():
            if layer.isGroupLayer:
                # It's just a container - its children are already listed individually
                continue
            entries.append(_describe(map_obj.name, layer.name, layer))
        for table in map_obj.listTables():
            entries.append(_describe(map_obj.name, table.name, table))
    return entries


def main() -> dict:
    aprx_path = sys.argv[1] if len(sys.argv) > 1 else ""

    result = {
        "signed_in_account": get_signed_in_account(),
        "software_version": arcpy.GetInstallInfo().get("Version"),
        "python_version": platform.python_version(),
        "aprx_path": aprx_path,
        "layers": get_layer_inventory(aprx_path) if aprx_path else [],
    }
    return result


if __name__ == "__main__":
    try:
        output = main()
    except Exception as err:
        output = {"error": str(err)}
    # This must be the only thing written to stdout - the PowerShell caller parses it as JSON.
    print(json.dumps(output))
