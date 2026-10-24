# syntax=docker/dockerfile:1
# Imagen del servicio de embeddings (ARCHITECTURE §5.5; contrato de despliegue: infra §5.9).
# Contexto de construcción: esta carpeta (project/). Requiere uv.lock (se genera con `uv lock`).
#
#   docker build --platform linux/amd64 --build-arg GIT_COMMIT=$(git rev-parse HEAD) \
#     -t campus-locator/embedding:local .

ARG PYTHON_IMAGEN=python:3.12-slim

# 1) Dependencias exactas de uv.lock (PyTorch para CPU + transformers) en /opt/venv.
FROM ${PYTHON_IMAGEN} AS dependencias
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# 2) Pesos de la revisión fija, descargados en el build (ADR-EMB-05). Esta etapa solo depende de
#    config.py y del script: cambiar el resto del código no vuelve a bajar ~350 MB.
FROM dependencias AS pesos
COPY src/app/__init__.py src/app/config.py /build/src/app/
COPY tools/descargar_modelo.py /build/tools/
RUN PYTHONPATH=/build/src /opt/venv/bin/python /build/tools/descargar_modelo.py /opt/modelo

# 3) Imagen final: sin uv ni caché de descargas, usuario sin privilegios, sin red en ejecución.
FROM ${PYTHON_IMAGEN}
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --home-dir /nonexistent \
      --shell /usr/sbin/nologin app
COPY --from=dependencias /opt/venv /opt/venv
COPY --from=pesos /opt/modelo /opt/modelo
WORKDIR /srv
COPY src/app ./app
COPY tools/benchmark.py ./tools/benchmark.py
ARG GIT_COMMIT=desconocido
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODELO_DIR=/opt/modelo \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HOME=/tmp/huggingface \
    GIT_COMMIT=${GIT_COMMIT}
USER app
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-server-header"]
