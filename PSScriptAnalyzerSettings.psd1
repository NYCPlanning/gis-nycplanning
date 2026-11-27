@{
    Rules = @{
        PSUseCompatibleCommands = @{
            Enable         = $true
            TargetProfiles = @(
                # Windows PowerShell 5.1, Windows 10 Pro - closest match to GIS Team machines' OS
                'win-48_x64_10.0.17763.0_5.1.17763.316_x64_4.0.30319.42000_framework'  
            )
        }
    }
}
