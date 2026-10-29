from pathlib import Path


def create_dir_with_subdirs(parent_dir_path: Path, sub_dirs: list) -> None:
    """
    Create the provided parent directory and any requested sub-directories.

    The sub_dirs list may include nested paths, such as
    ["top_level", "another_top_level", "third_top_level/nested/nested_again"],
    and each path will be created along with any required intermediate directories.

    This function creates the target directory path and its sub-directories as needed,
    while leaving existing directories and files in place.

    Args:
        parent_dir_path (Path): The parent directory under which to create the sub-directories.
        sub_dirs (List): A list of directory paths to create beneath the parent directory.

    Returns:
        None
    """
    for sub_dir in sub_dirs:
        dir_path = Path(parent_dir_path / sub_dir)
        Path.mkdir(dir_path, parents=True, exist_ok=True)
