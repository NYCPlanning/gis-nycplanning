"""Derived reports - pure functions of the observed JSON.

Nothing here touches the network or re-reads another report. Every value is pulled from the
observed structure the scrape already produced, which is what makes these cheap to regenerate
and impossible to drift out of sync with each other.
"""

import csv
import posixpath
from collections import Counter, defaultdict
from pathlib import Path

from processes.get_bytes import pluto_lineage

URL_REPORT_FIELDS = [
    "identifier",
    "dataset_name",
    "type",
    "version",
    "url",
    "response_code",
]
DATASET_REPORT_FIELDS = [
    "identifier",
    "product",
    "dataset_name",
    "item",
    "sub_dataset",
    "extent",
    "spatial",
    "row_count",
    "column_count",
    "type",
    "path_in_zip",
    "has_lock_files",
]
ERROR_SUMMARY_FIELDS = [
    "identifier",
    "version",
    "level",
    "path_in_zip",
    "problem",
    "detail",
    "url",
]

# Types that carry geometry.
# TODO: gdb_raster isn't included here yet - revisit once a product actually exercises this path.
SPATIAL_TYPES = {"shp", "gdb_fc"}

TABULAR_TYPES = {"csv", "txt"}

# zip_level object kinds that always yield dataset_level entries when readable. Loose files
# (PDFs, xml sidecars) are listed but never read, so their absence proves nothing.
READABLE_KINDS = {"table", "shapefile", "zip"}

# Below this, a disagreeing sibling can't be told apart from a disagreeing majority.
MIN_SIBLINGS_FOR_OUTLIER = 3


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def report_path(out_dir: Path, report: str, observed: dict) -> Path:
    return (
        Path(out_dir)
        / f"{report}_{observed['page']}_{observed['initiated_timestamp']}.csv"
    )


def build_url_rows(observed: dict) -> list[dict]:
    return [
        {
            "identifier": entry["identifier"],
            "dataset_name": entry["url_level"]["dataset_name"],
            "type": entry["url_level"]["type"],
            "version": entry["url_level"]["version"],
            "url": entry["url_level"]["url_actual"],
            "response_code": entry["url_level"]["response_code"],
        }
        for entry in observed["entries"]
    ]


def lock_objects(entry: dict) -> list[dict]:
    zip_level = entry.get("zip_level") or {}
    return [obj for obj in zip_level.get("objects") or [] if obj["kind"] == "lock"]


def build_dataset_rows(observed: dict) -> list[dict]:
    """One row per dataset_level entry. `item`, `spatial` and `has_lock_files` are derived here
    rather than stored in the JSON"""
    rows = []
    for entry in observed["entries"]:
        has_lock_files = bool(lock_objects(entry)) if entry.get("zip_level") else ""
        for dataset in entry.get("dataset_level") or []:
            item = pluto_lineage.item_for(dataset["path_in_zip"])
            rows.append(
                {
                    "identifier": entry["identifier"],
                    "product": entry["url_level"]["product"],
                    "dataset_name": entry["url_level"]["dataset_name"],
                    "item": item,
                    "sub_dataset": dataset["sub_dataset"]
                    if item in pluto_lineage.CLIPPED_ITEMS
                    else "",
                    "extent": dataset["geog_extent"],
                    "spatial": dataset["type"] in SPATIAL_TYPES,
                    "row_count": dataset["row_count"],
                    "column_count": dataset["col_count"],
                    "type": dataset["type"],
                    "path_in_zip": dataset["path_in_zip"],
                    "has_lock_files": has_lock_files,
                }
            )
    return rows


def _problem(
    entry: dict, level: str, problem: str, path_in_zip: str = "", detail: str = ""
) -> dict:
    return {
        "identifier": entry["identifier"],
        "version": entry["url_level"]["version"],
        "level": level,
        "path_in_zip": path_in_zip,
        "problem": problem,
        "detail": detail,
        "url": entry["url_level"]["url_actual"],
    }


def find_broken_links(entry: dict) -> list[dict]:
    # None or "" means the request itself failed - a different claim from "the server said
    # this is missing" - so it isn't reported as a broken link.
    code = entry["url_level"]["response_code"]
    if code in (None, "", 200, 206):
        return []
    return [_problem(entry, "url", "broken_link", detail=str(code))]


def find_incorrect_file(entry: dict) -> list[dict]:
    """The page labels a link with one release but the file it serves names another.

    Catches the page listing the same zip under two versions, flagging only the wrong one.
    """
    url_level = entry["url_level"]
    filename = posixpath.splitext(posixpath.basename(url_level["url_actual"]))[0]
    served = pluto_lineage.version_token(filename)
    labelled = pluto_lineage.version_token(url_level["version"])
    if served is None or labelled is None or served == labelled:
        return []
    detail = f"labelled {url_level['version']}, file is {served}"
    return [_problem(entry, "url", "incorrect_file", detail=detail)]


def find_unreadable_zips(entry: dict) -> list[dict]:
    """Zips whose inspection failed outright, so none of their contents were checked.

    Skipped when the link itself is broken: the url-level row already names that cause.
    """
    error = (entry.get("zip_level") or {}).get("error")
    if not error or find_broken_links(entry):
        return []
    return [_problem(entry, "zip", "unreadable_zip", detail=error)]


