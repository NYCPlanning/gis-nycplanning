"""Zip-level and dataset-level inspection - everything depth 1 adds over depth 0.

One pass per zip. 

"zip_level" is the container's object inventory - one entry per shapefile, .gdb, lock file or
loose file, rather than per zip member. "dataset_level" describes what is inside each of those datasets. 

The two answer different questions, so a .gdb appears once in zip_level, naming its feature classes, 
and once per feature class in dataset_level.
"""

import csv
import io
import posixpath
import re
import struct
import zipfile

from osgeo import gdal, ogr

from processes.get_bytes.common import get_zip_central_directory, get_zip_member_bytes

# Without this, a failed open returns None instead of raising, so the crash happens one
# call later as a confusing AttributeError.
gdal.UseExceptions()

GRID_SIZE = 3

CELL_MISMATCH_TOLERANCE = 0.01

UNCLIPPED_PATTERN = re.compile(r"unclipped|water included|\bwi\b", re.IGNORECASE)
BOROUGH_PATTERN = re.compile(r"^(bx|bk|mn|qn|si)(?=_|[A-Z]|$)", re.IGNORECASE)

TABULAR_ENCODINGS = ("utf-8", "cp1252", "latin-1")


def configure_gdal() -> None:
    """Benchmarked tuning for vsicurl-heavy work. Call once at startup - SetConfigOption is
    process-global, not thread-local."""
    for key, value in {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_CHUNK_SIZE": "2097152",
        "CPL_VSIL_CURL_CACHE_SIZE": "67108864",
        "VSI_CACHE": "YES",
        "VSI_CACHE_SIZE": "67108864",
        "GDAL_HTTP_MULTIPLEX": "YES",
    }.items():
        gdal.SetConfigOption(key, value)


# --- pure helpers ---------------------------------------------------------------------


def has_unclipped_signal(text: str) -> bool:
    return bool(UNCLIPPED_PATTERN.search(text))


def extent_from_filename(name: str) -> str:
    """'BKMapPLUTO' -> 'bk'; 'MapPLUTO_25v2_clipped' -> 'citywide'.

    Derived from the dataset's own name, never its containing directory - some zips (e.g.
    mappluto_17v1_1.zip) bundle all five boroughs inside one folder misleadingly named
    'citywide/'.
    """
    match = BOROUGH_PATTERN.match(name)
    return match.group(1).lower() if match else "citywide"


def to_windows_path(*parts: str) -> str:
    return "/".join(p for p in parts if p).replace("/", "\\")


def apply_mappluto_sub_dataset(entries: list[dict], sibling_has_unclipped: bool) -> None:
    """MapPLUTO-specific clipped/unclipped label, kept out of the generic discovery logic
    since other products have no such concept.

    Mutates in place across one zip's entries, because the answer for any single entry
    depends on what else was found alongside it. Not derived from a version/year cutoff -
    that was tried and found wrong, since some pre-2019 zips already bundle both variants.
    """
    zip_has_internal_split = any(has_unclipped_signal(e["path_in_zip"]) for e in entries)
    for entry in entries:
        if has_unclipped_signal(entry["path_in_zip"]):
            entry["sub_dataset"] = "unclipped"
        elif zip_has_internal_split or sibling_has_unclipped:
            entry["sub_dataset"] = "clipped"
        else:
            entry["sub_dataset"] = ""


def find_versions_with_unclipped_sibling(entries: list[dict]) -> set[tuple[str, str]]:
    """(version, type) pairs whose zip is the unclipped variant - signals that a
    complementary clipped zip exists as its own separate entry."""
    return {
        (e["url_level"]["version"], e["url_level"]["type"])
        for e in entries
        if has_unclipped_signal(e["identifier"]) or has_unclipped_signal(e["url_level"]["url_actual"])
    }


# --- discovery over a flat namelist ----------------------------------------------------


def discover_gdb_folders(names: list[str]) -> list[str]:
    folders = set()
    for name in names:
        idx = name.lower().find(".gdb/")
        if idx != -1:
            folders.add(name[: idx + 4])
    return sorted(folders)


