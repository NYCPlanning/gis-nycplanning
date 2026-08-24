<#
    Title: GIS Machine Troubleshooter
    Purpose:
        Collects desktop and ArcGIS Pro project diagnostics into a single report so GIS
        support staff can triage common tickets (network/proxy/ODBC, wrong Pro sign-in
        account, broken layers) without a live session.
        Standalone by design - does not depend on this repo's dcpgis package, and calls
        the machine's default ArcGIS Pro conda env directly. No config file - everything
        needed is either derived at runtime or hardcoded below.
    Usage:
        Double-click, or from a terminal:
            .\run_troubleshooter.ps1 [-AprxPath <path to .aprx>]
        If -AprxPath is omitted you will be prompted for one; leave the prompt blank to
        skip GIS-level checks (e.g. if you don't have a project open).
        The window stays open after the report is built so the result and report path(s)
        can be read - press Enter to close it.
    Notes:
        - Report is always written to the current user's Desktop.
        - Produces a three-tab .xlsx (System Info / Installed Programs / GIS Info) via Excel
          COM automation; if Excel isn't available on the machine, falls back to writing
          three .csv files instead.
#>
param(
    [string]$AprxPath
)

function Get-InstalledPrograms {
    $uninstallPaths = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    Get-ItemProperty -Path $uninstallPaths -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName } |
        Select-Object @{N = 'DisplayName'; E = { $_.DisplayName } },
                       @{N = 'DisplayVersion'; E = { $_.DisplayVersion } },
                       @{N = 'Publisher'; E = { $_.Publisher } } |
        Sort-Object DisplayName
}

# No fixed list of expected drivers to check against - just surface whatever
# ODBC-related entries already showed up in the installed programs list.
function Get-OdbcDriversFromInstalledPrograms {
    param($InstalledPrograms)
    $InstalledPrograms | Where-Object { $_.DisplayName -match 'ODBC' }
}

function Get-NetworkDrives {
    # Get-SmbMapping misses drives mapped through non-SMB providers (e.g. NetWare
    # Services via legacy "net use") - Get-PSDrive's DisplayRoot catches all of them.
    Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue | Where-Object { $_.DisplayRoot } | ForEach-Object {
        [pscustomobject]@{
            DriveLetter = "$($_.Name):"
            Path        = $_.DisplayRoot
        }
    }
}

# Handles a bare "host:port", a protocol-keyed string like "http=host:port;https=host2:port2",
# and a scheme-prefixed URL like "http://host:port" (the shape netsh winhttp reports).
function Get-ProxyAddressPort {
    param([string]$ProxyServerValue)
    if (-not $ProxyServerValue) {
        return [pscustomobject]@{ Address = ''; Port = '' }
    }
    $primary = $ProxyServerValue
    if ($ProxyServerValue -match '=') {
        $entries = $ProxyServerValue -split ';' | Where-Object { $_ }
        $httpEntry = $entries | Where-Object { $_ -like 'http=*' } | Select-Object -First 1
        $chosen = if ($httpEntry) { $httpEntry } else { $entries[0] }
        $primary = ($chosen -split '=', 2)[1]
    }
    $primary = $primary -replace '^\w+://', ''
    $parts = $primary -split ':', 2
    [pscustomobject]@{
        Address = $parts[0]
        Port    = if ($parts.Count -gt 1) { $parts[1] } else { '' }
    }
}

# The per-user WinINet key (HKCU\...\Internet Settings) is what IE/legacy apps use, but
# many machines here are actually proxied machine-wide via WinHTTP instead - WinINet can
# report no proxy configured while WinHTTP has one active. Surface both.
function Get-WinHttpProxyAddressPort {
    $output = (netsh winhttp show proxy) -join "`n"
    if ($output -notmatch 'Proxy Server\(s\)\s*:\s*(\S+)') {
        return [pscustomobject]@{ Address = ''; Port = '' }
    }
    Get-ProxyAddressPort -ProxyServerValue $Matches[1]
}

# Default ArcGIS Pro install location and conda env name are hardcoded rather than
# configurable - this tool intentionally has no config file to go missing or drift.
function Resolve-ArcGisPythonPath {
    $candidate = "$Env:ProgramFiles\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
    if (Test-Path $candidate) { return $candidate }
    return $null
}

