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
  `shp`. **Because of this, `summarize_zip_datasets.py`'s `{shp, fgdb, csv, txt}` filter skips
  them** - confirmed separately that its nested-zip handling does work correctly against these
  two URLs directly, they just never reach it through the normal pipeline. Everything else
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

Reads `pluto_datasets.csv`, filters to rows where `type` is `shp`, `fgdb`, `csv`, or `txt`
(most of 212 as of this writing), and reports one row per distinct spatial layer, standalone
table, or standalone tabular file found inside each zip, into `zip_contents.csv`
(`identifier,product,dataset,sub_dataset,extent,spatial,row_count,path_in_zip`).

Two different access paths, depending on content type, both avoiding a local download of the
zip:
- **Spatial** (`.shp`/`.gdb` layers and standalone `.dbf` tables): opened *remotely* via GDAL's
  `/vsizip//vsicurl/<url>/<path>` virtual file system (via `pyogrio`) - not even a full
  in-memory fetch of the zip.
- **Tabular** (standalone `.csv`/`.txt` members, e.g. the plain-CSV PLUTO product and the PLUTO
  Change File releases): read via plain `requests` + stdlib `zipfile` random-access reads
  (`common.get_zip_member_bytes`, backed by ranged HTTP requests for whatever byte offsets
  `zipfile` needs - not GDAL/VSI), then parsed with stdlib `csv` for a row count (a
  `bytes.decode()` fallback chain - `utf-8`/`cp1252`/`latin-1` - then a plain `csv.reader()`
  pass, no delimiter sniffing - see below for why). No GDAL, and no third-party parsing
  library, involvement anywhere in this path - originally used `pandas`, swapped out after
  benchmarking against real full-scale files showed it was ~28% slower on an 858K-row citywide
  CSV (pandas builds a full typed DataFrame just to discard every value except the row count)
  with no correctness difference found on any case tested, including the one known real
  CSV-quoting-defect file below.
  - **No `csv.Sniffer()`**: an early version of this swap used `csv.Sniffer().sniff()` to
    detect the delimiter before parsing, matching what `pandas`'s `sep=None` fallback did
    internally. Found (via a real regeneration run, not a benchmark file) that Sniffer fails
    outright - `"Could not determine delimiter"` - on real, unambiguously comma-delimited wide
    PLUTO CSVs (e.g. `nyc_pluto_15v1.zip`'s `BK.csv`/`BX.csv`/`QN.csv`/`SI.csv`, ~80 columns of
    space-padded fixed-width text) - a known Sniffer weakness on this file shape. Fixed by
    dropping Sniffer entirely: row counting only needs correct row/quote/newline handling,
    which `csv.reader` does regardless of which delimiter character is configured - the actual
    delimiter never affects the count. Simpler than the Sniffer-based version, not just more
    correct.

