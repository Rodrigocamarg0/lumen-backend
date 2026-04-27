FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and uv.
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv

# Install Python dependencies from uv.lock.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

# Copy application code
COPY backend/app /app/app

# Expose port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
