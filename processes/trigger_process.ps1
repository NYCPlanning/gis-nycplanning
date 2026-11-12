<#
    Title: Trigger Python script with Esri Python interpreter
    Purpose:
        This script can be called by any GIS Team member to trigger a Python script using
        an Esri Python interpreter, which defaults to the standard interpreter for the team,
        or can use a user-provided value to call a custom environment.
    Usage:
        Named Parameters:
            $scriptName - (required) Absolute or relative path and file name of the Python
                script that will be triggered.
            $envName - (optional) Defaults to the value defined below. Can be overridden by
                a value provided by user. Should be name of env only, not the full path;
                conda resolves where the env lives.
        Task Scheduler Action settings:
            Program/script:
                powershell
            Add arguments:
                -NoExit -Command & '<ABSOLUTE PATH>\trigger_process.ps1' -scriptName <RELATIVE PATH\PY SCRIPT NAME.py>
    Author: J Rosacker
    Date: 2025-03-06
    Notes:
        - The "-NoExit" flag is optional, and will keep the terminal open after the script has executed
        - Make sure to replace all values within <> brackets in the Arguments clause of the scheduled task

#>
# Get script name and conda env parameters from user input
param ($scriptName, $envName='gis-env')

$condaExe = "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\Scripts\conda.exe"

# Relative script paths are resolved from this folder
Set-Location $PSScriptRoot

# conda run looks the env up by name, since where it lives depends on each user's .condarc envs_dirs.
# --no-capture-output streams the script's output live instead of dumping it when the script ends.
& $condaExe run -n $envName --no-capture-output python $scriptName
exit $LASTEXITCODE