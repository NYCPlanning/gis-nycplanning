"""Derived reports - pure functions of the observed JSON.

Nothing here touches the network or re-reads another report. Every value is pulled from the
observed structure the scrape already produced, which is what makes these cheap to regenerate
and impossible to drift out of sync with each other.
"""

import csv
import re
from pathlib import Path

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
    "dataset",
    "sub_dataset",
    "extent",
    "spatial",
    "row_count",
    "path_in_zip",
    "has_lock_files",
]
ERROR_SUMMARY_FIELDS = [
    "identifier",
    "level",
    "path_in_zip",
    "problem",
    "detail",
    "url",
]

# Types that carry geometry.
# TODO: gdb_raster isn't included here yet - revisit once a raster-bearing product (e.g.
# Zoning) actually exercises this path.
SPATIAL_TYPES = {"shp", "gdb_fc"}

# Matches the deterministic 5-digit disambiguation suffix scrape.assign_identifiers appends
# whenever two rows would otherwise share an identifier.
DUPLICATE_IDENTIFIER_PATTERN = re.compile(r"_\d{5}$")


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
    """One row per dataset_level item. `spatial` and `has_lock_files` are derived here rather
    than stored in the JSON"""
    rows = []
    for entry in observed["entries"]:
        has_lock_files = bool(lock_objects(entry)) if entry.get("zip_level") else ""
        for dataset in entry.get("dataset_level") or []:
            rows.append(
                {
                    "identifier": entry["identifier"],
                    "product": entry["url_level"]["product"],
                    "dataset": dataset["dataset"],
                    "sub_dataset": dataset["sub_dataset"],
                    "extent": dataset["geog_extent"],
                    "spatial": dataset["type"] in SPATIAL_TYPES,
                    "row_count": dataset["row_count"],
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


def find_duplicate_identifier(entry: dict) -> list[dict]:
    if not DUPLICATE_IDENTIFIER_PATTERN.search(entry["identifier"]):
        return []
    return [_problem(entry, "url", "duplicate_identifier")]


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


def build_error_rows(observed: dict) -> list[dict]:
    """One row per detected problem instance, not one per subject. A clean dataset shrinks
    this report toward nothing rather than padding it with all-blank rows.

    The zip- and file-level rules simply find nothing at depth 0, where zip_level is null and
    dataset_level is empty, so no depth branching is needed here.
    """
    finders = (
        find_broken_links,
        find_duplicate_identifier,
        find_extra_zip_nesting,
        find_lock_files,
        find_corrupted_spatial_indexes,
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
