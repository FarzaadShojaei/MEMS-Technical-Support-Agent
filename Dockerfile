# syntax=docker/dockerfile:1

# ---------- builder ----------
# Installs everything into an isolated venv we copy wholesale into the runtime
# image, so pip, build caches, and compilers never ship to production.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt .

# Install CPU-only PyTorch FIRST, from PyTorch's CPU wheel index. The default
# torch wheel drags in ~2 GB of CUDA/GPU libraries we never use on CPU. Doing
# this before `-r requirements.txt` means sentence-transformers sees torch as
# already satisfied and won't pull the fat CUDA build.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt

# ---------- runtime ----------
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy just the built venv — no pip cache, no build tools.
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY app/ app/
COPY scripts/ scripts/
COPY eval/ eval/

# Index + logs are bind-mounted by compose; create fallbacks for bare runs.
RUN mkdir -p data/raw data/index logs \
 && useradd -m appuser \
 && chown -R appuser /app
USER appuser

EXPOSE 8000

# Liveness check without needing curl in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