Two GDAL behaviors the spatial path leans on, confirmed empirically before writing the
discovery logic:
- Opening a bare directory-like VSI path (a folder inside a zip, or a whole zip's root) with
  the ESRI Shapefile driver returns one layer per `.shp` bundle plus one table layer per
  standalone `.dbf` with no matching `.shp` - exactly the shapefile/table grouping needed,
  for free, no manual file-grouping logic required.
- Nested zips (a `.zip` inside a zip - see the 2016v2/2017v1 case above) are handled by
  wrapping the whole VSI path in another `/vsizip/`, e.g.
  `/vsizip//vsizip//vsicurl/<url>/outer.zip/inner.zip` - confirmed working directly against
  both known zip-of-zips URLs even though they don't reach this script through the normal
  `pluto_datasets.csv` pipeline (see above). The tabular path does not yet do the equivalent for
  a `.csv`/`.txt` member sitting inside a nested zip - a known, documented limitation, not a
  silent gap.

`product` is a fixed `"pluto"` constant (`PRODUCT` at the top of the file) - the umbrella product
name for every row this tool ever produces, matching the main `dcpgis` repo's own product
vocabulary (`src/dcpgis/cli.py`'s `PRODUCT_CHOICES` lists `"pluto"` as one flat choice). `dataset`
is derived per-row from `pluto_datasets.csv`'s own `dataset_name` column (`mappluto`, `pluto`,
`pluto_change_file`, `mappluto_metadata`, etc.) - the two fields intentionally differ: `product`
never varies, `dataset` always does. Other DCP products (non-PLUTO) are out of scope for this
tool entirely, not a second pass planned within it.

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
- Previously, standalone tabular data was invisible for two independent reasons: `type=csv`/
  `type=txt` source rows (the plain-CSV PLUTO product, PLUTO Change File releases) were
  filtered out before ever reaching `discover_zip`, and even inside an in-scope `shp`/`fgdb`
  zip, a loose `.csv`/`.txt` member alongside the shapefile/gdb was silently skipped the same
  way `pluto_readme.pdf` still is. Both are now covered (see above) - confirmed against the
  real, live `nyc_pluto_26v2_csv.zip`, which now produces a real row (858,284 records) instead
  of none.
- Gut-checked the tabular path against all 101 real `csv`/`txt` source rows before trusting it.
  Found and fixed two real bugs in the process: `product`/`dataset` were hardcoded to
  `"mappluto"` for every row regardless of source (every real `csv`/`txt` row is actually
  `"pluto"` or `"pluto_change_file"`, never `"mappluto"`); and a UTF-8-only decode assumption
  failed outright on several older-vintage releases authored on Windows before UTF-8 was a
  practical default - now tried as UTF-8, then `cp1252`, then `latin-1` (which can never fail to
  decode, since it maps every byte 0x00-0xFF), closing that gap for any encoding a future
  release might use. **Follow-up correction**: the first fix set both `product` and `dataset` to
  the row's `dataset_name`, which was still wrong for every MapPLUTO-derived row (`product`
  came out `"mappluto"` instead of the umbrella `"pluto"`) - `product` is now a fixed `"pluto"`
  constant instead (see above), independent of `dataset_name`.
  Two genuine, newly-discovered upstream data defects surfaced by this same gut-check (not
  bugs in this tool, confirmed by reproducing each independently of this codebase) remain and
  are correctly handled by the existing warn-and-skip pattern, not silently swallowed:
  - `nyc_pluto_25v1_arc_csv.zip`'s central directory records the wrong byte offset for
    `pluto_25v1.csv` - a raw ranged HTTP fetch at that exact offset (bypassing this tool's code
    entirely) confirms the bytes there aren't a valid ZIP local file header. Not a Zip64 issue
    (no Zip64 extra field present); the archive itself appears to be malformed at the source.
  - `nyc_pluto_20v5_arc_csv.zip`'s `pluto_20v5.csv` has a CSV quoting defect
    (`',' expected after '"'`) that fails to parse under every encoding tried - a genuine
    malformed-CSV issue in that file, not an encoding problem.
  Both produce a `WARNING: could not read/parse ...` and a blank `row_count` rather than
  crashing the run; per-encoding brute-forcing stops at `latin-1` deliberately - anything
  that still fails past that point is a real structural defect worth a human's attention (see
  future item 9's error report), not something worth adding more auto-repair logic for.

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
The tabular (`.csv`/`.txt`) read path doesn't go through GDAL at all, so it's tested instead via
`tests/conftest.py`'s `mock_ranged_file_session` - a mocked `requests.Session.get`/`.head` that
actually honors the `Range` header's byte offsets against an in-memory zip's real bytes, so
`get_zip_member_bytes`'s random-access reads get correct slices back without any real network
call.

`uv run pytest --cov=. --cov-report=term-missing` adds a coverage report (`pytest-cov`).
`main()` in each script is intentionally not covered - both are thin CLI/IO wrappers; the
logic they call is what's under test.
