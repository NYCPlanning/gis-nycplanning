import os
import shutil
import zipfile

import pandas as pd
from osgeo import ogr
from pandas.testing import assert_frame_equal
from pytest import fixture

from dcpgis.utils import inspect_data

GDB_ZIP = "geodatabase_zoning_data.zip"
SHP_ZIP = "shapefile_nyzd_one_row.zip"


@fixture
def temp_shp_zip(resources_path, tmp_path):
    shutil.copy2(
        src=resources_path / SHP_ZIP,
        dst=tmp_path / SHP_ZIP,
    )
    assert zipfile.is_zipfile(tmp_path / SHP_ZIP), f"'{SHP_ZIP}' should be a valid zip file"
    return tmp_path / SHP_ZIP


@fixture
def temp_shp_nonzipped(temp_shp_zip, tmp_path):
    shutil.unpack_archive(filename=temp_shp_zip, extract_dir=tmp_path)
    shp_path = tmp_path / (temp_shp_zip.stem + ".shp")
    assert shp_path.is_file(), "Expected a shapefile, but found none"
    return shp_path


@fixture
def temp_gdb_zip(resources_path, tmp_path):
    shutil.copy2(
        src=resources_path / GDB_ZIP,
        dst=tmp_path / GDB_ZIP,
    )
    assert zipfile.is_zipfile(tmp_path / GDB_ZIP), f"'{GDB_ZIP}' should be a valid zip file"
    return tmp_path / GDB_ZIP


@fixture
def temp_gdb_nonzipped(temp_gdb_zip, tmp_path):
    shutil.unpack_archive(filename=temp_gdb_zip, extract_dir=tmp_path)
    gdb_path = (tmp_path / temp_gdb_zip.stem).with_suffix(".gdb")
    assert os.path.exists(gdb_path), "Expected a gdb, but found none"
    return gdb_path


def test_get_gdb_schema(temp_gdb_nonzipped):
    # Confirmed field-by-field against live arcpy.ListFields() output for this exact
    # fixture (and separately against a real production dataset, MapPLUTO) -- literal
    # Esri type names and lengths, not GDAL's generic vocabulary.
    expected_schema = pd.DataFrame(
        {
            "name": [
                "OBJECTID",
                "Shape",
                "ZONEDIST",
                "DT_ADDED",
                "SOURCE",
                "Boro_nm",
                "DT_EDITED",
                "EDITOR",
                "Shape_Length",
                "Shape_Area",
            ],
            "type": [
                "OID",
                "Geometry",
                "String",
                "Date",
                "String",
                "String",
                "Date",
                "String",
                "Double",
                "Double",
            ],
            "length": [4, 0, 15, 8, 50, 50, 8, 50, 8, 8],
        }
    )

    actual_schema = inspect_data.get_dataset_schema(temp_gdb_nonzipped, layer="nyzd_one_row")

    assert_frame_equal(expected_schema, actual_schema)


def test_get_gdb_schema_falls_back_when_native_xml_is_unavailable(temp_gdb_nonzipped, monkeypatch):
    # When the geodatabase's native schema catalog can't be read (older/non-standard
    # GDB, or a request that legitimately fails), get_dataset_schema should still work
    # via GDAL's generic field reporting rather than raising.
    monkeypatch.setattr(inspect_data, "_get_gdb_field_definitions", lambda ds, layer_name: None)

    schema = inspect_data.get_dataset_schema(temp_gdb_nonzipped, layer="nyzd_one_row")

    assert list(schema["name"]) == [
        "OBJECTID",
        "Shape",
        "ZONEDIST",
        "DT_ADDED",
        "SOURCE",
        "Boro_nm",
        "DT_EDITED",
        "EDITOR",
        "Shape_Length",
        "Shape_Area",
    ]
    by_name = schema.set_index("name")
    assert by_name.loc["OBJECTID", "type"] == "OID"
    assert by_name.loc["Shape", "type"] == "Geometry"
    assert by_name.loc["ZONEDIST", "type"] == "String"
    assert by_name.loc["ZONEDIST", "length"] == 15


