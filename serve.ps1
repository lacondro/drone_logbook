# Single-port launcher (Windows PowerShell): builds the frontend and serves both
# the API and the static UI from FastAPI on one port. Open http://localhost:8137
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$venvPy = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    python -m venv (Join-Path $root "backend\.venv")
    & $venvPy -m pip install --upgrade pip
    & $venvPy -m pip install -r (Join-Path $root "backend\requirements.txt")
}
if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
    Push-Location (Join-Path $root "frontend"); npm install; Pop-Location
}

Write-Host "Building frontend..." -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend"); npm run build; Pop-Location

Write-Host "Serving on http://localhost:8137" -ForegroundColor Green
Start-Process "http://localhost:8137"   # open the browser
Push-Location (Join-Path $root "backend")
& $venvPy -m uvicorn main:app --port 8137
Pop-Location
