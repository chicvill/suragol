# WangGung Order System Auto-start Registration
# This script MUST be run as Administrator.

$TaskName = "WangGungOrderSystem"
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$WorkingDir = $PSScriptRoot
$BatFile = Join-Path $WorkingDir "run_with_domain.bat"

# 1. Delete existing task if any
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# 2. Define Action
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatFile`"" -WorkingDirectory $WorkingDir

# 3. Define Trigger
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User

# 4. Define Settings
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# 5. Register Task (Requires Administrator privileges)
try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -RunLevel Highest -User $User -ErrorAction Stop
    Write-Host " "
    Write-Host "=================================================="
    Write-Host " ✅ Registration Successful!"
    Write-Host " - Task Name: $TaskName"
    Write-Host " - Target: $BatFile"
    Write-Host " - Trigger: At Log On ($User)"
    Write-Host "=================================================="
    Write-Host " "
} catch {
    Write-Host " "
    Write-Host " [!] ERROR: Permission Denied."
    Write-Host " Please run PowerShell as 'Administrator' (Admin Mode)."
    Write-Host " [!] 오류: 권한이 부족합니다. '관리자 권한'으로 실행해 주세요."
    Write-Host " "
}
