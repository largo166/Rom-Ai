param(
  [switch]$SkipInstall,
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$Backend = Join-Path $Root "backend"
$Desktop = Join-Path $Root "desktop"
$BackendDist = Join-Path $Backend "dist"
$Release = Join-Path $Root "release"
$BackendVenv = Join-Path $Backend ".venv-py39"
$BackendPython = Join-Path $BackendVenv "Scripts\python.exe"
$BuildHome = Join-Path $Root ".build-home"
$BuildAppData = Join-Path $Root ".build-appdata"

function Step($Message) {
  Write-Host ""
  Write-Host "== $Message =="
}

function Require-Command($Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Missing required command: $Name"
  }
}

Step "ROM-AI Windows EXE build"
Write-Host "Project root: $Root"

Require-Command npm

$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
if (-not $env:ELECTRON_MIRROR) {
  $env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
}
if (-not $env:ELECTRON_BUILDER_BINARIES_MIRROR) {
  $env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"
}

$trackedEnv = git -C $Root ls-files backend/.env 2>$null
if ($trackedEnv) {
  throw "Security stop: backend/.env is tracked by git. Remove it from git before building."
}

if (Test-Path (Join-Path $Backend ".env")) {
  Write-Warning "Local backend/.env exists. It will NOT be packaged; the desktop app creates an empty AppData config on first start."
}

New-Item -ItemType Directory -Force -Path $BuildHome, $BuildAppData | Out-Null
$env:HOME = $BuildHome
$env:USERPROFILE = $BuildHome
$env:APPDATA = $BuildAppData

if (-not (Test-Path (Join-Path $Desktop "build\icon.ico"))) {
  throw "Missing desktop/build/icon.ico"
}

if (-not $SkipInstall) {
  Step "Installing frontend dependencies"
  Push-Location $Frontend
  if (Test-Path "package-lock.json") { npm ci } else { npm install }
  Pop-Location

  Step "Installing desktop dependencies"
  Push-Location $Desktop
  if (Test-Path "package-lock.json") { npm ci } else { npm install }
  Pop-Location

  Step "Creating Python virtual environment"
  Push-Location $Backend
  if (-not (Test-Path $BackendPython)) {
    python -m venv $BackendVenv
  }
  & $BackendPython -m pip install --upgrade pip
  & $BackendPython -m pip install -r requirements.txt pyinstaller
  Pop-Location
}

if (-not $SkipTests) {
  Step "Running backend tests"
  Push-Location $Backend
  & $BackendPython -m pytest
  Pop-Location

  Step "Running frontend lint"
  Push-Location $Frontend
  npm run lint
  Pop-Location
}

Step "Building frontend"
Push-Location $Frontend
npm run build
Pop-Location

Step "Cleaning build outputs"
if (Test-Path $BackendDist) {
  Remove-Item $BackendDist -Recurse -Force
}
if (Test-Path $Release) {
  Remove-Item $Release -Recurse -Force
}

Step "Building backend executable"
Push-Location $Backend
& $BackendPython -m PyInstaller `
  rom_ai.spec `
  --noconfirm `
  --clean `
  --distpath $BackendDist `
  --workpath (Join-Path $Backend "build")
Pop-Location

$BackendExe = Join-Path $BackendDist "rmo-ai-backend\rmo-ai-backend.exe"
if (-not (Test-Path $BackendExe)) {
  throw "Backend executable was not created: $BackendExe"
}

Step "Building Windows installer"
Push-Location $Desktop
npm run dist:win -- --publish never
Pop-Location

$Installer = Get-ChildItem $Release -Filter "ROM-AI-Setup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $Installer) {
  throw "Installer was not created in $Release"
}
$LatestYml = Join-Path $Release "latest.yml"
$Blockmap = "$($Installer.FullName).blockmap"

Step "Done"
Write-Host "Backend exe: $BackendExe"
Write-Host "Installer: $($Installer.FullName)"
Write-Host "Size: $([Math]::Round($Installer.Length / 1MB, 2)) MB"
if (Test-Path $LatestYml) {
  Write-Host "Auto-update metadata: $LatestYml"
} else {
  Write-Warning "latest.yml was not found. In-app updates require uploading latest.yml to GitHub Release."
}
if (Test-Path $Blockmap) {
  Write-Host "Differential update blockmap: $Blockmap"
} else {
  Write-Warning "Installer blockmap was not found. Uploading it is recommended for in-app updates."
}
Write-Host "GitHub Release assets required for in-app update:"
Write-Host "  - $($Installer.Name)"
Write-Host "  - $($Installer.Name).blockmap"
Write-Host "  - latest.yml"
