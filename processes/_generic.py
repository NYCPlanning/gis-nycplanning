from pathlib import Path
from dcpgis import config
from dcpgis import logging as dcp_logging
import logging

SETTINGS_FILE_PARENT = Path(__file__).parent.parent / "config"
LOG_FILE_PARENT = Path(__file__).parent.parent / "log"
# TODO: add cli, and remove following constants
ENVIRONMENT = "dev"  # will be provided via cli
PRODUCT = "testingonly"  # will be "pluto", or similar, provided via cli
PROCESS = "generic"  # will be "distribute", or similar, provided via cli

print(config.msg())

dcp_logging.initialize_logging(
    log_filename=f"{ENVIRONMENT}_{PROCESS}_{PRODUCT}.log",
    log_path=LOG_FILE_PARENT,
)

settings = config.Config(
    app_env=ENVIRONMENT, config_file_path=SETTINGS_FILE_PARENT
).get_yaml_settings()

logging.info(settings)

logging.info(f"Log level: {logging.getLevelName(logging.root.getEffectiveLevel())}")

OPEN_DATA_STAGING = settings["open_data_staging"]
CONNECTION_FILE_PATH = settings["connection_file_path"]
ENTERPRISE_GDB = settings["enterprise_gdb"]
LOG_LEVEL_OVERRIDE = settings["log_level_override"]

if LOG_LEVEL_OVERRIDE is not None:
    log_level = getattr(logging, LOG_LEVEL_OVERRIDE.upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)
    logging.info(
        f"Log level overridden, and set to: {logging.getLevelName(logging.root.getEffectiveLevel())}"
    )
