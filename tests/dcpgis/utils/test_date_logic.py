from pytest import fixture
import shutil
import zipfile
import os
from dcpgis.utils import date_logic
from datetime import date, timedelta

GDB_ZIP = "geodatabase_zoning_data.zip"

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

def test_get_latest_date_from_field_no_override(temp_gdb_nonzipped):
    dataset_path = os.path.join(temp_gdb_nonzipped, "nyzma_two_rows")
    expected_date = "20250925"
    actual_date = date_logic.get_latest_date_from_field(feature_class_path=dataset_path,
                                                        date_field="EFFECTIVE")
    assert expected_date == actual_date
    
def test_get_latest_date_from_field_with_override(temp_gdb_nonzipped):
    dataset_path = os.path.join(temp_gdb_nonzipped, "nyzma_two_rows")
    override_config_value = "20260101"
    expected_date = "20260101"
    actual_date = date_logic.get_latest_date_from_field(feature_class_path=dataset_path,
                                                        date_field="EFFECTIVE",
                                                        override_config_value=override_config_value)
    assert expected_date == actual_date

def test_calc_open_data_cycle_month_no_override(config_date=None):
    expected_cycle_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y%m")
    actual_cycle_month = date_logic.calc_open_data_cycle_month(config_date=config_date)
    assert expected_cycle_month == actual_cycle_month
    
def test_calc_open_data_cycle_month_with_override(config_date="202601"):
    expected_cycle_month = "202601"
    actual_cycle_month = date_logic.calc_open_data_cycle_month(config_date=config_date)
    assert expected_cycle_month == actual_cycle_month

def test_reformat_date_str_to_written_month():
    date_string = "20250925"
    expected_formatted_date = "September 25, 2025"
    actual_formatted_date = date_logic.reformat_date_str_to_written_month(date_string=date_string)
    assert expected_formatted_date == actual_formatted_date