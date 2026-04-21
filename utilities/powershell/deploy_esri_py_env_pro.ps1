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

# ...existing code...

$newEnvName = 'gis-team-default-env'
$baseEnvName = 'arcgispro-py3'

# Dynamically detect Python version from base ArcGIS Pro environment
Write-Output "`r`n>>> Detecting Python version from $baseEnvName..."
$pythonVersion = ((& "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\Scripts\conda.exe" run -n $baseEnvName python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") | Where-Object { $_ -match '^\d+\.\d+$' } | Select-Object -Last 1).Trim()
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

# Install compatible versions for detected Python version using conda only
Write-Output "`r`n>>> Installing geopandas, numpy, and fiona with conda..."
& "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\Scripts\conda.exe" install -n $newEnvName geopandas=$geopandasVersion numpy=$numpyVersion fiona=$fionaVersion --yes
Write-Output ">>> Successfully installed packages using conda"


# List conda environments using explicit conda.exe path
Write-Output "`r`n>>> Listing conda environments..."
& "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\Scripts\conda.exe" env list

# Note: conda activate may not work as expected in all PowerShell contexts.
# If activation fails, activate manually in a new shell using:
# & 'C:\Program Files\ArcGIS\Pro\bin\Python\condabin\conda.bat' activate $newEnvName
Write-Output "`r`n>>> Activating $newEnvName..."
& 'C:\Program Files\ArcGIS\Pro\bin\Python\condabin\conda.bat' activate $newEnvName

Write-Output "`r`n>>> Done."