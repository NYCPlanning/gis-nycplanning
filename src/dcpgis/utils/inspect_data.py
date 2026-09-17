from dataclasses import dataclass
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


def load_reference_schema(reference: Path | str, layer: str | None = None) -> pd.DataFrame:
    """Load a reference schema to compare a dataset against.

    Args:
        reference (Union[Path, str]): Path to either a CSV with "name", "type", and
            "length" columns, or a vector dataset to inspect with `get_dataset_schema`.
        layer (Optional[str]): Layer name within `reference`, if it is a dataset.

    Returns:
        pd.DataFrame: Reference schema, in the same shape returned by
            `get_dataset_schema`.
    """
    reference = Path(reference)
    if reference.suffix.lower() == ".csv":
        return pd.read_csv(reference)

    return get_dataset_schema(reference, layer=layer)


@dataclass
class SchemaDiff:
    """Result of comparing a test dataset's schema against a reference schema."""

    added_fields: pd.DataFrame
    removed_fields: pd.DataFrame
    changed_fields: pd.DataFrame

    @property
    def is_match(self) -> bool:
        return self.added_fields.empty and self.removed_fields.empty and self.changed_fields.empty

    def __str__(self) -> str:
        if self.is_match:
            return "Schemas match."

        sections = []
        if not self.added_fields.empty:
            sections.append(
                "Fields present in the test dataset but not the reference:\n"
                f"{self.added_fields.to_string(index=False)}"
            )
        if not self.removed_fields.empty:
            sections.append(
                "Fields expected by the reference but missing from the test dataset:\n"
                f"{self.removed_fields.to_string(index=False)}"
            )
        if not self.changed_fields.empty:
            sections.append(
                f"Fields with mismatched type or length:\n{self.changed_fields.to_string(index=False)}"
            )

        return "\n\n".join(sections)


def compare_schema(
    test: Path | str,
    reference: Path | str,
    test_layer: str | None = None,
    reference_layer: str | None = None,
) -> SchemaDiff:
    """Compare a test dataset's schema against a reference schema.

    Args:
        test (Union[Path, str]): Path to the dataset being vetted.
        reference (Union[Path, str]): Path to the known-good schema to compare against;
            either a dataset or a CSV with "name", "type", and "length" columns.
        test_layer (Optional[str]): Layer name within `test`, if applicable.
        reference_layer (Optional[str]): Layer name within `reference`, if it is a
            dataset.

    Returns:
        SchemaDiff: The fields added, removed, and changed relative to the reference
            schema. `SchemaDiff.is_match` is True when the two schemas are identical.
    """
    test_schema = get_dataset_schema(test, layer=test_layer)
    reference_schema = load_reference_schema(reference, layer=reference_layer)

    merged = test_schema.merge(
        reference_schema,
        on="name",
        how="outer",
        suffixes=("_test", "_reference"),
        indicator=True,
    )

    added_fields = (
        merged.loc[merged["_merge"] == "left_only", ["name", "type_test", "length_test"]]
        .rename(columns={"type_test": "type", "length_test": "length"})
        .sort_values("name")
        .reset_index(drop=True)
    )

    removed_fields = (
        merged.loc[merged["_merge"] == "right_only", ["name", "type_reference", "length_reference"]]
        .rename(columns={"type_reference": "type", "length_reference": "length"})
        .sort_values("name")
        .reset_index(drop=True)
    )

    both = merged.loc[merged["_merge"] == "both"].copy()
    type_mismatch = both["type_test"] != both["type_reference"]
    both_lengths_missing = both["length_test"].isna() & both["length_reference"].isna()
    length_mismatch = ~both_lengths_missing & (both["length_test"] != both["length_reference"])

    changed_fields = (
        both.loc[
            type_mismatch | length_mismatch,
            ["name", "type_test", "type_reference", "length_test", "length_reference"],
        ]
        .sort_values("name")
        .reset_index(drop=True)
    )

    return SchemaDiff(added_fields=added_fields, removed_fields=removed_fields, changed_fields=changed_fields)