# Writes a list of {Title; Rows} sections to a worksheet as stacked mini-tables.
function Write-SheetSections {
    param($Worksheet, $Sections)
    $row = 1
    foreach ($section in $Sections) {
        $Worksheet.Cells.Item($row, 1) = $section.Title
        $Worksheet.Cells.Item($row, 1).Font.Bold = $true
        $row++
        $rows = @($section.Rows)
        if ($rows.Count -gt 0) {
            $headers = $rows[0].PSObject.Properties.Name
            for ($col = 0; $col -lt $headers.Count; $col++) {
                $Worksheet.Cells.Item($row, $col + 1) = $headers[$col]
                $Worksheet.Cells.Item($row, $col + 1).Font.Bold = $true
            }
            $row++
            foreach ($dataRow in $rows) {
                for ($col = 0; $col -lt $headers.Count; $col++) {
                    $Worksheet.Cells.Item($row, $col + 1) = [string]$dataRow.($headers[$col])
                }
                $row++
            }
        }
        $row++ # blank separator row between sections
    }
    $Worksheet.Columns.AutoFit() | Out-Null
}

# CSV fallback for when Excel COM automation isn't available - same section data, one file per tab.
function Export-SectionsToCsv {
    param($Sections, $Path)
    Remove-Item $Path -ErrorAction SilentlyContinue
    foreach ($section in $Sections) {
        Add-Content -Path $Path -Value "## $($section.Title)"
        $rows = @($section.Rows)
        if ($rows.Count -gt 0) {
            $rows | ConvertTo-Csv -NoTypeInformation | Add-Content -Path $Path
        }
        Add-Content -Path $Path -Value ''
    }
}

# --- Main ---
# Wrapped in try/catch/finally so the window always reports a clear result and
# stays open (via the Read-Host at the very end) instead of vanishing on exit.

