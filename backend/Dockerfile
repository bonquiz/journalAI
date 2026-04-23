FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libsqlcipher-dev sqlcipher pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Skip .pyc generation so the image stays compatible with a read-only
# root filesystem (no __pycache__ writes at runtime).
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app
# Copy code BEFORE pip install — setuptools needs app/ to build the package.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
