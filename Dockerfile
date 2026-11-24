FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.production VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv "$VIRTUAL_ENV" \
    && groupadd --system agentix \
    && useradd --system --gid agentix --no-create-home agentix

COPY requirements.txt requirements-production.txt /tmp/requirements/
RUN pip install --no-cache-dir --only-binary=:all: -r /tmp/requirements/requirements-production.txt \
    && pip check

WORKDIR /app
COPY agentix_backend/ /app/
COPY --chmod=755 deploy/web-start.sh /usr/local/bin/web-start
RUN sed -i 's/\r$//' /usr/local/bin/web-start \
    && install -d -o agentix -g agentix /app/staticfiles \
    && python -c 'from orchestrator.ml_engine.loader import load_model; load_model()'

USER agentix
EXPOSE 8000
CMD ["/usr/local/bin/web-start"]
