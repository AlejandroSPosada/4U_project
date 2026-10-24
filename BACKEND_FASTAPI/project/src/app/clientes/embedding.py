"""Cliente del servicio de embeddings (`SERVICE_EMBEDDING/docs/ARCHITECTURE.md` §5).

En BE-1.1 solo se usa la comprobación de disponibilidad para `GET /v1/health/ready`. `POST /v1/embed`, `GET /v1/info`
y la comprobación de `version_vector` (§5.10) llegan con los lotes que vectorizan (BE-2.2, BE-2.4, BE-3.2).
"""

from __future__ import annotations

import httpx

from app.config import Settings

RUTA_PREPARADO = "/health/ready"


async def esta_listo(ajustes: Settings, transporte: httpx.AsyncBaseTransport | None = None) -> bool:
    """`True` si `GET {EMBEDDING_URL}/health/ready` responde 200 dentro de `EMBEDDING_CONNECT_TIMEOUT_S`.

    Fuera de horario `embedding` está apagado y su nombre DNS no resuelve: eso es `False`, no un error.
    """
    if not ajustes.embedding_url:
        return False
    limite = httpx.Timeout(ajustes.embedding_connect_timeout_s)
    try:
        # trust_env=False: es un servicio interno de la VPC; no debe pasar por proxies del entorno.
        async with httpx.AsyncClient(timeout=limite, transport=transporte, trust_env=False) as cliente:
            respuesta = await cliente.get(f"{ajustes.embedding_url}{RUTA_PREPARADO}")
    except httpx.HTTPError:
        return False
    return respuesta.status_code == 200
