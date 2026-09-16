"""Summarize the per-dataset (layer/table) contents of each shp/fgdb zip listed in
pluto_datasets.csv.

Reads pluto_datasets.csv (produced by scrape_pluto_datasets.py), opens each dataset zip
remotely via GDAL's /vsizip//vsicurl/ virtual file system (no local download), and reports
every distinct spatial layer or standalone table found inside - its row count, whether it's
spatial, and its path within the zip.

Two GDAL behaviors this leans on heavily (confirmed empirically before writing this):
- Opening a bare directory-like VSI path (a folder inside a zip, or a whole zip's root)
  with the ESRI Shapefile driver returns one layer per .shp bundle plus one table layer
  per standalone .dbf with no matching .shp - exactly the shapefile/table grouping this
  tool needs, for free.
- Nested zips (a .zip inside a zip) are handled by wrapping the whole VSI path in another
  /vsizip/, e.g. /vsizip//vsizip//vsicurl/URL/outer.zip/inner.zip - no manual byte-range
  extraction needed.
"""

import csv
import posixpath
import re
from pathlib import Path

import pyogrio

from common import get_zip_namelist, make_session

INPUT_CSV = Path(__file__).parent / "pluto_datasets.csv"
OUTPUT_CSV = Path(__file__).parent / "zip_contents.csv"
FIELDNAMES = [
    "identifier",
    "product",
    "dataset",
    "sub_dataset",
    "extent",
    "spatial",
    "row_count",
    "path_in_zip",
]

IN_SCOPE_TYPES = {"shp", "fgdb"}

# Both constants for this pass, per the instructions file - "pluto" (tabular) and other DCP
# products are future scope. Nothing in the discovery/classification logic below depends on
# these values; extending to another product means a second pass with different constants
# and a different source row filter, not touching the logic in this file.
CURRENT_PRODUCT = "mappluto"
CURRENT_DATASET = "mappluto"

UNCLIPPED_PATTERN = re.compile(r"unclipped|water included|\bwi\b", re.IGNORECASE)
BOROUGH_PATTERN = re.compile(r"^(bx|bk|mn|qn|si)(?=_|[A-Z]|$)", re.IGNORECASE)


def configure_gdal() -> None:
    """Performance tuning confirmed (via benchmark) to give a modest, free win on top of
    plain vsicurl - see the plan for the A/B timing comparison this is based on."""
    pyogrio.set_gdal_config_options(
        {
            "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
            "CPL_VSIL_CURL_CHUNK_SIZE": "2097152",
            "CPL_VSIL_CURL_CACHE_SIZE": "67108864",
            "VSI_CACHE": "YES",
            "VSI_CACHE_SIZE": "67108864",
            "GDAL_HTTP_MULTIPLEX": "YES",
        }
    )


def has_unclipped_signal(text: str) -> bool:
    return bool(UNCLIPPED_PATTERN.search(text))


def apply_mappluto_sub_dataset(rows: list[dict], sibling_has_unclipped: bool) -> None:
    """MapPLUTO-specific clipped/unclipped label - lives in its own function rather than
    the generic discovery logic below, since other products have no such concept at all.

    Mutates `sub_dataset` in place for every row already collected from *one* zip, since
    the decision for any single row depends on what else was found alongside it:
    - A row whose own path already says unclipped/wi/water included -> "unclipped".
    - Otherwise, if this zip demonstrably bundles both variants internally (some other row
      from the same zip matched above), or a sibling row in pluto_datasets.csv for the same
      version+type is the unclipped one (the modern one-zip-per-variant pattern) ->
      "clipped", the implicit default.
    - Otherwise - no evidence of an unclipped counterpart anywhere for this vintage -> "".
      (Not derived from a version/year cutoff - that was tried and found wrong: some
      pre-2019 zips, e.g. 18v1.1, already bundle both variants internally.)
    """
    zip_has_internal_split = any(has_unclipped_signal(r["path_in_zip"]) for r in rows)
    for row in rows:
        if has_unclipped_signal(row["path_in_zip"]):
            row["sub_dataset"] = "unclipped"
        elif zip_has_internal_split or sibling_has_unclipped:
            row["sub_dataset"] = "clipped"
        else:
            row["sub_dataset"] = ""


def extent_from_filename(name: str) -> str:
    """'BKMapPLUTO' -> 'bk'; 'bx_pluto' -> 'bx'; 'MapPLUTO_25v2_clipped' -> 'citywide'.

    Derived from the dataset's own name, never its containing directory - some zips (e.g.
    mappluto_17v1_1.zip) bundle all five boroughs' files together inside one real folder
    misleadingly named 'citywide/', so the directory name can't be trusted.
    """
    match = BOROUGH_PATTERN.match(name)
    return match.group(1).lower() if match else "citywide"


def to_windows_path(*parts: str) -> str:
    posix = "/".join(p for p in parts if p)
    return posix.replace("/", "\\")


def discover_gdb_folders(names: list[str]) -> list[str]:
    """Distinct '<...>.gdb' folder paths (posix-style) found in a flat zip member list."""
    folders = set()
    for name in names:
        idx = name.lower().find(".gdb/")
        if idx != -1:
            folders.add(name[: idx + 4])
    return sorted(folders)


