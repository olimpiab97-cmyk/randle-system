Set-Location -LiteralPath "C:\Webhook\RandleSystem"

Write-Output "Running tests from locked project root..."

python -m unittest discover -s . -p "*test*.py"