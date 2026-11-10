import logging
from pathlib import Path
import re

import arcpy

from dcpgis.utils.config import Config
from dcpgis.utils.logging import initialize_logging, override_log_level
from processes.mih.bytes_distribute import run_bytes
from processes.mih.sde_distribute import run_sde

# ---------------------------------------------------------------------------
# MIH-specific helpers
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

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    from dcpgis.cli import CLI, DISTRIBUTE_ARGS
    cli = CLI()
    cli.add_arguments(DISTRIBUTE_ARGS)
    args = cli.parse_args()

    global_config = Config(args.env, Path(__file__).parent.parent.parent / "config").get_config_from_yaml()
    mih_config = Config(args.env, Path(__file__).parent / "config").get_config_from_yaml()

    initialize_logging(
        log_path=Path(__file__).parent / "log",
        log_filename=f"{args.env}_mih.log",
    )
    override_log_level(global_config.get("log_level_override"))

    if args.destination == "network_drive":
        run_bytes(global_config, mih_config)
    elif args.destination == "gisprod":
        run_sde(global_config, mih_config)


if __name__ == "__main__":
    main()
