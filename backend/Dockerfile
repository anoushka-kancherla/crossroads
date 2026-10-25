FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir ".[dev]"
COPY tests ./tests
COPY scripts ./scripts

# Both APIs run from this image; docker-compose.yml picks the module.
CMD ["uvicorn", "crossroads.customer_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
