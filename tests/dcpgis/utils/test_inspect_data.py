from pytest import fixture
import shutil
import zipfile
import os
from dcpgis.utils import inspect_data
import pandas as pd
from pandas.testing import assert_frame_equal

GDB_ZIP = "geodatabase_zoning_data.zip"
SHP_ZIP = "shapefile_nyzd_one_row.zip"


@fixture
def temp_shp_zip(resources_path, tmp_path):
    shutil.copy2(
        src=resources_path / SHP_ZIP,
        dst=tmp_path / SHP_ZIP,
    )
    assert zipfile.is_zipfile(tmp_path / SHP_ZIP), (
        f"'{SHP_ZIP}' should be a valid zip file"
    )
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
    assert zipfile.is_zipfile(tmp_path / GDB_ZIP), (
        f"'{GDB_ZIP}' should be a valid zip file"
    )
    return tmp_path / GDB_ZIP


@fixture
def temp_gdb_nonzipped(temp_gdb_zip, tmp_path):
    shutil.unpack_archive(filename=temp_gdb_zip, extract_dir=tmp_path)
    gdb_path = (tmp_path / temp_gdb_zip.stem).with_suffix(".gdb")
    assert os.path.exists(gdb_path), "Expected a gdb, but found none"
    return gdb_path


def test_get_gdb_schema(temp_gdb_nonzipped):
    dataset_path = os.path.join(temp_gdb_nonzipped, "nyzd_one_row")

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

    actual_schema = inspect_data.get_dataset_schema(dataset_path)

    assert_frame_equal(expected_schema, actual_schema)


def test_get_shp_schema(temp_shp_nonzipped):
    shp = temp_shp_nonzipped

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

    actual_schema = inspect_data.get_dataset_schema(shp)

    assert_frame_equal(expected_schema, actual_schema)


def test_get_record_count_comparison_gdb(temp_gdb_nonzipped):
    dataset_path = os.path.join(temp_gdb_nonzipped, "nyzd_one_row")

    dataset_1, dataset_2 = inspect_data.get_record_count_comparison(
        dataset_1=dataset_path, dataset_2=dataset_path
    )

    assert dataset_1 == 1
    assert dataset_2 == 1

def test_get_record_count_comparison_shp(temp_shp_nonzipped):
    dataset_path = os.path.join(temp_shp_nonzipped, "nyzd_one_row")

    dataset_1, dataset_2 = inspect_data.get_record_count_comparison(
        dataset_1=dataset_path, dataset_2=dataset_path
    )

    assert dataset_1 == 1
    assert dataset_2 == 1