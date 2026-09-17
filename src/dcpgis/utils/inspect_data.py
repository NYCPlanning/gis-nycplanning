from pathlib import Path

import fiona
import pandas as pd

# Maps fiona/OGR field type strings to their Esri/arcpy equivalents, so callers written
# against the old arcpy.ListFields()-based schema keep seeing familiar type names.
_FIONA_TO_ESRI_TYPE = {
    "int": "Integer",
    "int32": "Integer",
    "int64": "Integer64",
    "float": "Double",
    "str": "String",
    "date": "Date",
    "datetime": "Date",
    "time": "Date",
    "bool": "SmallInteger",
    "bytes": "Blob",
}

# OGR treats a dataset's object ID as the feature index rather than a regular schema
# property, so it isn't present in fiona's schema and has to be synthesized here to
# match arcpy's field listing. The conventional name differs by source format.
_OID_FIELD_BY_DRIVER = {
    "OpenFileGDB": "OBJECTID",
    "FileGDB": "OBJECTID",
    "ESRI Shapefile": "FID",
}


def get_dataset_schema(dataset: Path | str, layer: str | None = None) -> pd.DataFrame:
    """Take a path to a vector dataset (shapefile, File Geodatabase feature class, etc.)
    and return a pandas dataframe showing the dataset schema.

    Args:
        dataset (Union[Path, str]): Path to dataset to inspect. For a File Geodatabase,
            this is the path to the .gdb directory; use `layer` to select the feature
            class or table within it.
        layer (Optional[str]): Name of the layer to inspect, required when `dataset`
            contains multiple layers (e.g. a File Geodatabase). Ignored for
            single-layer datasets like shapefiles.

    Returns:
        pd.DataFrame: Dataframe of dataset schema information,
            listing column names, data types, and data lengths. Field lengths are only
            populated for string fields; OGR does not expose Esri's fixed storage
            widths for OID, geometry, date, or numeric fields.
    """
    with fiona.open(dataset, layer=layer) as src:
        properties = src.schema["properties"]
        has_geometry = src.schema["geometry"] not in (None, "None")
        oid_name = _OID_FIELD_BY_DRIVER.get(src.driver, "OID")

    fnames = [oid_name]
    ftypes = ["OID"]
    flength = [None]

    if has_geometry:
        fnames.append("Shape")
        ftypes.append("Geometry")
        flength.append(None)

    for field_name, field_type in properties.items():
        base_type, _, width = field_type.partition(":")
        fnames.append(field_name)
        ftypes.append(_FIONA_TO_ESRI_TYPE.get(base_type, base_type))
        flength.append(int(width.split(".")[0]) if base_type == "str" and width else None)

    return pd.DataFrame(list(zip(fnames, ftypes, flength)), columns=["name", "type", "length"])


def get_record_count_comparison(
    dataset_1: Path | str,
    dataset_2: Path | str,
    layer_1: str | None = None,
    layer_2: str | None = None,
) -> tuple[int, int]:
    """
    Compares the record count of an input dataset to an output dataset.

    Args:
        dataset_1 (Union[Path, str]): Path to the input dataset.
        dataset_2 (Union[Path, str]): Path to the output dataset.
        layer_1 (Optional[str]): Layer name within `dataset_1`, if applicable.
        layer_2 (Optional[str]): Layer name within `dataset_2`, if applicable.

    Returns:
        tuple[int, int]: Record counts for dataset_1 and dataset_2.
    """
    with fiona.open(dataset_1, layer=layer_1) as src_1:
        dataset_1_count = len(src_1)

    with fiona.open(dataset_2, layer=layer_2) as src_2:
        dataset_2_count = len(src_2)

    return dataset_1_count, dataset_2_count
