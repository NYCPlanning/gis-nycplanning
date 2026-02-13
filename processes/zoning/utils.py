import logging
from pathlib import Path
import arcpy
import os
import zipfile

from dcpgis.utils import inspect_data
from arcpy import metadata as md

def utils_test():
    logging.debug("Utils test is functioning properly.")

def export_features_using_dict(src: str, dst: str, dict_name: dict, src_key: str, dst_key: str, src_prefix: str= "", sql_key:str=None, export_as_shapefile: bool=False): 
    """
    Exports feature classes from a source to a destination using a dictionary to define parameters. 
    
    Args:
        src (str): The source path where the feature classes are located.   
        dst (str): The destination path where the feature classes will be exported. Destination can be a gdb or dir. If dst is a dir, set export_as_shapefile=True.
        dict_name (dict): A dictionary containing the parameters for each feature class to be exported.
        src_key (str): The key in the dictionary that contains the source feature class name.
        dst_key (str): The key in the dictionary that contains the destination feature class name.  
        src_prefix (str, optional): A prefix to be added to the source feature class names. Defaults to an empty string.
        sql_key (str, optional): The key in the dictionary that contains an optional SQL expression for filtering features during export. Defaults to None.
        export_as_shapefile (bool, optional): If True, exports the features as shapefiles. Defaults to False.
        
    #TODO: Consider making more atomic by removing looping functionality 
    """
    for key, value in dict_name.items():
        src_path = str(Path(src) / f"{src_prefix}{value[src_key]}")
        out_name = value[dst_key] + ".shp" if export_as_shapefile else value[dst_key]
        dst_path = str(Path(dst) / out_name)

        if sql_key is None: 
            arcpy.conversion.ExportFeatures(in_features=src_path,
                                            out_features=dst_path,
                                            )
        else:
            sql_query = value[sql_key]
            arcpy.conversion.ExportFeatures(in_features=src_path,
                                            out_features=dst_path,
                                            where_clause=sql_query
                                            )
            
        
        in_count, out_count = inspect_data.get_record_count_comparison(dataset_1=src_path,
                                                        dataset_2=dst_path)
        
        if out_count != in_count:
            logging.debug(f"Record count of {os.path.basename(dst_path)} changed from {in_count} to {out_count} during processing")

def drop_fields_from_fc(workspace: str, feature_class: str, keep_fields: list):
    """Drops all fields from a feature class except those specified in keep_fields.
    
    Args:
        workspace (str): The path to the workspace containing the feature class.
        feature_class (str): The name of the feature class from which to drop fields.
        keep_fields (list): A list of field names to retain in the feature class.
    """
    arcpy.env.workspace = workspace
    all_fields = [field.name for field in arcpy.ListFields(feature_class)]
    fields_to_delete = [field for field in all_fields if field not in keep_fields and field != "OBJECTID"]

    if fields_to_delete:
        arcpy.management.DeleteField(in_table=feature_class,
                                     drop_field=fields_to_delete)


def dissolve_in_place(workspace: str, feature_class: str, dissolve_field: list, statistics_fields: list):
    """
    Dissolves a feature class in place based on specified fields and statistics. 

    Args:
        workspace (str): The path to the workspace containing the feature class.
        feature_class (str): The name of the feature class to be dissolved.
        dissolve_field (list): A list of field names to dissolve on.
        statistics_fields (list): A list of statistics fields to include in the dissolve operation.
    """
    arcpy.env.workspace = workspace
    arcpy.management.Rename(in_data=feature_class, 
                            out_data=f"{feature_class}_UNDISSOLVED")
    
    arcpy.management.Dissolve(in_features=f"{feature_class}_UNDISSOLVED", 
                              out_feature_class=feature_class,
                              dissolve_field=dissolve_field, 
                              statistics_fields=statistics_fields,
                            )
    
    in_count, out_count = inspect_data.get_record_count_comparison(dataset_1=f"{feature_class}_UNDISSOLVED",
                                                                    dataset_2=feature_class)
    if out_count != in_count:
            logging.debug(f"Record count of {feature_class} changed from {in_count} to {out_count} during processing")
    
    # Drop statistics type prefix from field name to retain original schema
    fields_in_fc = [f.name for f in arcpy.ListFields(feature_class)]
    for field_name in fields_in_fc:
        if "_" in field_name:  # only process prefixed fields
            new_name = field_name.split("_", 1)[1]  # remove everything before first underscore
            arcpy.AlterField_management(
                in_table=feature_class,
                field=field_name,
                new_field_name=new_name,
            )

    arcpy.management.Delete(in_data=f"{feature_class}_UNDISSOLVED")


