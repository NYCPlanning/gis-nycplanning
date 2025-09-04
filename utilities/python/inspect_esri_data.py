from pathlib import Path
import pandas as pd
import arcpy
from typing import Union


# TODO - add to dcpgis package
def get_df_of_fc_schema(
    in_fc: Union[Path, str], columns: list = ["name", "type", "length"]
) -> pd.DataFrame:
    """Take a path to an Esri feature class, and return a pandas dataframe
    showing the dataset schema.
    """
    fields = arcpy.ListFields(in_fc)
    fnames = [f.name for f in fields]
    ftypes = [f.type for f in fields]
    flength = [f.length for f in fields]

    return pd.DataFrame(list(zip(fnames, ftypes, flength)), columns=columns)
