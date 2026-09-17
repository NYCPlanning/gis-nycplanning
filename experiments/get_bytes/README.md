# Getting the BYTES of the Big Apple: PLUTO dataset tooling

Two tools, meant to be run in sequence:

1. **`scrape_pluto_datasets.py`** - what dataset zip URLs exist, and what format is each.
2. **`summarize_zip_datasets.py`** - for the spatial ones, what's actually inside each zip.

## `scrape_pluto_datasets.py`

NYC DCP's [PLUTO, MapPLUTO and PLUTO Change File page](https://www.nyc.gov/content/planning/pages/resources/datasets/mappluto-pluto-change)
lists download links for every current and historical release of PLUTO, MapPLUTO, and the
PLUTO Change File. This script scrapes both the "Most Recent Release" and "Previous Releases
Archive" sections into a single CSV manifest
(`identifier,dataset_name,type,version,url,response_code`) intended as ground truth for this
repo's own PLUTO-related tooling.

The page itself is a client-rendered SPA (its `<main>` is empty on a plain fetch) - the script
instead hits the two JSON endpoints the page's own JS calls to render that content:

- Most Recent Release: `https://apps.nyc.gov/content-api/v1/content/planning/resources/datasets/mappluto-pluto-change`
- Previous Releases Archive: `https://www.nyc.gov/assets/planning/json/content/resources/dataset-archives/mappluto-pluto-change.json`

Neither section's data carries an explicit file-format field, so the script infers `type`
(shp/fgdb/csv/txt/pdf) from label text, then the URL filename, and - for the minority of
older archive links with neither hint (pre-2019 bare PLUTO/MapPLUTO zips) - by making a
ranged HTTP request for just the zip's central directory and inspecting the real file
extensions inside it. `identifier` is the URL's filename (extension stripped), with a
deterministic 5-digit suffix added whenever that collides with another row's - which itself
has caught a handful of real upstream errors (see Known gaps).

`response_code` is a cheap, unconditional per-row check of the download URL's actual HTTP
status - a `HEAD` request, falling back to a minimal ranged `GET` if the server rejects or
mishandles `HEAD` outright. Any status the request actually completes with (404 included) is
recorded as-is; it's left blank only if neither request could complete at all. This surfaces
dead links (like the already-known `nyc_mappluto_23v1_arc_fgdb.zip` 404, previously only
discovered downstream by `summarize_zip_datasets.py`) directly in this report.

`version` always comes from the page's own label text, never reconstructed from the download
URL - the two sections do this differently, intentionally: archive rows get their own
per-release label (`release["text"]` in the archive JSON), while every row scraped from the
Most Recent Release section shares a single page-level `"Latest Release: NNvN"` label, because
that's the only version concept that section actually has (confirmed by inspecting the real
page - there is no per-dataset version label anywhere in it, just the one page-wide string).
Label-vs-URL disagreement does happen for a handful of rows - see the 4 duplicate-link cases
below - but detecting that automatically is a separate concern from this column and isn't done
here; `tests/test_scrape_pluto_datasets.py` has regression tests locking in that the label
wins whenever the two would otherwise conflict.

### Known gaps in `pluto_datasets.csv`

- MapPLUTO 2016v2 and 2017v1 are each a zip-of-per-borough-zips (e.g. `Bronx16V2.zip`,
  `bk_mappluto_17v1.zip` inside the outer zip), so single-level content inspection can't see
  the `.shp` files nested a level down. They come out as `type=unknown`; the real format is
  `shp`. **Because of this, `summarize_zip_datasets.py`'s `{shp, fgdb}` filter skips them** -
  confirmed separately that its nested-zip handling does work correctly against these two
  URLs directly, they just never reach it through the normal pipeline. Everything else
  inspected cleanly at one level.
- 3 archive links carry a leftover cache-busting query string (`?r=1`/`?r=2`) on NYC's own
  site - likely added when DCP re-uploaded a corrected file at the same path and needed to
  force caches to pick up the new bytes. The scraper fetches through it fine and strips it
  from the `url` column, but the underlying links are still live with the suffix as of this
  writing and would be worth cleaning up at the source:
  - PLUTO 2017 `17v1` → `.../pluto/nyc_pluto_17v1.zip?r=1`
  - PLUTO 2017 `17v1.1` → `.../pluto/nyc_pluto_17v1_1.zip?r=1`
  - MapPLUTO 2017 `17v1.1` → `.../mappluto/mappluto_17v1_1.zip?r=2`
- 4 identifiers come out with a disambiguating suffix because NYC's own archive page links
  more than one version label to the exact same file - a real data error, not a scraper bug:
  `PLUTOChangeFile26v1.zip` (linked from both the `26v1` archive entry and, mislabeled `26v2`,
  the Most Recent Release section), `nyc_mappluto_22v2_arc_shp.zip` (`22v2` and `22v3`),
  `nyc_mappluto_21v1_arc_fgdb.zip` (`21v1` and `21v2`), `nyc_mappluto_20v2_arc_shp.zip`
  (`20v2` and `21v2`).
