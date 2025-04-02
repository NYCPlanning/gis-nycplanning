<#
    Title: Deploy GIS Team Esri Python Environment
    Purpose: 
        Clones the default Python environment, uses a standardized naming convention,
        installs packages such as geopandas to supplement the default packages, and attempts
        to adjust dependency versions (i.e. numpy for geopandas)
    Author: J Rosacker
    Date: 2025-02-21
    Notes: 
        The script assumes that the origin env uses Python 3.9.16, and that the subsequent
        numpy version to satisfy geopandas is 1.22. These will change as we upgrade to higher 
        versions of ArcGIS Pro.
#>
$newEnvName = 'gis-team-default-env'
$baseEnvName = 'arcgispro-py3'
$numpyVersion = 1.22

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

# Test for existence of env to clone, by activating it
# Exit script if env can not be found
try {
    Write-Output "`r`n>>> Checking for base env: $baseEnvName..."
    conda activate $baseEnvName
    conda deactivate
}
catch {
    Write-Output ">>> Existing script since $baseEnvName env could not be found"
    break
}

Write-Output "`r`n>>> Cloning $baseEnvName into $newEnvName..."
conda create --name $newEnvName --clone $baseEnvName

Write-Output "`r`n>>> Activating $newEnvName..."
conda activate $newEnvName

Write-Output "`r`n>>> pip installing geopandas..."
pip install geopandas

Write-Output "`r`n>>> Dropping numpy version to $numpyVersion to satisfy geopandas dependencies..."
pip install --user numpy==$numpyVersion

Write-Output "`r`n>>> Listing all conda environments..."
conda info --envs