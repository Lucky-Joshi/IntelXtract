# IntelXtract Dockerfile
# Multi-stage build for headless CLI image
#
# Build: docker build -t intelxtract:latest .
# Run CLI: docker run --rm intelxtract:latest scan example.com --mode deep
# Run with docker-compose: docker-compose up

# ============================================================================
# Stage 1: Build dependencies
# ============================================================================
FROM python:3.13-slim AS builder

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files first (for layer caching)
COPY requirements.txt requirements-dev.txt pyproject.toml ./

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# ============================================================================
# Stage 2: Runtime image (headless CLI)
# ============================================================================
FROM python:3.13-slim AS runtime

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r intelxtract && useradd -r -g intelxtract -d /home/intelxtract -s /bin/bash intelxtract

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=intelxtract:intelxtract . .

# Create directories for data persistence
RUN mkdir -p /data/exports /data/logs /data/cache \
    && chown -R intelxtract:intelxtract /data /app

# Switch to non-root user
USER intelxtract

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    INTELXTRACT_DB_PATH=/data/intelxtract.db \
    INTELXTRACT_EXPORT_DIR=/data/exports \
    INTELXTRACT_LOG_DIR=/data/logs \
    INTELXTRACT_CACHE_DIR=/data/cache

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD intelxtract doctor || exit 1

# Default entrypoint
ENTRYPOINT ["intelxtract"]
CMD ["--help"]

# ============================================================================
# Stage 3: GUI image (optional - includes GUI dependencies)
# ============================================================================
FROM runtime AS gui

# Switch back to root to install GUI dependencies
USER root

# Install GUI system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libxcb-xinerama0 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-shm0 \
    libxcb-sync1 \
    libxcb-xfixes0 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    libxkbcommon0 \
    libfontconfig1 \
    libfreetype6 \
    libegl1 \
    libopengl0 \
    && rm -rf /var/lib/apt/lists/*

# Switch back to non-root user
USER intelxtract

# GUI entrypoint
ENTRYPOINT ["intelxtract-gui"]