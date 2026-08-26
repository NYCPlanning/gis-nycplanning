#Requires -Modules Pester
<#
    This suite deliberately targets Pester 3.4.0 - the version built into Windows -
    rather than a newer Pester requiring a separate module install, since this repo is
    Python-primary and its PowerShell surface is intentionally kept small (this one tool).
    That means:
      - Assertions use the OLD `Should <op> <value>` syntax (e.g. `Should Be`), NOT the
        newer `Should -Be` dash syntax, which 3.4.0 does not understand. Do not "modernize"
        this without re-checking it still runs on the Windows-builtin Pester version.
      - `Mock` targets PowerShell functions only, never external executables directly (3.4.0
        doesn't reliably intercept those) - see Get-NetshWinHttpProxyOutput in
        troubleshooter_functions.ps1, added specifically to give Get-WinHttpProxyAddressPort
        a mockable seam.
      - Skip-style assertions use `Set-TestInconclusive` (3.4.0's equivalent), not the
        newer `Set-ItResult -Skipped`.
#>

# Dot-sourced directly at script scope, not inside a BeforeAll - Pester 3.4.0 only allows
# BeforeAll inside a Describe block, unlike newer Pester which also supports file-scoped ones.
. (Join-Path $PSScriptRoot '..\..\..\utilities\gis_machine_troubleshooter\internal\troubleshooter_functions.ps1')

Describe 'Get-ProxyAddressPort' {
    It 'returns empty Address/Port for a null/empty value' {
        $result = Get-ProxyAddressPort -ProxyServerValue ''
        $result.Address | Should Be ''
        $result.Port | Should Be ''
    }

    It 'parses a bare host:port' {
        $result = Get-ProxyAddressPort -ProxyServerValue 'proxy.example.com:8080'
        $result.Address | Should Be 'proxy.example.com'
        $result.Port | Should Be '8080'
    }

    It 'strips a scheme prefix' {
        $result = Get-ProxyAddressPort -ProxyServerValue 'http://proxy.example.com:8080'
        $result.Address | Should Be 'proxy.example.com'
        $result.Port | Should Be '8080'
    }

    It 'picks the http= entry from a protocol-keyed value' {
        $result = Get-ProxyAddressPort -ProxyServerValue 'http=proxy.example.com:8080;https=proxy2.example.com:8443'
        $result.Address | Should Be 'proxy.example.com'
        $result.Port | Should Be '8080'
    }

    It 'falls back to the first entry when there is no http= entry' {
        $result = Get-ProxyAddressPort -ProxyServerValue 'https=proxy2.example.com:8443'
        $result.Address | Should Be 'proxy2.example.com'
        $result.Port | Should Be '8443'
    }

    It 'returns an empty Port for a host with no port' {
        $result = Get-ProxyAddressPort -ProxyServerValue 'proxy.example.com'
        $result.Address | Should Be 'proxy.example.com'
        $result.Port | Should Be ''
    }
}

Describe 'Get-WinHttpProxyAddressPort' {
    It 'parses a real machine sample (scheme-prefixed, with a bypass list)' {
        Mock Get-NetshWinHttpProxyOutput {
            @(
                ''
                'Current WinHTTP proxy settings:'
                ''
                '    Proxy Server(s) :  http://bcpxy.nycnet:8080'
                '    Bypass List     :  10.*;192.168.*;*.nycnet;<local>'
            )
        }
        $result = Get-WinHttpProxyAddressPort
        $result.Address | Should Be 'bcpxy.nycnet'
        $result.Port | Should Be '8080'
    }

    It 'returns empty Address/Port for direct access (no proxy)' {
        Mock Get-NetshWinHttpProxyOutput {
            @(
                ''
                'Current WinHTTP proxy settings:'
                ''
                '    Direct access (no proxy server).'
            )
        }
        $result = Get-WinHttpProxyAddressPort
        $result.Address | Should Be ''
        $result.Port | Should Be ''
    }

    It 'parses correctly even with a non-English label (regression test for the locale fix)' {
        Mock Get-NetshWinHttpProxyOutput {
            @(
                ''
                'Aktuelle WinHTTP-Proxyeinstellungen:'
                ''
                '    Proxyserver : http://bcpxy.nycnet:8080'
                '    Umgehungsliste : (Keine)'
            )
        }
        $result = Get-WinHttpProxyAddressPort
        $result.Address | Should Be 'bcpxy.nycnet'
        $result.Port | Should Be '8080'
    }
}

Describe 'Resolve-ArcGisPythonPath' {
    BeforeEach {
        $script:originalProgramFiles = $env:ProgramFiles
        $script:originalProgramW6432 = $env:ProgramW6432
    }

    AfterEach {
        $env:ProgramFiles = $script:originalProgramFiles
        $env:ProgramW6432 = $script:originalProgramW6432
    }

    It 'prefers ProgramW6432 when its candidate exists (regression test for the x64-path fix)' {
        $env:ProgramW6432 = 'C:\Program Files'
        $env:ProgramFiles = 'C:\Program Files (x86)'
        Mock Test-Path {
            param($Path)
            $Path -eq 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe'
        }

        $result = Resolve-ArcGisPythonPath

        $result | Should Be 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe'
    }

    It 'falls back to ProgramFiles when only that candidate exists' {
        $env:ProgramW6432 = 'C:\Program Files'
        $env:ProgramFiles = 'C:\Program Files (x86)'
        Mock Test-Path {
            param($Path)
            $Path -eq 'C:\Program Files (x86)\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe'
        }

        $result = Resolve-ArcGisPythonPath

        $result | Should Be 'C:\Program Files (x86)\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe'
    }

    It 'returns $null when neither candidate exists' {
        $env:ProgramW6432 = 'C:\Program Files'
        $env:ProgramFiles = 'C:\Program Files (x86)'
        Mock Test-Path { $false }

        $result = Resolve-ArcGisPythonPath

        $result | Should Be $null
    }
}

Describe 'Get-OdbcDriversFromInstalledPrograms' {
    It 'filters to only entries whose DisplayName matches ODBC' {
        $programs = @(
            [pscustomobject]@{ DisplayName = 'PostgreSQL ODBC Driver' }
            [pscustomobject]@{ DisplayName = 'Google Chrome' }
            [pscustomobject]@{ DisplayName = 'Microsoft ODBC Driver 17 for SQL Server' }
        )

        $result = @(Get-OdbcDriversFromInstalledPrograms -InstalledPrograms $programs)

        $result.Count | Should Be 2
        # Should Contain in Pester 3.4.0 means "file at this path contains this text" (it
        # runs Get-Content on the piped value), not "collection contains element" like
        # newer Pester's -Contain - use PowerShell's own -contains operator instead.
        ($result.DisplayName -contains 'PostgreSQL ODBC Driver') | Should Be $true
        ($result.DisplayName -contains 'Microsoft ODBC Driver 17 for SQL Server') | Should Be $true
    }

    It 'returns nothing when no entries match' {
        $programs = @([pscustomobject]@{ DisplayName = 'Google Chrome' })
        $result = @(Get-OdbcDriversFromInstalledPrograms -InstalledPrograms $programs)
        $result.Count | Should Be 0
    }
}

Describe 'Get-NetworkDrives' {
    It 'drops drives with no DisplayRoot and renames the rest' {
        Mock Get-PSDrive {
            @(
                [pscustomobject]@{ Name = 'Z'; DisplayRoot = '\\server\share' }
                [pscustomobject]@{ Name = 'C'; DisplayRoot = $null }
            )
        }

        $result = @(Get-NetworkDrives)

        $result.Count | Should Be 1
        $result[0].DriveLetter | Should Be 'Z:'
        $result[0].Path | Should Be '\\server\share'
    }
}

Describe 'Get-InstalledPrograms' {
    It 'keeps only entries with a DisplayName and exposes DisplayName/DisplayVersion/Publisher' {
        Mock Get-ItemProperty {
            @(
                [pscustomobject]@{ DisplayName = 'Widget App'; DisplayVersion = '1.0'; Publisher = 'Acme' }
                [pscustomobject]@{ DisplayName = $null; DisplayVersion = '2.0'; Publisher = 'NoName' }
            )
        }

        $result = @(Get-InstalledPrograms)

        $result.Count | Should Be 1
        $result[0].DisplayName | Should Be 'Widget App'
        $result[0].DisplayVersion | Should Be '1.0'
        $result[0].Publisher | Should Be 'Acme'
    }
}

Describe 'Export-SectionsToCsv' {
    It 'writes a title line and CSV rows for a section with data' {
        $path = Join-Path $TestDrive 'report.csv'
        $sections = @(
            @{ Title = 'Identity'; Rows = @([pscustomobject]@{ Property = 'Username'; Value = 'jrosacker' }) }
        )

        Export-SectionsToCsv -Sections $sections -Path $path

        $content = Get-Content $path
        # See the note above on Get-OdbcDriversFromInstalledPrograms - Should Contain checks
        # a FILE's contents in Pester 3.4.0, not array membership, so use -contains here too.
        ($content -contains '## Identity') | Should Be $true
        ($content -join "`n") | Should Match 'jrosacker'
    }

    It 'writes just the title line for a section with no rows' {
        $path = Join-Path $TestDrive 'empty.csv'
        $sections = @(@{ Title = 'ODBC Drivers'; Rows = @() })

        Export-SectionsToCsv -Sections $sections -Path $path

        $content = Get-Content $path
        ($content -contains '## ODBC Drivers') | Should Be $true
    }
}

Describe 'Write-SheetSections' -Tag 'RequiresExcel' {
    BeforeAll {
        $script:excel = $null
        $script:workbook = $null
        try {
            $script:excel = New-Object -ComObject Excel.Application
            $script:excel.Visible = $false
            $script:excel.DisplayAlerts = $false
            $script:workbook = $script:excel.Workbooks.Add()
            $script:worksheet = $script:workbook.Worksheets.Item(1)
        } catch {
            $script:excel = $null
        }
    }

    AfterAll {
        if ($script:workbook) { $script:workbook.Close($false); [Runtime.InteropServices.Marshal]::ReleaseComObject($script:workbook) | Out-Null }
        if ($script:excel) { $script:excel.Quit(); [Runtime.InteropServices.Marshal]::ReleaseComObject($script:excel) | Out-Null }
        [GC]::Collect()
        [GC]::WaitForPendingFinalizers()
    }

    It 'writes section title, headers, and row values into real worksheet cells' {
        if (-not $script:excel) {
            Set-TestInconclusive -Message 'Excel is not available on this machine'
            return
        }

        $sections = @(
            @{ Title = 'Identity'; Rows = @([pscustomobject]@{ Property = 'Username'; Value = 'jrosacker' }) }
        )

        Write-SheetSections -Worksheet $script:worksheet -Sections $sections

        $script:worksheet.Cells.Item(1, 1).Value2 | Should Be 'Identity'
        $script:worksheet.Cells.Item(2, 1).Value2 | Should Be 'Property'
        $script:worksheet.Cells.Item(2, 2).Value2 | Should Be 'Value'
        $script:worksheet.Cells.Item(3, 1).Value2 | Should Be 'Username'
        $script:worksheet.Cells.Item(3, 2).Value2 | Should Be 'jrosacker'
    }
}
