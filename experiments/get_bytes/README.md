# Getting the BYTES of the Big Apple: PLUTO dataset tooling

Four tools, meant to be run in sequence:

1. **`scrape_pluto_datasets.py`** - what dataset zip URLs exist, and what format is each.
2. **`summarize_zip_datasets.py`** - for the spatial ones, what's actually inside each zip.
3. **`spatial_index_report.py`** - for the shapefiles found above, is each one's spatial index
   actually trustworthy.
4. **`error_report.py`** - pulls every problem the first three tools found into one place.

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
(`identifier,product,dataset,sub_dataset,extent,spatial,row_count,path_in_zip,has_lock_files`).

`has_lock_files` is whether that identifier's zip namelist contains any `.lock`-suffixed
member (an artifact of an interrupted upload/write on DCP's end) - computed for free from the
namelist already fetched for discovery, no extra network call. It's a whole-zip fact, so it's
written identically onto every row that zip produced, not just one of them. Feeds directly into
`error_report.py` below.

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

## `spatial_index_report.py`

ESRI's `.sbn`/`.sbx` shapefile spatial index format is unofficial and reverse-engineered - GDAL
(and by extension ArcGIS, QGIS, and every other GDAL-backed consumer) trusts it blindly.
`lyr.TestCapability("FastSpatialFilter")` reports an index as usable **even when it's actually
corrupted** - confirmed directly against a known-bad file, where it still returned `True`. The
only way to actually catch this is to run a real spatially-filtered query and compare it
against an index-free "truth" for the same window.

Reads `zip_contents.csv` + `pluto_datasets.csv` (joined on `identifier` for `url`), filtered to
`spatial == True` rows whose `path_in_zip` ends in `.shp` (`.gdb`-backed layers have their own
separate `.spx` indexing mechanism, out of scope here). For each one, writes a row to
`spatial_index_results.csv` (`identifier,path_in_zip,has_spatial_index,verdict`), where
`verdict` is `CONSISTENT`, `INCONSISTENT`, `NOT_APPLICABLE` (no spatial index present at all -
trivially consistent, mostly seen on pre-2010 vintages), or `ERROR` (couldn't open/read).

**How the check works**, for each shapefile:
1. Open remotely via `/vsizip//vsicurl/<url>/<path>` (same no-local-download approach as
   `summarize_zip_datasets.py`) and record `has_spatial_index` - informational only, per the
   above, never treated as a correctness signal itself.
2. Compute a **truth baseline without ever touching the index**: fetch the `.shp` member's raw
   bytes (`common.get_zip_member_bytes`, the same ranged-HTTP machinery `summarize_zip_datasets.py`
   uses for tabular files) and parse its binary records directly with `struct` - each record's
   bounding box lives in a fixed 32-byte field right after the record header, before the
   variable-length point/vertex array, so jumping straight to the next record via the header's
   declared content-length skips the expensive part entirely. This is dramatically faster than
   asking GDAL to decode full geometry for every feature (confirmed empirically during design:
   ~20-24x faster at real full-scale files) - the speed win is in *parsing*, not in avoiding the
   fetch itself, which still has to happen either way.
3. Sweep a 3x3 grid over the layer's extent (not just one whole-extent query) - for each cell,
   compare GDAL's indexed count (`SetSpatialFilterRect` + `GetFeatureCount(force=0)`, confirmed
   the fastest validated approach for this half) against the truth count (a pure Python
   bbox-intersects-rect test over the struct-parsed bboxes). A grid catches corruption
   localized to only part of a shapefile's extent that a single query might miss.
4. **Comparison uses a small tolerance, not exact equality** - `cells_mismatch()` flags a cell
   only if the two counts differ by more than 1% (or 2 features, whichever is larger). This
   isn't laziness: GDAL's spatial filter tests actual geometry intersection, but the struct-based
   truth only has each record's bounding box, not its real shape, so a polygon whose bbox
   straddles a grid boundary line can appear in a neighboring cell's truth count even though its
   actual body never reaches there. Confirmed directly against a known-good file: summing every
   cell's truth count exceeded the file's real total feature count, with 3 of 9 cells off by
   exactly 1 - vs. every populated cell being off by 90%+ on a known-corrupted file. The two
   failure modes sit orders of magnitude apart, so a small tolerance safely absorbs the former
   without any real risk of masking the latter.

**Correctness of the `struct`-based parser was independently verified**, not just trusted
because the end-to-end verdicts looked right: 60 sampled FIDs (first 5, last 5, 20 random) across
two real files - one known-valid, one of the new findings below - had their parsed bounding
boxes checked directly against GDAL's own `GetGeometryRef().GetEnvelope()`. Exact match on
every sample, zero discrepancies - and specifically rules out "the parser is buggy on this
vintage" as an explanation for the new finding.

### Known findings (from the real, current data)

Running against all 257 real shapefile-backed rows: **214 `CONSISTENT`, 30 `INCONSISTENT`
(across 8 identifiers), 11 `NOT_APPLICABLE`, 2 `ERROR`** (`nyc_mappluto_20v1_arc_shp`, both
layers - `cpl_unzOpenCurrentFile() failed`, the same compression-quirk family already logged as
warnings for `nyc_mappluto_20v2`/`20v6` elsewhere in this project - a pre-existing zip quirk,
not a bug in this script).

The 8 identifiers with at least one `INCONSISTENT` layer:
- `mappluto_14v2` and `mappluto_17v1_1` - previously known corrupted-index cases, now confirmed
  end-to-end by this script rather than a one-off manual check.
- `mappluto_14v1`, `mappluto_15v1`, `mappluto_16v1` - **new findings**. These sit contiguously
  with the two known cases (14v1 through 17v1_1 is essentially the entire 2014-2017 mappluto
  release run), suggesting a **systemic issue across that whole era**, not isolated corruption.
- `nyc_mappluto_20v5_arc_shp` - another new, standalone finding.
- `nyc_mappluto_22v2_arc_shp_05298`/`_05299` - both halves of a known duplicate-identifier
  collision pair show the same corruption across both clipped/unclipped variants, suggesting the
  underlying 22v2 release itself is affected, not that one of the two duplicate download entries
  happens to be a mismatched file.

## `error_report.py`

Grounded in `problem_log.xlsx`, a real historical error sheet DCP staff previously tracked by
hand (`Sheet3`, 15 rows, one row per problem with a `Problem` column naming 6 categories).
**Pure offline join, zero network calls** - unlike every other tool in this project - over
`pluto_datasets.csv` + `zip_contents.csv` (+ `spatial_index_results.csv` if it exists), into
`error_report.csv` (`identifier,level,path_in_zip,problem,detail`).

One row per **detected problem instance**, not one row per subject - matching the reference
sheet's own real shape (a `Problem` column, one row per issue) rather than a fixed row per
identifier padded with blank/false columns for everything that didn't happen. A fully clean
dataset shrinks this report toward nothing.

The problems this tool detects span three different grains, distinguished by `level`:
- **`"url"`** - about the download URL itself, before any zip is ever opened:
  `broken_link` (`pluto_datasets.csv`'s `response_code` not in `200`/`206`, `detail` = the
  actual code) and `duplicate_identifier` (a regex match on the `_\d{5}$` disambiguation suffix
  `scrape_pluto_datasets.py`'s `assign_identifiers` appends on collision).
- **`"zip"`** - about the archive as a whole: `extra_zip_nesting` (`pluto_datasets.csv`'s
  `type == "unknown"` - the 2016v2/2017v1 zip-of-zips case) and `has_lock_files` (from
  `zip_contents.csv`'s column of the same name - one row per affected identifier, not per
  dataset row, since it's a whole-zip fact repeated across however many rows that zip produced).
  `detail` is left blank for `has_lock_files`: `zip_contents.csv` only records *whether* a zip
  has a stray `.lock` file, not which one, and finding the actual filename would need a fresh
  namelist fetch - which this script's offline-only design rules out.
- **`"file"`** - tied to one specific `path_in_zip` within an archive: `corrupted_spatial_index`,
  one row per `(identifier, path_in_zip)` where `spatial_index_results.csv` says
  `verdict == "INCONSISTENT"`. Skipped entirely (not an error) if that file doesn't exist yet -
  Plan G's spatial index check is a separate, slower, opt-in stage this script must tolerate the
  absence of.

One category from the reference sheet needed no new detection at all: **cache buster on url** is
already fully resolved at the source - `strip_cache_buster()` strips `?r=` before the URL is
ever stored (`scrape_pluto_datasets.py`), confirmed by its own regression test. Not surfaced as
a live issue by design, not a gap in this report.

## Execution

(assumes `experiments/get_bytes` is the current working directory)

- `uv sync` - creates `.venv` and `uv.lock` scoped to this directory
- `uv run scrape_pluto_datasets.py` - writes `pluto_datasets.csv` alongside the script
- `uv run summarize_zip_datasets.py` - reads `pluto_datasets.csv`, writes `zip_contents.csv`
- `spatial_index_report.py` needs `osgeo`/GDAL, which has no working prebuilt wheel for this
  `uv`-managed venv on Windows (confirmed - building from source needs MSVC). Run it instead
  under the team's existing `gis-env` conda environment, which already bundles a working GDAL
  (built by `utilities/powershell/deploy_esri_py_env_pro.ps1` by cloning ArcGIS Pro's own
  `arcgispro-py3` environment - not a one-off workaround, the team's actual sanctioned way of
  getting a GDAL-capable Python on this machine):
  ```powershell
  & "$env:LOCALAPPDATA\miniforge3\envs\gis-env\python.exe" spatial_index_report.py
  ```
  This is expected to be temporary - once this toolset migrates into the main `dcpgis` repo
  (sharing one GDAL-having environment for everything), this split disappears on its own. A
  full run against all real shapefile rows takes roughly half an hour - practical as an
  occasional/manual check, not meant to run on every invocation of the other two scripts.
- `uv run error_report.py` - reads `pluto_datasets.csv` + `zip_contents.csv` (+
  `spatial_index_results.csv` if present), writes `error_report.csv`. No network access at all,
  so unlike every other step here it doesn't need the DCP proxy and runs in well under a second.

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
`main()` in `scrape_pluto_datasets.py`/`summarize_zip_datasets.py` is intentionally not
covered - both are thin CLI/IO wrappers around real network/GDAL calls; the logic they call is
what's under test. `error_report.py`'s `main()` is the one exception and **is** covered - it has
no network or GDAL dependency at all, just file I/O, so `tests/test_error_report.py` exercises
it directly (via `monkeypatch` on its module-level `Path` constants against `tmp_path` fixture
files) rather than only testing its constituent functions in isolation.

`spatial_index_report.py` has **no automated pytest coverage at all**, by deliberate choice, not
oversight: it needs `osgeo`, which isn't importable under this project's own `uv` venv (no
working prebuilt Windows wheel - see above) or the pytest suite's environment. Its correctness
was instead verified manually and directly, twice: end-to-end against the two known real
corrupted/valid shapefiles, and independently at the binary-parsing level (a sample of FIDs'
`struct`-parsed bounding boxes cross-checked against GDAL's own `GetGeometryRef().GetEnvelope()`,
exact match). Same precedent as `main()`/`configure_gdal()` above - environment-bound code
accepts a deliberate coverage gap, backed by manual verification instead.