$reportPaths = @()
try {
    Write-Output ">>> Collecting system-level info"
    $username = $env:USERNAME
    $deviceName = $env:COMPUTERNAME
    $networkProfiles = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object Name, InterfaceAlias, NetworkCategory
    $proxySettings = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
    $driveResults = Get-NetworkDrives
    $installedPrograms = Get-InstalledPrograms
    $odbcResults = Get-OdbcDriversFromInstalledPrograms -InstalledPrograms $installedPrograms
    $proxyAddressPort = Get-ProxyAddressPort -ProxyServerValue $proxySettings.ProxyServer
    $winHttpProxyAddressPort = Get-WinHttpProxyAddressPort

    $systemSections = @(
        @{ Title = 'Identity'; Rows = @(
            [pscustomobject]@{ Property = 'Username'; Value = $username }
            [pscustomobject]@{ Property = 'Device Name'; Value = $deviceName }
        ) }
        @{ Title = 'Network Connection'; Rows = $networkProfiles }
        @{ Title = 'Proxy Settings'; Rows = @(
            [pscustomobject]@{ Property = 'WinINet Proxy Enabled'; Value = [bool]$proxySettings.ProxyEnable }
            [pscustomobject]@{ Property = 'WinINet Proxy Address'; Value = $proxyAddressPort.Address }
            [pscustomobject]@{ Property = 'WinINet Proxy Port'; Value = $proxyAddressPort.Port }
            [pscustomobject]@{ Property = 'Auto Config URL'; Value = $proxySettings.AutoConfigURL }
            [pscustomobject]@{ Property = 'WinHTTP Proxy Address'; Value = $winHttpProxyAddressPort.Address }
            [pscustomobject]@{ Property = 'WinHTTP Proxy Port'; Value = $winHttpProxyAddressPort.Port }
        ) }
        @{ Title = 'ODBC Drivers'; Rows = $odbcResults }
        @{ Title = 'Network Drives'; Rows = $driveResults }
    )

    $installedProgramsSections = @(
        @{ Title = 'Installed Programs'; Rows = $installedPrograms }
    )

    Write-Output ">>> Locating default ArcGIS Pro python environment"
    $pythonPath = Resolve-ArcGisPythonPath

    if (-not $AprxPath) {
        $AprxPath = Read-Host "Enter path to .aprx project (leave blank to skip GIS-level checks)"
    }

    $gisInfo = $null
    if ($pythonPath) {
        Write-Output ">>> Collecting GIS-level info via $pythonPath"
        try {
            $scriptPath = Join-Path $PSScriptRoot 'collect_gis_info.py'
            $rawOutput = & $pythonPath $scriptPath $AprxPath
            $gisInfo = $rawOutput | ConvertFrom-Json
        } catch {
            Write-Output ">>> GIS-level collection failed: $_"
            $gisInfo = [pscustomobject]@{ error = "GIS-level collection failed: $_" }
        }
    } else {
        Write-Output ">>> Default ArcGIS Pro conda env not found - skipping GIS-level checks"
        $gisInfo = [pscustomobject]@{ error = 'ArcGIS Pro default conda env not found on this machine' }
    }

    if ($gisInfo.error) {
        $gisSections = @(
            @{ Title = 'GIS-Level Info'; Rows = @([pscustomobject]@{ Property = 'Error'; Value = $gisInfo.error }) }
        )
    } else {
        $gisSections = @(
            @{ Title = 'Project Info'; Rows = @(
                [pscustomobject]@{ Property = 'Aprx Path'; Value = $gisInfo.aprx_path }
            ) }
            @{ Title = 'Software Info'; Rows = @(
                [pscustomobject]@{ Property = 'Account'; Value = $gisInfo.signed_in_account }
                [pscustomobject]@{ Property = 'Software Version'; Value = $gisInfo.software_version }
                [pscustomobject]@{ Property = 'Python Version'; Value = $gisInfo.python_version }
            ) }
            @{ Title = 'Layer Inventory'; Rows = @($gisInfo.layers | Select-Object @{N = 'Map'; E = { $_.map } },
                                                                                    @{N = 'Layer'; E = { $_.layer } },
                                                                                    @{N = 'Data Source'; E = { $_.data_source } },
                                                                                    @{N = 'Is Broken'; E = { if ($_.is_broken) { 'TRUE' } else { 'FALSE' } } }) }
        )
    }

    $outputDir = [Environment]::GetFolderPath('Desktop')
    $timestamp = Get-Date -Format 'yyyyMMddHHmmss'
    $baseName = "gis_report_${username}_${deviceName}_${timestamp}"

    Write-Output ">>> Building report"
    $excel = $null
    $workbook = $null
    try {
        $excel = New-Object -ComObject Excel.Application
        $excel.Visible = $false
        $excel.DisplayAlerts = $false
        $workbook = $excel.Workbooks.Add()

        $sysSheet = $workbook.Worksheets.Item(1)
        $sysSheet.Name = 'System Info'
        while ($workbook.Worksheets.Count -gt 1) {
            $workbook.Worksheets.Item($workbook.Worksheets.Count).Delete()
        }
        $programsSheet = $workbook.Worksheets.Add()
        $programsSheet.Name = 'Installed Programs'
        $programsSheet.Move([System.Reflection.Missing]::Value, $sysSheet)

        $gisSheet = $workbook.Worksheets.Add()
        $gisSheet.Name = 'GIS Info'
        $gisSheet.Move([System.Reflection.Missing]::Value, $programsSheet)

        Write-SheetSections -Worksheet $sysSheet -Sections $systemSections
        Write-SheetSections -Worksheet $programsSheet -Sections $installedProgramsSections
        Write-SheetSections -Worksheet $gisSheet -Sections $gisSections

        $xlsxPath = Join-Path $outputDir "$baseName.xlsx"
        $workbook.SaveAs($xlsxPath, 51) # 51 = xlOpenXMLWorkbook (.xlsx)
        $reportPaths = @($xlsxPath)
    } catch {
        Write-Output ">>> Excel automation unavailable ($_) - falling back to CSV"
        $sysCsvPath = Join-Path $outputDir "${baseName}_system.csv"
        $programsCsvPath = Join-Path $outputDir "${baseName}_installed_programs.csv"
        $gisCsvPath = Join-Path $outputDir "${baseName}_gis.csv"
        Export-SectionsToCsv -Sections $systemSections -Path $sysCsvPath
        Export-SectionsToCsv -Sections $installedProgramsSections -Path $programsCsvPath
        Export-SectionsToCsv -Sections $gisSections -Path $gisCsvPath
        $reportPaths = @($sysCsvPath, $programsCsvPath, $gisCsvPath)
    } finally {
        if ($workbook) { $workbook.Close($false); [Runtime.InteropServices.Marshal]::ReleaseComObject($workbook) | Out-Null }
        if ($excel) { $excel.Quit(); [Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null }
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }

    $flags = @()
    if (@($odbcResults).Count -eq 0) { $flags += 'no ODBC driver detected' }
    if (@($driveResults).Count -eq 0) { $flags += 'no network drives mapped' }
    if ($gisInfo -and $gisInfo.layers -and ($gisInfo.layers | Where-Object { $_.is_broken })) { $flags += 'broken layer(s)' }

    if ($flags.Count -gt 0) {
        Write-Output ">>> Flags found: $($flags -join ', ')"
    } else {
        Write-Output ">>> No issues flagged"
    }

    $resultMessage = ">>> SUCCESS"
} catch {
    $resultMessage = ">>> FAILURE: $_"
} finally {
    Write-Output $resultMessage
    Write-Output ">>> Report path(s): $($reportPaths -join ', ')"
    Read-Host "Press Enter to close this window"
}
