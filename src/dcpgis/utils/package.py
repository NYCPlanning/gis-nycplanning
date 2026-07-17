from pathlib import Path
import zipfile
import logging

def archive_zipping(parent_dir: str, archive_specs: dict, output_dir_name: str, ignore_locks: bool = False, product_version: str = None):
    """
    Creates zip files in a sub-directory = as defined in the archive_specs dictionary.
    
    Expected archive spec dictionary shape:
    {
        "archive_name": {
            "source_dirs": ["source_folder"],
            "content": ["file_one.shp", "file_two.shp.xml"],
            "output_name": "product_package_shp.zip",
            "output_dir": "web",
        }
    }

    Args:
        parent_dir (str or Path): Root directory containing the source folders.
        archive_specs (dict): Mapping of archive definitions, where each entry contains source_dirs, content, output_name, and output_dir.
        output_dir_name (str): Folder where zip files are written.
        ignore_locks (bool, optional): if Ture, skips any files with .lock in the name. Default is False. False will raise clear exception when lock is encountered.
        product_version (str, optional): Value used to format output names.
        
    """
    parent_dir = Path(parent_dir)
    output_dir = parent_dir / output_dir_name
    output_dir.mkdir(parents=True, exist_ok=True) # redundant but safe

    for archive_name, spec in archive_specs.items():
        logging.debug(f"{archive_name=}")

        source_dirs = spec.get("source_dirs")
        if isinstance(source_dirs, str):
            source_dirs = [source_dirs]
            
        content = spec.get ("content", [])
        if isinstance(content, str):
            content = [content]
        
        output_name = spec.get("output_name", archive_name)
        if product_version is not None: 
            output_name = output_name.format(cycle_date=product_version)

        zip_path = output_dir / output_name
        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for source_dir_name in source_dirs:
                source_dir = parent_dir / source_dir_name
                if not source_dir.exists():
                    logging.warning(f"Source directory {source_dir} does not exist. Skipping.")
                    continue
                
                for pattern in content:
                    matches = list(source_dir.glob(pattern))
                    if not matches:
                        logging.warning(f"No matches found for pattern '{pattern}' in {source_dir}.")
                        continue

                    for match in matches:
                        if match.is_dir():
                            if match.is_dir():
                                for nested in sorted(match.rglob("*")):
                                    if not nested.is_file():
                                        continue

                                    if ".lock" in nested.name.lower():
                                        if ignore_locks:
                                            logging.debug(f"Skipping lock file: {nested}")
                                            continue
                                        raise RuntimeError(f"Lock file found: {nested}. Set ignore_locks=True to skip.")
                                    
                                    zf.write(nested, arcname=nested.relative_to(source_dir))
                        
                        elif match.is_file():
                            if ".lock" in match.name.lower():
                                if ignore_locks:
                                    logging.debug(f"Skipping lock file {match}")
                                    continue
                                raise RuntimeError(f"Lock file found: {match}. Set ignore_locks=True to skip.")
                            
                            zf.write(match, arcname=match.relative_to(source_dir))
                            
# Need to iterate through content list, identify pattern + glob, confirm item exists in directory, then write 

