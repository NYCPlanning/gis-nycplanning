from pathlib import Path
import pandas as pd
import arcpy
from typing import Union


# TODO - add to dcpgis package
def get_dataset_schema(dataset: Union[Path, str]) -> pd.DataFrame:
    """Take a path to an Esri feature class or shapefile, and return a pandas dataframe
    showing the dataset schema.

    Args:
        dataset (Union[Path, str]): Path to dataset to inspect. Can be a feature class
            or shapefile.

    Returns:
        pd.DataFrame: Dataframe of dataset schema information,
            listing column names, data types, and data lengths.
    """
    fields = arcpy.ListFields(dataset)
    fnames = [f.name for f in fields]
    ftypes = [f.type for f in fields]
    flength = [f.length for f in fields]

    return pd.DataFrame(
        list(zip(fnames, ftypes, flength)), columns=["name", "type", "length"]
    )

def get_record_count_comparison(in_feature: str, out_feature: str) -> int: 
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

    return in_count, out_count