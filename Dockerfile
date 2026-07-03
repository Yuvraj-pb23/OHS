# ==============================================================================
# Stage 1: Base Runtime Environment
# ==============================================================================
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf_cache \
    MPLCONFIGDIR=/tmp/matplotlib \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ==============================================================================
# Stage 2: Builder
# ==============================================================================
FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libcairo2-dev \
    libpango1.0-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Download model weights cleanly without multiline indentation errors
RUN python -c "from sentence_transformers import SentenceTransformer; from transformers import AutoTokenizer, AutoModelForCausalLM; print('Caching SentenceTransformer...'); SentenceTransformer('all-MiniLM-L6-v2'); print('Caching GPT-2...'); AutoTokenizer.from_pretrained('gpt2'); AutoModelForCausalLM.from_pretrained('gpt2')"

# ==============================================================================
# Stage 3: Production Environment
# ==============================================================================
FROM base AS production

# Create non-root user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -d /app -s /bin/bash appuser

# Copy virtual environment and model cache from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appgroup /opt/hf_cache /opt/hf_cache

# Copy application code
COPY --chown=appuser:appgroup . .

# Create writable directories for runtime
# /app/data         - SQLite database
# /app/media        - User-uploaded files
# /app/staticfiles  - Collected static files
# /tmp/matplotlib   - Matplotlib cache (fixes MPLCONFIGDIR permission error)
# /tmp/celery       - Celery beat schedule and PID files
RUN mkdir -p /app/data /app/media /app/staticfiles /tmp/matplotlib /tmp/celery && \
    chown -R appuser:appgroup /app/data /app/media /app/staticfiles /tmp/matplotlib /tmp/celery && \
    chmod -R 775 /app/data /app/media /app/staticfiles /tmp/matplotlib /tmp/celery

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
