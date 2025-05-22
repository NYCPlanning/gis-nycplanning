from pathlib import Path
from dcpgis import config
from dcpgis import logging

SETTINGS_FILE_PARENT = Path(__file__).parent.parent / "config"
LOG_FILE_PARENT = Path(__file__).parent.parent / "log"
ENVIRONMENT = "dev"
PRODUCT = 'testingonly'

print(config.msg())

logger = logging.set_logger(file=LOG_FILE_PARENT / f"{__name__}_{ENVIRONMENT}_{PRODUCT}.log")

settings = config.Config(
    app_env=ENVIRONMENT, config_file_path=SETTINGS_FILE_PARENT
).get_settings()

logger.info(settings)
