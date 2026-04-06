# ============================================================
# Stage 1: Build dependencies (heavy — cached by Docker)
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps for torch / numpy / pyarrow
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install \
    -r requirements.txt

# ============================================================
# Stage 2: Runtime image (slim)
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# Copy pre-built packages from builder
COPY --from=builder /install /usr/local

# Copy backend code
COPY backend/ ./backend/
COPY pyproject.toml ./

# Create output / data directories
RUN mkdir -p output logs lancedb_data backend/uploads

# Non-root user for security
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app/backend

EXPOSE 8000

# Default: run the API server
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
