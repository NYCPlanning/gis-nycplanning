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
