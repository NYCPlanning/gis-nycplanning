import logging
from pathlib import Path
import argparse
import importlib

from dcpgis import config
from dcpgis import logging as dcp_logging


def main():
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
            "--app-env",
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

        return arg_parser.parse_args()

    args = get_cli_arguments()

    SETTINGS_FILE_PARENT = Path(__file__).parent.parent / "config"
    LOG_FILE_PARENT = Path(__file__).parent.parent / "log"

    ENVIRONMENT = args.app_env
    PROCESS = args.process
    PRODUCT = args.product

    dcp_logging.initialize_logging(
        log_filename=f"{ENVIRONMENT}_{PROCESS}_{PRODUCT}.log",
        log_path=LOG_FILE_PARENT,
    )

    logging.info("{delim} Process Starting {delim}".format(delim="=" * 15))
    logging.info(f"ENVIRONMENT:     {ENVIRONMENT}")
    logging.info(f"PRODUCT:         {PRODUCT}")
    logging.info(f"PROCESS:         {PROCESS}")

    settings = config.Config(
        app_env=ENVIRONMENT, config_file_path=SETTINGS_FILE_PARENT
    ).get_config_from_yaml()

    logging.info(f"Log level: {logging.getLevelName(logging.root.getEffectiveLevel())}")

    OPEN_DATA_STAGING_PATH = Path(settings["open_data_staging_path"])
    CONNECTION_FILE_PATH = Path(settings["connection_file_path"])
    CONNECTION_FILE_NAME = settings["connection_file_name"]
    LOG_LEVEL_OVERRIDE = settings["log_level_override"]

    if LOG_LEVEL_OVERRIDE is not None:
        log_level = getattr(logging, LOG_LEVEL_OVERRIDE.upper(), logging.INFO)
        logging.getLogger().setLevel(log_level)
        logging.info(
            f"Log level overridden, and set to: {logging.getLevelName(logging.root.getEffectiveLevel())}"
        )

    logging.debug(settings)

    try:
        process_module = importlib.import_module(args.process)
    except ModuleNotFoundError:
        logging.warning(f"Module {args.process} not found")
        return
    
    if hasattr(process_module, "run"):
        process_module.run(process=args.process, product=args.product)


if __name__ == "__main__":
    main()
