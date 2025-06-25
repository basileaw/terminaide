# Dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Copy project directories
COPY terminaide/ ./terminaide/
COPY terminarcade/ ./terminarcade/
COPY tryit/ ./tryit/
COPY pyproject.toml ./

# Install dependencies from pyproject.toml
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "tryit/apps.py"]