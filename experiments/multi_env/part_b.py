from dcpy.utils.geospatial import shapefile
from pathlib import Path
import sys
import platform


def part_b():
    """Generate new metadata and write it to a shapefile"""
    print("Part B: Writing metadata with dcpy-based environment")
    print(f"\tPython version: {platform.python_version()}")
    print(f"\tFile: {__file__}")
    print(f"\tInterpreter: {sys.executable}")

    if len(sys.argv) < 2:
        print("Error: No input file provided", file=sys.stderr)
        return 1
    input_shp = Path(sys.argv[1])
    shp_name = input_shp.name

    md = shapefile.generate_metadata()

    shp = shapefile.Shapefile(path=input_shp.parent, shp_name=shp_name)

    shp.write_metadata(md, overwrite=True)

    # metadata = shp.read_metadata()

    # print(metadata)
    return 0


if __name__ == "__main__":
    sys.exit(part_b())
