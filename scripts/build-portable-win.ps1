param(
  [switch]$BuildFrontend,
  [switch]$BuildBackend,
  [switch]$NoZip
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root "frontend"
$Backend = Join-Path $Root "backend"
$Desktop = Join-Path $Root "desktop"
$Release = Join-Path $Root "release"
$BackendPython = Join-Path $Backend ".venv-py39\Scripts\python.exe"
$BackendExe = Join-Path $Backend "dist\rmo-ai-backend\rmo-ai-backend.exe"
$FrontendIndex = Join-Path $Frontend "dist\index.html"
$BuilderCmd = Join-Path $Desktop "node_modules\.bin\electron-builder.cmd"
$ElectronCmd = Join-Path $Desktop "node_modules\.bin\electron.cmd"

function Step($Message) {
  Write-Host ""
  Write-Host "== $Message =="
}

function Assert-File($Path, $Help) {
  if (-not (Test-Path $Path)) {
    throw "$Help`nMissing: $Path"
  }
}

Step "ROM-AI portable Windows build (--dir)"
Write-Host "Project root: $Root"

$env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
if (-not $env:ELECTRON_MIRROR) {
  $env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
}
if (-not $env:ELECTRON_BUILDER_BINARIES_MIRROR) {
  $env:ELECTRON_BUILDER_BINARIES_MIRROR = "https://npmmirror.com/mirrors/electron-builder-binaries/"
}

if ($BuildFrontend) {
  Step "Building frontend"
  Push-Location $Frontend
  npm run build
  Pop-Location
}

if ($BuildBackend) {
  Step "Building backend executable"
  Assert-File $BackendPython "Python venv is missing. Build backend deps first."
  Push-Location $Backend
  & $BackendPython -m PyInstaller `
    rom_ai.spec `
    --noconfirm `
    --clean `
    --distpath (Join-Path $Backend "dist") `
    --workpath (Join-Path $Backend "build")
  Pop-Location
}

Assert-File $FrontendIndex "Frontend dist is missing. Re-run with -BuildFrontend or run npm run build in frontend."
Assert-File $BackendExe "Backend onedir exe is missing. Re-run with -BuildBackend or run the backend PyInstaller build first."
Assert-File $BuilderCmd "electron-builder is not installed or node_modules is incomplete. Run npm install in desktop after allowing cache/network access."
Assert-File $ElectronCmd "electron is not installed or node_modules is incomplete. Run npm install in desktop after allowing cache/network access."

Step "Building win-unpacked portable folder"
Push-Location $Desktop
& $BuilderCmd --dir --win --publish never
Pop-Location

$PortableDir = Join-Path $Release "win-unpacked"
Assert-File (Join-Path $PortableDir "Rmo-AI.exe") "Portable build did not produce release\win-unpacked\Rmo-AI.exe."

if (-not $NoZip) {
  Step "Creating portable zip"
  $Zip = Join-Path $Release "ROM-AI-portable-win-unpacked.zip"
  if (Test-Path $Zip) {
    Remove-Item $Zip -Force
  }
  Compress-Archive -Path (Join-Path $PortableDir "*") -DestinationPath $Zip -Force
  Write-Host "Portable zip: $Zip"
  Write-Host "Size: $([Math]::Round((Get-Item $Zip).Length / 1MB, 2)) MB"
}

Step "Done"
Write-Host "Portable folder: $PortableDir"
Write-Host "Run: $(Join-Path $PortableDir 'Rmo-AI.exe')"
