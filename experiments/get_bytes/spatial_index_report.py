"""Detect shapefiles whose .sbn/.sbx spatial index silently returns wrong results.

Runs under the `gis-env` conda environment (needs osgeo/GDAL - see README for why and how to
invoke). Reads zip_contents.csv + pluto_datasets.csv (already produced by
summarize_zip_datasets.py / scrape_pluto_datasets.py) and writes spatial_index_results.csv.
Per explicit design direction, this script is fully isolated: it never imports, and is never
imported by, summarize_zip_datasets.py/common.py's tests, and never modifies either input CSV.

For each shapefile-backed layer, compares a GDAL spatial-filtered query (which consults the
.sbn/.sbx index, if one exists) against an index-free "truth" computed by directly parsing the
.shp file's own binary records with struct. This needs no local download (the shapefile is read
remotely via the same byte-ranged approach used throughout this project) and is far cheaper than
letting GDAL decode every feature's full geometry just to get its bounding box (confirmed
~20x+ faster at real full-scale files during design research - see the plan for the empirical
case). GDAL's TestCapability("FastSpatialFilter") was confirmed during research to report an
index as usable even when it's actually corrupted, so it's recorded here as informational
metadata only, never as the correctness signal itself.
"""

import csv
import struct
import sys
from pathlib import Path

from osgeo import gdal

sys.path.insert(0, str(Path(__file__).parent))
from common import get_zip_member_bytes, make_session

gdal.UseExceptions()

DATASETS_CSV = Path(__file__).parent / "pluto_datasets.csv"
ZIP_CONTENTS_CSV = Path(__file__).parent / "zip_contents.csv"
OUTPUT_CSV = Path(__file__).parent / "spatial_index_results.csv"
FIELDNAMES = ["identifier", "path_in_zip", "has_spatial_index", "verdict"]

GRID_SIZE = 3


def configure_gdal() -> None:
    """Same tuning confirmed useful (via benchmark) for the vsicurl-heavy work this project
    already does elsewhere - see summarize_zip_datasets.py's own configure_gdal()."""
    for key, value in {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_CHUNK_SIZE": "2097152",
        "CPL_VSIL_CURL_CACHE_SIZE": "67108864",
        "VSI_CACHE": "YES",
        "VSI_CACHE_SIZE": "67108864",
        "GDAL_HTTP_MULTIPLEX": "YES",
    }.items():
        gdal.SetConfigOption(key, value)


def read_shp_bboxes(
    url: str, member_name: str, session
) -> "list[tuple[float, float, float, float] | None] | None":
    """Parse a remote .shp file's records directly via struct, returning each record's
    bounding box (xmin, ymin, xmax, ymax), or None for a null-shape record. Returns None (the
    whole thing) if the member couldn't be fetched, or is truncated/malformed mid-record.

    Never consults the .sbn/.sbx spatial index - a true index-free "truth" baseline. Jumps
    straight past each record's point/vertex array via its declared content-length, instead of
    decoding it, which is where nearly all of a full GDAL feature scan's cost actually is.
    """
    data = get_zip_member_bytes(url, member_name, session)
    if data is None:
        return None

    bboxes = []
    pos = 100  # fixed 100-byte file header
    try:
        while pos < len(data):
            content_length_words = struct.unpack(">i", data[pos + 4 : pos + 8])[0]
            content_length = content_length_words * 2
            shape_type = struct.unpack("<i", data[pos + 8 : pos + 12])[0]
            if shape_type == 0:
                bboxes.append(None)
            else:
                bboxes.append(struct.unpack("<dddd", data[pos + 12 : pos + 44]))
            pos += 8 + content_length
    except struct.error as exc:
        print(
            f"WARNING: malformed/truncated .shp record in {member_name!r} from {url}: {exc}"
        )
        return None
    return bboxes


def make_grid(
    minx: float, miny: float, maxx: float, maxy: float, n: int = GRID_SIZE
) -> list[tuple[float, float, float, float]]:
    """n x n grid cells covering the extent, each (minx, miny, maxx, maxy) - catches
    corruption localized to only part of the extent, not just a single whole-extent query."""
    width = (maxx - minx) / n
    height = (maxy - miny) / n
    return [
        (
            minx + col * width,
            miny + row * height,
            minx + (col + 1) * width,
            miny + (row + 1) * height,
        )
        for row in range(n)
        for col in range(n)
    ]


