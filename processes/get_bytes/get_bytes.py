"""Gather every observed data point about a NYC DCP dataset page into one JSON file, then
derive the CSV reports from it.

    python get_bytes.py <page url> [--depth {0,1}] [--output-dir DIR]
    python get_bytes.py --resume <prior report> --depth 1

    depth 0 (default)  url-level only: observed JSON, url report, error summary
    depth 1            adds zip-level and dataset-level inspection, plus the dataset report

Depth 1 takes about an hour, so it flushes the observed report as it goes and --resume picks
up where a previous run stopped, skipping entries already inspected. A finished depth-0 report
is therefore a valid starting point for depth 1.

Reports are written to the current directory unless --output-dir says otherwise. Scheduled
runs should pass it explicitly: trigger_process.ps1 sets cwd to its own location first.

"Observed" means anything that took a network call to learn. Everything else - format
inference, identifier disambiguation, the spatial flag, every problem rule - is derived from
the observed data, recomputed on demand, and never persisted twice.

"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

# Run by script path, sys.path[0] is this file's own directory, so the absolute imports below
# would not resolve without this.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from processes.get_bytes import reports, scrape  # noqa: E402
from processes.get_bytes.common import get_response_code, make_session  # noqa: E402

# Types worth opening at depth 1. pdf-typed entries are reference docs with no archive to
# inspect, and unknown-typed ones are the zip-of-zips cases GDAL cannot reach single-level.
IN_SCOPE_ZIP_TYPES = {"shp", "fgdb", "csv", "txt"}

# Response-code lookups are pure I/O wait with no decompression behind them, so threads help
# here in a way they demonstrably do not for the CPU-bound zip work at depth 1.
RESPONSE_CODE_WORKERS = 8

# How often depth 1 flushes the observed report to disk, in entries.
OBSERVED_WRITE_BATCH = 5


def timestamp_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_url_level(row: dict) -> dict:
    return {
        "dataset_name": row["dataset_name"],
        "type": row["type"],
        "version": row["version"],
        "url_actual": row["url"],
        "response_code": row["response_code"],
        "product": scrape.PRODUCT,
    }


def build_observed(input_url: str, depth: int, session) -> dict:
    page = scrape.page_slug_from_url(input_url)
    observed = {
        "input_url": input_url,
        "page": page,
        "initiated_timestamp": timestamp_now(),
        "depth": depth,
        "entries": [],
    }

    rows = scrape.fetch_page_rows(page, session)
    print(f"Found {len(rows)} dataset links on {page}")

    with ThreadPoolExecutor(max_workers=RESPONSE_CODE_WORKERS) as pool:
        codes = pool.map(lambda row: get_response_code(row["url"], session), rows)
    for row, code in zip(rows, codes):
        row["response_code"] = code

    observed["entries"] = [
        {
            "identifier": row["identifier"],
            "url_level": build_url_level(row),
            "zip_level": None,
            "dataset_level": [],
        }
        for row in rows
    ]
    return observed


def load_observed(path: Path, depth: int) -> dict:
    """Pick up an earlier report. Its timestamp is kept, so the resumed run rewrites that same
    file rather than starting a second one alongside it."""
    observed = json.loads(Path(path).read_text(encoding="utf-8"))
    observed["depth"] = depth
    print(
        f"Resuming {Path(path).name}: {len(observed['entries'])} entries from the {observed['initiated_timestamp']} run"
    )
    return observed


def add_zip_and_dataset_levels(observed: dict, session, out_dir: "Path | None" = None) -> None:
    """Fill in zip_level/dataset_level for every in-scope entry, in place.

    Imported here rather than at module scope because it pulls in osgeo, which only exists
    under gis-env - depth 0 stays runnable in any environment.

    With out_dir, the observed report is flushed every OBSERVED_WRITE_BATCH entries so an
    hour-long run leaves usable partial output if it dies, and can be resumed rather than
    restarted. Entries already carrying a zip_level are skipped, which is what makes --resume
    work: depth 0 sets zip_level to None explicitly, so "still None" means "not yet inspected".
    """
    from processes.get_bytes import zip_inspect

    zip_inspect.configure_gdal()

    in_scope = [e for e in observed["entries"] if e["url_level"]["type"] in IN_SCOPE_ZIP_TYPES]
    pending = [e for e in in_scope if e.get("zip_level") is None]
    unclipped_siblings = zip_inspect.find_versions_with_unclipped_sibling(observed["entries"])

    already_done = len(in_scope) - len(pending)
    resumed = f" ({already_done} already inspected, skipping)" if already_done else ""
    print(f"Inspecting {len(pending)} of {len(in_scope)} zips at depth 1{resumed}...")

    for i, entry in enumerate(pending, 1):
        url_level = entry["url_level"]
        sibling_has_unclipped = (
            url_level["version"],
            url_level["type"],
        ) in unclipped_siblings
        try:
            zip_level, dataset_level = zip_inspect.inspect_zip(
                url_level["url_actual"],
                url_level["dataset_name"],
                sibling_has_unclipped,
                session,
            )
        except (RuntimeError, OSError) as exc:
            # One unreadable archive must never abort the run - there are known upstream
            # defects (a bad central-directory offset, a compression quirk) that would.
            print(f"WARNING: failed inspecting {entry['identifier']}: {exc}")
            continue

        entry["zip_level"] = zip_level
        entry["dataset_level"] = dataset_level
        print(f"[{i}/{len(pending)}] {entry['identifier']}: {len(dataset_level)} dataset(s)")

        if out_dir is not None and i % OBSERVED_WRITE_BATCH == 0:
            write_observed(observed, out_dir)


def observed_path(observed: dict, out_dir: Path) -> Path:
    return Path(out_dir) / f"observed_report_{observed['page']}_{observed['initiated_timestamp']}.json"


def write_observed(observed: dict, out_dir: Path) -> Path:
    """Written via temp-then-rename, because depth 1 rewrites this file repeatedly while the
    run is in progress and a crash mid-write would otherwise leave truncated JSON - which is
    exactly the file a resume needs to be able to read."""
    path = observed_path(observed, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(observed, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "url",
        nargs="?",
        help="dataset page to scrape, e.g. the PLUTO dataset page",
    )
    parser.add_argument(
        "--depth",
        type=int,
        choices=(0, 1),
        default=0,
        help="0 = url-level only (default); 1 = also inspect zip and dataset levels",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        # Resolved per call rather than at import, so it tracks the caller's actual cwd.
        default=Path.cwd(),
        help="where to write reports (default: the current directory)",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        help=("continue from an existing report instead of rescraping; entries already inspected are skipped"),
    )
    args = parser.parse_args(argv)
    if not args.url and not args.resume:
        parser.error("a url is required unless --resume points at an existing report")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    session = make_session()

    if args.resume:
        observed = load_observed(args.resume, args.depth)
    else:
        observed = build_observed(args.url, args.depth, session)

    if args.depth >= 1:
        add_zip_and_dataset_levels(observed, session, args.output_dir)

    written = [
        write_observed(observed, args.output_dir),
        reports.write_url_report(observed, args.output_dir),
        reports.write_error_summary(observed, args.output_dir),
    ]
    if args.depth >= 1:
        written.append(reports.write_dataset_report(observed, args.output_dir))

    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
