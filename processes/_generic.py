import logging
from pathlib import Path
from typing import Union

from dcpgis import config
from dcpgis import logging as dcp_logging

SETTINGS_FILE_PARENT = Path(__file__).parent.parent / "config"
LOG_FILE_PARENT = Path(__file__).parent.parent / "log"
# TODO: add cli, and remove following constants
ENVIRONMENT = "dev"  # will be provided via cli
PRODUCT = "testingonly"  # will be "pluto", or similar, provided via cli
PROCESS = "generic"  # will be "distribute", or similar, provided via cli


dcp_logging.initialize_logging(
    log_filename=f"{ENVIRONMENT}_{PROCESS}_{PRODUCT}.log",
    log_path=LOG_FILE_PARENT,
)

logging.info("{delim} Process Starting {delim}".format(delim="=" * 15))
logging.info(f"ENVIRONMENT: {ENVIRONMENT}")
logging.info(f"PRODUCT:     {PRODUCT}")
logging.info(f"PROCESS:     {PROCESS}")

settings = config.Config(
    app_env=ENVIRONMENT, config_file_path=SETTINGS_FILE_PARENT
).get_config_from_yaml()

logging.info(f"Log level: {logging.getLevelName(logging.root.getEffectiveLevel())}")

OPEN_DATA_STAGING_PATH: Path = Path(settings["open_data_staging_path"])
CONNECTION_FILE_PATH: Path = Path(settings["connection_file_path"])
CONNECTION_FILE_NAME: str = settings["connection_file_name"]
LOG_LEVEL_OVERRIDE: Union[str, None] = settings["log_level_override"]

if LOG_LEVEL_OVERRIDE is not None:
    log_level = getattr(logging, LOG_LEVEL_OVERRIDE.upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)
    logging.info(
        f"Log level overridden, and set to: {logging.getLevelName(logging.root.getEffectiveLevel())}"
    )

logging.debug(settings)
