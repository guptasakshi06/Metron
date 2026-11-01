FROM python:3.12.3-slim-bookworm@sha256:afc139a0a640942491ec481ad8dda10f2c5b753f5c969393b12480155fe15a63
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ARROW_NUM_THREADS=1 HOME=/tmp
COPY infra/worker/requirements.lock /requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /requirements.lock
COPY backend/src/data_optimizer /app/data_optimizer
ENV PYTHONPATH=/app
USER 65534:65534
WORKDIR /tmp
ENTRYPOINT ["python", "-m", "data_optimizer.benchmarking.worker"]