def test_get_shp_schema(temp_shp_nonzipped):
    # Confirmed field-by-field against live arcpy.ListFields() output for this exact
    # fixture. Shapefiles never go through the native-XML path (no Esri schema catalog
    # exists for that format), but Esri's fixed byte-widths for OID/Geometry/Date still
    # apply on top of GDAL's generic field reporting.
    expected_schema = pd.DataFrame(
        {
            "name": [
                "FID",
                "Shape",
                "ZONEDIST",
                "DT_ADDED",
                "SOURCE",
                "Boro_nm",
                "DT_EDITED",
                "EDITOR",
            ],
            "type": [
                "OID",
                "Geometry",
                "String",
                "Date",
                "String",
                "String",
                "Date",
                "String",
            ],
            "length": [4, 0, 15, 8, 50, 50, 8, 50],
        }
    )

    actual_schema = inspect_data.get_dataset_schema(temp_shp_nonzipped)

    assert_frame_equal(expected_schema, actual_schema)


def test_normalize_fallback_type_narrows_real_above_width_7_to_double():
    # Confirmed against live arcpy.ListFields() output (both a real shapefile's
    # numeric fields and a synthetic arcpy-authored test shapefile): a Real field's
    # declared width is precision + 1, so width > 7 corresponds to Esri's documented
    # "precision > 6 digits -> Double" rule.
    assert inspect_data._normalize_fallback_type("Real", 8) == "Double"
    assert inspect_data._normalize_fallback_type("Real", 19) == "Double"


def test_normalize_fallback_type_narrows_real_at_or_below_width_7_to_single():
    assert inspect_data._normalize_fallback_type("Real", 7) == "Single"
    assert inspect_data._normalize_fallback_type("Real", 4) == "Single"


def test_normalize_fallback_type_collapses_integer64_to_integer():
    # Confirmed against live arcpy.ListFields(): arcpy never reports "Long"/Integer64
    # for a shapefile, even for a wide (10-digit) integer field -- always plain
    # "Integer", regardless of whether the field was created as Short or Long.
    assert inspect_data._normalize_fallback_type("Integer64", 10) == "Integer"


def test_normalize_fallback_type_leaves_other_types_unchanged():
    assert inspect_data._normalize_fallback_type("String", 50) == "String"
    assert inspect_data._normalize_fallback_type("Integer", 4) == "Integer"
    assert inspect_data._normalize_fallback_type("Date", None) == "Date"


def test_get_shp_schema_numeric_fields(tmp_path):
    # End-to-end check of the Real->Single/Double narrowing and Integer64->Integer
    # collapse, built with plain osgeo.ogr (not arcpy) so the test suite stays
    # arcpy-free. Field widths mirror a live arcpy-authored test shapefile confirmed
    # separately: a narrow Real field (width 7, precision 6) arcpy calls "Single", a
    # wide one (width 16, precision 15) arcpy calls "Double", and a 10-digit integer
    # field arcpy still calls plain "Integer" (never "Long"/Integer64).
    shp_path = tmp_path / "numeric_probe.shp"
    ds = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(str(shp_path))
    lyr = ds.CreateLayer("numeric_probe", geom_type=ogr.wkbPoint)

    float_fld = ogr.FieldDefn("FloatFld", ogr.OFTReal)
    float_fld.SetWidth(7)
    float_fld.SetPrecision(2)
    lyr.CreateField(float_fld)

    double_fld = ogr.FieldDefn("DoubleFld", ogr.OFTReal)
    double_fld.SetWidth(16)
    double_fld.SetPrecision(4)
    lyr.CreateField(double_fld)

    long_fld = ogr.FieldDefn("LongFld", ogr.OFTInteger64)
    long_fld.SetWidth(10)
    lyr.CreateField(long_fld)

    ds = None  # flush to disk

    schema = inspect_data.get_dataset_schema(shp_path).set_index("name")

    assert schema.loc["FloatFld", "type"] == "Single"
    assert schema.loc["FloatFld", "length"] == 7
    assert schema.loc["DoubleFld", "type"] == "Double"
    assert schema.loc["DoubleFld", "length"] == 16
    assert schema.loc["LongFld", "type"] == "Integer"
    assert schema.loc["LongFld", "length"] == 10


def test_get_record_count_comparison_gdb(temp_gdb_nonzipped):
    dataset_1, dataset_2 = inspect_data.get_record_count_comparison(
        dataset_1=temp_gdb_nonzipped,
        dataset_2=temp_gdb_nonzipped,
        layer_1="nyzd_one_row",
        layer_2="nyzd_one_row",
    )

    assert dataset_1 == 1
    assert dataset_2 == 1


def test_get_record_count_comparison_shp(temp_shp_nonzipped):
    dataset_1, dataset_2 = inspect_data.get_record_count_comparison(
        dataset_1=temp_shp_nonzipped,
        dataset_2=temp_shp_nonzipped,
    )

    assert dataset_1 == 1
    assert dataset_2 == 1


