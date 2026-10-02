"""Check a shapefile's .sbn/.sbx spatial index against the geometry it claims to index.

GDAL reports a corrupted index as usable, so the only way to catch one is to compare indexed
spatial-filter counts with a truth baseline built without the index: each record's bounding
box, parsed straight out of the .shp binary.

Works on an already-open OGR layer, duck-typed, so this module never imports osgeo itself.
Callers must have enabled `gdal.UseExceptions()`, or GDAL failures won't surface as the
RuntimeError that becomes an ERROR verdict here.
"""

import logging
import struct
from collections.abc import Callable

logger = logging.getLogger(__name__)

GRID_SIZE = 3

CELL_MISMATCH_TOLERANCE = 0.01

# Point, PointZ and PointM records store a bare coordinate where every other type has a bbox.
POINT_SHAPE_TYPES = {1, 11, 21}

BBox = tuple[float, float, float, float]


def parse_shp_bboxes(data: bytes, label: str = ".shp") -> "list[BBox | None] | None":
    """Each record's bounding box, parsed from a .shp file's bytes, or None if malformed.

    `label` names the file in log messages. Null-shape records give None.

    Never consults the .sbn/.sbx index, which is what makes it a usable truth baseline.
    Jumps past each record's vertex array via its declared content-length rather than
    decoding it, where nearly all of a full GDAL feature scan's cost actually is.
    """
    bboxes: list[BBox | None] = []
    pos = 100  # fixed 100-byte file header
    try:
        while pos < len(data):
            content_length = struct.unpack(">i", data[pos + 4 : pos + 8])[0] * 2
            # Every record holds at least its shape type; a corrupt length below that would
            # stop pos advancing and loop forever.
            if content_length < 4:
                logger.warning(f"malformed .shp record length {content_length} at byte {pos} in {label}")
                return None
            shape_type = struct.unpack("<i", data[pos + 8 : pos + 12])[0]
            if shape_type == 0:
                bboxes.append(None)
            elif shape_type in POINT_SHAPE_TYPES:
                x, y = struct.unpack("<dd", data[pos + 12 : pos + 28])
                bboxes.append((x, y, x, y))
            else:
                bboxes.append(struct.unpack("<dddd", data[pos + 12 : pos + 44]))
            pos += 8 + content_length
    except struct.error as exc:
        logger.warning(f"malformed .shp record in {label}: {exc}")
        return None
    return bboxes


def make_grid(minx: float, miny: float, maxx: float, maxy: float, n: int = GRID_SIZE) -> list[BBox]:
    """n x n cells over the extent - catches corruption localized to part of the extent that
    a single whole-extent query would miss."""
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


def truth_count(bboxes: "list[BBox | None]", cell: BBox) -> int:
    cminx, cminy, cmaxx, cmaxy = cell
    return sum(
        1 for b in bboxes if b is not None and b[2] >= cminx and b[0] <= cmaxx and b[3] >= cminy and b[1] <= cmaxy
    )


def indexed_count(layer, cell: BBox) -> int:
    layer.SetSpatialFilterRect(*cell)
    count = layer.GetFeatureCount(force=0)
    layer.SetSpatialFilter(None)
    return count


def cells_mismatch(indexed: int, truth: int) -> bool:
    """Tolerant rather than exact: GDAL filters by real geometry while the truth baseline only
    has bounding boxes, so a polygon whose bbox straddles a grid line lands in a neighbouring
    cell's truth count. Measured on real data, that noise stays within CELL_MISMATCH_TOLERANCE
    per cell, while genuine corruption drops counts by 90%+ - the two regimes don't overlap.
    """
    return abs(indexed - truth) > max(2, CELL_MISMATCH_TOLERANCE * max(indexed, truth))


def check_spatial_index(
    layer,
    load_bboxes: "Callable[[], list[BBox | None] | None]",
    label: str = "layer",
) -> dict:
    """Validate one open shapefile layer's .sbn/.sbx index.

    Args:
        layer: an open OGR shapefile layer.
        load_bboxes: returns the layer's truth bboxes (e.g. parse_shp_bboxes over its .shp
            bytes), or None if they couldn't be read. Called only when an index is present,
            so an indexless layer costs no read.
        label: names the layer in log messages.

    Returns:
        `{"present": bool | None, "status": str | None}`. `status` is CONSISTENT,
        INCONSISTENT or ERROR, and None when there is no index to check. `present` is
        informational only - GDAL reports a corrupted index as usable, which is why this
        comparison exists at all.
    """
    try:
        present = bool(layer.TestCapability("FastSpatialFilter"))
        minx, maxx, miny, maxy = layer.GetExtent()
        if not present:
            return {"present": False, "status": None}

        bboxes = load_bboxes()
        if bboxes is None:
            return {"present": True, "status": "ERROR"}

        for cell in make_grid(minx, miny, maxx, maxy):
            if cells_mismatch(indexed_count(layer, cell), truth_count(bboxes, cell)):
                return {"present": True, "status": "INCONSISTENT"}
        return {"present": True, "status": "CONSISTENT"}
    except RuntimeError as exc:
        # A compression quirk lands here: the layer lists fine, but reading its data fails.
        logger.warning(f"spatial index check failed for {label}: {exc}")
        return {"present": None, "status": "ERROR"}
