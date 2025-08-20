import logging
from pathlib import Path
import argparse
import importlib

from dcpgis import config
from dcpgis import logging as dcp_logging

SETTINGS_FILE_PARENT = Path(__file__).parent.parent.parent / "config"
LOG_FILE_PARENT = Path(__file__).parent / "log"

env_choices = ["prod", "dev"]
process_choices = ["ingest", "transform"]

def get_cli_arguments():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "--process",
        action="store",
        choices=process_choices,
        required=True,
        help="Process to initiate (distribute, etc.)",
    )
    
    arg_parser.add_argument(
        "--env",
        required=True,
        choices=env_choices,
        action="store",
        help="Used to specify either prod or dev configuration parameters",
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

    dcp_logging.initialize_logging(
        log_filename=f"{ENVIRONMENT}_zoning.log",
        log_path=LOG_FILE_PARENT,
    )

    logging.info("{delim} Process Starting {delim}".format(delim="=" * 15))
    logging.info(f"ENVIRONMENT:     {ENVIRONMENT}")
    logging.info(f"PROCESS:         {PROCESS}")

    main_config = config.Config(
        app_env=ENVIRONMENT, config_file_path=SETTINGS_FILE_PARENT
    )

    settings = main_config.get_config_from_yaml()

    logging.info(f"Log level: {logging.getLevelName(logging.root.getEffectiveLevel())}")

    LOG_LEVEL_OVERRIDE = settings["log_level_override"]
    override_log_level(new_level=LOG_LEVEL_OVERRIDE)   
    logging.debug(settings)

    module = f"processes.zoning.{args.process}"

    try: 
        process_module = importlib.import_module(module)
    except ModuleNotFoundError:
        logging.warning(f"Module {module} not found")
        return
    if hasattr(process_module, "run"):
        process_module.run(args, settings)

if __name__ == "__main__":
    main()