def web_packaging(parent_dir: str, packaging_dict: dict):
    """
    Creates zip files in the /web folder as defined in the packaging_dict.
    
    Args:
        parent_dir (str or Path): Path to the parent directory containing 'gdb', 'shp', 'web', etc.
        packaging_dict (dict): The ZONING_PACKAGING dictionary.
    """
    parent_dir = Path(parent_dir)
    web_dir = parent_dir / "web"
    web_dir.mkdir(parents=True, exist_ok=True) # redundant but safe

    for zip_key, zip_info in packaging_dict["zip_files"].items():
        zip_name = zip_info["name"]
        src_parent_dir = parent_dir / zip_info["src_parent_dir"]
        contents = zip_info["contents"]

        zip_path = web_dir / zip_name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for pattern in contents:
                for file_path in src_parent_dir.glob(pattern):
                    # Write file to zip, preserving only the filename (not full path)
                    zf.write(file_path, arcname=file_path.name)
        logging.debug(f"Created {zip_name}")


def update_metadata_values(base_dict: dict, feature_info: dict, cycle_date: str, council_date:str) -> dict:
    """
    Creates an updated metadata dictionary for a specific feature.
    
    Args:
        base_dict (dict): Base metadata dictionary with default values
        feature_info (dict): Dictionary containing feature-specific information
        cycle_date (str): Publication date for the dataset
        council_date (str): Council approval date
    
    Returns:
        dict: Updated metadata dictionary for this feature
    """
    metadata_values = base_dict.copy()

    # Update with feature-specific values
    updates = {
        "pub_date": cycle_date if cycle_date else "",
        "council_date": council_date if council_date else "",
        "item_name": feature_info["meta_res_title"],
        "res_title": feature_info["meta_res_title"]
    }

    metadata_values.update(updates)
    return metadata_values    


def update_xml_via_dictionary(input_xml_path: str, output_xml_path: str, metadata_dict: dict):
    """
    Updates an XML file's elements based on a provided dictionary.

    Args:
        input_xml_path (str): Path to the XML file template.
        output_xml_path (str): Path to the desired XML output.
        metadata_dict (dict): Dictionary containing metadata values to insert.
    """
    
    # Read the XML as text
    with open(input_xml_path, 'r') as f:
        xml_content = f.read()

    # TODO: Compare against Alex's implementation of xml updates
    # # Replace placeholders with values
    for key, value in metadata_dict.items():
        placeholder = '{' + key + '}'
        xml_content = xml_content.replace(placeholder, value)

    # Write the modified content
    with open(output_xml_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)


def import_and_clean_feature_metadata(in_feature: str, md_template_file: str):
    """
    Imports metadata from a template into a feature class and removes machine-specific information.
    
    Upgrades metadata to ESRI ISO 19139 format, imports template metadata, removes geoprocessing history,
    and cleans the metadata of machine names before syncing back to the feature class.

    Args:
        in_feature (str): Path to the feature class to update with metadata.
        md_template_file (str): Path to the metadata XML template file to import.
    """
    logging.info(f"Importing and cleaning metadata for {in_feature}")
    item_md = md.Metadata(in_feature)

    # upgrade md
    item_md.upgrade("ESRI_ISO")
    logging.debug(f"Upgrading metadata for {in_feature}")

    # import from metadata template
    item_md.importMetadata(
        sourceUri=md_template_file, #metadata_import_option="ISO19139"
    )
    logging.debug(f"Importing metadata from {md_template_file}")

    # # synchronize md (NOTE: doesn't play well w/ template - room for improvement)
    # item_md.synchronize("ALWAYS")
    # logging.debug(f"Synchronizing metadata for {in_feature}")

    # TODO: assign thumbnail from template @ templates\_template_{product}_thumbnail.jpg

    # delete gp etc
    item_md.deleteContent("GPHISTORY")
    logging.debug(f"Deleting GP history from metadata for {in_feature}")

    item_md.save()

    # Overwrite XML with metadata cleaned of machine names
    item_md.saveAsXML(md_template_file, "REMOVE_MACHINE_NAMES")
    
    # Create metadata object for cleaned XML and copy back to feature
    updated_md = md.Metadata(md_template_file)

    item_md.copy(updated_md) # copy as opposed to importMetadata prevents paths from being reintroduced
    item_md.save()
