from pathlib import Path

import arcpy
import pandas as pd


# TODO - add to dcpgis package
def get_dataset_schema(dataset: Path | str) -> pd.DataFrame:
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
        list(zip(fnames, ftypes, flength, strict=True)), columns=["name", "type", "length"]
    )
