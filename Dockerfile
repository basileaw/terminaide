FROM python:3.12-slim

ENV IS_CONTAINER=true \
    PYTHONUNBUFFERED=1 \
    PORT=80

WORKDIR /app

# Install only the essential system dependencies for ttyd
RUN apt-get update && apt-get install -y --no-install-recommends \
    libwebsockets-dev \
    libjson-c-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy only the necessary files for dependency installation
COPY pyproject.toml poetry.lock ./

# Install dependencies (without dev dependencies or project itself)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main --no-root \
    && pip uninstall -y poetry virtualenv-clone virtualenv

# Copy the rest of the application
COPY protottyde/ /app/protottyde/
COPY test-server/ /app/test-server/

EXPOSE 80
CMD ["python", "test-server/main.py"]