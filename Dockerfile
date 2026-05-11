FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

WORKDIR /app

# Install build deps first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip && pip install .

EXPOSE 8000

CMD ["python", "-m", "contoso_travel.server"]
