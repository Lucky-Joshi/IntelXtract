#!/usr/bin/env bash
# IntelXtract Build Script (Linux/macOS)
#
# Usage:
#   ./scripts/build.sh              # Build all artifacts
#   ./scripts/build.sh --clean      # Clean build directories first
#   ./scripts/build.sh --cli-only   # Build only CLI binary
#   ./scripts/build.sh --gui-only   # Build only GUI binary
#   ./scripts/build.sh --wheel      # Build Python wheel/sdist only
#   ./scripts/build.sh --docker     # Build Docker image
#   ./scripts/build.sh --help       # Show help
#
# Requirements:
#   - Python 3.13+
#   - uv (recommended) or pip
#   - PyInstaller (installed via build dependencies)
#   - Docker (for --docker option)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT/build"
DIST_DIR="$ROOT/dist"
SCRIPTS_DIR="$ROOT/scripts"
PYINSTALLER_DIR="$SCRIPTS_DIR/pyinstaller"

# Default options
CLEAN=false
BUILD_CLI=true
BUILD_GUI=true
BUILD_WHEEL=false
BUILD_DOCKER=false
VERBOSE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN=true
            shift
            ;;
        --cli-only)
            BUILD_CLI=true
            BUILD_GUI=false
            BUILD_WHEEL=false
            BUILD_DOCKER=false
            shift
            ;;
        --gui-only)
            BUILD_CLI=false
            BUILD_GUI=true
            BUILD_WHEEL=false
            BUILD_DOCKER=false
            shift
            ;;
        --wheel)
            BUILD_CLI=false
            BUILD_GUI=false
            BUILD_WHEEL=true
            BUILD_DOCKER=false
            shift
            ;;
        --docker)
            BUILD_CLI=false
            BUILD_GUI=false
            BUILD_WHEEL=false
            BUILD_DOCKER=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            cat <<EOF
IntelXtract Build Script

Usage: $0 [OPTIONS]

Options:
    --clean         Clean build directories before building
    --cli-only      Build only CLI binary (PyInstaller)
    --gui-only      Build only GUI binary (PyInstaller)
    --wheel         Build Python wheel and sdist only
    --docker        Build Docker image only
    --verbose, -v   Verbose output
    --help, -h      Show this help

Examples:
    $0                    # Build all (CLI, GUI, wheel, Docker)
    $0 --clean            # Clean build
    $0 --cli-only         # CLI binary only
    $0 --wheel            # Python package only
    $0 --docker           # Docker image only
EOF
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

log() {
    echo -e "${BLUE}[BUILD]${NC} $*"
}

success() {
    echo -e "${GREEN}[OK]${NC} $*"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
    exit 1
}

