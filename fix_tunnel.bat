@echo off
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo Requesting Administrative Privileges...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /B

:gotAdmin
    cd /d "%~dp0"
    echo ==============================================
    echo  [WangGung] Process Cleanup & Reset
    echo ==============================================
    echo.
    echo Killing Python Server...
    taskkill /f /im python.exe /t >nul 2>&1
    
    echo Killing Background Cloudflared...
    taskkill /f /im cloudflared.exe /t >nul 2>&1
    
    echo Uninstalling Zombie Service (If exists)...
    cd /d C:\Users\USER\Dev\YTDownloader_v2
    cloudflared.exe service uninstall >nul 2>&1
    
    echo.
    echo ==============================================
    echo  [SUCCESS] All clean!
    echo ==============================================
    echo.
    echo Please close this window, and any other Black CMD windows.
    echo Then run [ run_with_domain.bat ] to start fresh!
    echo.
    pause
