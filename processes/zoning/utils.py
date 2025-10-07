import logging
from pathlib import Path
import arcpy
import os

def utils_test():
    logging.debug("Utils test is functioning properly.")


def get_record_count_comparison(in_feature: str, out_feature: str): 
    """
    Compares the record count of an input feature class to an output feature class and logs a debug message if they differ.
    
    Args:
        in_feature (str): The path to the input feature class.
        out_feature (str): The path to the output feature class.
    """
    in_result=arcpy.management.GetCount(in_feature)
    in_count=int(in_result[0])

    out_result=arcpy.management.GetCount(out_feature)
    out_count=int(out_result[0])

    if out_count != in_count:
        logging.debug(f"Record count of {os.path.basename(out_feature)} changed from {in_count} to {out_count} during processing")


def export_features_using_dict(src: str, dst: str, dict_name: dict, src_key: str, dst_key: str, src_prefix: str= "", sql_key:str=None, export_as_shapefile: bool=False): 
    """
    Exports feature classes from a source to a destination using a dictionary to define parameters. 
    
    Args:
        src (str): The source path where the feature classes are located.   
        dst (str): The destination path where the feature classes will be exported.
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
            
        
        get_record_count_comparison(in_feature=src_path,
                                    out_feature=dst_path)
        

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