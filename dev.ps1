# Dev launcher (Windows PowerShell): runs the FastAPI backend (port 8137) and
# the Vite dev server (port 5173) in two windows. Open http://localhost:5173
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# --- backend: create venv + install deps if needed ---
$venvPy = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating backend venv..." -ForegroundColor Cyan
    python -m venv (Join-Path $root "backend\.venv")
    & $venvPy -m pip install --upgrade pip
    & $venvPy -m pip install -r (Join-Path $root "backend\requirements.txt")
}

# --- frontend: install deps if needed ---
if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
    Write-Host "Installing frontend deps..." -ForegroundColor Cyan
    Push-Location (Join-Path $root "frontend"); npm install; Pop-Location
}

Write-Host "Starting backend (http://127.0.0.1:8137) and frontend (http://localhost:5173)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8137"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"
Write-Host "Open http://localhost:5173 in your browser." -ForegroundColor Yellow
