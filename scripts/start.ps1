# Starts the app (API + built web UI) on http://127.0.0.1:8000
# For phones on the same Wi-Fi: .\scripts\start.ps1 -Lan   then open http://<this-PC-IP>:8000 (PC must stay on; not for public internet)
param([switch]$Lan)
Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) "backend")
python -m alembic upgrade head
$bind = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
python -m uvicorn app.main:app --host $bind --port 8000
