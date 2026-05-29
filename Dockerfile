FROM python:3.12-slim

WORKDIR /app

# System deps for sentence-transformers, OpenCV, and runtime libs.
# build-essential is needed only for any wheel that has to compile from sdist;
# remove after install to keep the image lean.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Pin uv to a version that understands the lockfile schema we generate.
# Bump in lockstep with local uv when regenerating uv.lock.
RUN pip install --no-cache-dir uv==0.10.1

# Copy lockfile + pyproject first so dependency resolution is layer-cached.
# We need the source tree on disk *before* `uv sync` because hatchling builds
# the local `synapse` package from the wheel target list in pyproject.
COPY pyproject.toml uv.lock README.md ./
COPY api api
COPY schema schema
COPY ingestion ingestion
COPY seed seed
COPY domains domains
COPY admin admin
COPY embedding embedding
COPY webhook webhook
COPY budget budget
COPY providers providers
COPY prompt prompt
COPY reasoning reasoning
COPY retrieval retrieval
COPY mcp mcp
COPY nlp nlp
COPY sync sync
COPY config config
COPY eval eval
COPY scripts scripts
COPY query query
COPY main.py ./

# Install production deps from the lockfile, no dev extras, no editable.
# `uv sync --frozen` errors out if uv.lock is stale — exactly what we want
# in CI/CD so production never resolves a different graph than local.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_PREFERENCE=system
RUN uv sync --frozen --no-dev --no-editable

# Bake the SentenceTransformer model into the image so cold-starts don't
# hit HuggingFace. ~90MB, lives in /model_cache.
RUN /app/.venv/bin/python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('sentence-transformers/all-MiniLM-L6-v2', cache_dir='/model_cache')"

# Force offline mode at runtime so a network blip can't break startup.
ENV HF_HUB_OFFLINE=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1 \
    TRANSFORMERS_OFFLINE=1 \
    SENTENCE_TRANSFORMERS_HOME=/model_cache \
    PATH="/app/.venv/bin:$PATH"

# Cloud Run injects PORT (default 8080). Use shell-form CMD so it expands.
ENV PORT=8080
EXPOSE 8080

# shell-form so ${PORT} is interpolated by sh at container start
CMD exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT}" --workers 1
