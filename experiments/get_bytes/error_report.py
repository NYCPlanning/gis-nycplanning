"""Final consolidated error/anomaly report, grounded in a real historical reference sheet
(problem_log.xlsx) DCP staff previously tracked by hand.

Pure offline join over already-produced reports (pluto_datasets.csv, zip_contents.csv, and
spatial_index_results.csv if present) - unlike every other tool in this project, this script
makes no network calls at all. One row per detected problem instance, not one row per subject -
a clean dataset should shrink this report toward nothing, not pad it with all-blank rows for
every non-problematic identifier.

Three grains of problem, distinguished by `level`:
- "url": about the download URL itself, before any zip is ever opened (broken links,
  duplicate-identifier collisions).
- "zip": about the archive as a whole (extra zip-of-zips nesting, stray .lock files).
- "file": tied to one specific path_in_zip within an archive (a corrupted spatial index on
  one particular shapefile - a single zip can hold several, e.g. one per borough).
"""

import csv
import re
from pathlib import Path

DATASETS_CSV = Path(__file__).parent / "pluto_datasets.csv"
ZIP_CONTENTS_CSV = Path(__file__).parent / "zip_contents.csv"
SPATIAL_INDEX_CSV = Path(__file__).parent / "spatial_index_results.csv"
OUTPUT_CSV = Path(__file__).parent / "error_report.csv"
FIELDNAMES = ["identifier", "level", "path_in_zip", "problem", "detail", "url"]

# Matches the deterministic 5-digit disambiguation suffix scrape_pluto_datasets.py's own
# assign_identifiers appends whenever two rows would otherwise share an identifier.
DUPLICATE_IDENTIFIER_PATTERN = re.compile(r"_\d{5}$")


def _problem_row(
    identifier: str, level: str, problem: str, path_in_zip: str = "", detail: str = ""
) -> dict:
    return {
        "identifier": identifier,
        "level": level,
        "path_in_zip": path_in_zip,
        "problem": problem,
        "detail": detail,
    }


def find_broken_links(source_rows: list[dict]) -> list[dict]:
    return [
        _problem_row(
            row["identifier"], "url", "broken_link", detail=row["response_code"]
        )
        for row in source_rows
        if row["response_code"] and row["response_code"] not in ("200", "206")
    ]


def find_duplicate_identifiers(source_rows: list[dict]) -> list[dict]:
    return [
        _problem_row(row["identifier"], "url", "duplicate_identifier")
        for row in source_rows
        if DUPLICATE_IDENTIFIER_PATTERN.search(row["identifier"])
    ]


def find_extra_zip_nesting(source_rows: list[dict]) -> list[dict]:
    return [
        _problem_row(row["identifier"], "zip", "extra_zip_nesting")
        for row in source_rows
        if row["type"] == "unknown"
    ]


def find_lock_files(zip_content_rows: list[dict]) -> list[dict]:
    """One row per affected identifier, not per zip_contents.csv row - has_lock_files is a
    whole-zip fact repeated across every dataset row that zip produced.

    detail is deliberately left blank: zip_contents.csv only records whether a zip contains
    at least one .lock-suffixed member, not which one - surfacing the actual filename would
    need a fresh namelist fetch, which this script's offline-only design rules out.
    """
    identifiers_with_lock_files = {
        row["identifier"] for row in zip_content_rows if row["has_lock_files"] == "True"
    }
    return [
        _problem_row(identifier, "zip", "has_lock_files")
        for identifier in sorted(identifiers_with_lock_files)
    ]


def find_corrupted_spatial_indexes(spatial_index_rows: list[dict]) -> list[dict]:
    return [
        _problem_row(
            row["identifier"],
            "file",
            "corrupted_spatial_index",
            path_in_zip=row["path_in_zip"],
        )
        for row in spatial_index_rows
        if row["verdict"] == "INCONSISTENT"
    ]


def main() -> None:
    with DATASETS_CSV.open(newline="", encoding="utf-8") as f:
        source_rows = list(csv.DictReader(f))

    with ZIP_CONTENTS_CSV.open(newline="", encoding="utf-8") as f:
        zip_content_rows = list(csv.DictReader(f))

    problems = []
    problems.extend(find_broken_links(source_rows))
    problems.extend(find_duplicate_identifiers(source_rows))
    problems.extend(find_extra_zip_nesting(source_rows))
    problems.extend(find_lock_files(zip_content_rows))

    if SPATIAL_INDEX_CSV.exists():
        with SPATIAL_INDEX_CSV.open(newline="", encoding="utf-8") as f:
            spatial_index_rows = list(csv.DictReader(f))
        problems.extend(find_corrupted_spatial_indexes(spatial_index_rows))
    else:
        print(
            f"NOTE: {SPATIAL_INDEX_CSV.name} not found - skipping corrupted_spatial_index "
            "checks (run spatial_index_report.py under gis-env first if this report should "
            "include them)"
        )

    # zip_contents.csv/spatial_index_results.csv don't carry their own url column, so every
    # problem instance's url is looked up from pluto_datasets.csv - the one place it's stored.
    url_by_identifier = {row["identifier"]: row["url"] for row in source_rows}
    for problem in problems:
        problem["url"] = url_by_identifier.get(problem["identifier"], "")

    problems.sort(key=lambda r: (r["identifier"], r["level"], r["problem"]))

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(problems)

    print(f"Wrote {len(problems)} problem rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
