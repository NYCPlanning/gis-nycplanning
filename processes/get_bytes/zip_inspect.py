"""Zip-level and dataset-level inspection - everything depth 1 adds over depth 0.

One pass per zip. 

"zip_level" is the container's object inventory - one entry per shapefile, .gdb, lock file or
loose file, rather than per zip member. "dataset_level" describes what is inside each of those datasets. 

The two answer different questions, so a .gdb appears once in zip_level, naming its feature classes,
and once per feature class in dataset_level.

The product-agnostic pieces - archive discovery and inventory, the spatial-index check, table
profiling - live in dcpgis. This module adds the PLUTO rules and the observed-JSON shape.
"""

import posixpath
import re
import zipfile

from osgeo import gdal, ogr

from dcpgis import archive
from dcpgis.validate import spatial_index, tabular
from dcpgis.web.remote_zip import get_zip_central_directory, get_zip_member_bytes

# Without this, a failed open returns None instead of raising, so the crash happens one
# call later as a confusing AttributeError.
gdal.UseExceptions()

UNCLIPPED_PATTERN = re.compile(r"unclipped|water included|\bwi\b", re.IGNORECASE)
# The code runs straight into a name (BKMapPLUTO) or a version (MN05D), so under IGNORECASE any
# letter, digit or underscore may follow and only punctuation rules a match out. An unrelated
# stem that merely starts with a code (e.g. "sidewalk") would therefore read as a borough.
BOROUGH_PATTERN = re.compile(r"^(bx|bk|mn|qn|si)(?=[_\dA-Z]|$)", re.IGNORECASE)


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


# --- spatial index validation, over a remote zip ---------------------------------------


def read_shp_bboxes(url: str, member_name: str, session) -> "list[spatial_index.BBox | None] | None":
    """The truth bboxes for one .shp inside a remote zip, or None if it can't be fetched or
    parsed."""
    data = get_zip_member_bytes(url, member_name, session)
    if data is None:
        return None
    return spatial_index.parse_shp_bboxes(data, label=f"{member_name!r} from {url}")


def check_layer_spatial_index(layer, url: str, posix_path: str, session) -> dict:
    """Validate one already-open shapefile layer's .sbn/.sbx index.

    Takes a live layer rather than a path, so the caller's single OpenEx covers both layer
    discovery and this check. The truth read goes over ranged HTTP, and only once the layer
    reports an index.
    """
    return spatial_index.check_spatial_index(
        layer,
        lambda: read_shp_bboxes(url, posix_path, session),
        label=f"{posix_path} in {url}",
    )


# --- dataset-level entries --------------------------------------------------------------


def dataset_entry(
    path_in_zip: str,
    name: str,
    type_: str,
    *,
    encoding: "str | None" = None,
    row_count: "int | None" = None,
    col_count: "int | None" = None,
) -> dict:
    """One dataset_level entry, its extent taken from `name` (the dataset's own name).

    `dataset` and `sub_dataset` are placeholders here: build_dataset_level fills both in once
    the whole zip has been seen, since sub_dataset depends on the zip's other entries.
    """
    return {
        "dataset": None,
        "sub_dataset": "",
        "path_in_zip": path_in_zip,
        "geog_extent": extent_from_filename(name),
        "type": type_,
        "encoding": encoding,
        "row_count": row_count,
        "col_count": col_count,
    }


def read_tabular_entry(url: str, member_name: str, session) -> "dict | None":
    """One standalone .csv/.txt member, via ranged HTTP and stdlib csv - no GDAL here.

    PLUTO's pre-2015 files predate UTF-8, which is what profile_table's encoding fallback is
    for.
    """
    data = get_zip_member_bytes(url, member_name, session)
    if data is None:
        return None

    profile = tabular.profile_table(data, label=f"{member_name!r} in {url}")
    stem = posixpath.splitext(posixpath.basename(member_name))[0]
    return dataset_entry(
        to_windows_path(member_name),
        stem,
        "txt" if member_name.lower().endswith(".txt") else "csv",
        encoding=profile["encoding"],
        row_count=profile["row_count"],
        col_count=profile["col_count"],
    )


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

        entry = dataset_entry(path_in_zip, name, type_, row_count=row_count, col_count=col_count)
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
        entries.append(dataset_entry(to_windows_path(gdb_path, raster), raster, "gdb_raster"))
    return entries


# --- the two depth-1 builders -------------------------------------------------------------


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
    """A .gdb's contents come from dataset_level, already resolved, rather than a second GDAL
    pass. The inventory still names shapefiles in archives GDAL can't open, such as the 20vN
    releases."""
    return {
        "filename": posixpath.basename(url),
        "obs_size_bytes": total_size,
        "objects": archive.build_object_inventory(infolist, gdb_contents(dataset_level), unreadable),
    }


def failed_zip_level(url: str, reason: str) -> dict:
    """zip_level for an archive whose inspection could not finish.

    `objects` is None rather than [] for the same reason an unreadable .gdb's `contents` is:
    "could not look" must stay distinguishable from "empty". The `error` key is what reports
    and --resume key off.
    """
    return {
        "filename": posixpath.basename(url),
        "obs_size_bytes": None,
        "objects": None,
        "error": reason,
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

    for gdb_path in archive.discover_gdb_folders(names):
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

    for dir_path in archive.discover_loose_dirs(names):
        folder_vsi = f"{vsi_prefix}/{dir_path}" if dir_path else vsi_prefix
        collect(layers_from_vsi(folder_vsi, dir_path, None, url, session, check_index), dir_path)

    for nested_zip in archive.discover_nested_zips(names):
        collect(
            layers_from_vsi(
                f"/vsizip/{vsi_prefix}/{nested_zip}",
                nested_zip,
                None,
                url,
                session,
                # The index check's truth read goes over ranged HTTP, which only reaches members
                # of the outer zip, so it would report ERROR for every shapefile in here.
                check_index=False,
            ),
            nested_zip,
        )

    for tabular_file in archive.discover_tabular_files(names):
        entry = read_tabular_entry(url, tabular_file, session)
        if entry is not None:
            entries.append(entry)

    # No counts to report, but recorded anyway so PDFs aren't silently dropped from the
    # inventory.
    for pdf_file in archive.discover_pdf_files(names):
        stem = posixpath.splitext(posixpath.basename(pdf_file))[0]
        entries.append(dataset_entry(to_windows_path(pdf_file), stem, "pdf"))

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
) -> "tuple[dict, list[dict]]":
    """One zip's (zip_level, dataset_level).

    The central directory is fetched once here and shared with both halves.

    dataset_level is built first because zip_level's inventory names each .gdb's contents
    from it, rather than opening the archive a second time.
    """
    result = get_zip_central_directory(url, session)
    if result is None:
        return failed_zip_level(url, "central directory could not be read"), []
    infolist, total_size = result
    names = [info.filename for info in infolist]

    dataset_level, unreadable = build_dataset_level(
        url, names, dataset_name, sibling_has_unclipped, session, check_index
    )
    zip_level = build_zip_level(url, infolist, total_size, dataset_level, unreadable)
    return zip_level, dataset_level
