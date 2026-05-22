# syntax=docker/dockerfile:1.7

# Single image used for both the API and the ingestion CLI.
# It's a bit heavy (~1.5GB) because PDF parsing needs poppler + tesseract;
# acceptable for dev. For prod you'd split api vs ingestion images.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps:
#   - poppler-utils, tesseract-ocr: required by `unstructured` for PDF parsing
#   - libmagic1: file type sniffing used by unstructured
#   - build-essential: needed by some wheels (sentence-transformers transitive deps)
#   - curl: for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        libmagic1 \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for better layer caching.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Pre-download the embedding model at build time so the container starts fast.
# Comment this out if you want to defer the download to first run.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"

# Source comes in via bind mount in dev (docker-compose mounts ./src).
# For prod builds, uncomment the COPY and remove the volume mount.
# COPY src ./src

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
