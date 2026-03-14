FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

RUN addgroup --system app && adduser --system --ingroup app app

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for uploads, results, progress, artifacts, and runtime state
RUN mkdir -p uploads results_data progress_data analysis_runs runtime && \
    chown -R app:app /app

USER app

# Expose port
EXPOSE 8000

# Run the web app behind Gunicorn; heavy analysis work lives in the worker service.
# gthread keeps SSE connections responsive while queue workers handle long-running jobs.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--worker-class", "gthread", "--timeout", "120", "--graceful-timeout", "120", "app:app"]
