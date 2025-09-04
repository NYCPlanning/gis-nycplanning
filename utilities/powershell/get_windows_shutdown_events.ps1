<#
    Title: Get Windows Shutdown Events
    Purpose: 
        Queries the Windows Event Log and returns shutdown events, formatted.
    Author: J Rosacker
    Date: 2024-06-03
    Notes: 
    References:
        https://devblogs.microsoft.com/scripting/use-powershell-to-parse-event-log-for-shutdown-events/
        https://learn.microsoft.com/en-us/windows/win32/shutdown/system-shutdown-reason-codes?redirectedfrom=MSDN
#>


Get-EventLog -LogName system -Source user32 | Select-Object TimeGenerated, Message | Sort-Object TimeGenerated | Format-Table -Wrap