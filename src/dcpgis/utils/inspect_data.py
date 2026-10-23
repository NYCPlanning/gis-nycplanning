from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

import pandas as pd
from osgeo import ogr

# Drivers whose ExecuteSQL("GetLayerDefinition ...") returns the geodatabase's own
# internal schema catalog XML, containing literal esriFieldType* strings.
_GDB_DRIVERS = ("OpenFileGDB", "FileGDB")

# Opt in now to GDAL's exception-based error reporting (ogr.Open() raising instead of
# returning None on failure), which becomes the default in GDAL 4.0.
ogr.UseExceptions()


def _open_layer(dataset: Path | str, layer: str | None) -> tuple[ogr.DataSource, ogr.Layer]:
    """Open a layer, returning its DataSource alongside it. The caller must keep the
    DataSource referenced for as long as the layer is used: GDAL's Python bindings tie
    a Layer's lifetime to its parent DataSource, so if the DataSource is garbage
    collected the layer becomes an invalid ("proxy of None") object.
    """
    try:
        ds = ogr.Open(str(dataset))
    except RuntimeError as exc:
        raise ValueError(f"Could not open dataset: {dataset}") from exc

    lyr = ds.GetLayerByName(layer) if layer else ds.GetLayer(0)
    if lyr is None:
        raise ValueError(f"Could not find layer {layer!r} in dataset: {dataset}")

    return ds, lyr


def _get_gdb_field_definitions(ds: ogr.DataSource, layer_name: str) -> list[dict] | None:
    """Return literal Esri field definitions (name, type, length) for a File Geodatabase
    layer, parsed from its native GetLayerDefinition XML -- the geodatabase's own
    internal schema catalog, not a separate/cacheable metadata document -- in Esri's own
    field order (OID and Shape/geometry included as regular entries, unlike GDAL's
    generic field-defn API where they aren't regular schema properties). Confirmed
    against a live File Geodatabase: the response is a <DEFeatureClassInfo> document
    with fields listed as <GPFieldInfoEx><Name>/<FieldType> elements; it does not carry
    a Length/Precision/Scale value for any field, so length is filled in by the caller.

    Returns None if the XML isn't available or doesn't parse into any fields, so the
    caller can fall back to GDAL's generic field reporting for the whole layer.
    """
    try:
        sql_lyr = ds.ExecuteSQL(f"GetLayerDefinition {layer_name}")
    except RuntimeError:
        return None
    if sql_lyr is None:
        return None

    try:
        feature = sql_lyr.GetNextFeature()
        xml_text = feature.GetField(0) if feature is not None else None
    finally:
        ds.ReleaseResultSet(sql_lyr)

    if not xml_text:
        return None

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return None

    fields = []
    for field_el in root.iter("GPFieldInfoEx"):
        name_el, type_el = field_el.find("Name"), field_el.find("FieldType")
        if name_el is None or type_el is None or not name_el.text or not type_el.text:
            continue
        fields.append({"name": name_el.text, "type": type_el.text.removeprefix("esriFieldType")})

    return fields or None


# Fixed byte-widths for the geodatabase's binary storage format (used only for fields
# sourced from _get_gdb_field_definitions, which doesn't carry a Length for any field --
# confirmed empirically, not a parsing gap). Unlike Esri's field *type* vocabulary
# (which grows over time and is why that translation isn't hardcoded), these are fixed
# byte-widths defined by the geodatabase storage format itself (a Double is always 8
# bytes, an Integer always 4) and have been stable since the format's inception.
# GlobalID/GUID=38 (a "{8-4-4-4-12}" registry-format string, braces included) is the
# documented Esri convention but hasn't been empirically confirmed against a real
# GlobalID/GUID field in this session -- no dataset tested so far has one.
_GDB_FIXED_FIELD_LENGTHS = {
    "OID": 4,
    "SmallInteger": 2,
    "Integer": 4,
    "Single": 4,
    "Double": 8,
    "Date": 8,
    "Geometry": 0,
    "GlobalID": 38,
    "GUID": 38,
}

# For non-GDB sources (shapefiles, or a GDB whose native schema catalog is
# unavailable), only OID/Geometry/Date have a confirmed Esri-fixed length regardless of
# the field's declared DBF width -- confirmed against live arcpy.ListFields() output on
# a real shapefile. Numeric fields (Integer/Single/Double) do NOT get a fixed length
# here: DBF encodes them as ASCII text with a declared, variable digit width, and
# GDAL's own declared width already matches arcpy's reported length exactly (confirmed
# against both real shapefile data and a synthetic arcpy-authored test shapefile) --
# unlike a geodatabase's fixed-width binary storage, there's no type-implied constant
# to prefer here.
_FALLBACK_FIXED_FIELD_LENGTHS = {
    "OID": 4,
    "Geometry": 0,
    "Date": 8,
}


def _normalize_fallback_type(field_type: str, declared_width: int | None) -> str:
    """Narrow GDAL's generic field type names toward arcpy's shapefile-reporting
    conventions. Confirmed against a live, arcpy-authored test shapefile: arcpy never
    distinguishes Short/Long Integer for a shapefile -- always plain "Integer", even
    for a wide field GDAL promotes to "Integer64" -- and narrows "Real" to "Single" or
    "Double" using Esri's documented precision-greater-than-6-digits-means-double
    threshold (a Real field's declared width is precision + 1, confirmed empirically,
    so width > 7 corresponds to precision > 6).
    """
    if field_type == "Integer64":
        return "Integer"
    if field_type == "Real" and declared_width:
        return "Double" if declared_width > 7 else "Single"
    return field_type


