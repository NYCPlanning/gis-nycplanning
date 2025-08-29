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

def get_latest_date_from_field(feature_class_path: str, date_field: str) -> str:
    """
    Retrieve the latest date from a specified date field in an ArcGIS feature class.

    Args:
        feature_class_path (str): The path to the feature class to search.
        date_field (str): The name of the date field to query for the latest date.

    Returns:
        str: The latest date in YYYYMMDD format, or None if no date is found.
    """
    latest_date = None
    with arcpy.da.SearchCursor(in_table=feature_class_path, field_names=[date_field], 
                               #sql_clause=("TOP 1", f"ORDER BY {date_field} DESC")
                               ) as cursor:
        for row in cursor:
            if row[0] is not None:
                if latest_date is None or row[0] > latest_date:
                    latest_date = row[0]
    return latest_date.strftime("%Y%m%d") if latest_date else None

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

    LOG_LEVEL_OVERRIDE = settings["log_level_override"]
    OPEN_DATA_STAGING_PATH: Path = Path(resolve_path(path_str=settings["open_data_staging_path"], 
                                                     base_dir=PROJECT_ROOT))
    CONNECTION_FILE_PATH: Path = Path(resolve_path(path_str=settings["connection_file_path"],
                                                   base_dir=PROJECT_ROOT))
    PRIMARY_CONNECTION_FILE_NAME: str = settings["primary_connection_file_name"]
    TRD_CONNECTION_FILE_NAME: str = settings["trd_connection_file_name"]
    
    #TODO : Make dynamic 
    CYCLE_DATE: str = "202507"

    dcp_logging.override_log_level(LOG_LEVEL_OVERRIDE)

    logging.debug(f"OPEN_DATA_STAGING_PATH: {OPEN_DATA_STAGING_PATH}")
    logging.debug(f"CONNECTION_FILE_PATH: {CONNECTION_FILE_PATH}")
    logging.debug(f"PRIMARY_CONNECTION_FILE_NAME: {PRIMARY_CONNECTION_FILE_NAME}")
    logging.debug(f"TRD_CONNECTION_FILE_NAME: {TRD_CONNECTION_FILE_NAME}")

    # Append trd_path and output_path to ZONING_CONVENTIONS entries
    for key, value in ZONING_CONVENTIONS.items():
        value["trd_path"] = str(Path(CONNECTION_FILE_PATH / TRD_CONNECTION_FILE_NAME / 'GISTRD.TRD.Digital_Zoning_Map' / f'GISTRD.TRD.{value["trd_fc_name"]}'))
        value["output_shp_path"] = str(Path(OPEN_DATA_STAGING_PATH / "zoning" / CYCLE_DATE[:4] / CYCLE_DATE / 'shp' / value["public_output_name"]))  + ".shp"
        value["output_fc_path"] = str(Path(OPEN_DATA_STAGING_PATH / "zoning" / CYCLE_DATE[:4] / CYCLE_DATE / 'gdb' / 'nyc_zoning_features.gdb' / value["public_output_name"]))

    for key, value in ZONING_CONVENTIONS.items():
        print(f"{key}:")
        for subkey, subvalue in value.items():
            print(f"  {subkey}: {subvalue}")
        print("-" * 30)

    #TODO: generalize and establish as function
    for key, value in ZONING_CONVENTIONS.items():
        trd_fc_name = value["trd_fc_name"]
        trd_fc_path = value["trd_path"]
        public_output_name = value["public_output_name"]

        #TODO: make TRD Digitial_Zoning_Map subfolder path a constant
        trd_fc_path = str(Path(CONNECTION_FILE_PATH) / TRD_CONNECTION_FILE_NAME / 'GISTRD.TRD.Digital_Zoning_Map' / f'GISTRD.TRD.{trd_fc_name}')

        if arcpy.Exists(trd_fc_path):
            logging.info(f"Exporting {trd_fc_name} to {value['output_fc_path']}")
            arcpy.env.overwriteOutput = True
            arcpy.conversion.ExportFeatures(in_features=trd_fc_path,
                                            out_features=value["output_fc_path"])
        else:
            logging.error(f"TRD Feature Class does not exist: {trd_fc_name}")
            continue
    
    council_date = get_latest_date_from_field(
        feature_class_path=ZONING_CONVENTIONS["nyzma"]["trd_path"],
        date_field="EFFECTIVE"
    ) 

    logging.info(f"Latest Council Date found: {council_date}")

if __name__ == "__main__":
    main()
