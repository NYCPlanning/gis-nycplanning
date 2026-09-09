import logging
import shutil
from pathlib import Path


def copy_matching_files(source_dir: str, output_dir: str, files: list):
    """
    Copies specified files from a source directory to an output directory.

    Args:
        source_dir (str): Path to the source directory containing metadata files.
        output_dir (str): Path to the destination directory where files will be copied.
        files (list): List of file names to copy.
    """
    metadata_source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for file_name in files:
        source_file_path = metadata_source_dir / file_name
        if not source_file_path.exists():
            logging.warning(f"{source_file_path} does not exist. Skipping.")
            continue

        shutil.copy2(src=source_file_path, dst=output_dir)
