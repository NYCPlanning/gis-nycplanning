import logging
from pathlib import Path

import arcpy

from dcpgis.utils.config import Config
from dcpgis.utils.logging import initialize_logging, override_log_level
from processes.mih.bytes_distribute import run_bytes
from processes.mih.bytes_distribute import run_sde

# ---------------------------------------------------------------------------
# MIH-specific helpers
# ---------------------------------------------------------------------------

def find_latest_mih_fc(sde_path: Path) -> tuple[str, str]:
    """Return (version_name, publication_date) for the most recently dated nycmih_YYYYMMDD child version in SDE."""
    ...


def get_city_council_date(sde_path: Path, version_name: str) -> str:
    """Return max(DateAdopte) from DCP_MIH queried against the given SDE version as a YYYYMMDD string."""
    ...


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
