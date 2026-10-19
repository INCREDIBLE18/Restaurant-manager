# One-time setup (Windows PowerShell). Run from the project root:  .\scripts\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .env)) {
  $key = -join ((48..57 + 97..102) | Get-Random -Count 64 | ForEach-Object { [char]$_ })
  "SECRET_KEY=$key`nGEMINI_ENABLED=false" | Set-Content .env -Encoding utf8
  Write-Host "Created .env with a random SECRET_KEY"
}
python -m pip install -r backend/requirements.txt
Push-Location backend; python -m alembic upgrade head; Pop-Location
Push-Location frontend; npm install; npm run build; Pop-Location
Write-Host "Setup done. Start with .\scripts\start.ps1"
