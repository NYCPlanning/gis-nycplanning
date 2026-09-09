import logging

from dcpgis.utils.package import copy_metadata_to_folder


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
