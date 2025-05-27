### 2025-05-27
#### EGDB Distribution must be able to:
- Get the relevant version number
- Unambiguously determine which constituent files should be distributed (i.e. PLUTO is the product, while PLUTO, MapPLUTO water included, MapPLUTO clipped, etc. are the constituent files)
- Handle the EGDB
  - Disconnect connected users
  - Block new connections
  - Allow connections after distribution – firmly, regardless of success of script
- Access the source location for the data (initially only Digital Ocean)
- Handle errors gracefully – both from arcpy and Python

#### EGDB Distribution should ideally also be able to:
- Update LYR file metadata

#### Thoughts: 
- Consider how to ideally distribute that to EGDB w/out CLI, and then map that to CLI, rather than vice versa
- Use conditional statement or other to separate egdb destination from other destinations
- Determine process-specific config to get dataset constituent files into distribute module (likely: add a parse_xlsx fn to config class, mockup an example sheet for PLUTO)
- Would it be beneficial to grab a snapshot or backup of feature classes to be overwritten? e.g. export MapPLUTO fcs from GISPROD to a file geodatabase before 

#### Distribute to EGDB outline
1. [DISPATCHER] Set up logging 
2. [DISPATCHER] Get *process*-specific config values --> EGDB path, DO URL, environment type 
3. [TODO>HERE] Get *product*-specific config values --> constituent file info: names at source, names at destination, which to distribute, which to hold back
4. [TODO>HERE] Get relevant data from source --> download and unzip (to temp dir?) from DO or other
5. [TODO>HERE] Manage EGDB connections --> disconnect users, block new connections
6. [TODO>HERE] Overwrite feature classes (seems best to have to manually push new FCs, and an error check on update is for the script to throw an exception if the expected FCs don't already exist. This would be different for an archival distribution)
7. [TODO>HERE] Confirm validity of overwritten feature classes
8. [TODO>HERE] Manage EGDB connections --> allow connections again

### YYYY-MM-DD Potential Repo Structure
```
.
├─── README.md
├─── environment.yml        --conda env snapshot
├─── pyproject.toml         --package definition
├─── tests.py
├─── .gitignore
├─── docs
│   └─── diagrams
├─── templates
│   ├─── metadata           --XML files
│   └─── issues             --GH issue MD files
├─── utilities              --Misc. tools
│   ├─── powershell
│   ├─── sql
│   └─── python
├─── processes              --main files for each product/process
├─── src
│   └─── dcpgis             --package
│      ├─── __init__.py
│      ├─── logging.py      --module
│      ├─── metadata.py     --module
│      └─── ... 
└─── config                 --config for whole repo
    └─── constants.py
```

Ref:

[Structuring Your Project](https://docs.python-guide.org/writing/structure/)
  