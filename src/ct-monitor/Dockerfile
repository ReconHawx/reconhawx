# CT Monitor Service Dockerfile
# Monitors Certificate Transparency logs for typosquat domains

FROM python:3.14-slim

# Set environment variables
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 ctmonitor && \
    useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home ctmonitor

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ .

# Change ownership to non-root user
RUN chown -R ctmonitor:ctmonitor /app

# Switch to non-root user
USER ctmonitor

# Health check - verify Python can import main modules
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from main import CTMonitorService; print('OK')" || exit 1

# Default command
CMD ["python", "main.py"]
