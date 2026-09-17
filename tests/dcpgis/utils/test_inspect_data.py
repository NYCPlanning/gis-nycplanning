import os
import shutil
import zipfile

import pandas as pd
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
            "length": [None, None, 15, None, 50, 50, None, 50, None, None],
        }
    )

    actual_schema = inspect_data.get_dataset_schema(temp_gdb_nonzipped, layer="nyzd_one_row")

    assert_frame_equal(expected_schema, actual_schema)


def test_get_shp_schema(temp_shp_nonzipped):
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
            "length": [None, None, 15, None, 50, 50, None, 50],
        }
    )

    actual_schema = inspect_data.get_dataset_schema(temp_shp_nonzipped)

    assert_frame_equal(expected_schema, actual_schema)


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


def test_compare_schema_detects_added_removed_and_changed_fields(temp_shp_nonzipped, tmp_path):
    # Reference schema: drops EDITOR (making it "added" relative to the reference),
    # adds NOTES (making it "removed" relative to the test dataset), and shortens
    # ZONEDIST's length (making it "changed").
    csv_path = tmp_path / "reference_schema.csv"
    csv_path.write_text(
        "name,type,length\n"
        "FID,OID,\n"
        "Shape,Geometry,\n"
        "ZONEDIST,String,10\n"
        "DT_ADDED,Date,\n"
        "SOURCE,String,50\n"
        "Boro_nm,String,50\n"
        "DT_EDITED,Date,\n"
        "NOTES,String,255\n"
    )

    diff = inspect_data.compare_schema(test=temp_shp_nonzipped, reference=csv_path)

    assert not diff.is_match
    assert list(diff.added_fields["name"]) == ["EDITOR"]
    assert list(diff.removed_fields["name"]) == ["NOTES"]
    assert list(diff.changed_fields["name"]) == ["ZONEDIST"]
    assert diff.changed_fields.loc[0, "length_test"] == 15
    assert diff.changed_fields.loc[0, "length_reference"] == 10
