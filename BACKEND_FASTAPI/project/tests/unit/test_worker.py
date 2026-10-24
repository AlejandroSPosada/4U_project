"""Worker de BE-1.1: latido y parada limpia."""

from __future__ import annotations

import asyncio

from app import worker


def test_emite_latidos_y_se_detiene(logs_json):
    async def escenario():
        detener = asyncio.Event()
        tarea = asyncio.create_task(worker.ejecutar(detener, intervalo_s=0.01))
        await asyncio.sleep(0.05)
        detener.set()
        await asyncio.wait_for(tarea, timeout=1)

    asyncio.run(escenario())
    latidos = [linea for linea in logs_json.lineas if linea["evento"] == "latido"]
    assert len(latidos) >= 2