def find_extra_zip_nesting(entry: dict) -> list[dict]:
    if entry["url_level"]["type"] != "unknown":
        return []
    return [_problem(entry, "zip", "extra_zip_nesting")]


def find_lock_files(entry: dict) -> list[dict]:
    """One row per lock file, naming it in path_in_zip."""
    return [
        _problem(entry, "zip", "has_lock_files", path_in_zip=obj["path"])
        for obj in lock_objects(entry)
    ]


def find_corrupted_spatial_indexes(entry: dict) -> list[dict]:
    problems = []
    for dataset in entry.get("dataset_level") or []:
        spatial_index = dataset.get("spatial_index") or {}
        if spatial_index.get("status") == "INCONSISTENT":
            problems.append(
                _problem(
                    entry,
                    "file",
                    "corrupted_spatial_index",
                    path_in_zip=dataset["path_in_zip"],
                )
            )
    return problems


def find_corrupted_files(entry: dict) -> list[dict]:
    return (
        _unparseable_tables(entry)
        + _column_count_outliers(entry)
        + _unread_objects(entry)
        + _failed_spatial_index_checks(entry)
    )


def _failed_spatial_index_checks(entry: dict) -> list[dict]:
    """Shapefiles GDAL could list but whose records could not be read back to check the index
    against - left out, they would pass as clean."""
    return [
        _problem(
            entry,
            "file",
            "corrupted_file",
            path_in_zip=dataset["path_in_zip"],
            detail="spatial index could not be checked",
        )
        for dataset in entry.get("dataset_level") or []
        if (dataset.get("spatial_index") or {}).get("status") == "ERROR"
    ]


def _unparseable_tables(entry: dict) -> list[dict]:
    return [
        _problem(
            entry,
            "file",
            "corrupted_file",
            path_in_zip=dataset["path_in_zip"],
            detail="rows could not be parsed",
        )
        for dataset in entry.get("dataset_level") or []
        if dataset["type"] in TABULAR_TYPES and dataset["row_count"] is None
    ]


def _column_count_outliers(entry: dict) -> list[dict]:
    """Members of one item within a zip - typically its borough splits - should agree on
    their columns, so one that disagrees with a clear majority is suspect."""
    groups: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
    for dataset in entry.get("dataset_level") or []:
        item = pluto_lineage.item_for(dataset["path_in_zip"])
        # Unclassified files are unrelated to each other, so they have no siblings to agree with.
        if dataset["col_count"] is None or item == pluto_lineage.NOT_CLASSIFIED:
            continue
        groups[(item, dataset["type"])].append(dataset)

    problems = []
    for members in groups.values():
        if len(members) < MIN_SIBLINGS_FOR_OUTLIER:
            continue
        ((typical, votes),) = Counter(m["col_count"] for m in members).most_common(1)
        if votes * 2 <= len(members):
            continue
        for member in members:
            if member["col_count"] != typical:
                detail = f"{member['col_count']} columns; siblings have {typical}"
                problems.append(
                    _problem(
                        entry,
                        "file",
                        "corrupted_file",
                        path_in_zip=member["path_in_zip"],
                        detail=detail,
                    )
                )
    return problems


def _unread_objects(entry: dict) -> list[dict]:
    """Data the archive lists but inspection never produced - a damaged member, or one in a
    compression format the readers don't support."""
    zip_level = entry.get("zip_level") or {}
    read = [
        d["path_in_zip"].replace("\\", "/").lower()
        for d in entry.get("dataset_level") or []
    ]
    problems = []
    for obj in zip_level.get("objects") or []:
        if obj["kind"] == "gdb":
            unread = obj.get("contents") is None
        elif obj["kind"] in READABLE_KINDS:
            path = obj["path"].lower()
            unread = not any(p == path or p.startswith(f"{path}/") for p in read)
        else:
            continue
        if unread:
            problems.append(
                _problem(
                    entry,
                    "file",
                    "corrupted_file",
                    path_in_zip=obj["path"],
                    detail="listed in the zip but could not be read",
                )
            )
    return problems


def build_error_rows(observed: dict) -> list[dict]:
    """One row per detected problem instance, not one per subject. A clean dataset shrinks
    this report toward nothing rather than padding it with all-blank rows.

    The zip- and file-level rules simply find nothing at depth 0, where zip_level is null and
    dataset_level is empty, so no depth branching is needed here.
    """
    finders = (
        find_broken_links,
        find_incorrect_file,
        find_unreadable_zips,
        find_extra_zip_nesting,
        find_lock_files,
        find_corrupted_spatial_indexes,
        find_corrupted_files,
    )
    problems = [
        row for entry in observed["entries"] for find in finders for row in find(entry)
    ]
    problems.sort(key=lambda r: (r["identifier"], r["level"], r["problem"]))
    return problems


def write_url_report(observed: dict, out_dir: Path) -> Path:
    path = report_path(out_dir, "url_report", observed)
    _write_csv(path, URL_REPORT_FIELDS, build_url_rows(observed))
    return path


def write_dataset_report(observed: dict, out_dir: Path) -> Path:
    path = report_path(out_dir, "dataset_report", observed)
    _write_csv(path, DATASET_REPORT_FIELDS, build_dataset_rows(observed))
    return path


def write_error_summary(observed: dict, out_dir: Path) -> Path:
    path = report_path(out_dir, "error_summary", observed)
    _write_csv(path, ERROR_SUMMARY_FIELDS, build_error_rows(observed))
    return path
