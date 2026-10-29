import re
from pathlib import Path

import arcpy


# ---------------------------------------------------------------------------
# MIH-specific helpers — shared by bytes_distribute.py and sde_distribute.py
# ---------------------------------------------------------------------------

def find_latest_mih_fc(sde_path: Path) -> tuple[str, str]:
    """Return (version_name, publication_date) for the most recently dated nycmih_YYYYMMDD child version in SDE."""
    versions = arcpy.da.ListVersions(str(sde_path))
    mih_versions = []
    for v in versions:
        name = v.name.split(".")[-1]  # strip owner prefix e.g. "SDE."
        if re.fullmatch(r"nycmih_\d{8}", name):
            mih_versions.append((v.name, name.split("_")[1]))
    if not mih_versions:
        raise ValueError(f"No nycmih_YYYYMMDD versions found in {sde_path}")
    return max(mih_versions, key=lambda x: x[1])  # latest by date string


def get_city_council_date(fc_path: str, version_name: str) -> str:
    """Return max(DateAdopte) from DCP_MIH queried against the given SDE version as a YYYYMMDD string."""
    arcpy.env.workspaceVersion = version_name
    dates = [row[0] for row in arcpy.da.SearchCursor(fc_path, ["DateAdopte"])]
    return max(dates).strftime("%Y%m%d")
