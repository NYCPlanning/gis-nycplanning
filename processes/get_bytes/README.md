# get_bytes

Audits a NYC DCP dataset page (built against the MapPLUTO/PLUTO page) for problems the hosted data: broken links, mislabeled files, damaged or unreadable zips, stray lock
files, and corrupted shapefile spatial indexes. It also inventories what each release zip
actually contains.

Everything the tool learns over the network is stored once, in a central JSON report. The
CSV reports are derived from that JSON, so they can be regenerated without refetching
anything.

## Usage

Run in the `gis-env` conda env (depth 1 needs `osgeo`).

Ensure `HTTP_PROXY`/`HTTPS_PROXY` are set before running.

```
python processes/get_bytes/get_bytes.py <page url> [--depth {0,1}] [--output-dir DIR]
python processes/get_bytes/get_bytes.py --resume <observed_report_*.json>
```

| Option | Effect |
|---|---|
| `--depth 0` (default) | Scrapes the page and checks each link's response code. Takes a few minutes. |
| `--depth 1` | Also opens every zip, reading its contents, row and column counts, and shapefile spatial indexes. Takes about an hour for PLUTO. |
| `--resume` | Continues an interrupted run, or upgrades a depth-0 report to depth 1. Zips already inspected are skipped; ones that failed are retried. |

Reports go to the current directory, or next to the report being resumed, unless
`--output-dir` says otherwise.

Example:

```
python processes/get_bytes/get_bytes.py https://www.nyc.gov/content/planning/pages/resources/datasets/mappluto-pluto-change --depth 1
```

## Outputs

Each file name ends in `_{page}_{timestamp}`.

| File | Contents |
|---|---|
| `observed_report_*.json` | Everything observed, per link: url level, zip level, dataset level. |
| `url_report_*.csv` | One row per link: dataset, type, version, URL, response code. |
| `dataset_report_*.csv` | Depth 1 only. One row per layer, table or file inside each zip. |
| `error_summary_*.csv` | One row per problem found. Empty means clean. |

## Next steps

- **Performance.** Depth 1 is slow, mostly on the large citywide releases. Measure first,
  then read shapefiles through GDAL's own file access instead of a second download, stream
  CSVs instead of loading them whole, and try process-based parallelism across zips.
- **Product-agnostic.** The scraper, file vocabulary and clipped/unclipped logic are still
  PLUTO-specific. The aim is a per-product profile, so that supporting another DCP page is
  configuration, not code.
- **Migrate** into the `dcpgis` package.
- **Pytest in CI**, as part of a repo-wide change.
- **More error rules:**
  - cache-busting query strings on archive links
  - separating unsupported compression (the 20vN releases) from `corrupted_file`
  - row and column counts that diverge beyond an expected margin against an item's own release history
