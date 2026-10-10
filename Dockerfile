# syntax=docker/dockerfile:1
FROM python:3.11-slim

# System metadata & performance optimizations
LABEL maintainer="Event Inventory Management System"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source files
COPY . /app/

# Generate training data and train ML models if not already present
RUN python ml/generate_training_data.py && python ml/train_models.py

# Expose HTTP application port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Start production server
CMD ["python", "wsgi.py"]
