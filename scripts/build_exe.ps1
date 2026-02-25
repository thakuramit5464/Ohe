# scripts/build_exe.ps1
# ----------------------
# One-click build script for the OHE GUI executable.
# Run from the project root: .\scripts\build_exe.ps1
#
# Prerequisites:
#   - .venv must exist (run: python -m venv .venv && .venv\Scripts\pip install -e ".[dev]")
#   - PyInstaller must be installed: .venv\Scripts\pip install pyinstaller

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "OHE GUI Build Script" -ForegroundColor Cyan
Write-Host "====================" -ForegroundColor Cyan

# Ensure PyInstaller is available
$pyinstaller = ".\.venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $pyinstaller)) {
    Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
    .\.venv\Scripts\pip.exe install pyinstaller --quiet
}

# Clean previous build artifacts
Write-Host "`n[1/3] Cleaning previous build..." -ForegroundColor Green
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

# Run tests first
Write-Host "`n[2/3] Running test suite..." -ForegroundColor Green
.\.venv\Scripts\pytest.exe tests/ -q --tb=short
if ($LASTEXITCODE -ne 0) {
    Write-Host "Tests FAILED — aborting build." -ForegroundColor Red
    exit 1
}

# Build executable
Write-Host "`n[3/3] Building executable with PyInstaller..." -ForegroundColor Green
& $pyinstaller ohe.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "Build FAILED." -ForegroundColor Red
    exit 1
}

# Copy runtime data dirs (sessions, debug output dirs)
New-Item -ItemType Directory -Force "dist\ohe-gui\data\sample_videos" | Out-Null
New-Item -ItemType Directory -Force "dist\ohe-gui\data\sessions"      | Out-Null
New-Item -ItemType Directory -Force "dist\ohe-gui\data\debug"          | Out-Null

# Summary
$exePath = "dist\ohe-gui\ohe-gui.exe"
$exeSize = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
Write-Host "`n==============================" -ForegroundColor Cyan
Write-Host " BUILD SUCCESSFUL" -ForegroundColor Green
Write-Host "==============================" -ForegroundColor Cyan
Write-Host "  Executable : $exePath"
Write-Host "  Size       : ${exeSize} MB"
Write-Host "  Launch     : .\$exePath"
Write-Host ""
Write-Host "To distribute: zip the dist\ohe-gui\ folder." -ForegroundColor Yellow
