from pathlib import Path
import shutil
import sys
import platform
import arcpy


def part_a(data_dir: Path, shp_name):

    print("Part A: Creating shapefile with arcpy/conda-based env")
    print(f"\tPython version: {platform.python_version()}")
    print(f"\tFile: {__file__}")
    print(f"\tInterpreter: {sys.executable}")

    if data_dir.is_dir():
        shutil.rmtree(data_dir)
    data_dir.mkdir()
    arcpy.management.CreateFeatureclass(str(data_dir), shp_name)

    return data_dir / shp_name
