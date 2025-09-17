import os
import arcpy
import logging
import tempfile
import utils as zoning_utils

from pathlib import Path
from dcpgis.cli import CLI
from dcpgis.utils import config
from dcpgis.utils import logging as dcp_logging
from dcpgis.utils import date_logic
from dcpgis.utils import dir_mgmt
from _naming_convention import ZONING_CONVENTIONS, GEOREF_CONVENTIONS

CONFIG_FILE_PARENT = Path(__file__).parent.parent.parent / "config"
LOG_FILE_PARENT = Path(__file__).parent / "log"

# TODO: Data class exploration (pertenant to field mapping)

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
        app_env=ENVIORNMENT, config_file_path=CONFIG_FILE_PARENT
    )

    settings = main_config.get_config_from_yaml()

    LOG_LEVEL_OVERRIDE = settings["log_level_override"]
    OPEN_DATA_STAGING_PATH: Path = Path(settings["open_data_staging_path"]).absolute()
    CONNECTION_FILE_PATH: Path = Path(settings["connection_file_path"]).absolute()
    PRIMARY_CONNECTION_FILE_NAME: str = settings["primary_connection_file_name"]
    TRD_CONNECTION_FILE_NAME: str = settings["trd_connection_file_name"]
    CYCLE_DATE: str = date_logic.calc_open_data_cycle_month(settings["open_data_cycle_date"])
    
    # Define secondary constants
    TRD_SDE_PATH: Path = Path(CONNECTION_FILE_PATH / TRD_CONNECTION_FILE_NAME)
    TRD_SDE_DZM_PATH: Path = Path(TRD_SDE_PATH / "GISTRD.TRD.Digital_Zoning_Map")
    PRIMARY_SDE_PATH: Path = Path(CONNECTION_FILE_PATH / PRIMARY_CONNECTION_FILE_NAME)
    OPEN_DATA_STAGING_YEAR_PATH: Path = Path(OPEN_DATA_STAGING_PATH / "zoning" / CYCLE_DATE[:4])
    OPEN_DATA_STAGING_CYCLE_PATH: Path = Path(OPEN_DATA_STAGING_YEAR_PATH / CYCLE_DATE)

    dcp_logging.override_log_level(LOG_LEVEL_OVERRIDE)

    COUNCIL_DATE = date_logic.get_latest_date_from_field(
        feature_class_path=str(TRD_SDE_DZM_PATH / ZONING_CONVENTIONS["nyzma"]["trd_full_fc_name"]),
        date_field="EFFECTIVE",
        override_config_value=settings["city_council_date"] #defaults to None if blank in config file
    )

    logging.debug(f"OPEN_DATA_STAGING_PATH: {OPEN_DATA_STAGING_PATH}")
    logging.debug(f"CONNECTION_FILE_PATH: {CONNECTION_FILE_PATH}")
    logging.debug(f"PRIMARY_CONNECTION_FILE_NAME: {PRIMARY_CONNECTION_FILE_NAME}")
    logging.debug(f"TRD_CONNECTION_FILE_NAME: {TRD_CONNECTION_FILE_NAME}")
    logging.debug(f"TRD_SDE_PATH: {TRD_SDE_PATH}")
    logging.debug(f"TRD_SDE_DZM_PATH: {TRD_SDE_DZM_PATH}")
    logging.debug(f"PRIMARY_SDE_PATH: {PRIMARY_SDE_PATH}")
    logging.debug(f"OPEN_DATA_STAGING_CYCLE_PATH: {OPEN_DATA_STAGING_YEAR_PATH}")
    logging.debug(f"OPEN_DATA_STAGING_CYCLE_PATH: {OPEN_DATA_STAGING_CYCLE_PATH}")
    logging.info(f"CYCLE_DATE: {CYCLE_DATE}")
    logging.info(f"COUNCIL_DATE: {COUNCIL_DATE}")

    # Create directory structure
    dir_mgmt.create_dir_if_not_exists(dir_path=OPEN_DATA_STAGING_YEAR_PATH)

    with tempfile.TemporaryDirectory() as temp_dir:
        dir_mgmt.create_cycle_dir_with_subdirs(parent_dir_path=temp_dir, cycle_date=CYCLE_DATE)
        temp_cycle_dir = Path(temp_dir) / CYCLE_DATE
        
        arcpy.management.CreateFileGDB(out_folder_path=os.path.join(temp_cycle_dir, "gdb"),
                                       out_name="zoning.gdb")
        # insert temp processing here

        # Copy temporary cycle directory to open data staging area, overwriting if it already exists
        
        dir_mgmt.copytree_overwrite(src=temp_cycle_dir, dst=OPEN_DATA_STAGING_CYCLE_PATH)
        

    # # TODO: generalize and establish as function
    # for key, value in ZONING_CONVENTIONS.items():

    #     # TODO: make TRD Digitial_Zoning_Map subfolder path a constant
    #     trd_fc_path = str(
    #         Path(TRD_SDE_DZM_PATH / value["trd_full_fc_name"])
    #     )
    #     output_fc_path = str(Path(OPEN_DATA_STAGING_CYCLE_PATH / "gdb" / "nyc_zoning_features.gdb" / value["public_output_name"]))

    #     if arcpy.Exists(trd_fc_path):
    #         logging.info(f"Exporting {value['trd_full_fc_name']} to {output_fc_path}")
    #         arcpy.env.overwriteOutput = True
    #         arcpy.conversion.ExportFeatures(
    #             in_features=trd_fc_path, out_features=output_fc_path
    #         )
    #     else:
    #         logging.error(f"TRD Feature Class does not exist: {value['trd_full_fc_name']}")
    #         continue


if __name__ == "__main__":
    main()
