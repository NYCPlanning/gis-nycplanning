import shutil
import zipfile

import pytest
from pytest import fixture

from dcpgis.compare_schema import main
from dcpgis.utils import inspect_data

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


def test_main_exits_zero_on_match(temp_shp_nonzipped, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        ["dcpgis-compare-schema", "--test", str(temp_shp_nonzipped), "--reference", str(temp_shp_nonzipped)],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 0
    assert "Schemas match." in capsys.readouterr().out


def test_main_exits_nonzero_on_mismatch(temp_shp_nonzipped, tmp_path, monkeypatch, capsys):
    reference_csv = tmp_path / "reference_schema.csv"
    reference_csv.write_text("name,type,length\nZONEDIST,String,10\n")

    monkeypatch.setattr(
        "sys.argv",
        ["dcpgis-compare-schema", "--test", str(temp_shp_nonzipped), "--reference", str(reference_csv)],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    assert "ZONEDIST" in capsys.readouterr().out


def test_main_exits_with_distinct_code_when_dataset_not_found(tmp_path, monkeypatch, capsys):
    missing_path = tmp_path / "does_not_exist.gdb"

    monkeypatch.setattr(
        "sys.argv",
        ["dcpgis-compare-schema", "--test", str(missing_path), "--reference", str(missing_path)],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "Comparison could not be run" in captured.err
    assert captured.out == ""


def test_main_strict_order_detects_reordered_fields(temp_shp_nonzipped, tmp_path, monkeypatch, capsys):
    actual_schema = inspect_data.get_dataset_schema(temp_shp_nonzipped)
    reordered_schema = actual_schema.iloc[::-1].reset_index(drop=True)

    reference_csv = tmp_path / "reference_schema.csv"
    reordered_schema.to_csv(reference_csv, index=False)

    monkeypatch.setattr(
        "sys.argv",
        [
            "dcpgis-compare-schema",
            "--test",
            str(temp_shp_nonzipped),
            "--reference",
            str(reference_csv),
            "--strict-order",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    assert "changed positions" in capsys.readouterr().out


def test_main_ignores_field_order_without_strict_order_flag(temp_shp_nonzipped, tmp_path, monkeypatch, capsys):
    actual_schema = inspect_data.get_dataset_schema(temp_shp_nonzipped)
    reordered_schema = actual_schema.iloc[::-1].reset_index(drop=True)

    reference_csv = tmp_path / "reference_schema.csv"
    reordered_schema.to_csv(reference_csv, index=False)

    monkeypatch.setattr(
        "sys.argv",
        ["dcpgis-compare-schema", "--test", str(temp_shp_nonzipped), "--reference", str(reference_csv)],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 0
    assert "Schemas match." in capsys.readouterr().out
