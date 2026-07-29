import os
import arcpy
import logging
import tempfile
import shutil
import time
import utils as zoning_utils
from arcpy import metadata as md


from pathlib import Path
from datetime import datetime
from dcpgis.cli import CLI
from dcpgis.utils import config
from dcpgis.utils import logging as dcp_logging
from dcpgis.utils import date_logic
from dcpgis.utils import dir_mgmt
from dcpgis.utils import package

from constants import (
    ZONING_CONVENTIONS,
    GEOREF_CONVENTIONS,
    ZONING_PACKAGING,
    ZONING_DATA_DICTS,
    METADATA_XML_VALUES,
)
from dcpgis.constants import OPEN_DATA_SUB_DIRS

CONFIG_FILE_PARENT = Path(__file__).parent.parent.parent / "config"
PRODUCT_CONFIG_FILE_PARENT = Path(__file__).parent / "config"
LOG_FILE_PARENT = Path(__file__).parent / "log"

logger = logging.getLogger(__name__)


def main():
    cli = CLI()
    args = cli.parse_args()

    ENVIRONMENT = args.env

    dcp_logging.initialize_logging(
        log_filename=f"{ENVIRONMENT}_zoning.log",
        log_path=LOG_FILE_PARENT,
    )

    start_time = datetime.now().replace(microsecond=0)
    logger.info("{delim} Process Starting {delim}".format(delim="=" * 15))
    logger.info(f"ENVIRONMENT:     {ENVIRONMENT}")

    # Product Config values
    product_config = config.Config(app_env=ENVIRONMENT, config_file_path=PRODUCT_CONFIG_FILE_PARENT)
    settings_product = product_config.get_config_from_yaml()

    SOURCE_CONNECTION_FILE_NAME: str = settings_product["source_connection_file"]["name"]
    SOURCE_SCHEMA: str = settings_product["source_connection_file"]["schema"]
    DESTINATION_CONNECTION_FILE_NAME: str = settings_product["destination_connection_file"]["name"]

    # Global Config values
    main_config = config.Config(app_env=ENVIRONMENT, config_file_path=CONFIG_FILE_PARENT)

    settings_global = main_config.get_config_from_yaml()

    LOG_LEVEL_OVERRIDE = settings_global["log_level_override"]
    OPEN_DATA_STAGING_PATH: Path = Path(settings_global["open_data_staging_path"]).absolute()
    CONNECTION_FILE_PATH: Path = Path(settings_global["connection_file_path"]).absolute()
    CYCLE_DATE: str = date_logic.calc_open_data_cycle_month(settings_global["open_data_cycle_date"])

    # Define secondary constants
    SOURCE_SDE_PATH: Path = Path(CONNECTION_FILE_PATH / SOURCE_CONNECTION_FILE_NAME)
    source_middle = SOURCE_CONNECTION_FILE_NAME.removeprefix("sde@GIS").removesuffix(".sde")
    SOURCE_SDE_PREFIX: str = f"GIS{source_middle}.{SOURCE_SCHEMA}."
    SOURCE_SDE_DZM_PATH: Path = Path(SOURCE_SDE_PATH / f"{SOURCE_SDE_PREFIX}Digital_Zoning_Map")
    METADATA_STAGING_DIR: Path = Path(OPEN_DATA_STAGING_PATH / "zoning" / "_metadata_staging")
    OPEN_DATA_STAGING_YEAR_PATH: Path = Path(OPEN_DATA_STAGING_PATH / "zoning" / CYCLE_DATE[:4])
    OPEN_DATA_STAGING_CYCLE_PATH: Path = Path(OPEN_DATA_STAGING_YEAR_PATH / CYCLE_DATE)
    XML_TEMPLATES_PATH: Path = Path(__file__).parent / "templates" / "metadata"

    dcp_logging.override_log_level(LOG_LEVEL_OVERRIDE)

    COUNCIL_DATE = date_logic.get_latest_date_from_field(
        feature_class_path=str(
            SOURCE_SDE_DZM_PATH / f"{SOURCE_SDE_PREFIX}{ZONING_CONVENTIONS['nyzma']['trd_fc_name']}"
        ),
        date_field="EFFECTIVE",
        override_config_value=settings_global["city_council_date"],  # defaults to None if blank in config file
    )

    logger.debug(f"OPEN_DATA_STAGING_PATH: {OPEN_DATA_STAGING_PATH}")
    logger.debug(f"CONNECTION_FILE_PATH: {CONNECTION_FILE_PATH}")
    logger.debug(f"SOURCE_CONNECTION_FILE_NAME: {SOURCE_CONNECTION_FILE_NAME}")
    logger.debug(f"DESTINATION_CONNECTION_FILE_NAME: {DESTINATION_CONNECTION_FILE_NAME}")
    logger.debug(f"SOURCE_SDE_PATH: {SOURCE_SDE_PATH}")
    logger.debug(f"SOURCE_SDE_DZM_PATH: {SOURCE_SDE_DZM_PATH}")
    logger.debug(f"OPEN_DATA_STAGING_YEAR_PATH: {OPEN_DATA_STAGING_YEAR_PATH}")
    logger.debug(f"OPEN_DATA_STAGING_CYCLE_PATH: {OPEN_DATA_STAGING_CYCLE_PATH}")
    logger.info(f"XML_TEMPLATES_PATH: {XML_TEMPLATES_PATH}")
    logger.info(f"CYCLE_DATE: {CYCLE_DATE}")
    logger.info(f"COUNCIL_DATE: {COUNCIL_DATE}")

    # Set Environment Parallel Processing (100% = maximum available cores)
    arcpy.env.parallelProcessingFactor = "100%"

    # Create directory structure
    os.makedirs(name=OPEN_DATA_STAGING_YEAR_PATH, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_cycle_dir = Path(temp_dir) / CYCLE_DATE
        dir_mgmt.create_dir_with_subdirs(
            parent_dir_path=temp_cycle_dir,
            sub_dirs=OPEN_DATA_SUB_DIRS,
        )
        assert temp_cycle_dir.exists(), f"Temporary cycle directory {temp_cycle_dir} was not created successfully."

        # Extract all unique geodatabase names from conventions
        GDB_NAMES = set()
        for convention in [ZONING_CONVENTIONS, GEOREF_CONVENTIONS]:
            for info in convention.values():
                GDB_NAMES.add(info["gdb_name"])
        logger.debug(f"The following GDBs referenced in constants.py will be created: {GDB_NAMES}")

        # Create Zoning GeoDatabases
        logger.info("Creating GeoDatabases...")
        for gdb_name in GDB_NAMES:
            arcpy.management.CreateFileGDB(out_folder_path=os.path.join(temp_cycle_dir, "gdb"), out_name=gdb_name)

        # Export zoning fcs to gdb workspace
        logger.info("Exporting zoning features from source ...")
        for feature_info in ZONING_CONVENTIONS.values():
            dst_gdb = os.path.join(temp_cycle_dir, "gdb", feature_info["gdb_name"])
            zoning_utils.export_feature_using_dict(
                src=SOURCE_SDE_DZM_PATH,
                dst=dst_gdb,
                feature_info=feature_info,
                src_prefix=SOURCE_SDE_PREFIX,
                src_key="trd_fc_name",
                dst_key="public_output_name",
                sql_key="sql_expression",
            )

        logger.info("Removing internal-only fields from Feature Classes ...")
        for feature_info in ZONING_CONVENTIONS.values():
            if feature_info["desired_fields"]:
                zoning_utils.drop_fields_from_fc(
                    workspace=os.path.join(temp_cycle_dir, "gdb", feature_info["gdb_name"]),
                    feature_class=feature_info["public_output_name"],
                    keep_fields=feature_info["desired_fields"],
                )

        logger.info("Dissolving Special Districts ... ")
        zoning_utils.dissolve_in_place(
            workspace=os.path.join(temp_cycle_dir, "gdb", ZONING_CONVENTIONS["nysp"]["gdb_name"]),
            feature_class=ZONING_CONVENTIONS["nysp"]["public_output_name"],
            dissolve_field=["SDNAME"],
            statistics_fields=ZONING_CONVENTIONS["nysp"]["statistics_fields"],
        )

        logger.info("Exporting FCs to Shapefiles...")
        for feature_info in ZONING_CONVENTIONS.values():
            src_gdb = os.path.join(temp_cycle_dir, "gdb", feature_info["gdb_name"])
            zoning_utils.export_feature_using_dict(
                src=src_gdb,
                dst=os.path.join(temp_cycle_dir, "shp"),
                feature_info=feature_info,
                src_key="public_output_name",
                dst_key="public_output_name",
                export_as_shapefile=True,
            )

        logger.info("Exporting Zoning Georeferenced Map raster...")
        src_raster_name = SOURCE_SDE_PREFIX + GEOREF_CONVENTIONS["zoning_georeferenced_maps"]["trd_fc_name"]
        src_raster_path = os.path.join(SOURCE_SDE_PATH, src_raster_name)
        dst_raster_gdb = os.path.join(
            temp_cycle_dir,
            "gdb",
            GEOREF_CONVENTIONS["zoning_georeferenced_maps"]["gdb_name"],
        )
        dst_raster_name = GEOREF_CONVENTIONS["zoning_georeferenced_maps"]["public_output_name"]
        dst_raster_path = os.path.join(dst_raster_gdb, dst_raster_name)

        arcpy.env.workspace = dst_raster_path
        arcpy.env.parallelProcessingFactor = "100%"
        arcpy.conversion.RasterToGeodatabase(Input_Rasters=src_raster_path, Output_Geodatabase=dst_raster_gdb)

        arcpy.management.Rename(
            in_data=os.path.join(
                dst_raster_gdb,
                GEOREF_CONVENTIONS["zoning_georeferenced_maps"]["trd_fc_name"],
            ),
            out_data=dst_raster_path,
        )

        # Update metadata XML files and apply them to features according to feature and metadata dictionaries
        logger.info("Updating and applying metadata...")
        for feature_info in ZONING_CONVENTIONS.values():
            # Create feature_metadata dict using static METADATA_XML_VALUES dict updated with feature-specific and
            # cycle-specific values from ZONING_CONVENTIONS;
            # these will be used to update the metadata XML template before importing to features
            feature_metadata = zoning_utils.update_metadata_values(
                base_dict=METADATA_XML_VALUES,
                feature_info=feature_info,
                cycle_date=CYCLE_DATE,
                council_date=date_logic.reformat_date_str_to_written_month(COUNCIL_DATE),
            )

            xml_template_path = XML_TEMPLATES_PATH / f"{feature_info['public_output_name']}.xml"
            updated_xml_path = temp_cycle_dir / "metadata" / f"{feature_info['public_output_name']}.xml"
            fc_path = temp_cycle_dir / "gdb" / feature_info["gdb_name"] / f"{feature_info['public_output_name']}"
            shp_path = temp_cycle_dir / "shp" / f"{feature_info['public_output_name']}.shp"

            fc_path = str(fc_path)
            updated_xml_path = str(updated_xml_path)
            shp_path = str(shp_path)

            # Update XML template with feature-specific and cycle-specific metadata values
            zoning_utils.update_xml_via_dictionary(
                input_xml_path=xml_template_path,
                output_xml_path=updated_xml_path,
                metadata_dict=feature_metadata,
            )

            # Import updated metadata into feature class
            zoning_utils.import_and_clean_feature_metadata(in_feature=fc_path, md_template_file=updated_xml_path)

            # Sync metadata outside of import_and_clean_feature_metadata() to ensure updates are applied correctly. Only for FCs
            item_md = md.Metadata(fc_path)
            item_md.synchronize("ALWAYS")

            # Import updated metadata into shapefile
            zoning_utils.import_and_clean_feature_metadata(in_feature=shp_path, md_template_file=updated_xml_path)

        # Zoning Georeferenced Maps metadata
        """
        TODO: This logic is all very redundant. 
        The only difference for applying metadata to zoning vectors and georef zm is output gdb. 
        Initially I though perhaps gdb name should be part of feature dict and georef and zoning convention dicts could be combined.
        However, incorporating the georef zm into the same dict as the rest of zoning features became overly complicated when I remembered that 
        georef zm source data is not nested within a feature dataset, meaning file name construction doesn't work for both simultaneously.        
        """
        for _, feature_info in GEOREF_CONVENTIONS.value():
            feature_metadata = zoning_utils.update_metadata_values(
                base_dict=METADATA_XML_VALUES,
                feature_info=feature_info,
                cycle_date=CYCLE_DATE,
                council_date=date_logic.reformat_date_str_to_written_month(COUNCIL_DATE),
            )

            xml_template_path = XML_TEMPLATES_PATH / f"{feature_info['public_output_name']}.xml"
            updated_xml_path = temp_cycle_dir / "metadata" / f"{feature_info['public_output_name']}.xml"
            fc_path = temp_cycle_dir / "gdb" / feature_info["gdb_name"] / f"{feature_info['public_output_name']}"

            fc_path = str(fc_path)
            updated_xml_path = str(updated_xml_path)

            # Update XML template with feature-specific and cycle-specific metadata values
            zoning_utils.update_xml_via_dictionary(
                input_xml_path=xml_template_path,
                output_xml_path=updated_xml_path,
                metadata_dict=feature_metadata,
            )

            # Import updated metadata into feature class
            zoning_utils.import_and_clean_feature_metadata(in_feature=fc_path, md_template_file=updated_xml_path)

            # Sync metadata outside of import_and_clean_feature_metadata() to ensure updates are applied correctly. Only for FCs
            item_md = md.Metadata(fc_path)
            item_md.synchronize("ALWAYS")

        logger.info("Packaging data for web distribution...")
        arcpy.ClearWorkspaceCache_management()
        time.sleep(5)
        package.archive_zipping(
            parent_dir=temp_cycle_dir,
            archive_specs=ZONING_PACKAGING,
            output_dir_name="web",
            dangerous_ignore_locks=False,  # Can be set to True if arcpy.ClearWorkspaceCache_management() doesn't work
            product_version=CYCLE_DATE,
        )

        metadata_output_dirs = ["web", "metadata"]
        for dir in metadata_output_dirs:
            package.copy_metadata_to_folder(
                metadata_source_dir=METADATA_STAGING_DIR,
                output_dir=temp_cycle_dir / dir,
                metadata_files=ZONING_DATA_DICTS,
            )

        # Copy temporary cycle directory to open data staging area, overwriting if it already exists
        logger.info("Copying cycle directory to production location ...")
        arcpy.ClearWorkspaceCache_management()
        time.sleep(5)
        shutil.copytree(src=temp_cycle_dir, dst=OPEN_DATA_STAGING_CYCLE_PATH, dirs_exist_ok=True)

        end_time = datetime.now().replace(microsecond=0)
        duration = end_time - start_time
        logger.info("{delim} Runtime: {dur} {delim}\n\n".format(delim="=" * 15, dur=duration))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Process failed")
        raise
