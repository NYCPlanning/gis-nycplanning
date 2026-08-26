GIS MACHINE TROUBLESHOOTER

A self-service diagnostic tool for GIS desktop issues. Collects a snapshot
of the machine (network, proxy, ODBC drivers, mapped drives, installed
programs) and, optionally, a snapshot of a specified ArcGIS Pro project
(sign-in account, software/Python version, layer inventory) into a single
report, so support staff can triage likely root causes before starting a
live troubleshooting session.


FOR END USERS

1. Run run_troubleshooter.ps1 - double-click it, or run it from a terminal.
2. If you have an ArcGIS Pro project to include, you'll be prompted for the
   path to its .aprx file. Leave this blank to skip GIS-level checks.
3. A terminal window stays open while it runs and shows a SUCCESS or
   FAILURE message plus the report location when it's done. Press Enter to
   close it.
4. The report is written to your Desktop, named
   gis_report_{username}_{devicename}_{timestamp}.xlsx, with three tabs:
   System Info, Installed Programs, and GIS Info. If Excel isn't available
   on your machine, you'll get three .csv files instead.
5. Attach the report to the ongoing email thread with the GIS Team, or
   share according to their instructions.

No installation, configuration, or internet access needed to run it.


FOR DEVELOPERS

- run_troubleshooter.ps1 is the entry point - the only file end users
  interact with directly.
- internal/ holds the implementation: troubleshooter_functions.ps1
  (PowerShell) and collect_gis_info.py (Python, requires the ArcGIS Pro
  conda env - it imports arcpy).
- Tests live in tests/utilities/gis_machine_troubleshooter/ - pytest for
  the Python side, Pester for the PowerShell side.
- No config file, and no deploy script yet - copy the
  gis_machine_troubleshooter folder to the network drive location
  manually after merging a change.
