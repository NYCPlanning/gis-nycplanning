from pathlib import Path
import shutil

def create_dir_if_not_exists(dir_path: Path) -> None:
    """
    Create given directory if it does not already exist.
    Args:
        dir_path (Path): The directory to create if it does not exist.
"""
    if not dir_path.exists():
        dir_path.mkdir(parents=True, exist_ok=True)
    else:
        pass


def create_cycle_dir_with_subdirs(parent_dir_path: str, cycle_date: str) -> None:
    
    """
    Create standard sub-directory structure for open data staging area. 
    Args:
        parent_dir (Path): The parent directory under which to create the sub-directories
        cycle_date (str): The cycle date in YYYYMM format
    Returns:    
        None        
    """
    sub_dirs = ["raw_data", "metadata", "shp", "gdb", 'web']
    cycle_dir = Path(parent_dir_path) / cycle_date
    cycle_dir.mkdir(parents=True, exist_ok=True)
    for sub_dir in sub_dirs:
        dir_path = cycle_dir / sub_dir
        dir_path.mkdir(parents=True, exist_ok=True)


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
