# Construir SIEMPRE para X86_64 (el módulo ecs_service usa X86_64 por defecto):
#   docker buildx build --platform linux/amd64 -t <url ECR backend>:<tag> --push .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Capa de dependencias: solo se reconstruye si cambia pyproject.toml
COPY pyproject.toml .
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt \
 && rm /tmp/requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

RUN useradd --system --uid 10001 --no-create-home appuser
USER appuser

EXPOSE 8000

# Detrás del ALB: confiar en X-Forwarded-*. Sin HEALTHCHECK propio (lo hace el ALB con GET /health).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
