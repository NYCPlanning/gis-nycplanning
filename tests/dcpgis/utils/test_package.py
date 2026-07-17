\
import zipfile
import logging
import pytest

from dcpgis.utils.package import archive_zipping, copy_metadata_to_folder


@pytest.fixture
def package_test_tree(tmp_path):
    root = tmp_path / "cycle"
    root.mkdir()

    gdb_dir = root / "gdb"
    gdb_dir.mkdir()

    data_gdb = gdb_dir / "product.gdb"
    data_gdb.mkdir()

    (data_gdb / "data.dbf").write_text("dbf-data")

    metadata_dir = root / "metadata"
    metadata_dir.mkdir()
    (metadata_dir / "product.xml").write_text("<metadata/>")

    shp_dir = root / "shp"
    shp_dir.mkdir()
    (shp_dir / "product.shp").write_text("shape-data")
    (shp_dir / "product.shp.xml").write_text("<shpxml/>")

    return root


@pytest.fixture
def package_test_tree_with_lock(package_test_tree):
    (package_test_tree / "gdb" / "product.gdb" / "_gdb.some.lock").write_text("lock")
    return package_test_tree


def test_archive_zipping_writes_regular_files_and_nested_directories(package_test_tree):
    archive_specs = {
        "bundle": {
            "source_dirs": ["gdb", "metadata", "shp"],
            "content": ["product.gdb", "product.xml", "product.shp", "product.shp.xml"],
            "output_name": "product.zip",
            "output_dir": "web",
        }
    }

    archive_zipping(package_test_tree, archive_specs, output_dir_name="web")

    archive_path = package_test_tree / "web" / "product.zip"
    assert archive_path.exists()

    with zipfile.ZipFile(archive_path) as zf:
        names = zf.namelist()

        assert any(name.startswith("product.gdb/") for name in names)
        assert "product.gdb/data.dbf" in names
        assert "product.xml" in names
        assert "product.shp" in names
        assert "product.shp.xml" in names


def test_archive_zipping_skips_lock_files_when_ignore_locks_true(package_test_tree_with_lock):
    archive_specs = {
        "bundle": {
            "source_dirs": ["gdb"],
            "content": ["product.gdb"],
            "output_name": "product.zip",
            "output_dir": "web",
        }
    }

    archive_zipping(package_test_tree_with_lock, archive_specs, output_dir_name="web", ignore_locks=True)

    archive_path = package_test_tree_with_lock / "web" / "product.zip"
    with zipfile.ZipFile(archive_path) as zf:
        names = zf.namelist()

        assert any(name.startswith("product.gdb/") for name in names)
        assert "product.gdb/data.dbf" in names
        assert "product.gdb/_gdb.some.lock" not in names


def test_archive_zipping_raises_when_lock_files_found_and_ignore_locks_false(package_test_tree_with_lock):
    archive_specs = {
        "bundle": {
            "source_dirs": ["gdb"],
            "content": ["product.gdb"],
            "output_name": "product.zip",
            "output_dir": "web",
        }
    }

    with pytest.raises(RuntimeError, match="Lock file found"):
        archive_zipping(package_test_tree_with_lock, archive_specs, output_dir_name="web", ignore_locks=False)



def test_copy_metadata_to_folder_copies_selected_files(tmp_path, caplog):
    metadata_source_dir = tmp_path / "metadata_source"
    metadata_source_dir.mkdir()

    expected_file = metadata_source_dir / "product.xlsx"
    expected_file.write_text("xlsx-content")

    ignored_file = metadata_source_dir / "ignored.xlsx"
    ignored_file.write_text("ignored-content")

    output_dir = tmp_path / "copied_metadata"
    
    caplog.set_level(logging.WARNING, logger="root")

    copy_metadata_to_folder(
        metadata_source_dir=metadata_source_dir,
        output_dir=output_dir,
        metadata_files=["product.xlsx", "missing.xlsx"],
    )

    assert output_dir.exists()
    assert (output_dir / "product.xlsx").exists()
    assert (output_dir / "product.xlsx").read_text() == "xlsx-content"
    assert not (output_dir / "ignored.xlsx").exists()
    assert not (output_dir / "missing.xlsx").exists()
    assert "missing.xlsx" in caplog.text