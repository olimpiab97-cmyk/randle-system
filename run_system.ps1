# ALWAYS anchor to project root
Set-Location -LiteralPath "C:\Webhook\RandleSystem"

Write-Output "======================================="
Write-Output "RANDLE SYSTEM STARTUP"
Write-Output "======================================="

# Kill existing Python processes (clean start)
Write-Output "Stopping existing Python processes..."
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

Start-Sleep -Seconds 2

# Start Executor (Port 6001)
Write-Output "Starting Executor..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd C:\Webhook\RandleSystem; python executor.py"

Start-Sleep -Seconds 3

# Start Rithmic Listener
Write-Output "Starting Rithmic Listener..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd C:\Webhook\RandleSystem; python rithmic_live_listener.py"

Start-Sleep -Seconds 5

# Start Trade Manager (Port 7001)
Write-Output "Starting Trade Manager..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd C:\Webhook\RandleSystem; python Engines\trade_manager.py"

Start-Sleep -Seconds 5

Write-Output "======================================="
Write-Output "SYSTEM STARTED"
Write-Output "======================================="

Write-Output ""
Write-Output "Executor: http://127.0.0.1:6001"
Write-Output "Trade Manager: http://127.0.0.1:7001"
Write-Output ""
Write-Output "Open command_center.html manually if needed"