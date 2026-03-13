FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for uploads and results
RUN mkdir -p uploads results_data

# Expose port
EXPOSE 8000

# Run with gunicorn in production
# Timeout set to 1800s (30 min) to accommodate slow local LLM inference
# Using gthread worker class for better handling of long-running requests
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--worker-class", "gthread", "--timeout", "1800", "--graceful-timeout", "1800", "app:app"]