def discover_loose_dirs(names: list[str]) -> list[str]:
    """Parent directories ('' for top level) holding at least one .shp or standalone .dbf.

    Gated on those actually being present: a directory of only PDFs can never be identified
    by the Shapefile driver, so there is no point asking GDAL to try.
    """
    dirs = set()
    for name in names:
        lower = name.lower()
        if ".gdb/" in lower or lower.endswith(".zip"):
            continue
        if lower.endswith((".shp", ".dbf")):
            dirs.add(posixpath.dirname(name))
    return sorted(dirs)


def discover_nested_zips(names: list[str]) -> list[str]:
    return sorted(n for n in names if n.lower().endswith(".zip"))


def _discover_by_suffix(names: list[str], suffixes: tuple[str, ...]) -> list[str]:
    found = []
    for name in names:
        lower = name.lower()
        if ".gdb/" in lower or lower.endswith(".zip"):
            continue
        if lower.endswith(suffixes):
            found.append(name)
    return sorted(found)


def discover_tabular_files(names: list[str]) -> list[str]:
    """Standalone .csv/.txt members. 

    Skips .gdb-internal files (a gdb's tabular data already arrives as layers) and nested zips."""
    return _discover_by_suffix(names, (".csv", ".txt"))


def discover_pdf_files(names: list[str]) -> list[str]:
    return _discover_by_suffix(names, (".pdf",))


# --- spatial index validation ----------------------------------------------------------


def read_shp_bboxes(url: str, member_name: str, session) -> "list[tuple[float, float, float, float] | None] | None":
    """Each record's bounding box, parsed straight out of the .shp binary.

    Never consults the .sbn/.sbx index, which is what makes it a usable truth baseline.
    Jumps past each record's vertex array via its declared content-length rather than
    decoding it, where nearly all of a full GDAL feature scan's cost actually is.
    """
    data = get_zip_member_bytes(url, member_name, session)
    if data is None:
        return None

    bboxes: list[tuple[float, float, float, float] | None] = []
    pos = 100  # fixed 100-byte file header
    try:
        while pos < len(data):
            content_length = struct.unpack(">i", data[pos + 4 : pos + 8])[0] * 2
            shape_type = struct.unpack("<i", data[pos + 8 : pos + 12])[0]
            if shape_type == 0:
                bboxes.append(None)
            else:
                bboxes.append(struct.unpack("<dddd", data[pos + 12 : pos + 44]))
            pos += 8 + content_length
    except struct.error as exc:
        print(f"WARNING: malformed .shp record in {member_name!r} from {url}: {exc}")
        return None
    return bboxes


def make_grid(
    minx: float, miny: float, maxx: float, maxy: float, n: int = GRID_SIZE
) -> list[tuple[float, float, float, float]]:
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


def truth_count(
    bboxes: "list[tuple[float, float, float, float] | None]",
    cell: tuple[float, float, float, float],
) -> int:
    cminx, cminy, cmaxx, cmaxy = cell
    return sum(
        1 for b in bboxes if b is not None and b[2] >= cminx and b[0] <= cmaxx and b[3] >= cminy and b[1] <= cmaxy
    )


def indexed_count(layer, cell: tuple[float, float, float, float]) -> int:
    layer.SetSpatialFilterRect(*cell)
    count = layer.GetFeatureCount(force=0)
    layer.SetSpatialFilter(None)
    return count


def cells_mismatch(indexed: int, truth: int) -> bool:
    """Tolerant rather than exact: GDAL filters by real geometry while the truth baseline only
    has bounding boxes, so a polygon whose bbox straddles a grid line lands in a neighbouring
    cell's truth count. Measured on real data, that noise stays under 1% per cell, while
    genuine corruption drops counts by 90%+ - the two regimes don't overlap.
    """
    return abs(indexed - truth) > max(2, CELL_MISMATCH_TOLERANCE * max(indexed, truth))


def check_layer_spatial_index(layer, url: str, posix_path: str, session) -> dict:
    """Validate one already-open shapefile layer's .sbn/.sbx index.

    Takes a live layer rather than a path, so the caller's single OpenEx covers both layer
    discovery and this check. `present` is informational only - GDAL reports a corrupted
    index as usable, which is why this comparison exists at all.
    """
    try:
        present = bool(layer.TestCapability("FastSpatialFilter"))
        minx, maxx, miny, maxy = layer.GetExtent()
        if not present:
            return {"present": False, "status": None}

        bboxes = read_shp_bboxes(url, posix_path, session)
        if bboxes is None:
            return {"present": True, "status": "ERROR"}

        for cell in make_grid(minx, miny, maxx, maxy):
            if cells_mismatch(indexed_count(layer, cell), truth_count(bboxes, cell)):
                return {"present": True, "status": "INCONSISTENT"}
        return {"present": True, "status": "CONSISTENT"}
    except RuntimeError as exc:
        # A compression quirk lands here: the layer lists fine, but reading its data fails.
        # (initially observed with pluto 20vN)
        print(f"WARNING: spatial index check failed for {posix_path} in {url}: {exc}")
        return {"present": None, "status": "ERROR"}


