"""Gather every observed data point about a NYC DCP dataset page into one JSON file, then
derive the CSV reports from it.

    python get_bytes.py <page url> [--depth {0,1}] [--output-dir DIR]

    depth 0 (default)  url-level only: observed JSON, url report, error summary
    depth 1            adds zip-level and dataset-level inspection, plus the dataset report

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

# Response-code lookups are pure I/O wait with no decompression behind them, so threads help
# here in a way they demonstrably do not for the CPU-bound zip work at depth 1.
RESPONSE_CODE_WORKERS = 8


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


def write_observed(observed: dict, out_dir: Path) -> Path:
    path = (
        Path(out_dir)
        / f"observed_report_{observed['page']}_{observed['initiated_timestamp']}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(observed, indent=2), encoding="utf-8")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "url", help="dataset page to scrape, e.g. the PLUTO dataset page"
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    session = make_session()

    observed = build_observed(args.url, args.depth, session)

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
