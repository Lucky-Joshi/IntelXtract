<# 
.SYNOPSIS
    IntelXtract Build Script (Windows PowerShell)

.DESCRIPTION
    Builds IntelXtract CLI/GUI binaries, Python wheel/sdist, and Docker images.
    Generates SHA256/SHA512 checksums for all artifacts.

.PARAMETER Clean
    Clean build directories before building.

.PARAMETER CliOnly
    Build only CLI binary (PyInstaller).

.PARAMETER GuiOnly
    Build only GUI binary (PyInstaller).

.PARAMETER Wheel
    Build Python wheel and sdist only.

.PARAMETER Docker
    Build Docker image only.

.PARAMETER Verbose
    Verbose output.

.EXAMPLE
    .\scripts\build.ps1
    # Build all artifacts

.EXAMPLE
    .\scripts\build.ps1 -Clean
    # Clean build

.EXAMPLE
    .\scripts\build.ps1 -CliOnly
    # CLI binary only

.EXAMPLE
    .\scripts\build.ps1 -Wheel
    # Python package only

.EXAMPLE
    .\scripts\build.ps1 -Docker
    # Docker image only
#>

[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$CliOnly,
    [switch]$GuiOnly,
    [switch]$Wheel,
    [switch]$Docker,
    [switch]$Verbose
)

# Colors
$Red = [Console]::ForegroundColor = 'Red'
$Green = [Console]::ForegroundColor = 'Green'
$Yellow = [Console]::ForegroundColor = 'Yellow'
$Blue = [Console]::ForegroundColor = 'Blue'
$Reset = [Console]::ResetColor()

function Write-Log($msg) { Write-Host -ForegroundColor Blue "[BUILD] $msg" }
function Write-Success($msg) { Write-Host -ForegroundColor Green "[OK] $msg" }
function Write-Warn($msg) { Write-Host -ForegroundColor Yellow "[WARN] $msg" }
function Write-Error($msg) { Write-Host -ForegroundColor Red "[ERROR] $msg"; exit 1 }

# Paths
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
$BuildDir = Join-Path $Root "build"
$DistDir = Join-Path $Root "dist"
$ScriptsDir = Join-Path $Root "scripts"
$PyInstallerDir = Join-Path $ScriptsDir "pyinstaller"

# Determine what to build
$BuildCli = $true
$BuildGui = $true
$BuildWheel = $false
$BuildDocker = $false

if ($CliOnly) { $BuildCli = $true; $BuildGui = $false; $BuildWheel = $false; $BuildDocker = $false }
if ($GuiOnly) { $BuildCli = $false; $BuildGui = $true; $BuildWheel = $false; $BuildDocker = $false }
if ($Wheel) { $BuildCli = $false; $BuildGui = $false; $BuildWheel = $true; $BuildDocker = $false }
if ($Docker) { $BuildCli = $false; $BuildGui = $false; $BuildWheel = $false; $BuildDocker = $true }

# Clean build directories
if ($Clean) {
    Write-Log "Cleaning build directories..."
    Remove-Item -Recurse -Force $BuildDir, $DistDir, (Join-Path $Root "*.egg-info") -ErrorAction SilentlyContinue
    Write-Success "Cleaned"
}

# Setup Python environment
Write-Log "Setting up Python environment..."
Set-Location $Root

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Log "Using uv for dependency management"
    & uv venv .venv --python 3.13 2>$null
    & uv pip install --no-cache -r requirements.txt
    & uv pip install --no-cache -e ".[build]"
} else {
    Write-Log "Using pip for dependency management"
    python -m venv .venv
    & .venv\bin\pip install --no-cache-dir --upgrade pip setuptools wheel
    & .venv\bin\pip install --no-cache-dir -r requirements.txt
    & .venv\bin\pip install --no-cache-dir -e ".[build]"
}

$env:PATH = "$Root\.venv\bin;$env:PATH"
Write-Success "Environment ready"