def _resolve_fallback_length(field_type: str, declared_width: int | None) -> int | None:
    fixed_length = _FALLBACK_FIXED_FIELD_LENGTHS.get(field_type)
    return fixed_length if fixed_length is not None else (declared_width or None)


def get_dataset_schema(dataset: Path | str, layer: str | None = None) -> pd.DataFrame:
    """Take a path to a vector dataset (shapefile, File Geodatabase feature class, etc.)
    and return a pandas dataframe showing the dataset schema.

    For a File Geodatabase, field types are the literal Esri type names (e.g. "String",
    "Date", "GlobalID"), read from the geodatabase's own internal schema catalog rather
    than a hardcoded translation. For other sources (or if that catalog is unavailable),
    field types fall back to GDAL's own generic type names.

    Args:
        dataset (Union[Path, str]): Path to dataset to inspect. For a File Geodatabase,
            this is the path to the .gdb directory; use `layer` to select the feature
            class or table within it.
        layer (Optional[str]): Name of the layer to inspect, required when `dataset`
            contains multiple layers (e.g. a File Geodatabase). Ignored for
            single-layer datasets like shapefiles.

    Returns:
        pd.DataFrame: Dataframe of dataset schema information,
            listing column names, data types, and data lengths.
    """
    ds, lyr = _open_layer(dataset, layer)

    if ds.GetDriver().GetName() in _GDB_DRIVERS:
        esri_fields = _get_gdb_field_definitions(ds, lyr.GetName())
        if esri_fields is not None:
            defn = lyr.GetLayerDefn()
            ogr_widths = {
                defn.GetFieldDefn(i).GetName(): defn.GetFieldDefn(i).GetWidth()
                for i in range(defn.GetFieldCount())
            }
            for f in esri_fields:
                fixed_length = _GDB_FIXED_FIELD_LENGTHS.get(f["type"])
                f["length"] = fixed_length if fixed_length is not None else (ogr_widths.get(f["name"]) or None)
            return pd.DataFrame(esri_fields, columns=["name", "type", "length"])

    oid_name = lyr.GetFIDColumn() or "FID"

    fnames = [oid_name]
    ftypes = ["OID"]
    flength = [_resolve_fallback_length("OID", None)]

    if lyr.GetGeomType() != ogr.wkbNone:
        fnames.append("Shape")
        ftypes.append("Geometry")
        flength.append(_resolve_fallback_length("Geometry", None))

    defn = lyr.GetLayerDefn()
    for i in range(defn.GetFieldCount()):
        fld = defn.GetFieldDefn(i)
        width = fld.GetWidth()
        field_type = _normalize_fallback_type(ogr.GetFieldTypeName(fld.GetType()), width)
        fnames.append(fld.GetName())
        ftypes.append(field_type)
        flength.append(_resolve_fallback_length(field_type, width))

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
    _ds_1, lyr_1 = _open_layer(dataset_1, layer_1)
    _ds_2, lyr_2 = _open_layer(dataset_2, layer_2)

    return lyr_1.GetFeatureCount(), lyr_2.GetFeatureCount()


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
    reordered_fields: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=["name", "test_position", "reference_position", "shift"])
    )

    @property
    def is_match(self) -> bool:
        return (
            self.added_fields.empty
            and self.removed_fields.empty
            and self.changed_fields.empty
            and self.reordered_fields.empty
        )

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
        if not self.reordered_fields.empty:
            sections.append(f"Fields with changed positions:\n{self.reordered_fields.to_string(index=False)}")

        return "\n\n".join(sections)


def _find_reordered_fields(test_schema: pd.DataFrame, reference_schema: pd.DataFrame) -> pd.DataFrame:
    """Report fields present in both schemas whose 1-based position differs between them."""
    test_names = list(test_schema["name"])
    reference_names = list(reference_schema["name"])
    reference_name_set = set(reference_names)

    test_positions = {name: position for position, name in enumerate(test_names, start=1)}
    reference_positions = {name: position for position, name in enumerate(reference_names, start=1)}

    reordered = [
        {
            "name": name,
            "test_position": test_positions[name],
            "reference_position": reference_positions[name],
            "shift": reference_positions[name] - test_positions[name],
        }
        for name in test_names
        if name in reference_name_set and test_positions[name] != reference_positions[name]
    ]

    return pd.DataFrame(reordered, columns=["name", "test_position", "reference_position", "shift"])


def compare_schema(
    test: Path | str,
    reference: Path | str,
    test_layer: str | None = None,
    reference_layer: str | None = None,
    check_field_order: bool = False,
) -> SchemaDiff:
    """Compare a test dataset's schema against a reference schema.

    Args:
        test (Union[Path, str]): Path to the dataset being vetted.
        reference (Union[Path, str]): Path to the known-good schema to compare against;
            either a dataset or a CSV with "name", "type", and "length" columns.
        test_layer (Optional[str]): Layer name within `test`, if applicable.
        reference_layer (Optional[str]): Layer name within `reference`, if it is a
            dataset.
        check_field_order (bool): When True, also flag fields present in both schemas
            whose position differs between them. Off by default.

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

    reordered_fields = (
        _find_reordered_fields(test_schema, reference_schema)
        if check_field_order
        else pd.DataFrame(columns=["name", "test_position", "reference_position", "shift"])
    )

    return SchemaDiff(
        added_fields=added_fields,
        removed_fields=removed_fields,
        changed_fields=changed_fields,
        reordered_fields=reordered_fields,
    )
