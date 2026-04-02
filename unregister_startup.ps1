# WangGung Order System Auto-start Unregistration
# This script MUST be run as Administrator.

$TaskName = "WangGungOrderSystem"

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host " "
    Write-Host "=================================================="
    Write-Host " ✅ PC 부팅 시 서버 자동 실행 설정이 해제되었습니다!"
    Write-Host " - Task Name: $TaskName"
    Write-Host "=================================================="
    Write-Host " "
} catch {
    Write-Host " "
    Write-Host " [!] ERROR: Permission Denied or Task Not Found."
    Write-Host " Please run PowerShell as 'Administrator' (Admin Mode)."
    Write-Host " [!] 오류: 권한이 부족하시거나 스케줄러를 찾지 못했습니다. '관리자 권한'으로 실행해 주세요."
    Write-Host " "
}

Write-Host "창을 닫으려면 아무 키나 누르세요..."
$Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") | Out-Null
