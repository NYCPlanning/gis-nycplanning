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

def schema_print(path):
    fc_fields=arcpy.ListFields(path)
    
    logging.debug(f"Fields in {path}:")
    for field in fc_fields:
        logging.debug(f"    Field Name: {field.name}, Field Type: {field.type}")