@echo off
title SAP ERP MCP Launcher
color 0A
cls

echo.
echo  ============================================================
echo   SAP ERP Remote MCP Server — One-Click Launcher
echo  ============================================================
echo.

:: ── Resolve the project directory (folder where this batch file lives) ──
set "PROJECT_DIR=%~dp0"
:: Remove trailing backslash
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

set "PYTHON=C:\Users\anand\AppData\Local\Programs\Python\Python314\python.exe"
set "PORT=8000"

echo  [1/3] Starting SAP ERP MCP Server (Python)...
start "SAP MCP Server" powershell -NoExit -Command ^
  "Set-Location '%PROJECT_DIR%'; Write-Host 'Starting SAP ERP MCP Server...' -ForegroundColor Cyan; & '%PYTHON%' server.py"

echo  Waiting for server to initialise...
timeout /t 4 /nobreak >nul

echo.
echo  [2/3] Starting ngrok HTTP tunnel on port %PORT%...
start "ngrok Tunnel" powershell -NoExit -Command ^
  "Write-Host 'Starting ngrok tunnel on port %PORT%...' -ForegroundColor Yellow; ngrok http %PORT%"

echo  Waiting for ngrok to start...
timeout /t 5 /nobreak >nul

echo.
echo  [3/3] Fetching ngrok public URL...
start "ngrok Public URL" powershell -NoExit -Command ^
  "$port = %PORT%; ^
   Write-Host ''; ^
   Write-Host 'Querying ngrok API...' -ForegroundColor Yellow; ^
   Start-Sleep -Seconds 2; ^
   try { ^
     $resp = Invoke-RestMethod -Uri 'http://localhost:4040/api/tunnels' -ErrorAction Stop; ^
     $tunnel = $resp.tunnels | Where-Object { $_.proto -eq 'https' } | Select-Object -First 1; ^
     if (-not $tunnel) { $tunnel = $resp.tunnels | Select-Object -First 1 }; ^
     $url = $tunnel.public_url; ^
     Write-Host ''; ^
     Write-Host ' ============================================================' -ForegroundColor Green; ^
     Write-Host '  ngrok Public URL:' -ForegroundColor Green; ^
     Write-Host ''; ^
     Write-Host ('  ' + $url) -ForegroundColor Cyan; ^
     Write-Host ''; ^
     Write-Host '  MCP SSE Endpoint (copy this):' -ForegroundColor Green; ^
     Write-Host ('  ' + $url + '/sse') -ForegroundColor Yellow; ^
     Write-Host ''; ^
     Write-Host '  Paste the /sse URL into:' -ForegroundColor White; ^
     Write-Host '  claude.ai -> Settings -> Integrations -> Add MCP Server' -ForegroundColor White; ^
     Write-Host ''; ^
     Write-Host '  For Claude Desktop, set in claude_desktop_config.json:' -ForegroundColor White; ^
     Write-Host ('  ""url"": ""' + $url + '/sse""') -ForegroundColor White; ^
     Write-Host ' ============================================================' -ForegroundColor Green; ^
   } catch { ^
     Write-Host 'Could not fetch ngrok URL.' -ForegroundColor Red; ^
     Write-Host 'Is ngrok running? Check: http://localhost:4040' -ForegroundColor Yellow; ^
     Write-Host ('Error: ' + $_.Exception.Message) -ForegroundColor DarkRed; ^
   }; ^
   Write-Host ''; ^
   Read-Host 'Press Enter to close this window'"

echo.
echo  All three windows launched.
echo  Check the "ngrok Public URL" window for your MCP endpoint.
echo.
pause
