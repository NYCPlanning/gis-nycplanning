<#
    Title: Deploy GIS Team Esri Python Environment
    Purpose:
        Clones the default Python environment, installs packages listed in conda-requirements.txt
        and conda-requirements-dev.txt (in this same folder), then installs dcpgis in editable mode
        from the checkout this script is run from.
        -EnvName defaults to gis-env from the main clone, or gis-env-<worktree folder> from a worktree.
    Author: J Rosacker
    Updated by: U Podder
    Date: _ongoing_
    Notes:
        The script was written to interact with Python 3.11.11 (ArcGIS Pro 3.5.5),
        but should still function for later versions of both Python and Pro.
        To add or change a base/dev package, edit conda-requirements.txt or conda-requirements-dev.txt
        and rerun this script -- do not hardcode packages here.
#>
param ([string]$EnvName)

$prodEnvName = 'gis-env'
$baseEnvName = 'arcgispro-py3'
$baseRequirementsFile = Join-Path $PSScriptRoot 'conda-requirements.txt'
$devRequirementsFile = Join-Path $PSScriptRoot 'conda-requirements-dev.txt'
$defaultCondaExe = "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\Scripts\conda.exe"
$repoRoot = Split-Path $PSScriptRoot -Parent

# .git is a file, not a directory, in a linked worktree
$isWorktree = -not (Test-Path (Join-Path $repoRoot '.git') -PathType Container)
if (-not $EnvName) {
    if ($isWorktree) { $EnvName = "gis-env-$(Split-Path $repoRoot -Leaf)" } else { $EnvName = $prodEnvName }
}
if ($isWorktree -and $EnvName -eq $prodEnvName) {
    Write-Output ">>> Refusing to build $prodEnvName from a git worktree ($repoRoot). Run this script from your main clone."
    exit 1
}
Write-Output ">>> Building env '$EnvName' with dcpgis pointed at $repoRoot"

# Dynamically detect Python version from base ArcGIS Pro environment
Write-Output "`r`n>>> Detecting Python version from $baseEnvName..."
$pythonVersion = ((& $defaultCondaExe run -n $baseEnvName python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") | Where-Object { $_ -match '^\d+\.\d+$' } | Select-Object -Last 1).Trim()
Write-Output ">>> Detected Python version: $pythonVersion"

# Check conda version as a proxy to determine if conda is initialized in this shell
try {
    Write-Output "`r`n>>> Checking conda version..."
    & $defaultCondaExe --version
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

foreach ($requirementsFile in @($baseRequirementsFile, $devRequirementsFile)) {
    if (-not (Test-Path $requirementsFile)) {
        Write-Output ">>> Exiting script since requirements file could not be found at: $requirementsFile"
        exit 1
    }
}


# Clone the base environment using explicit conda.exe path
Write-Output "`r`n>>> Cloning $baseEnvName into $EnvName..."
& $defaultCondaExe create --name $EnvName --clone $baseEnvName --yes

Write-Output "`r`n>>> Installing packages from $baseRequirementsFile and $devRequirementsFile with conda..."
& $defaultCondaExe install -n $EnvName --file $baseRequirementsFile --file $devRequirementsFile --yes
if ($LASTEXITCODE -ne 0) {
    Write-Output "`r`n>>> conda install failed (exit code $LASTEXITCODE). If a pinned version in conda-requirements.txt no longer fits this ArcGIS Pro release, bump it (see docs/wiki.md). Otherwise see docs/wiki.md Known Issues."
    exit 1
}
Write-Output ">>> Successfully installed packages using conda"

Write-Output "`r`n>>> Installing dcpgis from $repoRoot in editable mode..."
& $defaultCondaExe run -n $EnvName python -m pip install -e $repoRoot --no-deps --no-build-isolation
if ($LASTEXITCODE -ne 0) {
    Write-Output "`r`n>>> Editable install of dcpgis failed (exit code $LASTEXITCODE). To retry manually, from the repo root in $EnvName run:"
    Write-Output "    python -m pip install -e . --no-deps --no-build-isolation"
    exit 1
}
Write-Output ">>> Successfully installed dcpgis"

# print installed versions of required packages after installation
# facilitates bumping versions after a Pro upgrade
$basePackageNames = Get-Content $baseRequirementsFile |
    Where-Object { $_ -match '^\s*[A-Za-z0-9]' } |
    ForEach-Object { ($_ -split '[=<>!~ ]')[0].Trim() }
Write-Output "`r`n>>> Resolved versions of packages in conda-requirements.txt:"
& $defaultCondaExe list -n $EnvName "^($($basePackageNames -join '|'))$"


# List conda environments using explicit conda.exe path
# Note: `conda env list` is broken on Pro 3.5+ (see docs/wiki.md Known Issues) -- use `conda info --envs` instead
Write-Output "`r`n>>> Listing conda environments..."
& $defaultCondaExe info --envs

# Note: If activation doesn't visibly take effect, run `conda activate <env name>` manually in your terminal.
# Bare conda command called here to avoid init + subprocess nonsense.
Write-Output "`r`n>>> Activating $EnvName..."
conda activate $EnvName

Write-Output "`r`n>>> Done."