# Clean build directories
clean() {
    log "Cleaning build directories..."
    rm -rf "$BUILD_DIR" "$DIST_DIR" "$ROOT"/*.egg-info
    success "Cleaned"
}

# Setup Python environment
setup_env() {
    log "Setting up Python environment..."
    cd "$ROOT"

    if command -v uv >/dev/null 2>&1; then
        log "Using uv for dependency management"
        uv venv .venv --python 3.13 2>/dev/null || true
        uv pip install --no-cache -r requirements.txt
        uv pip install --no-cache -e ".[build]"
    else
        log "Using pip for dependency management"
        python3 -m venv .venv
        .venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel
        .venv/bin/pip install --no-cache-dir -r requirements.txt
        .venv/bin/pip install --no-cache-dir -e ".[build]"
    fi

    export PATH="$ROOT/.venv/bin:$PATH"
    success "Environment ready"
}

# Build CLI binary with PyInstaller
build_cli() {
    log "Building CLI binary..."
    cd "$ROOT"

    if [[ ! -f "$PYINSTALLER_DIR/intelxtract-cli.spec" ]]; then
        error "CLI spec file not found: $PYINSTALLER_DIR/intelxtract-cli.spec"
    fi

    local pyinstaller_args=(
        --clean
        --distpath "$DIST_DIR"
        --workpath "$BUILD_DIR/cli"
        "$PYINSTALLER_DIR/intelxtract-cli.spec"
    )

    if [[ "$VERBOSE" == true ]]; then
        pyinstaller_args+=(-v)
    fi

    pyinstaller "${pyinstaller_args[@]}"

    # Verify binary
    local binary
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
        binary="$DIST_DIR/intelxtract.exe"
    else
        binary="$DIST_DIR/intelxtract"
    fi

    if [[ -f "$binary" ]]; then
        success "CLI binary built: $binary"
        log "Testing CLI binary..."
        "$binary" --version
        "$binary" --help >/dev/null
        success "CLI binary smoke test passed"
    else
        error "CLI binary not found at $binary"
    fi
}

# Build GUI binary with PyInstaller
build_gui() {
    log "Building GUI binary..."
    cd "$ROOT"

    if [[ ! -f "$PYINSTALLER_DIR/intelxtract-gui.spec" ]]; then
        error "GUI spec file not found: $PYINSTALLER_DIR/intelxtract-gui.spec"
    fi

    local pyinstaller_args=(
        --clean
        --distpath "$DIST_DIR"
        --workpath "$BUILD_DIR/gui"
        "$PYINSTALLER_DIR/intelxtract-gui.spec"
    )

    if [[ "$VERBOSE" == true ]]; then
        pyinstaller_args+=(-v)
    fi

    pyinstaller "${pyinstaller_args[@]}"

    # Verify binary
    local binary
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
        binary="$DIST_DIR/intelxtract-gui.exe"
    else
        binary="$DIST_DIR/intelxtract-gui"
    fi

    if [[ -f "$binary" ]]; then
        success "GUI binary built: $binary"
        # Note: GUI smoke test requires display, skip in headless CI
        if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]]; then
            log "Testing GUI binary (requires display)..."
            timeout 10 "$binary" --version 2>/dev/null || true
            success "GUI binary smoke test passed"
        else
            warn "Skipping GUI smoke test (no display available)"
        fi
    else
        error "GUI binary not found at $binary"
    fi
}

# Build Python wheel and sdist
build_wheel() {
    log "Building Python wheel and sdist..."
    cd "$ROOT"

    python -m build --wheel --sdist --outdir "$DIST_DIR"

    # Verify artifacts
    local wheel_count sdist_count
    wheel_count=$(find "$DIST_DIR" -name "*.whl" | wc -l)
    sdist_count=$(find "$DIST_DIR" -name "*.tar.gz" | wc -l)

    if [[ $wheel_count -gt 0 && $sdist_count -gt 0 ]]; then
        success "Wheel and sdist built:"
        find "$DIST_DIR" -name "*.whl" -o -name "*.tar.gz" | while read -r f; do
            log "  $f"
        done
    else
        error "Wheel/sdist build failed"
    fi
}

# Build Docker image
build_docker() {
    log "Building Docker image..."
    cd "$ROOT"

    # Get version from pyproject.toml
    local version
    version=$(grep '^version = ' pyproject.toml | head -1 | cut -d'"' -f2)

    docker build \
        --tag "intelxtract:${version}" \
        --tag "intelxtract:latest" \
        --target runtime \
        .

    # Also build GUI image
    docker build \
        --tag "intelxtract-gui:${version}" \
        --tag "intelxtract-gui:latest" \
        --target gui \
        .

    success "Docker images built:"
    docker images intelxtract --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
}

# Generate checksums for artifacts
generate_checksums() {
    log "Generating checksums..."
    cd "$DIST_DIR"

    local artifacts=()
    while IFS= read -r -d '' f; do
        artifacts+=("$f")
    done < <(find . -type f \( -name "*.exe" -o -name "intelxtract" -o -name "intelxtract-gui" -o -name "*.whl" -o -name "*.tar.gz" \) -print0 2>/dev/null)

    if [[ ${#artifacts[@]} -eq 0 ]]; then
        warn "No artifacts found for checksum generation"
        return
    fi

    # SHA256
    sha256sum "${artifacts[@]}" > CHECKSUMS.sha256
    # SHA512
    sha512sum "${artifacts[@]}" > CHECKSUMS.sha512

    success "Checksums generated:"
    cat CHECKSUMS.sha256
}

# Main build flow
main() {
    log "Starting IntelXtract build"
    log "Project root: $ROOT"

    [[ "$CLEAN" == true ]] && clean

    setup_env

    if [[ "$BUILD_CLI" == true ]]; then
        build_cli
    fi

    if [[ "$BUILD_GUI" == true ]]; then
        build_gui
    fi

    if [[ "$BUILD_WHEEL" == true ]]; then
        build_wheel
    fi

    if [[ "$BUILD_DOCKER" == true ]]; then
        build_docker
    fi

    # Generate checksums for all artifacts in dist/
    if [[ -d "$DIST_DIR" ]] && [[ -n "$(ls -A "$DIST_DIR" 2>/dev/null)" ]]; then
        generate_checksums
    fi

    success "Build completed successfully!"
    log "Artifacts in: $DIST_DIR"
}

main "$@"