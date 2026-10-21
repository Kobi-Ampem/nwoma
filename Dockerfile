# The API as a Lambda container image. Lambda Web Adapter runs the FastAPI app as a normal web
# server, so the same code runs locally and in Lambda.
# Build inputs not in the repository (the LOINC table, trained model, embedding caches) are
# unpacked into ./artifacts by the deploy workflow from the private build-inputs bucket.
FROM python:3.12-slim-bookworm

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.0.1 /lambda-adapter /opt/extensions/lambda-adapter
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./
# Runtime dependencies only: no data generator, MCP, training or test tools.
RUN uv sync --frozen --no-dev --no-install-project --no-cache

COPY api ./api
COPY extract ./extract
COPY normalise ./normalise
COPY ocr ./ocr
COPY datagen/__init__.py datagen/models.py ./datagen/
COPY artifacts/ ./

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/hf \
    HF_HUB_OFFLINE=1 \
    LLM_CACHE=/tmp/llm_cache \
    AWS_LWA_PORT=8000 \
    AWS_LWA_READINESS_CHECK_PATH=/health \
    AWS_LWA_ASYNC_INIT=true

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
