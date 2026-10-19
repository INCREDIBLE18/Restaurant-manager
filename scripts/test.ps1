# Runs backend tests (fast), frontend tests, and optionally the slow OCR tests:  .\scripts\test.ps1 -Slow
param([switch]$Slow)
Set-Location (Split-Path $PSScriptRoot -Parent)
Push-Location backend; python -m pytest -m "not slow"; if ($Slow) { python -m pytest -m slow }; Pop-Location
Push-Location frontend; npm run typecheck; npm test; Pop-Location
