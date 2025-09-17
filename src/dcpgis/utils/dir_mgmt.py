from pathlib import Path
import shutil
import os

def create_dir_with_subdirs(parent_dir_path: Path, sub_dirs: list) -> None:
    """
    Creates a parent directory and desired sub-directories.
    Args:
        parent_dir_path (Path): The parent directory under which to create the sub-directories
        sub_dirs (List): The cycle date in YYYYMM format
    Returns:    
        None        
    """
    for sub_dir in sub_dirs:
        dir_path = Path(parent_dir_path / sub_dir)
        os.makedirs(dir_path)


def copytree_overwrite(src: Path, dst: Path) -> None:
    """
    Copy contents of src directory to dst directory, overwriting existing files.
    Args:
        src (Path): The source directory to copy from.
        dst (Path): The destination directory to copy to.
    Returns:
        None
    """
    if dst.exists():
        shutil.rmtree(dst)  # Remove existing dir tree to avoid errors
    shutil.copytree(src, dst)
