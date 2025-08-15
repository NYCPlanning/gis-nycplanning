import logging
import arcpy
from pathlib import Path

from dcpgis import config
from dcpgis import logging as dcp_logging

SETTINGS_FILE_PARENT = Path(__file__).parent.parent.parent / "config"
LOG_FILE_PARENT = Path(__file__).parent / "log"

def announce_module(module_name, env, process):
    logging.info(
        f"Hi! This is the {module_name} module, ready to {process.upper()}"
    )

def run(
    args,
    settings: dict,
):
    announce_module(
        module_name=__name__,
        env=args.env, 
        process=args.process,
    )

    print(f"var settings: {settings}")

    LOCAL_STAGING_PATH: Path = Path(settings["local_staging_path"])
    OPEN_DATA_STAGING_PATH: Path = Path(settings["open_data_staging_path"])
    CONNECTION_FILE_PATH: Path = Path(settings["connection_file_path"])
    PRIMARY_CONNECTION_FILE_NAME: str = settings["primary_connection_file_name"]
    TRD_CONNECTION_FILE_NAME: str = settings["trd_connection_file_name"]


    logging.info("Testing logging setup for INGEST zoning process.")
    print("log should have occured")
    
    # Here you would implement the logic for ingesting zoning data
    logging.info(f"Ingesting zoning data from {TRD_CONNECTION_FILE_NAME}")
    # Example of using arcpy to perform some GIS operations
    # arcpy.management.CopyFeatures(...)

    logging.info(f"Log level: {logging.getLevelName(logging.root.getEffectiveLevel())}")

