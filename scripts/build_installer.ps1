# scripts/build_installer.ps1
# ----------------------------
# Complete build pipeline:
#   1.  Run pytest (abort on failure)
#   2.  Build PyInstaller bundle  (dist\ohe-gui\)
#   3.  Compile Inno Setup script (installer\Output\OHE_Setup_1.0.0.exe)
#
# Usage (from project root):
#   .\scripts\build_installer.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Write-Step {
    param([int]$n, [int]$total, [string]$msg)
    Write-Host ""
    Write-Host "[$n/$total] $msg" -ForegroundColor Cyan
}

function Abort {
    param([string]$msg)
    Write-Host ""
    Write-Host "[FAILED] $msg" -ForegroundColor Red
    exit 1
}

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  OHE -- Full Build + Installer Pipeline"        -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# --------------------------------------------------------------------------
# Step 1: Tests
# --------------------------------------------------------------------------
Write-Step 1 3 "Running test suite..."
.\.venv\Scripts\pytest.exe tests/ -q --tb=short
if ($LASTEXITCODE -ne 0) { Abort "Tests failed -- fix before packaging." }
Write-Host "  All tests passed." -ForegroundColor Green

# --------------------------------------------------------------------------
# Step 2: PyInstaller
# --------------------------------------------------------------------------
Write-Step 2 3 "Building PyInstaller bundle..."

$pyinstaller = ".\.venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $pyinstaller)) {
    Write-Host "  Installing PyInstaller..." -ForegroundColor Yellow
    .\.venv\Scripts\pip.exe install pyinstaller --quiet
}

@("dist", "build") | ForEach-Object {
    if (Test-Path $_) { Remove-Item -Recurse -Force $_ }
}

& $pyinstaller ohe.spec --noconfirm
if ($LASTEXITCODE -ne 0) { Abort "PyInstaller failed." }

@("data\sessions", "data\debug", "data\sample_videos") | ForEach-Object {
    New-Item -ItemType Directory -Force "dist\ohe-gui\$_" | Out-Null
}

$bundleMB = [math]::Round(
    (Get-ChildItem "dist\ohe-gui" -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB,
    1
)
Write-Host "  Bundle ready: dist\ohe-gui\  ($bundleMB MB)" -ForegroundColor Green

# --------------------------------------------------------------------------
# Step 3: Inno Setup
# --------------------------------------------------------------------------
Write-Step 3 3 "Compiling Inno Setup installer..."

$isccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Host ""
    Write-Host "  [WARNING] Inno Setup not found at default locations." -ForegroundColor Yellow
    Write-Host "  Download from: https://jrsoftware.org/isinfo.php"    -ForegroundColor Yellow
    Write-Host "  After installing, compile manually:"                  -ForegroundColor Yellow
    Write-Host "    iscc installer\ohe_setup.iss"                       -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  PyInstaller bundle is ready at: dist\ohe-gui\" -ForegroundColor Green
    exit 0
}

New-Item -ItemType Directory -Force "installer\Output" | Out-Null

& $iscc "installer\ohe_setup.iss"
if ($LASTEXITCODE -ne 0) { Abort "Inno Setup compilation failed." }

$setupExe = Get-ChildItem "installer\Output\OHE_Setup*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$setupMB = [math]::Round($setupExe.Length / 1MB, 1)

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  BUILD COMPLETE" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Installer : $($setupExe.FullName)"
Write-Host "  Size      : $setupMB MB"
Write-Host ""
Write-Host "  Distribute this single file to end users." -ForegroundColor Yellow
Write-Host "  They do NOT need Python installed."        -ForegroundColor Yellow
Write-Host ""