# --- dataset-level entries --------------------------------------------------------------


def read_tabular_entry(url: str, member_name: str, session) -> "dict | None":
    """One standalone .csv/.txt member, via ranged HTTP and stdlib csv - no GDAL here.

    Encoding order: PLUTO's pre-2015 files predate UTF-8, a few use bytes cp1252
    leaves undefined, and latin-1 decodes every byte, so it's the guaranteed fallback. No
    delimiter sniffing - csv.reader counts rows correctly regardless, and sniffing broke on
    really wide, space-padded files.
    """
    data = get_zip_member_bytes(url, member_name, session)
    if data is None:
        return None

    text = ""
    encoding = None
    for candidate in TABULAR_ENCODINGS:
        try:
            text = data.decode(candidate)
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue

    row_count = None
    col_count = None
    if not text.strip():
        print(f"WARNING: {member_name!r} in {url} is empty")
    else:
        try:
            reader = csv.reader(io.StringIO(text))
            header = next(reader, None)
            col_count = len(header) if header else None
            row_count = sum(1 for _ in reader)
        except csv.Error as exc:
            print(f"WARNING: could not parse {member_name!r} in {url}: {exc}")

    stem = posixpath.splitext(posixpath.basename(member_name))[0]
    return {
        "dataset": None,  # filled in by build_dataset_level
        "sub_dataset": "",
        "path_in_zip": to_windows_path(member_name),
        "geog_extent": extent_from_filename(stem),
        "type": "txt" if member_name.lower().endswith(".txt") else "csv",
        "encoding": encoding,
        "row_count": row_count,
        "col_count": col_count,
    }


def layers_from_vsi(
    vsi_path: str,
    path_prefix: str,
    gdb_path: "str | None",
    url: str,
    session,
    check_index: bool,
) -> "list[dict] | None":
    """Open one datasource and return an entry per layer it contains, or None if it could not
    be read at all.

    None rather than [] on failure, because zip_level's inventory has to tell "GDAL could not
    open this" apart from "this really is empty".

    `gdb_path` set means this is a .gdb folder (layers become gdb_fc/gdb_tb, path_in_zip is
    the gdb path plus layer name); None means a shapefile-style directory (layers become
    shp/dbf, path_in_zip is reconstructed with the matching extension).

    Opening a directory-like VSI path with the Shapefile driver yields one layer per .shp
    bundle plus one per standalone .dbf - the grouping this needs, for free.
    """
    try:
        # OF_RASTER is the only way
        # GetSubDatasets() can see a gdb's rasters.
        dataset = gdal.OpenEx(vsi_path, gdal.OF_VECTOR | gdal.OF_RASTER)
    except RuntimeError as exc:
        print(f"WARNING: could not open {vsi_path}: {exc}")
        return None
    if dataset is None:
        print(f"WARNING: could not open {vsi_path}")
        return None

    try:
        layer_count = dataset.GetLayerCount()
    except RuntimeError as exc:
        print(f"WARNING: could not list layers in {vsi_path}: {exc}")
        return None

    entries = []
    for i in range(layer_count):
        # GetLayer is inside the try too: the Shapefile driver defers opening each member, so a
        # corrupt .shp raises here rather than at OpenEx - catching it per layer saves the rest
        # of the datasource instead of losing the whole zip.
        try:
            layer = dataset.GetLayer(i)
            name = layer.GetName()
            spatial = layer.GetGeomType() != ogr.wkbNone
            row_count = layer.GetFeatureCount()
            col_count = layer.GetLayerDefn().GetFieldCount()
        except RuntimeError as exc:
            print(f"WARNING: could not read layer {i} in {vsi_path}: {exc}")
            continue

        if gdb_path is not None:
            type_ = "gdb_fc" if spatial else "gdb_tb"
            path_in_zip = to_windows_path(gdb_path, name)
        else:
            type_ = "shp" if spatial else "dbf"
            path_in_zip = to_windows_path(path_prefix, f"{name}{'.shp' if spatial else '.dbf'}")

        entry = {
            "dataset": None,  # filled in by build_dataset_level
            "sub_dataset": "",
            "path_in_zip": path_in_zip,
            "geog_extent": extent_from_filename(name),
            "type": type_,
            "encoding": None,
            "row_count": row_count,
            "col_count": col_count,
        }
        # .gdb layers use .spx, a different mechanism that this check does not cover.
        if check_index and type_ == "shp":
            entry["spatial_index"] = check_layer_spatial_index(layer, url, path_in_zip.replace("\\", "/"), session)
        entries.append(entry)

    if gdb_path is not None:
        entries.extend(raster_entries(dataset, gdb_path, vsi_path))
    return entries


