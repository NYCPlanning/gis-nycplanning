# GIS Machine Troubleshooter

A self-service diagnostic tool for GIS desktop issues. The tool collects a snapshot of the machine (network, proxy, ODBC drivers, mapped drives, installed programs) and, optionally, a snapshot of a specified ArcGIS Pro project (sign-in account, software/Python version, layer inventory). This info is collected into a single report, so support staff can triage likely root causes before beginning a live troubleshooting session.

## For end users

1. Run `run_troubleshooter.ps1` - double-click it, or run it from a terminal.
2. If you have an ArcGIS Pro project you want to add to the inventory, you'll be prompted to enter the path to its `.aprx` file. You can leave this blank to skip the GIS-level checks and only collect machine-level info.
3. A terminal window stays open while it runs and shows a `SUCCESS` or `FAILURE` message plus the report location when it's done. Press Enter to close it.
4. The report is written to your Desktop, named `gis_report_{username}_{devicename}_{timestamp}.xlsx`, with three tabs: System Info, Installed Programs, and GIS Info. (If Excel isn't available on your machine, you'll get three `.csv` files instead, with the same information split across them.)
5. Attach the report to the ongoing email thread with the GIS Team, or share according to their instructions.

No installation, configuration, or internet access needed to run it.

## For maintainers

**Files:**
- `run_troubleshooter.ps1` - the entry point. Dot-sources `troubleshooter_functions.ps1`, collects machine-level info directly (registry, built-in cmdlets), then shells out to `collect_gis_info.py` for anything that requires `arcpy`, and assembles the final report.
- `troubleshooter_functions.ps1` - all of `run_troubleshooter.ps1`'s function definitions, split into their own file so they can be dot-sourced independently - by the script itself, and by the Pester tests below - without also running the script's top-level collection/report logic (which prompts, touches the real registry/network, and drives Excel).
- `collect_gis_info.py` - runs under the machine's default ArcGIS Pro conda env (`arcgispro-py3`) and prints a single JSON object to stdout for the PowerShell side to parse.

**Design constraints:**
- No dependency on this repo's `dcpgis` package, and no assumption of a custom/cloned conda env. The tool has to run standalone on an arbitrary GIS user's machine using only what ArcGIS Pro installs by default.
- No config file. Everything needed is either derived at runtime (e.g. proxy settings, mapped drives, installed ODBC drivers) or hardcoded (the default Pro conda env path).
- Report generation prefers Excel COM automation (a true multi-tab `.xlsx`, no extra installs required) and falls back to plain `.csv` files if Excel isn't available - see `Write-SheetSections` / `Export-SectionsToCsv` in `troubleshooter_functions.ps1`, which both consume the same section data so the two output paths can't drift apart.
- Network drive and proxy detection were tested against an actual desktop and designed accordingly: mapped drives use `Get-PSDrive -PSProvider FileSystem` rather than `Get-SmbMapping`, because non-SMB mappings (e.g. legacy NetWare/`net use` drives) don't show up under `Get-SmbMapping`. Proxy settings check both the per-user WinINet registry key and machine-wide WinHTTP (`netsh winhttp show proxy`), since the two can disagree and either one can be what's actually in effect for a given app.

**Testing changes:** run `run_troubleshooter.ps1 -AprxPath <path>` directly against a real `.aprx` and inspect the resulting report. After any change touching the Excel COM code, check `Get-Process excel` afterward to confirm no orphaned `EXCEL.EXE` process was left behind.

**Automated tests:** `tests/utilities/gis_machine_troubleshooter/` has a pytest suite for `collect_gis_info.py` and a Pester suite for `troubleshooter_functions.ps1`.
- Python: run under an arcpy-enabled interpreter (e.g. the ArcGIS Pro conda env), from the repo root: `python -m pytest tests/utilities/gis_machine_troubleshooter/test_collect_gis_info.py -v`
- PowerShell: no install needed - the tests deliberately target Pester 3.4.0, the version built into Windows (this repo is Python-primary; keeping its small PowerShell surface at zero extra setup was judged worth the older `Should <op> <value>` assertion syntax over a newer Pester's ergonomics). From the repo root: `Invoke-Pester -Path tests\utilities\gis_machine_troubleshooter\troubleshooter_functions.Tests.ps1`. The test file's own header comment documents the syntax/mocking constraints this implies - read it before editing the suite.
- The `Write-SheetSections` test is a real-Excel integration test (Excel COM's cell-assignment syntax can't be faked with a plain object) and marks itself inconclusive (Pester 3.4's skip-equivalent) if Excel isn't installed on the machine running it.

**Deploying:** there's currently no deploy script - manually copy the `gis_machine_troubleshooter/` directory to the network drive location after merging a change. This can be improved upon over time as needed.
