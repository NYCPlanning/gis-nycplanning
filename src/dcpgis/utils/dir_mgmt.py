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
        Path.mkdir(parents=True, exist_ok=True)
