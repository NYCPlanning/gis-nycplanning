import logging
from pathlib import Path
import arcpy

def utils_test():
    logging.debug("Utils test is functioning properly.")

def export_features_using_dict(src: str, dst: str, dict_name: dict, src_key: str, dst_key: str, sql_key:str): 
    for key, value in dict_name.items():
        src_path = str(Path(src) / value[src_key])
        dst_path = str(Path(dst) / value[dst_key])
        sql_query = value[sql_key]

        src_result =  arcpy.management.GetCount(src_path)
        src_count = int(src_result[0])

        arcpy.conversion.ExportFeatures(in_features=src_path,
                                        out_features=dst_path,
                                        where_clause=sql_query)
        
        dst_result = arcpy.management.GetCount(dst_path)
        dst_count = int(dst_result[0])

        if dst_count != src_count:
            logging.debug(f"{value[dst_key]} retained {dst_count} of {src_count} records as a result of SQL expression.")
        
def keep_fields(workspace: str, feature_class: str, keep_fields: list):
    arcpy.env.workspace = workspace
    all_fields = [field.name for field in arcpy.ListFields(feature_class)]
    fields_to_delete = [field for field in all_fields if field not in keep_fields and field != "OBJECTID"]

    if fields_to_delete:
        arcpy.management.DeleteField(in_table=feature_class,
                                     drop_field=fields_to_delete)


def schema_print(path):
    fc_fields=arcpy.ListFields(path)
    
    logging.debug(f"Fields in {path}:")
    for field in fc_fields:
        logging.debug(f"    Field Name: {field.name}, Field Type: {field.type}")