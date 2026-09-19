import logging
import os
import zipfile
from pathlib import Path

import arcpy
from arcpy import metadata as md

from dcpgis.utils import inspect_data

logger = logging.getLogger(__name__)


def utils_test():
    logger.debug("Utils test is functioning properly.")


def export_feature_using_dict(
    src: str,
    dst: str,
    feature_info: dict,
    src_key: str,
    dst_key: str,
    src_prefix: str = "",
    sql_key: str = None,
    export_as_shapefile: bool = False,
    drop_global_id: bool = False,
):
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
    """
    src_path = str(Path(src) / f"{src_prefix}{feature_info[src_key]}")
    out_name = feature_info[dst_key] + (".shp" if export_as_shapefile else "")
    dst_path = str(Path(dst) / out_name)

    # Use Field Mapping to drop GlobalID because it can not be deleted using DeleteFields()
    if drop_global_id is True:
        fms = arcpy.FieldMappings()
        fms.addTable(src_path)

        gid_index = fms.findFieldMapIndex("GlobalID")
        if gid_index != 1:
            fms.removeFieldMap(gid_index)
    else:
        fms = None

    if sql_key is None:
        arcpy.conversion.ExportFeatures(
            in_features=src_path,
            out_features=dst_path,
            field_mapping=fms,
        )
    else:
        arcpy.conversion.ExportFeatures(
            in_features=src_path,
            out_features=dst_path,
            where_clause=feature_info[sql_key],
            field_mapping=fms,
        )

    in_count, out_count = inspect_data.get_record_count_comparison(dataset_1=src_path, dataset_2=dst_path)

    if out_count != in_count:
        logger.debug(
            f"Record count of {os.path.basename(dst_path)} changed from {in_count} to {out_count} during processing"
        )


def drop_fields_from_fc(workspace: str, feature_class: str, keep_fields: list):
    """Drops all fields from a feature class except those specified in keep_fields.

    Args:
        workspace (str): The path to the workspace containing the feature class.
        feature_class (str): The name of the feature class from which to drop fields.
        keep_fields (list): A list of field names to retain in the feature class.
    """
    arcpy.env.workspace = workspace
    all_fields = [field.name for field in arcpy.ListFields(feature_class)]
    exceptions = ["OBJECTID", "GlobalID"]
    fields_to_delete = [field for field in all_fields if field not in keep_fields and field not in exceptions]

    if fields_to_delete:
        arcpy.management.DeleteField(in_table=feature_class, drop_field=fields_to_delete)


def dissolve_in_place(workspace: str, feature_class: str, dissolve_field: list, statistics_fields: list[list]):
    """
    Dissolves a feature class in place based on specified fields and statistics.

    Args:
        workspace (str): The path to the workspace containing the feature class.
        feature_class (str): The name of the feature class to be dissolved.
        dissolve_field (list): A list of field names to dissolve on.
        statistics_fields (list[list]): A list of lists that include statistics fields for dissolve. Example: [["Shape_Length", "SUM"], ["Shape_Area", "SUM"]]
    """
    arcpy.env.workspace = workspace
    arcpy.management.Rename(in_data=feature_class, out_data=f"{feature_class}_UNDISSOLVED")

    arcpy.management.Dissolve(
        in_features=f"{feature_class}_UNDISSOLVED",
        out_feature_class=feature_class,
        dissolve_field=dissolve_field,
        statistics_fields=statistics_fields,
    )

    in_count, out_count = inspect_data.get_record_count_comparison(
        dataset_1=f"{feature_class}_UNDISSOLVED", dataset_2=feature_class
    )
    if out_count != in_count:
        logger.debug(f"Record count of {feature_class} changed from {in_count} to {out_count} during processing")

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


def update_metadata_values(base_dict: dict, feature_info: dict, cycle_date: str, council_date: str) -> dict:
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
        "res_title": feature_info["meta_res_title"],
    }

    metadata_values.update(updates)
    return metadata_values


def unpack_dict_into_string_file(input_str_path: str, output_str_path: str, value_dict: dict):
    """
    Updates an string file's elements based on a provided dictionary.

    Args:
        input_str_path (str): Path to the text file template.
        output_str_path (str): Path to the desired text output.
        value_dict (dict): Dictionary containing values to insert.
    """

    # Read the XML as text
    with open(input_str_path, "r") as f:
        str_content = f.read()

    # # Replace placeholders with values
    str_content = str_content.format(**value_dict)
    # Write the modified content
    with open(output_str_path, "w", encoding="utf-8") as f:
        f.write(str_content)


def import_and_clean_feature_metadata(in_feature: str, md_template_file: str):
    """
    Imports metadata from a template into a feature class or shapefile and removes machine-specific information.

    Upgrades metadata to ESRI ISO 19139 format, imports template metadata, removes geoprocessing history,
    and cleans the metadata of machine names before syncing back to the feature class or shapefile.

    Args:
        in_feature (str): Path to the feature class to update with metadata.
        md_template_file (str): Path to the metadata XML template file to import.
    """
    item_md = md.Metadata(in_feature)

    # upgrade md
    item_md.upgrade("ESRI_ISO")

    # import from metadata template
    item_md.importMetadata(
        sourceUri=md_template_file,  # metadata_import_option="ISO19139"
    )

    # # synchronize md (NOTE: doesn't play well w/ template - room for improvement)
    # item_md.synchronize("ALWAYS")
    # logger.debug(f"Synchronizing metadata for {in_feature}")

    # TODO: assign thumbnail from template @ templates\_template_{product}_thumbnail.jpg

    # delete gp etc
    item_md.deleteContent("GPHISTORY")
    logger.debug(f"Deleting GP history from metadata for {in_feature}")

    item_md.save()

    # Overwrite XML with metadata cleaned of machine names
    item_md.saveAsXML(md_template_file, "REMOVE_MACHINE_NAMES")

    # Create metadata object for cleaned XML and copy back to feature
    updated_md = md.Metadata(md_template_file)

    item_md.copy(updated_md)  # copy as opposed to importMetadata prevents paths from being reintroduced
    item_md.save()


# TODO: consider adding decorators for ClearingworkspaseCache_management() + sleep to clear locks
def archive_zipping(
    parent_dir: str,
    archive_specs: dict,
    output_dir_name: str,
    dangerous_ignore_locks: bool = False,
    product_version: str = None,
):
    """
    Creates zip files in a sub-directory as defined in the archive_specs dictionary.

    Expected archive spec dictionary shape:
    {
        "archive_name": {
            "source_dirs": ["source_folder"],
            "content": ["file_one.shp", "file_two.shp.xml"],
            "output_name": "product_package_shp.zip",
            "output_dir": "web",
        }
    }

    Args:
        parent_dir (str or Path): Root directory containing the source folders.
        archive_specs (dict): Mapping of archive definitions, where each entry contains source_dirs, content, output_name, and output_dir.
        output_dir_name (str): Folder where zip files are written.
        dangerous_ignore_locks (bool, optional): if Ture, skips any files with .lock in the name. Default is False. False will raise clear exception when lock is encountered.
        product_version (str, optional): Value used to format output names.

    """
    parent_dir = Path(parent_dir)
    output_dir = parent_dir / output_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)  # redundant but safe

    for archive_name, spec in archive_specs.items():
        source_dirs = spec.get("source_dirs")
        if isinstance(source_dirs, str):
            source_dirs = [source_dirs]

        content = spec.get("content", [])
        if isinstance(content, str):
            content = [content]

        output_name = spec.get("output_name", archive_name)
        if product_version is not None:
            output_name = output_name.format(cycle_date=product_version)

        zip_path = output_dir / output_name
        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for source_dir_name in source_dirs:
                source_dir = parent_dir / source_dir_name
                if not source_dir.exists():
                    logging.warning(f"Source directory {source_dir} does not exist. Skipping.")
                    continue

                for pattern in content:
                    matches = list(source_dir.glob(pattern))
                    if not matches:
                        logging.warning(f"No matches found for pattern '{pattern}' in {source_dir}.")
                        continue

                    for match in matches:
                        if match.is_dir():
                            if match.is_dir():
                                for nested in sorted(match.rglob("*")):
                                    if not nested.is_file():
                                        continue

                                    if ".lock" in nested.name.lower():
                                        if dangerous_ignore_locks:
                                            logging.debug(f"Skipping lock file: {nested}")
                                            continue
                                        raise RuntimeError(
                                            f"Lock file found: {nested}. Set dangerous_ignore_locks=True to skip."
                                        )

                                    zf.write(nested, arcname=nested.relative_to(source_dir))

                        elif match.is_file():
                            if ".lock" in match.name.lower():
                                if dangerous_ignore_locks:
                                    logging.debug(f"Skipping lock file {match}")
                                    continue
                                raise RuntimeError(
                                    f"Lock file found: {match}. Set dangerous_ignore_locks=True to skip."
                                )

                            zf.write(match, arcname=match.relative_to(source_dir))
