# GIS Team Wiki

## Development Environment Setup
Most custom code written and executed by the GIS Team is written in python, with a lesser amount written in PowerShell and SQL. Git is used heavily. Firewall and software installation restrictions are often a defining factor in deciding what tools to use and why. 

### Install and configure an IDE
The GIS Team tends to use VS Code, but any standard IDE that supports Python development with work

### Set proxy server environment variables
NYC Planning uses a proxy server. `http` and `https` environment variables must be set to allow conda to install Python packages.
1. From Start menu, open "Edit environment variables for your **account**".
2. Under "User variables for <username>", click "New..."
3. Create an HTTP variable:
   1. For "Variable name", enter `http_proxy`
   2. For "Variable value", get this from a coworker or internal documentation, and enter
4. Create an HTTPS variable:
   1. For "Variable name", enter `https_proxy`
   2. For "Variable value", get this from a coworker or internal documentation, and enter

### Python
For python, the GIS Team relies on the conda distribution that comes with ArcGIS Pro. The the bulk of our operations relate in some way or other to Esri software or file types, although we are increasingly adopting open source alternatives to the `arcpy` and `arcgis` libraries where it makes sense.

#### Using Python via conda
The GIS team uses a default conda environment ("gis-team-default-env") that can be generated with this [PowerShell script](utilities\powershell\deploy_esri_py_env_pro.ps1). At the time of writing, the script takes the base environment provided by ArcGIS Pro ("arcgispro-py3"), pip installs a few custom packages, and manually tunes package dependencies. We should ideally be able to use an environment.yml file to define and create our default environment, or at least use conda and not pip for installations, but the commands to do so often fail, likely due to firewall restrictions.

The default conda environment name is important to remain consistent across GIS Team member's environments, because the [PowerShell files used in Task Scheduler](processes\trigger_process.ps1) to call python scripts all call that default environment name.

Conda env setup (requires an active installation of ArcGIS Pro, and access to the deployment PowerShell script):
- Initialize conda in PowerShell
   1. Open PowerShell in Terminal
   2. Run this: 
        ```powershell
        & $Env:programFiles\ArcGIS\Pro\bin\Python\condabin\conda.bat init
        ```
   5. Open a new PowerShell terminal for the initialization to take effect (the prompt in PowerShell should now be prefixed with the active conda environment in parentheses, e.g: `(base) PS C:\Users\J_Jacobs>`)
- Run GIS Team default conda env deployment script
   1. Open PowerShell in Terminal
   2. Change directory to the root of this repository, so that the relative path called below allows PowerShell to find the necessary .ps1 file
   3. Run this: 
        ```powershell
        & utilities\powershell\deploy_esri_py_env_pro.ps1
        ```
   4. In case of errors, read and follow any output messages carefully

