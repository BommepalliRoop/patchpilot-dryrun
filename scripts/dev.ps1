# Starts backend (:8000) and frontend (:5173) in two PowerShell windows. Usage: powershell -File scripts/dev.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path "$root\.env")) {
    Copy-Item "$root\.env.example" "$root\.env"
    Write-Host "Created .env from .env.example (all modes = mock)."
}
if (-not (Test-Path "$root\frontend\.env.local")) {
    Copy-Item "$root\frontend\.env.example" "$root\frontend\.env.local"
}

# Prefer the project venv; fall back to whatever `python` is on PATH.
$venvPy = "$root\backend\.venv\Scripts\python.exe"
if (Test-Path $venvPy) { $py = $venvPy } else { $py = "python" }

if (-not (Test-Path "$root\frontend\node_modules")) {
    Write-Host "Installing frontend dependencies..."
    Push-Location "$root\frontend"; npm install; Pop-Location
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; & '$py' -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"

Write-Host "Backend  http://localhost:8000  (docs at /docs)"
Write-Host "Frontend http://localhost:5173"
