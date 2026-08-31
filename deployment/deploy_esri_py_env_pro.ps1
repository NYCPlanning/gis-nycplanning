<#
    Title: Deploy GIS Team Esri Python Environment
    Purpose:
        Clones the default Python environment, uses a standardized naming convention,
        and installs packages listed in conda-requirements.txt and conda-requirements-dev.txt
        (in this same folder) to supplement the default packages.
    Author: J Rosacker
    Updated by: U Podder
    Date: 2026-02-03
    Notes:
        The script was written to interact with Python 3.11.11 (ArcGIS Pro 3.5.5),
        but should still function for later versions of both Python and Pro.
        Compatible package versions (e.g., geopandas, numpy, fiona) will be automatically resolved by conda.
        To add or change a base/dev package, edit conda-requirements.txt or conda-requirements-dev.txt
        and rerun this script -- do not hardcode packages here.
#>


$newEnvName = 'gis-env'
$baseEnvName = 'arcgispro-py3'
$baseRequirementsFile = Join-Path $PSScriptRoot 'conda-requirements.txt'
$devRequirementsFile = Join-Path $PSScriptRoot 'conda-requirements-dev.txt'

# Dynamically detect Python version from base ArcGIS Pro environment
Write-Output "`r`n>>> Detecting Python version from $baseEnvName..."
$pythonVersion = ((& "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\Scripts\conda.exe" run -n $baseEnvName python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") | Where-Object { $_ -match '^\d+\.\d+$' } | Select-Object -Last 1).Trim()
Write-Output ">>> Detected Python version: $pythonVersion"

# Check conda version as a proxy to determine if conda is initialized in this shell
try {
    Write-Output "`r`n>>> Checking conda version..."
    & "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\Scripts\conda.exe" --version
}
catch {
    $message = @"

>>> Encountered an error. Is conda initialized for your PowerShell? If not:

1. Run the two commands below in PowerShell (copy/paste the two lines in their entirety into PS and run): 
    set-executionpolicy remotesigned -scope currentuser
    & 'C:\Program Files\ArcGIS\Pro\bin\Python\condabin\conda.bat' init

2. Open a new PowerShell window (or close and restart) and run this deployment script again

More info: https://www.esri.com/arcgis-blog/products/arcgis-pro/developers/conda-init-and-arcgis-pro/

"@
    Write-Output $message
    Write-Output ">>> Error message: " $_
    break 
}

# Test for existence of base env by checking if its directory exists (avoids slow conda env list)
Write-Output "`r`n>>> Checking for base env: $baseEnvName..."
$baseEnvPath = "$Env:programFiles\ArcGIS\Pro\bin\Python\envs\$baseEnvName"
if (-not (Test-Path $baseEnvPath)) {
    Write-Output ">>> Exiting script since $baseEnvName env could not be found at: $baseEnvPath"
    exit 1
}
Write-Output ">>> Found base env: $baseEnvName"


# Clone the base environment using explicit conda.exe path
Write-Output "`r`n>>> Cloning $baseEnvName into $newEnvName..."
& "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\Scripts\conda.exe" create --name $newEnvName --clone $baseEnvName --yes

# Install base and dev packages from the frozen requirement files
foreach ($requirementsFile in @($baseRequirementsFile, $devRequirementsFile)) {
    if (-not (Test-Path $requirementsFile)) {
        Write-Output ">>> Exiting script since requirements file could not be found at: $requirementsFile"
        exit 1
    }
}

Write-Output "`r`n>>> Installing packages from $baseRequirementsFile and $devRequirementsFile with conda..."
& "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\Scripts\conda.exe" install -n $newEnvName --file $baseRequirementsFile --file $devRequirementsFile --yes
if ($LASTEXITCODE -ne 0) {
    Write-Output "`r`n>>> conda install failed (exit code $LASTEXITCODE). Falling back to pip install, per docs/wiki.md Known Issues..."
    & "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\envs\$newEnvName\Scripts\pip.exe" install -r $baseRequirementsFile -r $devRequirementsFile
    if ($LASTEXITCODE -ne 0) {
        Write-Output "`r`n>>> pip install fallback also failed (exit code $LASTEXITCODE). See docs/wiki.md Known Issues for troubleshooting."
        exit 1
    }
    Write-Output ">>> Successfully installed packages using pip fallback"
}
else {
    Write-Output ">>> Successfully installed packages using conda"
}


# List conda environments using explicit conda.exe path
# Note: `conda env list` is broken on Pro 3.5+ (see docs/wiki.md Known Issues) -- use `conda info --envs` instead
Write-Output "`r`n>>> Listing conda environments..."
& "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\Scripts\conda.exe" info --envs

# Note: If activation doesn't visibly take effect, run `conda activate gis-env` manually in your terminal.
Write-Output "`r`n>>> Activating $newEnvName..."
conda activate $newEnvName

Write-Output "`r`n>>> Done."