#### Using python outside of conda
Python can be installed directly from [python.org](https://www.python.org/), at a per user level and without admin credentials. This is a valid approach to non-arcpy-based workflows, since it has so far proven impossible to pip install arcpy directly into a non-conda virtual environment.

#### Known issues
- ArcGIS Pro notebooks do not work on GIS Team PCs, but do on other DCP staff machines. We have hypothesized that this has something to do with either firewall rules, or the fact that our machines have static IP addresses assigned.
- `conda install` fails or freezes often, when using either the ArcGIS Pro GUI or PowerShell. This is likely due to our firewall rules. `pip install` is a viable alternative.

### SQL
If SQL usage outside of ArcGIS Pro is desired, it is recommended to use SQL Server Management Studio (SSMS) for enterprise geodatabase management, with the optional additional usage of DBeaver to access the SQL Server databases, or any other databases such as DuckDB, SQLite, etc.

SSMS requires administrative access to install, but DBeaver and DuckDB can both be installed per user with the `winget` package manager.

### Optional quality of life improvements
#### Add Git Bash to your Terminal
Bash is not native to Windows, but a limited version of bash is added when Git is installed. This version of bash can be used in the IDE, or directly in Terminal, but the latter requires some configuration, described [here.](https://superuser.com/a/1834543) 

## Concept Illustration

### The BBL (Borough, Block, Lot)
A BBL is a (usually) unique identifier for tax lots around NYC. The number is used in the digital tax map (DTM) from the NYC Department of Finance (DOF), and is also commonly used when accessing the MapPLUTO dataset.

A BBL is always 10 numeric characters.

The BBL refers to a single tax lot (there are infrequent exceptions to this rule - sometimes areas like street medians can end up sharing BBLs)

There is a lot of information encoded in these 10 characters.

<img src="diagrams\bbl.png" alt="BBL character explanation" style="width:75%; height:auto;">

#### The base lot
The BBL above refers to a physical plot of land. This is known as the "base lot", and is referred to by the base BBL. This is the BBL that you will find in the tax lot polygon dataset of the DTM:

<img src="diagrams\base_lot.png" alt="Base lot" style="width:75%; height:auto;">

#### Condo and unit lots
What happens when a building with condos is built on this lot, and each condo building contains multiple taxable condo units?

In this case, the base lot becomes one or more condo lots. The condo BBL is what you will find in MapPLUTO and the Zola application, or in the condo table of the DTM.

Additionally, each individual condo unit gets its own unit lot, which are also designated by unit BBLs, but do not necessarily represent a geographic feature in the same way that a base or condo lot do.

<img src="diagrams\condo_and_unit_lots.png" alt="Condo and unit lots" style="width:75%; height:auto;">

Condo and unit BBLs are encoded neatly into the 10-character BBL as well. If the last four digits of the BBL start with a "75", you know this is a condo BBL. The numbers coming after the "75" refer to condos within a single base lot, so if a single base lot is split into condo lots, the last four characters of their condo BBLs will be "7501" and "7502" respectively.

<img src="diagrams\bbl_condo.png" alt="Condo BBL example" style="width:75%; height:auto;">

Similarly, if the last four digits of a BBL start with "1", you know this is a unit BBL. The numbers coming after the "1" refer to units within a single condo, so if two units exist in one condo (like in the image), the last four characters of their unit BBLs will be "1001" and "1002" respectively.

<img src="diagrams\bbl_unit.png" alt="Unit BBL example" style="width:75%; height:auto;">

### Constructing a BBL
Sometimes you have borough, block, and lot values, but you want use them to construct the full 10-character BBL. Here are some methods, assuming your data is in a CSV like this:

| BORO | BLOCK | LOT |
|------|-------|-----|
| 1	| 2345 | 678 |

And you want to calculate a new BBL column that looks like this:
| ... | BBL |
|------|-------|
| ... | 1023450678 |

---
#### Excel
`=(A2*1000000000)+(B2*10000)+C2`

Update the cell references as needed to refer to BORO, BLOCK, and LOT, in that order.

---
#### Python/pandas:
```python
import pandas as pd

data = r"data.csv"
df = pd.read_csv(data)

df["BBL"] = (
    df["BORO"].astype("str")
    + df["BLOCK"].astype("str").str.pad(width=5, side="left", fillchar="0")
    + df["LOT"].astype("str").str.pad(width=4, side="left", fillchar="0")
)
```
---
#### ArcGIS Field Calculator:

`Expression:`
```python
calculate_bbl(!BORO!, !BLOCK!, !LOT!)
```
`Code Block:`
```python
def calculate_bbl(boro, block, lot):
    padded_boro = str(boro)
    padded_block = str(block).rjust(5, "0")
    padded_lot = str(lot).rjust(4, "0")
    return f"{padded_boro}{padded_block}{padded_lot}"
```
---
#### SQL:
```sql
SELECT
	BORO,
	BLOCK,
	LOT,
	CONCAT(
        BORO::VARCHAR, 
        LPAD(BLOCK::VARCHAR, 5, '0'), 
        LPAD(LOT::VARCHAR, 4, '0')
        ) as BBL 
FROM TABLE;
```
Written using `duckdb`, but can be adapted to other SQL flavors.

---

