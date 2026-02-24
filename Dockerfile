FROM python:3.11-slim AS base

# Security: run as non-root user
RUN groupadd -r lumeops && useradd -r -g lumeops lumeops

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Copy application code
COPY app/ ./app/

# Copy optional directories (config, alembic)
COPY config/ ./config/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Security: set proper permissions
RUN chown -R lumeops:lumeops /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Switch to non-root user
USER lumeops

EXPOSE 8000

# Run with uvicorn
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
