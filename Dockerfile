# ============================================================
# Stage 1: Build dependencies (heavy — cached by Docker)
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for torch / numpy / pyarrow
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY sas_converter/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install \
    -r requirements.txt \
    langgraph redis markdown2 \
    azure-monitor-opentelemetry opentelemetry-api

# ============================================================
# Stage 2: Runtime image (slim)
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# Copy pre-built packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY sas_converter/ ./sas_converter/
COPY main.py conftest.py pyproject.toml ./
COPY config/ ./config/
COPY scripts/ ./scripts/

# Create output / data directories
RUN mkdir -p output logs lancedb_data

# Non-root user for security
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Default: run the pipeline API (override with docker run ... CMD)
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