def truth_count(
    bboxes: "list[tuple[float, float, float, float] | None]",
    cell: tuple[float, float, float, float],
) -> int:
    cminx, cminy, cmaxx, cmaxy = cell
    return sum(
        1
        for b in bboxes
        if b is not None
        and b[2] >= cminx
        and b[0] <= cmaxx
        and b[3] >= cminy
        and b[1] <= cmaxy
    )


def indexed_count(layer, cell: tuple[float, float, float, float]) -> int:
    layer.SetSpatialFilterRect(*cell)
    count = layer.GetFeatureCount(force=0)
    layer.SetSpatialFilter(None)
    return count


# GDAL's spatial filter tests actual geometry intersection against a cell rect; the
# struct-based "truth" only has each record's bounding box, not its real shape, so a
# polygon whose bbox straddles a grid boundary line can show up in a neighboring cell's
# truth count even though its actual body never reaches there. Confirmed empirically
# against the known-valid mappluto_09v1 case: summing every cell's truth count (44,214)
# exceeds the file's real total feature count (43,615), and 3 of 9 cells were off by
# exactly 1 - vs. the known-corrupted mappluto_14v2 case, where every populated cell was
# off by 90%+. The two failure modes sit many orders of magnitude apart, so a small
# relative tolerance safely absorbs the former without masking the latter.
CELL_MISMATCH_TOLERANCE = (
    0.01  # 1% relative difference, or 2 features, whichever is larger
)


def cells_mismatch(indexed: int, truth: int) -> bool:
    return abs(indexed - truth) > max(2, CELL_MISMATCH_TOLERANCE * max(indexed, truth))


def check_shapefile(url: str, path_in_zip: str, session) -> tuple[bool, str]:
    """Returns (has_spatial_index, verdict) for one shapefile layer."""
    posix_path = path_in_zip.replace("\\", "/")
    vsi_path = f"/vsizip//vsicurl/{url}/{posix_path}"
    try:
        dataset = gdal.OpenEx(vsi_path, gdal.OF_VECTOR)
        layer = dataset.GetLayer(0)
        has_spatial_index = bool(layer.TestCapability("FastSpatialFilter"))
        minx, maxx, miny, maxy = layer.GetExtent()
    except RuntimeError as exc:
        print(f"WARNING: could not open {vsi_path}: {exc}")
        return False, "ERROR"

    if not has_spatial_index:
        return False, "NOT_APPLICABLE"

    bboxes = read_shp_bboxes(url, posix_path, session)
    if bboxes is None:
        return True, "ERROR"

    for cell in make_grid(minx, miny, maxx, maxy):
        if cells_mismatch(indexed_count(layer, cell), truth_count(bboxes, cell)):
            return True, "INCONSISTENT"
    return True, "CONSISTENT"


def main() -> None:
    configure_gdal()
    session = make_session()

    with DATASETS_CSV.open(newline="", encoding="utf-8") as f:
        url_by_identifier = {row["identifier"]: row["url"] for row in csv.DictReader(f)}

    with ZIP_CONTENTS_CSV.open(newline="", encoding="utf-8") as f:
        shapefile_rows = [
            row
            for row in csv.DictReader(f)
            if row["spatial"] == "True" and row["path_in_zip"].lower().endswith(".shp")
        ]

    print(f"Checking {len(shapefile_rows)} shapefile-backed layers...")

    results = []
    for i, row in enumerate(shapefile_rows, 1):
        url = url_by_identifier.get(row["identifier"])
        if url is None:
            print(
                f"WARNING: no url found for identifier {row['identifier']!r}, skipping"
            )
            continue
        has_spatial_index, verdict = check_shapefile(url, row["path_in_zip"], session)
        print(
            f"[{i}/{len(shapefile_rows)}] {row['identifier']} {row['path_in_zip']}: {verdict}"
        )
        results.append(
            {
                "identifier": row["identifier"],
                "path_in_zip": row["path_in_zip"],
                "has_spatial_index": has_spatial_index,
                "verdict": verdict,
            }
        )

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"Wrote {len(results)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
