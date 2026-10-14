"""Punto de entrada. Routers de negocio se añaden en B2–B6."""
import logging

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.db.engine import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("campus")

settings = get_settings()

app = FastAPI(
    title="Campus Locator API",
    version="0.1.0",
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_prod else "/openapi.json",
)


@app.exception_handler(StarletteHTTPException)
async def http_error(_request, exc: StarletteHTTPException) -> JSONResponse:
    # Formato de error de la sección 4.2: {"detail": ..., "codigo": ...}
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "codigo": f"http_{exc.status_code}"},
        headers=getattr(exc, "headers", None),
    )


@app.get("/health")
def health() -> dict:
    """Health check del ALB: SUPERFICIAL a propósito (solo el proceso, sin BD ni embedding),
    para que una caída ajena no haga que el ALB reinicie tareas. Sin autenticación."""
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> JSONResponse:
    """Comprueba BD y embedding. NO lo usa el ALB; es para diagnóstico manual."""
    checks: dict[str, str] = {}

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - solo se registra el tipo, nunca credenciales
        log.warning("ready: base de datos no disponible (%s)", type(exc).__name__)
        checks["database"] = "fail"

    url = settings.embedding_service_url
    if not url:
        checks["embedding"] = "sin configurar"
    else:
        try:
            httpx.get(f"{url.rstrip('/')}/health", timeout=3.0).raise_for_status()
            checks["embedding"] = "ok"
        except Exception as exc:  # noqa: BLE001
            log.warning("ready: embedding no disponible (%s)", type(exc).__name__)
            checks["embedding"] = "fail"

    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(status_code=200 if ok else 503, content={"status": "ok" if ok else "degraded", **checks})
