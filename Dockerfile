# ==============================================================================
# Multi-Stage Production Dockerfile for LedgerCore
# ==============================================================================

# Stage 1: Build dependencies and wheels
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./

# Install pip-tools and build dependency wheels
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels .

# Stage 2: Final lightweight runtime container
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Install runtime dependencies (e.g. curl for health check)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user
RUN groupadd -r appgroup && useradd -r -g appgroup -s /sbin/nologin -d /app appuser

# Copy wheels from builder and install
COPY --from=builder /build/wheels /wheels
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

# Copy application source code
COPY app /app/app

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["sh", "-c", "exec gunicorn -w ${WEB_CONCURRENCY:-$(nproc)} -k uvicorn.workers.UvicornWorker app.api.main:app --bind 0.0.0.0:8000 --access-logfile -"]
