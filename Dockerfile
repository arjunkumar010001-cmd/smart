# ============================================================================
# PRODUCTION DOCKERFILE FOR SMART HIRING SYSTEM
# Full-featured deployment with spaCy NLP support
# Version: 3.0 - Full Edition with NLP capabilities
# ============================================================================

# Multi-stage build for optimized image size
FROM python:3.10-slim AS builder

# Set working directory
WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    ca-certificates \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Download spaCy English model (pinned version compatible with spacy 3.7.x)
RUN pip install --no-cache-dir --user https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl

# ============================================================================
# Final stage - slim production image
# ============================================================================
FROM python:3.10-slim

# Install runtime dependencies (ffmpeg for recording merge, WeasyPrint GTK libs for PDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl-dev \
    ffmpeg \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# Set working directory
WORKDIR /app

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy spaCy model from builder
COPY --from=builder /root/.local/lib/python3.10/site-packages/en_core_web_sm /home/appuser/.local/lib/python3.10/site-packages/en_core_web_sm

# Copy application code
COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser frontend/ ./frontend/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser app.py .

# Set environment variables
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production \
    PORT=8000

# Create necessary directories
RUN mkdir -p /app/backend/uploads /app/backend/logs && \
    chown -R appuser:appuser /app/backend/uploads /app/backend/logs

# Switch to non-root user
USER appuser

# Verify spaCy model is installed
RUN python -c "import spacy; nlp = spacy.load('en_core_web_sm'); print('✅ spaCy model loaded successfully')"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health').read()" || exit 1

# Start Flask app with Gunicorn (eventlet for Flask-SocketIO / WebSocket support)
# Single worker with greenlet concurrency — eventlet does NOT support multiple workers.
# --max-requests recycles the worker to prevent memory leaks in long-running deployments.
CMD ["sh", "-c", "gunicorn --worker-class eventlet --workers 1 --worker-connections 1000 --timeout 120 --max-requests 1000 --max-requests-jitter 100 --access-logfile - --error-logfile - --bind 0.0.0.0:${PORT:-8000} app:app"]
