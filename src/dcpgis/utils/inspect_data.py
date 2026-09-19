from pathlib import Path
import pandas as pd
import arcpy
from typing import Union

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

def get_record_count_comparison(dataset_1: str, dataset_2: str) -> int: 
    """
    Compares the record count of an input feature class or shapefile to an output feature class and logs a debug message if they differ.
    
    Args:
        in_feature (str): The path to the input feature class or shapefile.
        out_feature (str): The path to the output feature class or shapefile.
    """
    dataset_1_result=arcpy.management.GetCount(dataset_1)
    dataset_1_count=int(dataset_1_result[0])

    dataset_2_result=arcpy.management.GetCount(dataset_2)
    dataset_2_count=int(dataset_2_result[0])

    return dataset_1_count, dataset_2_count