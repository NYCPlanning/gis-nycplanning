import os
import arcpy
import logging
import tempfile
import shutil
import utils as zoning_utils
from arcpy import metadata as md

from pathlib import Path
from datetime import datetime
from dcpgis.cli import CLI
from dcpgis.utils import config
from dcpgis.utils import logging as dcp_logging
from dcpgis.utils import date_logic
from dcpgis.utils import dir_mgmt

from constants import ZONING_CONVENTIONS, GEOREF_CONVENTIONS, ZONING_PACKAGING, METADATA_XML_VALUES
from dcpgis.constants import OPEN_DATA_SUB_DIRS

CONFIG_FILE_PARENT = Path(__file__).parent.parent.parent / "config"
PRODUCT_CONFIG_FILE_PARENT = Path(__file__).parent / "config"
LOG_FILE_PARENT = Path(__file__).parent / "log"

# TODO: Update NYZMA metadata to no longer include "since 2002" language

def main():
    cli = CLI()
    args = cli.parse_args()

    ENVIRONMENT = args.env

    dcp_logging.initialize_logging(
        log_filename=f"{ENVIRONMENT}_zoning.log",
        log_path=LOG_FILE_PARENT,
    )

    start_time = datetime.now().replace(microsecond=0)
    logging.info("{delim} Process Starting {delim}".format(delim="=" * 15))
    logging.info(f"ENVIRONMENT:     {ENVIRONMENT}")

    # Product Config values
    product_config = config.Config(
        app_env=ENVIRONMENT, config_file_path=PRODUCT_CONFIG_FILE_PARENT
    )
    settings = product_config.get_config_from_yaml()

    SOURCE_CONNECTION_FILE_NAME: str = settings["source_connection_file"]["name"]
    SOURCE_SCHEMA: str = settings["source_connection_file"]["schema"]
    DESTINATION_CONNECTION_FILE_NAME: str = settings["destination_connection_file"]["name"]
    DESTINATION_SCHEMA: str = settings["destination_connection_file"]["schema"]
    
    # Global Config values
    main_config = config.Config(
        app_env=ENVIRONMENT, config_file_path=CONFIG_FILE_PARENT
    )

    settings = main_config.get_config_from_yaml()

    LOG_LEVEL_OVERRIDE = settings["log_level_override"]
    OPEN_DATA_STAGING_PATH: Path = Path(settings["open_data_staging_path"]).absolute()
    CONNECTION_FILE_PATH: Path = Path(settings["connection_file_path"]).absolute()
    CYCLE_DATE: str = date_logic.calc_open_data_cycle_month(settings["open_data_cycle_date"])
    
    # Define secondary constants
    SOURCE_SDE_PATH: Path = Path(CONNECTION_FILE_PATH / SOURCE_CONNECTION_FILE_NAME)
    source_middle = SOURCE_CONNECTION_FILE_NAME.removeprefix("sde@GIS").removesuffix(".sde")
    SOURCE_SDE_PREFIX: str = f"GIS{source_middle}.{SOURCE_SCHEMA}."
    SOURCE_SDE_DZM_PATH: Path = Path(SOURCE_SDE_PATH / f"{SOURCE_SDE_PREFIX}Digital_Zoning_Map")
    DESTINATION_SDE_PATH: Path = Path(CONNECTION_FILE_PATH / DESTINATION_CONNECTION_FILE_NAME)
    dest_middle = DESTINATION_CONNECTION_FILE_NAME.removeprefix("sde@GIS").removesuffix(".sde")
    DESTINATION_SDE_PREFIX: str = f"GIS{dest_middle}.{DESTINATION_SCHEMA}."
    OPEN_DATA_STAGING_YEAR_PATH: Path = Path(OPEN_DATA_STAGING_PATH / "zoning" / CYCLE_DATE[:4])
    OPEN_DATA_STAGING_CYCLE_PATH: Path = Path(OPEN_DATA_STAGING_YEAR_PATH / CYCLE_DATE)
    XML_TEMPLATES_PATH: Path = Path(__file__).parent / "templates" / "metadata"

    dcp_logging.override_log_level(LOG_LEVEL_OVERRIDE)

    COUNCIL_DATE = date_logic.get_latest_date_from_field(
        feature_class_path=str(SOURCE_SDE_DZM_PATH / f"{SOURCE_SDE_PREFIX}{ZONING_CONVENTIONS['nyzma']['trd_fc_name']}"),
        date_field="EFFECTIVE",
        override_config_value=settings["city_council_date"] #defaults to None if blank in config file
    )

    logging.debug(f"OPEN_DATA_STAGING_PATH: {OPEN_DATA_STAGING_PATH}")
    logging.debug(f"CONNECTION_FILE_PATH: {CONNECTION_FILE_PATH}")
    logging.debug(f"SOURCE_CONNECTION_FILE_NAME: {SOURCE_CONNECTION_FILE_NAME}")
    logging.debug(f"DESTINATION_CONNECTION_FILE_NAME: {DESTINATION_CONNECTION_FILE_NAME}")
    logging.debug(f"SOURCE_SDE_PATH: {SOURCE_SDE_PATH}")
    logging.debug(f"SOURCE_SDE_DZM_PATH: {SOURCE_SDE_DZM_PATH}")
    logging.debug(f"DESTINATION_SDE_PATH: {DESTINATION_SDE_PATH}")
    logging.debug(f"OPEN_DATA_STAGING_YEAR_PATH: {OPEN_DATA_STAGING_YEAR_PATH}")
    logging.debug(f"OPEN_DATA_STAGING_CYCLE_PATH: {OPEN_DATA_STAGING_CYCLE_PATH}")
    logging.info(f"XML_TEMPLATES_PATH: {XML_TEMPLATES_PATH}")
    logging.info(f"CYCLE_DATE: {CYCLE_DATE}")
    logging.info(f"COUNCIL_DATE: {COUNCIL_DATE}")

    # Create directory structure
    os.makedirs(name=OPEN_DATA_STAGING_YEAR_PATH,
                exist_ok=True)

    # Set Environment Parallel Processing (100% = maximum available cores)
    arcpy.env.parallelProcessingFactor = "100%"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_cycle_dir = Path(temp_dir) / CYCLE_DATE
        dir_mgmt.create_dir_with_subdirs(parent_dir_path=temp_cycle_dir, 
                                        sub_dirs=OPEN_DATA_SUB_DIRS,
                                        )
        
        # Create Zoning GeoDatabases
        logging.info("Creating GeoDatabases...")
        arcpy.management.CreateFileGDB(out_folder_path=os.path.join(temp_cycle_dir, "gdb"),
                                       out_name="nyc_zoning_features.gdb")
        arcpy.management.CreateFileGDB(out_folder_path=os.path.join(temp_cycle_dir, "gdb"),
                                      out_name="nyc_georeferenced_zoning_maps.gdb")
        
        # Set workspace
        arcpy.env.workspace = os.path.join(temp_cycle_dir, 'gdb', 'nyc_zoning_features.gdb')

        #TODO: turn gdb_name into a variable earlier in processes
        # Export zoning fcs to gdb workspace
        logging.info("Exporting zoning features from source ...")
        zoning_utils.export_features_using_dict(src=SOURCE_SDE_DZM_PATH,
                                                dst=os.path.join(temp_cycle_dir, "gdb", "nyc_zoning_features.gdb"),
                                                dict_name=ZONING_CONVENTIONS,
                                                src_prefix=SOURCE_SDE_PREFIX,
                                                src_key="trd_fc_name",
                                                dst_key="public_output_name",
                                                sql_key="sql_expression")
        
        #TODO: decide on whether to alter/remove field aliases (not present in current gdb ouputs)
        logging.info("Removing internal-only fields from Feature Classes ...")
        for _, zoning_value in ZONING_CONVENTIONS.items():    
            if zoning_value["desired_fields"]:
                zoning_utils.drop_fields_from_fc(workspace=os.path.join(temp_cycle_dir, 'gdb', 'nyc_zoning_features.gdb'),
                                         feature_class=zoning_value["public_output_name"],
                                         keep_fields=zoning_value["desired_fields"]
                                         )      
                
        logging.info("Dissolving Special Districts ... ")
        zoning_utils.dissolve_in_place(workspace=os.path.join(temp_cycle_dir, 'gdb', 'nyc_zoning_features.gdb'),
                                       feature_class=ZONING_CONVENTIONS["nysp"]["public_output_name"],
                                       dissolve_field=["SDNAME"],
                                       statistics_fields=ZONING_CONVENTIONS["nysp"]["statistics_fields"]
                                       )

        logging.info("Exporting FCs to Shapefiles...")
        zoning_utils.export_features_using_dict(src=os.path.join(temp_cycle_dir, "gdb", "nyc_zoning_features.gdb"),
                                                dst=os.path.join(temp_cycle_dir, "shp"),
                                                dict_name=ZONING_CONVENTIONS, 
                                                src_key="public_output_name",
                                                dst_key="public_output_name",
                                                export_as_shapefile=True
                                                )

        logging.info("Exporting Georeferenced Zoning Map raster...")
        arcpy.env.workspace = os.path.join(temp_cycle_dir, 'gdb', 'nyc_georeferenced_zoning_maps.gdb')
        src_raster_path = os.path.join(SOURCE_SDE_PATH, GEOREF_CONVENTIONS["georeferenced_zoning_maps"]["trd_fc_name"])
        dst_raster_path = os.path.join(temp_cycle_dir, "gdb", "nyc_georef_zm") #File name hardcoded because CopyRaster() 13 char limit; renamed to final name in next step after export
        final_raster_name = os.path.join(GEOREF_CONVENTIONS["georeferenced_zoning_maps"]["public_output_name"])
        arcpy.management.CopyRaster(in_raster=src_raster_path,
                                    out_rasterdataset=dst_raster_path
                                    )
        arcpy.management.Rename(dst_raster_path, final_raster_name)

 # Update metadata XML files and apply to features according to feature and metadata dictionaries
        logging.info("Updating and applying metadata...")
        for _, feature_info in ZONING_CONVENTIONS.items():
            
            # Create feature_metadata dict using static METADATA_XML_VALUES dict updated with feature-specific and cycle-specific values from ZONING_CONVENTIONS; these will be used to update the metadata XML template before importing to features
            feature_metadata = zoning_utils.update_metadata_values(
                base_dict=METADATA_XML_VALUES,
                feature_info=feature_info,
                cycle_date=CYCLE_DATE,
                council_date=date_logic.reformat_date_str_to_written_month(COUNCIL_DATE)
            )
            
            xml_template_path = XML_TEMPLATES_PATH / f"{feature_info['public_output_name']}.xml"
            updated_xml_path = temp_cycle_dir / "metadata" / f"{feature_info['public_output_name']}.xml"
            fc_path = temp_cycle_dir / "gdb" / "nyc_zoning_features.gdb" / f"{feature_info['public_output_name']}"
            shp_path = temp_cycle_dir / "shp" / f"{feature_info['public_output_name']}.shp"

            fc_path = str(fc_path)
            updated_xml_path = str(updated_xml_path)
            shp_path = str(shp_path)

            # Update XML template with feature-specific and cycle-specific metadata values 
            zoning_utils.update_xml_via_dictionary(
                input_xml_path=xml_template_path,
                output_xml_path=updated_xml_path,
                metadata_dict=feature_metadata
            )

            # Import updated metadata into feature class
            zoning_utils.import_and_clean_feature_metadata(in_feature=fc_path,
                                                            md_template_file=updated_xml_path)
            
            # Sync metadata outside of import_and_clean_feature_metadata() to ensure updates are applied correctly. Only for FCs
            item_md = md.Metadata(fc_path)
            item_md.synchronize("ALWAYS")
            
            # Import updated metadata into shapefile
            zoning_utils.import_and_clean_feature_metadata(in_feature=shp_path,
                                                            md_template_file=updated_xml_path)

        # Georeferenced Zoning Maps metadata
        '''
        TODO: This logic is all very redundant. 
        The only difference for applying metadata to zoning vectors and georef zm is output gdb. 
        Initially I though perhaps gdb name should be part of feature dict and georef and zoning convention dicts could be combined.
        However, incorporating the georef zm into the same dict as the rest of zoning features became overly complicated when I remembered that 
        georef zm source data is not nested within a feature dataset, meaning file name construction doesn't work for both simultaneously.        
        '''
        for _, feature_info in GEOREF_CONVENTIONS.items():    
            feature_metadata = zoning_utils.update_metadata_values(
                base_dict=METADATA_XML_VALUES,
                feature_info=feature_info,
                cycle_date=CYCLE_DATE,
                council_date=date_logic.reformat_date_str_to_written_month(COUNCIL_DATE)
            )

            xml_template_path = XML_TEMPLATES_PATH / f"{feature_info['public_output_name']}.xml"
            updated_xml_path = temp_cycle_dir / "metadata" / f"{feature_info['public_output_name']}.xml"
            fc_path = temp_cycle_dir / "gdb" / "nyc_georeferenced_zoning_maps.gdb" / f"{feature_info['public_output_name']}"
                                            
            fc_path = str(fc_path)
            updated_xml_path = str(updated_xml_path)

            # Update XML template with feature-specific and cycle-specific metadata values 
            zoning_utils.update_xml_via_dictionary(
                input_xml_path=xml_template_path,
                output_xml_path=updated_xml_path,
                metadata_dict=feature_metadata
            )

            # Import updated metadata into feature class
            zoning_utils.import_and_clean_feature_metadata(in_feature=fc_path,
                                                            md_template_file=updated_xml_path)
            
            # Sync metadata outside of import_and_clean_feature_metadata() to ensure updates are applied correctly. Only for FCs
            item_md = md.Metadata(fc_path)
            item_md.synchronize("ALWAYS")

        # Not including yet-to-be-produced data dictionaries
        logging.info("Packaging data for web distribution...")
        zoning_utils.web_packaging(parent_dir=temp_cycle_dir,
                                   packaging_dict=ZONING_PACKAGING
                                   )

        # Copy temporary cycle directory to open data staging area, overwriting if it already exists
        logging.info("Copying cycle directory to production location ...")
        shutil.copytree(src=temp_cycle_dir, dst=OPEN_DATA_STAGING_CYCLE_PATH, dirs_exist_ok=True)

        end_time = datetime.now().replace(microsecond=0)
        duration = end_time - start_time
        logging.info('{delim} Runtime: {dur} {delim}\n\n'.format(delim='='*15,dur=duration))

if __name__ == "__main__":
    main()
