FROM python:3.12-slim

ENV IS_CONTAINER=true \
    PYTHONUNBUFFERED=1 \
    PORT=80

WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir poetry

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main --no-root

# Copy the application
COPY test-server/ /app/test-server/

EXPOSE 80
CMD ["python", "test-server/main.py"]