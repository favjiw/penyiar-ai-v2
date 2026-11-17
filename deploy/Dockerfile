# Image tunggal: backend FastAPI + frontend hasil build (disajikan backend, lihat app/main.py).
# Build dari ROOT repo:  docker build -f deploy/Dockerfile --build-arg GIT_SHA=$(git rev-parse HEAD) -t penyiar-ai .
# Dibangun di GitHub Actions (.github/workflows/build-image.yml); VPS 2 GB cukup menarik image jadi.

# ── Tahap 1: build frontend ──────────────────────────────────────────────────
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Tahap 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
ARG GIT_SHA=""
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    GIT_SHA=${GIT_SHA} \
    FRONTEND_DIST=/srv/frontend \
    DATA_DIR=/data/data \
    CACHE_DIR=/data/cache

WORKDIR /srv/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY backend/seed ./seed
COPY --from=frontend /build/dist /srv/frontend

# Data aplikasi ada di Postgres; volume /data hanya cache audio (dan berkas lama yang menunggu diimpor). Pengguna non-root.
RUN useradd --system --uid 10001 --home-dir /srv appuser \
    && mkdir -p /data && chown -R appuser /data
USER appuser
VOLUME ["/data"]
EXPOSE 8000

# Satu proses saja: status siaran hidup di memori (jangan naikkan --workers).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