def discover_loose_dirs(names: list[str]) -> list[str]:
    """Distinct parent directories ('' for top-level) that contain at least one shapefile
    component (.shp, or a standalone .dbf), skipping .gdb folders and nested zips.

    Gated on .shp/.dbf actually being present, mirroring discover_gdb_folders' own gate on
    .gdb - a directory holding only reference files (e.g. pluto_datadictionary.pdf sitting
    alongside a .gdb folder at a zip's root) can never be identified by the Shapefile driver,
    so there's no point asking GDAL to try.
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


def read_layer_rows(
    vsi_path: str,
    identifier: str,
    path_prefix_for_display: str,
    layer_path_key: "str | None",
) -> list[dict]:
    """Open a VSI path (a gdb folder, or a directory-like shapefile datasource) and
    return one output row per layer/table found in it. `sub_dataset` is intentionally
    left unset here - apply_mappluto_sub_dataset fills it in afterward, once every
    dataset in the containing zip has been collected (see discover_zip).

    layer_path_key is the gdb folder's own path (used verbatim in path_in_zip, no
    extension) when opening a gdb; None when opening a shapefile-style directory
    (path_in_zip is reconstructed from the layer name + inferred .shp/.dbf extension).
    """
    try:
        layers = pyogrio.list_layers(vsi_path)
    except (RuntimeError, OSError) as exc:
        # RuntimeError covers every pyogrio.errors.* exception (all derive from it);
        # OSError covers lower-level network/VSI failures.
        print(f"WARNING: could not list layers for {vsi_path}: {exc}")
        return []

    rows = []
    for name, geom_type in layers:
        spatial = geom_type is not None
        try:
            info = pyogrio.read_info(vsi_path, layer=name)
        except (RuntimeError, OSError) as exc:
            print(f"WARNING: could not read layer {name!r} in {vsi_path}: {exc}")
            continue

        if layer_path_key is not None:
            path_in_zip = to_windows_path(layer_path_key, name)
        else:
            ext = ".shp" if spatial else ".dbf"
            path_in_zip = to_windows_path(path_prefix_for_display, f"{name}{ext}")

        rows.append(
            {
                "identifier": identifier,
                "product": CURRENT_PRODUCT,
                "dataset": CURRENT_DATASET,
                "extent": extent_from_filename(name),
                "spatial": spatial,
                "row_count": info["features"],
                "path_in_zip": path_in_zip,
            }
        )
    return rows


def discover_zip(
    url: str, identifier: str, sibling_has_unclipped: bool, session
) -> list[dict]:
    names = get_zip_namelist(url, session)
    if names is None:
        return []

    vsi_prefix = f"/vsizip//vsicurl/{url}"
    rows: list[dict] = []

    for gdb_path in discover_gdb_folders(names):
        rows.extend(
            read_layer_rows(f"{vsi_prefix}/{gdb_path}", identifier, gdb_path, gdb_path)
        )

    for dir_path in discover_loose_dirs(names):
        folder_vsi = f"{vsi_prefix}/{dir_path}" if dir_path else vsi_prefix
        rows.extend(read_layer_rows(folder_vsi, identifier, dir_path, None))

    for nested_zip in discover_nested_zips(names):
        nested_vsi = f"/vsizip/{vsi_prefix}/{nested_zip}"
        rows.extend(read_layer_rows(nested_vsi, identifier, nested_zip, None))

    apply_mappluto_sub_dataset(rows, sibling_has_unclipped)
    return rows


def find_versions_with_unclipped_sibling(
    source_rows: list[dict],
) -> set[tuple[str, str]]:
    """(version, type) pairs where some pluto_datasets.csv row for that pair is the
    unclipped variant - signals "the complementary clipped zip for this version/type
    exists as a separate row" for zips that don't bundle both variants internally.
    """
    return {
        (row["version"], row["type"])
        for row in source_rows
        if has_unclipped_signal(row["identifier"]) or has_unclipped_signal(row["url"])
    }


def main() -> None:
    configure_gdal()
    session = make_session()

    with INPUT_CSV.open(newline="", encoding="utf-8") as f:
        source_rows = [
            row for row in csv.DictReader(f) if row["type"] in IN_SCOPE_TYPES
        ]

    unclipped_siblings = find_versions_with_unclipped_sibling(source_rows)

    print(
        f"Processing {len(source_rows)} rows with type in {sorted(IN_SCOPE_TYPES)}..."
    )

    all_rows: list[dict] = []
    for i, row in enumerate(source_rows, 1):
        sibling_has_unclipped = (row["version"], row["type"]) in unclipped_siblings
        try:
            found = discover_zip(
                row["url"], row["identifier"], sibling_has_unclipped, session
            )
        except (RuntimeError, OSError) as exc:
            print(
                f"WARNING: failed processing {row['identifier']} ({row['url']}): {exc}"
            )
            found = []
        if not found:
            print(f"WARNING: no datasets found in {row['identifier']} ({row['url']})")
        print(f"[{i}/{len(source_rows)}] {row['identifier']}: {len(found)} dataset(s)")
        all_rows.extend(found)

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
