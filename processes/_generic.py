import logging
from pathlib import Path
import argparse
import importlib

from dcpgis import config
from dcpgis import logging as dcp_logging

SETTINGS_FILE_PARENT = Path(__file__).parent.parent / "config"
LOG_FILE_PARENT = Path(__file__).parent.parent / "log"


def get_cli_arguments():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "--process",
        action="store",
        choices=("distribute", "transform"),
        required=True,
        help="Process to initiate (distribute, etc.)",
    )

    arg_parser.add_argument(
        "--env",
        required=True,
        choices=("prod", "dev"),
        action="store",
        help="Used to specify either prod or dev configuration parameters",
    )

    arg_parser.add_argument(
        "--product",
        required=True,
        choices=("pluto", "mih", "template"),
        action="store",
        help="Product to process",
    )

    arg_parser.add_argument(
        "--destination",
        required=True,
        choices=("egdb", "ago", "networklocation"),
        action="store",
        help="Output location of process. Expects a keyword, and not a path",
    )

    return arg_parser.parse_args()


def override_log_level(new_level: str):
    if new_level is not None:
        log_level = getattr(logging, new_level.upper(), logging.INFO)
        logging.getLogger().setLevel(log_level)
        logging.info(
            f"Log level overridden, and set to: {logging.getLevelName(logging.root.getEffectiveLevel())}"
        )


def main():
    args = get_cli_arguments()

    ENVIRONMENT = args.env
    PROCESS = args.process
    PRODUCT = args.product
    DESTINATION = args.destination

    dcp_logging.initialize_logging(
        log_filename=f"{ENVIRONMENT}_{PROCESS}_{PRODUCT}.log",
        log_path=LOG_FILE_PARENT,
    )

    logging.info("{delim} Process Starting {delim}".format(delim="=" * 15))
    logging.info(f"ENVIRONMENT:     {ENVIRONMENT}")
    logging.info(f"PRODUCT:         {PRODUCT}")
    logging.info(f"PROCESS:         {PROCESS}")
    logging.info(f"DESTINATION:     {DESTINATION}")

    primary_config = config.Config(
        app_env=ENVIRONMENT, config_file_path=SETTINGS_FILE_PARENT
    )

    settings = primary_config.get_config_from_yaml()

    logging.info(f"Log level: {logging.getLevelName(logging.root.getEffectiveLevel())}")

    OPEN_DATA_STAGING_PATH = Path(settings["open_data_staging_path"])
    CONNECTION_FILE_PATH = Path(settings["connection_file_path"])
    CONNECTION_FILE_NAME = settings["connection_file_name"]
    LOG_LEVEL_OVERRIDE = settings["log_level_override"]

    override_log_level(new_level=LOG_LEVEL_OVERRIDE)

    logging.debug(settings)

    try:
        process_module = importlib.import_module(args.process)
    except ModuleNotFoundError:
        logging.warning(f"Module {args.process} not found")
        return

    if hasattr(process_module, "run"):
        process_module.run(
            args
        )


if __name__ == "__main__":
    main()
