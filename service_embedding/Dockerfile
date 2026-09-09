# ============================================================
# Build stage: install Python deps into a clean layer
# ============================================================
FROM python:3.11-slim AS builder

WORKDIR /install

# Install build tools needed by some packages (e.g. psycopg2-binary)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install all deps (torch CPU wheel ~750 MB, transformers ~500 MB)
RUN pip install --no-cache-dir --prefix=/install/pkg -r requirements.txt

# ============================================================
# Runtime stage: minimal image
# ============================================================
FROM python:3.11-slim

# Runtime PostgreSQL shared lib required by psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for least-privilege execution
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install/pkg /usr/local

# Copy application source
COPY app/ ./app/

# HuggingFace caches the model here; make it writable for the non-root user
ENV HF_HOME=/tmp/hf_cache
ENV TRANSFORMERS_CACHE=/tmp/hf_cache

# Switch to non-root
USER appuser

# One-shot job — no port exposed
CMD ["python", "-m", "app.main"]
