FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# - curl: healthcheck
# - git: optional Retraction Watch dataset sync method (MISCITE_RW_SYNC_METHOD=git)
# - sqlite3: optional inspection/backup tooling
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    curl \
    git \
    sqlite3 \
    libgl1 \
    libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server ./server

RUN useradd -m -u 1000 app \
  && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["python", "-m", "server.main"]
