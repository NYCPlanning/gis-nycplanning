import shutil
import zipfile

import pytest
from pytest import fixture

from dcpgis.compare_schema import main

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
