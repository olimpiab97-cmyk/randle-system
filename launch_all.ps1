$Root = "C:\Webhook\RandleSystem"

function Start-RandleWindow {
    param(
        [string]$Title,
        [string]$Command
    )

    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "cd '$Root'; `$host.UI.RawUI.WindowTitle = '$Title'; $Command"
    )
}

Write-Host "Launching Randle System..." -ForegroundColor Cyan

Start-RandleWindow "Randle Executor :6001" "python executor.py"

Start-RandleWindow "Randle Trade Manager :7001" "python Engines\trade_manager.py"

Start-RandleWindow "Randle Entry Agent :7002" "python EntryAgent\tv_context_server.py"

Start-RandleWindow "Randle Rithmic Listener" "python rithmic_live_listener.py"

Start-RandleWindow "Randle Ngrok 7001" "ngrok http 7001"

Write-Host "All launch commands sent." -ForegroundColor Green