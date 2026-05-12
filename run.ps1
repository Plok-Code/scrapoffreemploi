#!/usr/bin/env pwsh
# Lance l'app web locale
$ErrorActionPreference = "Stop"

# Active le venv si présent
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}

# Ouvre le navigateur après 1.5s
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process "http://localhost:8000"
} | Out-Null

# Lance uvicorn
python -m backend
