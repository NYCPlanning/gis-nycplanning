<#
    Title: Trigger Python script with Esri Python interpreter
    Purpose: 
        This script can be called by any GIS Team member to trigger a Python script using
        an Esri Python interpreter, which defaults to the standard interpreter for the team,
        or can use a user-provided value to call a custom environment.
    Usage:
        Named Parameters:
            $scriptName - (required) Should be the absolute or relative path and file name
                of the Python script that will be triggered.
            $envName - (optional) Defaults to the value defined below. Can be overridden by
                a value provided by user. Should be name of env only, not the full path.
    Author: J Rosacker
    Date: 2025-03-06
    Notes:
        
#>
# Get script name and conda env parameters from user input
param ($scriptName, $envName='gis-team-default-env')

# Get name of current user
$currentUser = (Get-ChildItem Env:USERNAME).Value
# Use conda env name and username params to construct the path to the correct Esri python interpreter
$interpreterPath = 'C:/Users/{0}/AppData/Local/ESRI/conda/envs/{1}/python.exe' -f $currentUser, $envName

# Change directory to the location of this script
Set-Location $PSScriptRoot

# Run specified Python file using specified Esri Python interpreter
& $interpreterPath $scriptName