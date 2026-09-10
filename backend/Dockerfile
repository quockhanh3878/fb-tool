# ============================================================
# CommHunter AI - image dung chung cho API va Celery worker.
#
# LUU Y: build context la THU MUC GOC cua repo (khong phai backend/),
# vi worker can ca ma Phase 1 trong commhunter/.
#   docker build -f backend/Dockerfile -t commhunter-api .
# ============================================================
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Ho_Chi_Minh

WORKDIR /srv

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /srv/backend/requirements.txt
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt

COPY backend /srv/backend
COPY commhunter /srv/commhunter

WORKDIR /srv/backend
RUN mkdir -p data/profiles

# ------------------------------------------------------------
# API: chi phuc vu HTTP, khong can trinh duyet -> image gon.
# ------------------------------------------------------------
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ------------------------------------------------------------
# Worker: can Chromium that de chay Scout/Shooter/Warm-up.
# ------------------------------------------------------------
FROM base AS worker
RUN playwright install --with-deps chromium
CMD ["celery", "-A", "app.workers.celery_app.celery_app", "worker", "--loglevel=info", "--concurrency=2"]

# ------------------------------------------------------------
# Beat: bo dinh gio, khong mo trinh duyet.
# ------------------------------------------------------------
FROM base AS beat
CMD ["celery", "-A", "app.workers.celery_app.celery_app", "beat", "--loglevel=info"]