def raster_entries(dataset, gdb_path: str, vsi_path: str) -> list[dict]:
    """A .gdb's raster datasets, invisible to the layer API.

    GDAL names each subdataset `DRIVER:"source":name`, but quoting varies by driver, so only
    the trailing segment is taken rather than the whole string parsed. No observed archive has
    one yet, so this path is covered by unit test only.
    """
    try:
        subdatasets = dataset.GetSubDatasets()
    except RuntimeError as exc:
        print(f"WARNING: could not list rasters in {vsi_path}: {exc}")
        return []

    entries = []
    for name, _description in subdatasets:
        raster = name.rsplit(":", 1)[-1].strip('"')
        entries.append(
            {
                "dataset": None,
                "sub_dataset": "",
                "path_in_zip": to_windows_path(gdb_path, raster),
                "geog_extent": extent_from_filename(raster),
                "type": "gdb_raster",
                "encoding": None,
                "row_count": None,
                "col_count": None,
            }
        )
    return entries


# --- the two depth-1 builders -------------------------------------------------------------


def object_key(path: str, shp_bases: set[str]) -> tuple[str, str]:
    """Which object a zip member belongs to, and that object's kind.

    Lock files are tested before the .gdb prefix so they stay top-level: whether an archive
    ships one is the question being asked, and folding them into the gdb would hide it.
    """
    lower = path.lower()
    if lower.endswith(".lock"):
        return path, "lock"

    idx = lower.find(".gdb/")
    if idx != -1:
        return path[: idx + 4], "gdb"

    if lower.endswith(".zip"):
        return path, "zip"

    base, ext = shapefile_split(path)
    if base in shp_bases:
        return f"{base}.shp", "shapefile"
    if ext in (".csv", ".txt", ".dbf"):
        return path, "table"
    return path, "file"


def shapefile_split(path: str) -> tuple[str, str]:
    """(basename, extension), treating .shp.xml as one extension so the metadata sidecar
    groups with its shapefile rather than looking like a lone .xml."""
    lower = path.lower()
    if lower.endswith(".shp.xml"):
        return path[: -len(".shp.xml")], ".shp.xml"
    base, ext = posixpath.splitext(path)
    return base, ext.lower()


def build_object_inventory(
    infolist: list[zipfile.ZipInfo],
    dataset_level: list[dict],
    unreadable: set[str],
) -> list[dict]:
    """What the archive holds, as objects rather than files.

    Grouping is filename-only, so it still names a shapefile inside an archive GDAL cannot
    open - the information otherwise lost on the 20vN releases. A .gdb's contents come from
    dataset_level, already resolved, rather than from a second GDAL pass.
    """
    files = [i for i in infolist if not i.is_dir()]
    shp_bases = {shapefile_split(i.filename)[0] for i in files if i.filename.lower().endswith(".shp")}

    objects: dict[str, dict] = {}
    parts: dict[str, set[str]] = {}
    for info in files:
        key, kind = object_key(info.filename, shp_bases)
        obj = objects.setdefault(key, {"path": key, "kind": kind, "size_bytes": 0})
        obj["size_bytes"] += info.file_size
        if kind == "shapefile":
            parts.setdefault(key, set()).add(shapefile_split(info.filename)[1])

    contents = gdb_contents(dataset_level)
    for key, obj in objects.items():
        if obj["kind"] == "shapefile":
            obj["parts"] = sorted(parts[key])
        elif obj["kind"] == "gdb":
            obj["contents"] = None if key in unreadable else contents.get(key, [])
    return sorted(objects.values(), key=lambda o: o["path"])


