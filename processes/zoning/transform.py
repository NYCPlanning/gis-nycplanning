import logging
import arcpy
from pathlib import Path

from dcpgis import config
from dcpgis import logging as dcp_logging

SETTINGS_FILE_PARENT = Path(__file__).parent.parent.parent / "config"
LOG_FILE_PARENT = Path(__file__).parent / "log"

def announce_module(module_name, process, product, destination):
    logging.info(
        f"Hi! This is the {module_name} module, ready to {process.upper()}"
    )

dcp_logging.initialize_logging(
    log_path=LOG_FILE_PARENT,
    log_filename=f"{ENVIRONMENT}_zoning.log",
)

logging.info("Testing logging setup for TRANSFORM zoning process.")
print("log should have occured")

main_config = config.Config(
        app_env=ENVIRONMENT, config_file_path=SETTINGS_FILE_PARENT
    )

settings = config.get_config_from_yaml()
logging.info(f"Log level: {logging.getLevelName(logging.root.getEffectiveLevel())}")