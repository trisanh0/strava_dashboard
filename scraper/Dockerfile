FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY scraper/requirements.txt /app/scraper/requirements.txt
RUN pip install --no-cache-dir -r /app/scraper/requirements.txt

# Copy source code
COPY scraper/ /app/scraper/

# Default command runs continuous scraper service
CMD ["python", "-m", "scraper.main"]