def test_load_reference_schema_from_csv(tmp_path):
    csv_path = tmp_path / "reference_schema.csv"
    csv_path.write_text("name,type,length\nZONEDIST,String,15\nSHAPE,Geometry,\n")

    schema = inspect_data.load_reference_schema(csv_path)

    assert list(schema["name"]) == ["ZONEDIST", "SHAPE"]
    assert list(schema["type"]) == ["String", "Geometry"]


def test_load_reference_schema_from_dataset(temp_shp_nonzipped):
    schema = inspect_data.load_reference_schema(temp_shp_nonzipped)

    assert_frame_equal(schema, inspect_data.get_dataset_schema(temp_shp_nonzipped))


def test_compare_schema_identical(temp_shp_nonzipped):
    diff = inspect_data.compare_schema(test=temp_shp_nonzipped, reference=temp_shp_nonzipped)

    assert diff.is_match
    assert diff.added_fields.empty
    assert diff.removed_fields.empty
    assert diff.changed_fields.empty
    assert diff.reordered_fields.empty


def test_compare_schema_detects_added_removed_and_changed_fields(temp_shp_nonzipped, tmp_path):
    actual_schema = inspect_data.get_dataset_schema(temp_shp_nonzipped)

    # Build the reference schema from the real output, then perturb it: drop EDITOR
    # (making it "added" relative to the reference), add NOTES (making it "removed"
    # relative to the test dataset), and shorten ZONEDIST's length (making it
    # "changed"). Deriving from real output rather than hardcoded literals avoids
    # depending on exact GDAL type/length values that couldn't be verified locally.
    zonedist_length = int(actual_schema.loc[actual_schema["name"] == "ZONEDIST", "length"].item())
    reference_schema = actual_schema.loc[actual_schema["name"] != "EDITOR"].copy()
    reference_schema.loc[reference_schema["name"] == "ZONEDIST", "length"] = zonedist_length - 5
    reference_schema = pd.concat(
        [reference_schema, pd.DataFrame([{"name": "NOTES", "type": "String", "length": 255}])],
        ignore_index=True,
    )

    csv_path = tmp_path / "reference_schema.csv"
    reference_schema.to_csv(csv_path, index=False)

    diff = inspect_data.compare_schema(test=temp_shp_nonzipped, reference=csv_path)

    assert not diff.is_match
    assert list(diff.added_fields["name"]) == ["EDITOR"]
    assert list(diff.removed_fields["name"]) == ["NOTES"]
    assert list(diff.changed_fields["name"]) == ["ZONEDIST"]
    assert diff.changed_fields.loc[0, "length_test"] == zonedist_length
    assert diff.changed_fields.loc[0, "length_reference"] == zonedist_length - 5


def test_compare_schema_field_name_case_always_matters(temp_shp_nonzipped, tmp_path):
    actual_schema = inspect_data.get_dataset_schema(temp_shp_nonzipped)
    reference_schema = actual_schema.copy()
    reference_schema.loc[reference_schema["name"] == "ZONEDIST", "name"] = "zonedist"

    csv_path = tmp_path / "reference_schema.csv"
    reference_schema.to_csv(csv_path, index=False)

    diff = inspect_data.compare_schema(test=temp_shp_nonzipped, reference=csv_path)

    assert not diff.is_match
    assert "ZONEDIST" in list(diff.added_fields["name"])
    assert "zonedist" in list(diff.removed_fields["name"])


def test_compare_schema_field_order_ignored_by_default(temp_shp_nonzipped, tmp_path):
    actual_schema = inspect_data.get_dataset_schema(temp_shp_nonzipped)
    reordered_schema = actual_schema.iloc[::-1].reset_index(drop=True)

    csv_path = tmp_path / "reference_schema.csv"
    reordered_schema.to_csv(csv_path, index=False)

    diff = inspect_data.compare_schema(test=temp_shp_nonzipped, reference=csv_path)

    assert diff.is_match
    assert diff.reordered_fields.empty


def test_compare_schema_strict_order_detects_reordered_fields(temp_shp_nonzipped, tmp_path):
    actual_schema = inspect_data.get_dataset_schema(temp_shp_nonzipped)
    reordered_schema = actual_schema.iloc[::-1].reset_index(drop=True)

    csv_path = tmp_path / "reference_schema.csv"
    reordered_schema.to_csv(csv_path, index=False)

    diff = inspect_data.compare_schema(test=temp_shp_nonzipped, reference=csv_path, check_field_order=True)

    assert not diff.is_match
    assert set(diff.reordered_fields["name"]) == set(actual_schema["name"])
