import logging
from pathlib import Path
import arcpy

def utils_test():
    logging.debug("Utils test is functioning properly.")

def export_features_using_dict(src: str, dst: str, dict_name: dict, src_key: str, dst_key: str): 
    for key, value in dict_name.items():
        src_path = str(Path(src) / value[src_key])
        dst_path = str(Path(dst) / value[dst_key])

        arcpy.conversion.ExportFeatures(in_features=src_path,
                                        out_features=dst_path)
        
def keep_fields(workspace: str, feature_class: str, keep_fields: list):
    print(feature_class)
    arcpy.env.workspace = workspace
    all_fields = [field.name for field in arcpy.ListFields(feature_class)]
    print(all_fields)
    fields_to_delete = [field for field in all_fields if field not in keep_fields and field != "OBJECTID"]
    print(fields_to_delete)

    if fields_to_delete:
        arcpy.management.DeleteField(in_table=feature_class,
                                     drop_field=fields_to_delete)


def schema_print(path):
    fc_fields=arcpy.ListFields(path)
    
    logging.debug(f"Fields in {path}:")
    for field in fc_fields:
        logging.debug(f"    Field Name: {field.name}, Field Type: {field.type}")