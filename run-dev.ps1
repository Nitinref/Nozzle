param(
  [switch]$OpenBrowser
)

$ErrorActionPreference = 'Stop'

$backendDir = Join-Path $PSScriptRoot 'backend'
$frontendDir = Join-Path $PSScriptRoot 'frontend'

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  throw "Python launcher 'py' was not found on PATH."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "npm was not found on PATH."
}

Start-Process -WindowStyle Hidden -WorkingDirectory $backendDir -FilePath 'py' -ArgumentList '-3', '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8001'
Start-Process -WindowStyle Hidden -WorkingDirectory $frontendDir -FilePath 'npm' -ArgumentList 'run', 'dev', '--', '--host', '0.0.0.0', '--port', '5173'

Start-Sleep -Seconds 3

if ($OpenBrowser) {
  Start-Process 'http://localhost:5173'
}

Write-Host 'Backend:  http://localhost:8001'
Write-Host 'Frontend: http://localhost:5173'
Write-Host 'SigNoz:   http://localhost:8080'
