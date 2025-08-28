import arcpy
import logging
#import tempfile
# import utils as zoning_utils

from pathlib import Path
from dcpgis.utils import config
from dcpgis.utils import logging as dcp_logging
from dcpgis.cli import CLI

from _naming_convention import ZONING_CONVENTIONS, GEOREF_CONVENTIONS

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_FILE_PARENT = Path (__file__).parent.parent.parent / "config"
LOG_FILE_PARENT = Path (__file__).parent / "log"   

def resolve_path(path_str, base_dir):
    """
    Resolve a path string to an absolute Path object.
    If the path is relative, it is resolved against the provided base directory.
    """
    path = Path(path_str)
    if not path.is_absolute():
        return base_dir / path
    return path

def main():
    cli = CLI()
    args = cli.parse_args()
    
    ENVIORNMENT = args.env

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
    LOG_LEVEL_OVERRIDE = settings["log_level_override"]
    OPEN_DATA_STAGING_PATH: Path = Path(resolve_path(path_str=settings["open_data_staging_path"], 
                                                     base_dir=PROJECT_ROOT))
    CONNECTION_FILE_PATH: Path = Path(resolve_path(path_str=settings["connection_file_path"],
                                                   base_dir=PROJECT_ROOT))
    PRIMARY_CONNECTION_FILE_NAME: str = settings["primary_connection_file_name"]
    TRD_CONNECTION_FILE_NAME: str = settings["trd_connection_file_name"]

    dcp_logging.override_log_level(LOG_LEVEL_OVERRIDE)
    
    logging.debug(f"CITY_COUNCIL_DATE: {CITY_COUNCIL_DATE}")
    logging.debug(f"OPEN_DATA_STAGING_PATH: {OPEN_DATA_STAGING_PATH}")
    logging.debug(f"CONNECTION_FILE_PATH: {CONNECTION_FILE_PATH}")
    logging.debug(f"PRIMARY_CONNECTION_FILE_NAME: {PRIMARY_CONNECTION_FILE_NAME}")
    logging.debug(f"TRD_CONNECTION_FILE_NAME: {TRD_CONNECTION_FILE_NAME}")

    for key, value in ZONING_CONVENTIONS.items():
        trd_fc_name = value["trd_fc_name"]
        public_output_name = value["public_output_name"]

        #TODO: make TRD Digitial_Zoning_Map subfolder path a constant
        trd_fc_path = str(Path(CONNECTION_FILE_PATH) / TRD_CONNECTION_FILE_NAME / 'GISTRD.TRD.Digital_Zoning_Map' / f'GISTRD.TRD.{trd_fc_name}')

        if arcpy.Exists(trd_fc_path):
            logging.info(f"TRD Feature Class exists: {trd_fc_name}")
        else:
            logging.error(f"TRD Feature Class does not exist: {trd_fc_name}")
            continue

if __name__ == "__main__":
    main()