def gdb_contents(dataset_level: list[dict]) -> dict[str, list[dict]]:
    """Each .gdb's datasets as Pro or QGIS would list them, keyed by gdb path."""
    kinds = {"gdb_fc": "feature_class", "gdb_tb": "table", "gdb_raster": "raster"}
    found: dict[str, list[dict]] = {}
    for entry in dataset_level:
        kind = kinds.get(entry["type"])
        if kind is None:
            continue
        path = entry["path_in_zip"].replace("\\", "/")
        idx = path.lower().find(".gdb/")
        if idx == -1:
            continue
        found.setdefault(path[: idx + 4], []).append({"name": posixpath.basename(path), "kind": kind})
    return found


def build_zip_level(
    url: str,
    infolist: list[zipfile.ZipInfo],
    total_size: "int | None",
    dataset_level: list[dict],
    unreadable: set[str],
) -> dict:
    return {
        "filename": posixpath.basename(url),
        "obs_size_bytes": total_size,
        "objects": build_object_inventory(infolist, dataset_level, unreadable),
    }


def build_dataset_level(
    url: str,
    names: list[str],
    dataset_name: str,
    sibling_has_unclipped: bool,
    session,
    check_index: bool = True,
) -> "tuple[list[dict], set[str]]":
    """Every layer, table and standalone file in one zip, as dataset-level entries.

    Also returns the paths GDAL could not read, so the object inventory can say "could not
    look" instead of claiming a .gdb is empty.
    """
    vsi_prefix = f"/vsizip//vsicurl/{url}"
    entries: list[dict] = []
    unreadable: set[str] = set()

    def collect(found: "list[dict] | None", path: str) -> None:
        if found is None:
            unreadable.add(path)
        else:
            entries.extend(found)

    for gdb_path in discover_gdb_folders(names):
        collect(
            layers_from_vsi(
                f"{vsi_prefix}/{gdb_path}",
                gdb_path,
                gdb_path,
                url,
                session,
                check_index,
            ),
            gdb_path,
        )

    for dir_path in discover_loose_dirs(names):
        folder_vsi = f"{vsi_prefix}/{dir_path}" if dir_path else vsi_prefix
        collect(layers_from_vsi(folder_vsi, dir_path, None, url, session, check_index), dir_path)

    for nested_zip in discover_nested_zips(names):
        collect(
            layers_from_vsi(
                f"/vsizip/{vsi_prefix}/{nested_zip}",
                nested_zip,
                None,
                url,
                session,
                check_index,
            ),
            nested_zip,
        )

    for tabular_file in discover_tabular_files(names):
        entry = read_tabular_entry(url, tabular_file, session)
        if entry is not None:
            entries.append(entry)

    # No counts to report, but recorded anyway so PDFs aren't silently dropped from the
    # inventory.
    for pdf_file in discover_pdf_files(names):
        entries.append(
            {
                "dataset": None,
                "sub_dataset": "",
                "path_in_zip": to_windows_path(pdf_file),
                "geog_extent": extent_from_filename(posixpath.splitext(posixpath.basename(pdf_file))[0]),
                "type": "pdf",
                "encoding": None,
                "row_count": None,
                "col_count": None,
            }
        )

    apply_mappluto_sub_dataset(entries, sibling_has_unclipped)
    for entry in entries:
        entry["dataset"] = dataset_name
    return entries, unreadable


def inspect_zip(
    url: str,
    dataset_name: str,
    sibling_has_unclipped: bool,
    session,
    check_index: bool = True,
) -> "tuple[dict | None, list[dict]]":
    """One zip's (zip_level, dataset_level).

    The central directory is fetched once here and shared with both halves.

    dataset_level is built first because zip_level's inventory names each .gdb's contents
    from it, rather than opening the archive a second time.
    """
    result = get_zip_central_directory(url, session)
    if result is None:
        return None, []
    infolist, total_size = result
    names = [info.filename for info in infolist]

    dataset_level, unreadable = build_dataset_level(
        url, names, dataset_name, sibling_has_unclipped, session, check_index
    )
    zip_level = build_zip_level(url, infolist, total_size, dataset_level, unreadable)
    return zip_level, dataset_level
