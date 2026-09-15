# Getting the BYTES of the Big Apple: PLUTO dataset URL manifest

## Context

NYC DCP's [PLUTO, MapPLUTO and PLUTO Change File page](https://www.nyc.gov/content/planning/pages/resources/datasets/mappluto-pluto-change)
lists download links for every current and historical release of PLUTO, MapPLUTO, and the
PLUTO Change File. `scrape_pluto_datasets.py` scrapes both the "Most Recent Release" and
"Previous Releases Archive" sections into a single CSV manifest (`dataset_name,type,version,url`)
intended as ground truth for this repo's own PLUTO-related tooling.

The page itself is a client-rendered SPA (its `<main>` is empty on a plain fetch) - the script
instead hits the two JSON endpoints the page's own JS calls to render that content:

- Most Recent Release: `https://apps.nyc.gov/content-api/v1/content/planning/resources/datasets/mappluto-pluto-change`
- Previous Releases Archive: `https://www.nyc.gov/assets/planning/json/content/resources/dataset-archives/mappluto-pluto-change.json`

Neither section's data carries an explicit file-format field, so the script infers `type`
(shp/fgdb/csv/txt/pdf) from label text, then the URL filename, and - for the minority of
older archive links with neither hint (pre-2019 bare PLUTO/MapPLUTO zips) - by making a
ranged HTTP request for just the zip's central directory and inspecting the real file
extensions inside it.

This is a standalone script with its own dependencies (`requests`, `beautifulsoup4`) managed
via `uv`, kept out of `dcpgis`'s own environment.

## Execution

(assumes `experiments/get_bytes` is the current working directory)

- `uv sync` - creates `.venv` and `uv.lock` scoped to this directory
- `uv run scrape_pluto_datasets.py` - writes `pluto_datasets.csv` alongside the script

If either command can't reach the network (PyPI for `uv sync`, or `nyc.gov`/`apps.nyc.gov` for
the scraper itself), set the DCP proxy from `.condarc` first:

```powershell
$env:HTTP_PROXY = "http://bcpxy.nycnet:8080"
$env:HTTPS_PROXY = "http://bcpxy.nycnet:8080"
```

## Known gaps in the output

- `nyc_pluto_23v1_1_arc_csv.zip`'s PLUTO Change File counterpart
  (`PLUTOChangeFile23v1_1.zip`) 404s on NYC's own site as of this writing - it still gets a
  row (`dataset_name=pluto_change_file, version=23v1.1`) but `type=unknown` since the file
  can't be fetched to inspect. Worth a look if this is feeding archive-error triage.
- MapPLUTO 2016v2 and 2017v1 are each a zip-of-per-borough-zips (e.g. `Bronx16V2.zip`,
  `bk_mappluto_17v1.zip` inside the outer zip), so single-level content inspection can't see
  the `.shp` files nested a level down. They come out as `type=unknown`; the real format is
  `shp`. Everything else inspected cleanly at one level.
