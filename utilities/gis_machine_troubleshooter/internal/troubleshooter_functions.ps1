<#
    Title: GIS Machine Troubleshooter - shared functions
    Purpose:
        Function definitions used by run_troubleshooter.ps1, split out into their own file
        so they can be dot-sourced independently (by the script, and by Pester tests)
        without also running run_troubleshooter.ps1's top-level collection/report logic.
#>

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
        # @(...) forces an array even when only one entry survives the filter - without it,
        # a single-string pipeline result collapses to a scalar and $entries[0] below would
        # index into the STRING'S CHARACTERS instead of the array.
        $entries = @($ProxyServerValue -split ';' | Where-Object { $_ })
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

# Thin wrapper around the external netsh call so it can be mocked in tests - Pester 3.4's
# Mock doesn't reliably intercept calls to external executables, only cmdlets/functions.
function Get-NetshWinHttpProxyOutput {
    netsh winhttp show proxy
}

# The per-user WinINet key (HKCU\...\Internet Settings) is what IE/legacy apps use, but
# many machines here are actually proxied machine-wide via WinHTTP instead - WinINet can
# report no proxy configured while WinHTTP has one active. Surface both.
function Get-WinHttpProxyAddressPort {
    $output = (Get-NetshWinHttpProxyOutput) -join "`n"
    # Match the proxy value's own shape (host:port, optionally scheme=-prefixed and
    # ;-chained) rather than keying off the "Proxy Server(s)" label, which netsh
    # localizes on non-English Windows installs.
    if ($output -notmatch '((?:\w+=)?[\w.-]+:\d+(?:;[\w.-]+=[\w.-]+:\d+)*)') {
        return [pscustomobject]@{ Address = ''; Port = '' }
    }
    Get-ProxyAddressPort -ProxyServerValue $Matches[1]
}

# Default ArcGIS Pro install location and conda env name are hardcoded rather than
# configurable - this tool intentionally has no config file to go missing or drift.
function Resolve-ArcGisPythonPath {
    # $Env:ProgramFiles is redirected to the x86 path under a 32-bit PowerShell host;
    # $Env:ProgramW6432 always points at the true 64-bit Program Files, so check it first.
    $programFilesRoots = @($Env:ProgramW6432, $Env:ProgramFiles) | Where-Object { $_ } | Select-Object -Unique
    foreach ($root in $programFilesRoots) {
        $candidate = Join-Path $root 'ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe'
        if (Test-Path $candidate) { return $candidate }
    }
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
