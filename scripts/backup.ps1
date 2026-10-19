# Creates a verified backup zip (database + attachments) in data\backups
Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) "backend")
python -m app.cli backup
