
import arcpy
import logging

from pathlib import Path
from dcpgis import config
from dcpgis import logging as dcp_logging
#from dcpgis.cli import CLI

CONFIG_FILE_PARENT = Path (__file__).parent.parent.parent / "config"
LOG_FILE_PARENT = Path (__file__).parent / "log"   
print(f"SETTINGS_FILE_PARENT: {CONFIG_FILE_PARENT}")
print(f"LOG_FILE_PARENT: {LOG_FILE_PARENT}")

#TODO: reinstate CLI functionality once jcr-issue9 merged to main
def main():
    #cli = CLI()
    #args = cli.parse_args()
    
    #ENVIORNMENT = args.env
    ENVIORNMENT = "dev"

    dcp_logging.initialize_logging(
        log_filename=f"{ENVIORNMENT}_zoning.log",
        log_path=LOG_FILE_PARENT,
        )
    
    logging.info("{delim} Process Starting {delim}".format(delim="=" * 15))
    logging.info(f"ENVIRONMENT:     {ENVIORNMENT}")

    main_config = config.Config(
        app_env=ENVIORNMENT, 
        config_file_path=CONFIG_FILE_PARENT
    )

    settings = main_config.get_config_from_yaml()

    CITY_COUNCIL_DATE = settings["city_council_date"]
    OPEN_DATA_STAGING_PATH: Path = Path(settings["open_data_staging_path"])
    CONNECTION_FILE_PATH: Path = Path(settings["connection_file_path"])
    PRIMARY_CONNECTION_FILE_NAME: str = settings["primary_connection_file_name"]
    TRD_CONNECTION_FILE_NAME: str = settings["trd_connection_file_name"]

    logging.info(f"CITY_COUNCIL_DATE: {CITY_COUNCIL_DATE}")
    logging.info(f"OPEN_DATA_STAGING_PATH: {OPEN_DATA_STAGING_PATH}")
    logging.info(f"CONNECTION_FILE_PATH: {CONNECTION_FILE_PATH}")
    logging.info(f"PRIMARY_CONNECTION_FILE_NAME: {PRIMARY_CONNECTION_FILE_NAME}")
    logging.info(f"TRD_CONNECTION_FILE_NAME: {TRD_CONNECTION_FILE_NAME}")
    
if __name__ == "__main__":
    main()