# Build CLI binary
if ($BuildCli) {
    Write-Log "Building CLI binary..."
    
    $SpecFile = Join-Path $PyInstallerDir "intelxtract-cli.spec"
    if (-not (Test-Path $SpecFile)) {
        Write-Error "CLI spec file not found: $SpecFile"
    }

    $PyInstallerArgs = @(
        "--clean",
        "--distpath", $DistDir,
        "--workpath", (Join-Path $BuildDir "cli"),
        $SpecFile
    )
    if ($Verbose) { $PyInstallerArgs += "-v" }

    & pyinstaller @PyInstallerArgs

    # Verify binary
    $Binary = Join-Path $DistDir "intelxtract.exe"
    if (Test-Path $Binary) {
        Write-Success "CLI binary built: $Binary"
        Write-Log "Testing CLI binary..."
        & $Binary --version
        & $Binary --help > $null
        Write-Success "CLI binary smoke test passed"
    } else {
        Write-Error "CLI binary not found at $Binary"
    }
}

# Build GUI binary
if ($BuildGui) {
    Write-Log "Building GUI binary..."
    
    $SpecFile = Join-Path $PyInstallerDir "intelxtract-gui.spec"
    if (-not (Test-Path $SpecFile)) {
        Write-Error "GUI spec file not found: $SpecFile"
    }

    $PyInstallerArgs = @(
        "--clean",
        "--distpath", $DistDir,
        "--workpath", (Join-Path $BuildDir "gui"),
        $SpecFile
    )
    if ($Verbose) { $PyInstallerArgs += "-v" }

    & pyinstaller @PyInstallerArgs

    # Verify binary
    $Binary = Join-Path $DistDir "intelxtract-gui.exe"
    if (Test-Path $Binary) {
        Write-Success "GUI binary built: $Binary"
        Write-Warn "Skipping GUI smoke test (requires display)"
    } else {
        Write-Error "GUI binary not found at $Binary"
    }
}

# Build Python wheel and sdist
if ($BuildWheel) {
    Write-Log "Building Python wheel and sdist..."
    
    & python -m build --wheel --sdist --outdir $DistDir

    $WheelCount = (Get-ChildItem $DistDir -Filter "*.whl").Count
    $SdistCount = (Get-ChildItem $DistDir -Filter "*.tar.gz").Count

    if ($WheelCount -gt 0 -and $SdistCount -gt 0) {
        Write-Success "Wheel and sdist built:"
        Get-ChildItem $DistDir -Filter "*.whl", "*.tar.gz" | ForEach-Object { Write-Log "  $($_.FullName)" }
    } else {
        Write-Error "Wheel/sdist build failed"
    }
}

# Build Docker image
if ($BuildDocker) {
    Write-Log "Building Docker image..."
    
    $Version = (Get-Content pyproject.toml | Select-String '^version = ' | ForEach-Object { $_.ToString().Split('"')[1] })
    
    docker build --tag "intelxtract:$Version" --tag "intelxtract:latest" --target runtime .
    docker build --tag "intelxtract-gui:$Version" --tag "intelxtract-gui:latest" --target gui .
    
    Write-Success "Docker images built:"
    docker images intelxtract --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
}

# Generate checksums
Write-Log "Generating checksums..."
Set-Location $DistDir

$Artifacts = Get-ChildItem -File | Where-Object { 
    $_.Extension -in @(".exe", ".whl", ".tar.gz") -or $_.Name -match "^intelxtract(-gui)?$" 
}

if ($Artifacts.Count -gt 0) {
    $Artifacts | ForEach-Object {
        $sha256 = Get-FileHash -Algorithm SHA256 $_.FullName
        $sha512 = Get-FileHash -Algorithm SHA512 $_.FullName
        "$($sha256.Hash)  $($_.Name)" | Out-File -Append -Encoding UTF8 CHECKSUMS.sha256
        "$($sha512.Hash)  $($_.Name)" | Out-File -Append -Encoding UTF8 CHECKSUMS.sha512
    }
    Write-Success "Checksums generated:"
    Get-Content CHECKSUMS.sha256
} else {
    Write-Warn "No artifacts found for checksum generation"
}

Write-Success "Build completed successfully!"
Write-Log "Artifacts in: $DistDir"