- 2 links 404 as of this writing, per `response_code` - real archive errors, not scraper bugs:
  `nyc_mappluto_23v1_arc_fgdb.zip` (already known from `summarize_zip_datasets.py`'s own gaps
  below) and `nyc_pluto_21v1_csv.zip` (newly surfaced by this column).

## `summarize_zip_datasets.py`

Reads `pluto_datasets.csv`, filters to rows where `type` is `shp` or `fgdb` (104 of 212 as of
this writing), and for each one opens the zip *remotely* via GDAL's
`/vsizip//vsicurl/<url>/<path>` virtual file system (via `pyogrio`) - no local download, not
even a full in-memory fetch of the zip. Reports one row per distinct spatial layer or
standalone table found inside, into `zip_contents.csv`
(`identifier,product,dataset,sub_dataset,spatial,row_count,path_in_zip`).

Two GDAL behaviors this leans on, confirmed empirically before writing the discovery logic:
- Opening a bare directory-like VSI path (a folder inside a zip, or a whole zip's root) with
  the ESRI Shapefile driver returns one layer per `.shp` bundle plus one table layer per
  standalone `.dbf` with no matching `.shp` - exactly the shapefile/table grouping needed,
  for free, no manual file-grouping logic required.
- Nested zips (a `.zip` inside a zip - see the 2016v2/2017v1 case above) are handled by
  wrapping the whole VSI path in another `/vsizip/`, e.g.
  `/vsizip//vsizip//vsicurl/<url>/outer.zip/inner.zip` - confirmed working directly against
  both known zip-of-zips URLs even though they don't reach this script through the normal
  `pluto_datasets.csv` pipeline (see above).

`product`/`dataset` are both hardcoded `"mappluto"` for this pass (single named constants at
the top of the file) - the instructions call for `"pluto"` (tabular) and other DCP products to
be added later as a second pass, not by extending this file's discovery logic.

Performance was benchmarked, not assumed - plain `vsicurl` averaged ~1s/row across a diverse
sample, with GDAL config tuning (`GDAL_DISABLE_READDIR_ON_OPEN`, larger curl chunk/cache
sizes, `VSI_CACHE`) giving a further ~14% for free. The full 104-row run took a few minutes.

### Known gaps in `zip_contents.csv`

- `nyc_mappluto_23v1_arc_fgdb.zip` 404s on NYC's own site as of this writing - another real
  archive error, not a scraper bug. It produces zero rows (warned, not silently dropped).
- Nearly every row logs a `WARNING: could not list layers for .../<zip>: '...' not
  recognized as being in a supported file format` for the *zip root* specifically - this is
  benign: most fgdb zips also bundle `pluto_datadictionary.pdf`/`pluto_readme.pdf` at the top
  level alongside the `.gdb` folder, and the discovery logic (correctly, generically) tries
  opening every loose-file parent directory as a shapefile datasource, including the root.
  GDAL correctly rejects a directory containing only PDFs; zero rows are contributed by that
  attempt and the `.gdb` folder itself is still found and read normally.

## Execution

(assumes `experiments/get_bytes` is the current working directory)

- `uv sync` - creates `.venv` and `uv.lock` scoped to this directory
- `uv run scrape_pluto_datasets.py` - writes `pluto_datasets.csv` alongside the script
- `uv run summarize_zip_datasets.py` - reads `pluto_datasets.csv`, writes `zip_contents.csv`

If any command can't reach the network (PyPI for `uv sync`, or `nyc.gov`/`apps.nyc.gov`/
`s-media.nyc.gov` for the scripts themselves), set the DCP proxy from `.condarc` first:

```powershell
$env:HTTP_PROXY = "http://bcpxy.nycnet:8080"
$env:HTTPS_PROXY = "http://bcpxy.nycnet:8080"
```

## Testing

`uv run pytest` runs the suite in `tests/` - fully offline, no proxy needed. HTTP calls are
mocked (`requests.Session.get`/`.head` patched per test via `tests/conftest.py`'s
`MockResponse`/`mock_session_call` helpers - no third-party mocking library, matching this
org's own convention found in both this repo and the sibling `data-engineering` repo) and an
autouse `block_network` fixture fails any test that tries to open a real socket regardless.
GDAL/pyogrio code is tested against small real fixture zips under `tests/resources/` via local
(non-`vsicurl`) `/vsizip/` paths - never the network - also matching precedent in both repos.

`uv run pytest --cov=. --cov-report=term-missing` adds a coverage report (`pytest-cov`).
`main()` in each script is intentionally not covered - both are thin CLI/IO wrappers; the
logic they call is what's under test.
