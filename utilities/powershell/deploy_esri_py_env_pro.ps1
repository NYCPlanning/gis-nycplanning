<#
    Title: Deploy GIS Team Esri Python Environment
    Purpose: 
        Clones the default Python environment, uses a standardized naming convention,
        installs packages such as geopandas to supplement the default packages, and attempts
        to adjust dependency versions (i.e. numpy for geopandas)
    Author: J Rosacker
    Updated by: U Podder
    Date: 2026-02-03
    Notes: 
        The script assumes that the origin env uses Python 3.11.11 (ArcGIS Pro 3.5.5), and that the subsequent
        numpy version to satisfy geopandas is 1.26.4. These will change as we upgrade to higher 
        versions of ArcGIS Pro.
#>

# Suppress the archspec/active_prefix_name plugin error in ArcGIS Pro's bundled conda
$env:CONDA_NO_PLUGINS = 'true'

$newEnvName = 'gis-team-default-env'
$baseEnvName = 'arcgispro-py3'

# Dynamically detect Python version from base ArcGIS Pro environment
Write-Output "`r`n>>> Detecting Python version from $baseEnvName..."
$pythonVersion = ((& conda run -n $baseEnvName python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") | Where-Object { $_ -match '^\d+\.\d+$' } | Select-Object -Last 1).Trim()
Write-Output ">>> Detected Python version: $pythonVersion"

# Set package versions based on detected Python version
# Add a new case here when upgrading to a new ArcGIS Pro / Python version
switch ($pythonVersion) {
    '3.11' {
        $numpyVersion = '1.26.4'
        $geopandasVersion = '0.14.3'
        $fionaVersion = '1.9.6'
    }
    default {
        # Update this script by adding a new case above with the correct package versions.
        Write-Output ">>> WARNING: Unrecognized Python version '$pythonVersion'. Using latest known compatible versions. Consider updating this script."
        $numpyVersion = '1.26.4'
        $geopandasVersion = '0.14.3'
        $fionaVersion = '1.9.6'
    }
}

# Check conda version as a proxy to determine if conda is initialized in this shell
try {
    Write-Output "`r`n>>> Checking conda version..."
    conda --version
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

# Check if target env already exists by directory, and remove it if so
$newEnvPath = "$Env:LOCALAPPDATA\ESRI\conda\envs\$newEnvName"
$existingEnvs = Test-Path $newEnvPath
if ($existingEnvs) {
    Write-Output "`r`n>>> Environment '$newEnvName' already exists. Removing it first..."
    Remove-Item -Recurse -Force $newEnvPath
    Write-Output ">>> Removed existing environment at: $newEnvPath"
}

Write-Output "`r`n>>> Cloning $baseEnvName into $newEnvName..."
conda create --name $newEnvName --clone $baseEnvName --yes

# Use pip from the new env directly to ensure packages install into the correct environment
$pipExe = "$newEnvPath\Scripts\pip.exe"

# Install compatible versions for detected Python version
Write-Output "`r`n>>> pip installing geopandas version $geopandasVersion..."
& $pipExe install "geopandas==$geopandasVersion"

Write-Output "`r`n>>> Installing numpy version $numpyVersion to satisfy geopandas dependencies..."
& $pipExe install numpy==$numpyVersion

Write-Output "`r`n>>> pip installing fiona version $fionaVersion..."
& $pipExe install "fiona==$fionaVersion"

Write-Output "`r`n>>> Listing conda environments..."
Get-ChildItem "$Env:LOCALAPPDATA\ESRI\conda\envs" -Directory | Select-Object -ExpandProperty Name

Write-Output "`r`n>>> Activating $newEnvName..."
conda activate $newEnvName

Write-Output "`r`n>>> Done."