import logging
from pathlib import Path
import arcpy
import os

def utils_test():
    logging.debug("Utils test is functioning properly.")


def get_record_count_comparison(in_feature: str, out_feature: str): 
    in_result=arcpy.management.GetCount(in_feature)
    in_count=int(in_result[0])

    out_result=arcpy.management.GetCount(out_feature)
    out_count=int(out_result[0])

    if out_count != in_count:
        logging.debug(f"Record count of {os.path.basename(out_feature)} changed from {in_count} to {out_count} during processing")


def export_features_using_dict(src: str, dst: str, dict_name: dict, src_key: str, dst_key: str, sql_key:str=None): 
    for key, value in dict_name.items():
        src_path = str(Path(src) / value[src_key])
        dst_path = str(Path(dst) / value[dst_key])

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
            
        
        get_record_count_comparison(in_feature=src_path,
                                    out_feature=dst_path)
        

def keep_fields(workspace: str, feature_class: str, keep_fields: list):
    arcpy.env.workspace = workspace
    all_fields = [field.name for field in arcpy.ListFields(feature_class)]
    fields_to_delete = [field for field in all_fields if field not in keep_fields and field != "OBJECTID"]

    if fields_to_delete:
        arcpy.management.DeleteField(in_table=feature_class,
                                     drop_field=fields_to_delete)

def dissolve_in_place(workspace: str, feature_class: str, dissolve_field: list, statistics_fields: list):
    arcpy.env.workspace = workspace
    arcpy.management.Rename(in_data=feature_class, 
                            out_data=f"{feature_class}_UNDISSOLVED")
    
    
    arcpy.management.Dissolve(in_features=f"{feature_class}_UNDISSOLVED", 
                              out_feature_class=feature_class,
                              dissolve_field=dissolve_field, 
                              statistics_fields=statistics_fields,
                            )
    
    get_record_count_comparison(in_feature=f"{feature_class}_UNDISSOLVED",
                                out_feature=feature_class)
    
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

def schema_print(path):
    fc_fields=arcpy.ListFields(path)
    
    logging.debug(f"Fields in {path}:")
    for field in fc_fields:
        logging.debug(f"    Field Name: {field.name}, Field Type: {field.type}")