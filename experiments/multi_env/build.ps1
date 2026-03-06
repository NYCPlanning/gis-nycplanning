$REPO_NAME = "data-engineering"
$VENV = ".venv"

conda activate arcgispro-py3

# Make .venv
Write-Host "Creating a new Python virtual environment"
conda create --prefix "$PSScriptRoot\$VENV" python=3.13 -c conda-forge

# Install dcpy
& "$PSScriptRoot\.venv\Scripts\pip.exe" install "git+https://github.com/NYCPlanning/data-engineering.git" --no-warn-script-location 