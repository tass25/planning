# ============================================================
# Stage 1: Build Python dependencies (heavy — cached by Docker)
# ============================================================
FROM python:3.11-slim AS deps

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements/base.txt ./requirements.txt
RUN sed -i '/^torch/d; /^tf-keras/d' requirements.txt && \
    pip install --no-cache-dir --prefix=/install --timeout 300 --retries 10 \
    torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --prefix=/install --timeout 300 --retries 10 \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt && \
    pip install --no-cache-dir --prefix=/install --timeout 300 --retries 10 \
    --no-deps tf-keras

# ============================================================
# Stage 2: Cython-compile protected IP modules (CDAIS + MIS)
# ============================================================
FROM python:3.11-slim AS protector

WORKDIR /protect

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir cython setuptools

COPY backend/partition/testing/cdais/ /protect/partition/testing/cdais/
COPY backend/partition/invariant/ /protect/partition/invariant/
RUN touch /protect/partition/__init__.py /protect/partition/testing/__init__.py

COPY infra/compile_protected.py /protect/
RUN python compile_protected.py

RUN find /protect/partition/testing/cdais/ -name "*.py" ! -name "__init__.py" -delete && \
    find /protect/partition/invariant/ -name "*.py" ! -name "__init__.py" -delete && \
    find /protect -name "*.c" -delete

# ============================================================
# Stage 3: Pre-download Nomic embedding model (cached in image)
# ============================================================
FROM python:3.11-slim AS model-dl

COPY --from=deps /install /usr/local

RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)"

# ============================================================
# Stage 4: Runtime image (slim)
# ============================================================
FROM python:3.11-slim

WORKDIR /app

COPY --from=deps /install /usr/local

COPY backend/ ./backend/
COPY pyproject.toml ./

# Replace protected source with compiled native binaries
COPY --from=protector /protect/partition/testing/cdais/ /tmp/protected/cdais/
COPY --from=protector /protect/partition/invariant/ /tmp/protected/invariant/

RUN rm -f backend/partition/testing/cdais/cdais_runner.py \
         backend/partition/testing/cdais/constraint_catalog.py \
         backend/partition/testing/cdais/coverage_oracle.py \
         backend/partition/testing/cdais/synthesizer.py \
         backend/partition/invariant/invariant_synthesizer.py && \
    cp /tmp/protected/cdais/*.so backend/partition/testing/cdais/ && \
    cp /tmp/protected/invariant/*.so backend/partition/invariant/ && \
    rm -rf /tmp/protected

# Pre-downloaded Nomic model — no internet needed on first boot
COPY --from=model-dl /root/.cache/huggingface /app/.cache/huggingface

RUN mkdir -p output logs backend/uploads backend/data backend/data/lancedb

COPY infra/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

RUN adduser --system --no-create-home --group appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app/backend
ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
