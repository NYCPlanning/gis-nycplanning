from pathlib import Path
import subprocess
import shutil
import time

import arcpy

from part_a import part_a
from part_c import part_c


VENV2_PYTHON = Path(__file__).parent / ".venv/python.exe"
PART_B_PY = Path(__file__).parent / "part_b.py"
DATA_DIR = Path(__file__).parent / "data"


def remove_esri_data_dir(dir: Path):
    arcpy.ClearWorkspaceCache_management()
    time.sleep(0.2)
    shutil.rmtree(dir)


def main():

    item_path = DATA_DIR / "temp.shp"

    # Part A, called from arcpy/conda env
    input_file = part_a(data_dir=DATA_DIR, shp_name=item_path)

    # Part B, called from dcpy env
    subprocess.run(
        [str(VENV2_PYTHON), "-I", PART_B_PY, str(input_file)],
        # capture_output=True,
        text=True,
        check=True,
    )

    # Part C, called from arcpy/conda env again
    part_c(item_path=item_path)

    remove_esri_data_dir(DATA_DIR)  # comment me out to examine temp.shp.xml outputs


if __name__ == "__main__":
    main()
