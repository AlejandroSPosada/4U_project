"""Validador de EMB-3.1 — Rendimiento en CPU (docs/validation/validation-3-1.md).

    uv run --group ops python src/ops/validate31.py --entorno dev

Lanza `tools/benchmark.py --salida json` como tarea suelta de Fargate con la revisión y la red del
servicio `embedding` (sin tocar el servicio: da igual que esté encendido o apagado) y lee el
resultado de su log en /campus-locator/dev/embedding. Solo `dev`.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from comun import (
    CLUSTER,
    CONTENEDOR,
    DIR_INFORMES,
    FAMILIA_TAREA,
    LOG_GROUP,
    SERVICIO_ECS,
    VERSION_VECTOR,
    Falla,
    Lote,
    Manual,
    Paso,
    PrecondicionNoCumplida,
    archivo_en_commit,
    ejecutar,
    entornos,
    estado_lote,
    sesion_aws,
)

STARTED_BY = "validacion-emb31"
COMANDO_BENCHMARK = ["python", "tools/benchmark.py", "--salida", "json"]
RUTA_BENCHMARK = "tools/benchmark.py"  # relativa a project/
PREFIJO_JSON = "BENCHMARK_JSON "  # el de tools/benchmark.py (§5.9)
LOTES_EXIGIDOS = (1, 5, 8)  # PLAN §2.2, EMB-3.1 C1
REPETICIONES_MIN = 20
OBJETIVO_P95_LOTE5_MS = 800  # §4.4 y §5.7; C3
CPU_TAREA, MEMORIA_TAREA = "2048", "4096"  # 2 vCPU / 4 GB (infra §3.4)
PLAZO_TAREA_S = 30 * 60
PAUSA_TAREA_S = 15
PLAZO_LOG_S = 120
PAUSA_LOG_S = 5
PATRON_IMAGEN_CI = re.compile(r"/campus-locator/embedding:([0-9a-f]{40})$")

DEV = entornos("dev")


# --- Precondiciones (orden: P3, P2, P1) -----------------------------------------------------------


def p3_credenciales(ctx) -> str:
    ctx.aws = sesion_aws()
    return "AWS_PROFILE de la cuenta del proyecto"


def p2_inf13(ctx) -> str:
    from botocore.exceptions import ClientError

    ctx.limpiar_restos()
    ecs = ctx.aws.client("ecs")
    clusters = ecs.describe_clusters(clusters=[CLUSTER])["clusters"]
    if not clusters or clusters[0]["status"] != "ACTIVE":
        raise PrecondicionNoCumplida(f"INF-1.3: el clúster {CLUSTER} no existe o no está ACTIVE")
    try:
        ultima = ecs.describe_task_definition(taskDefinition=FAMILIA_TAREA)["taskDefinition"]
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "ClientException":
            raise
        raise PrecondicionNoCumplida(f"INF-1.3: no existe la familia {FAMILIA_TAREA}") from error
    grupos = ctx.aws.client("logs").describe_log_groups(logGroupNamePrefix=LOG_GROUP)["logGroups"]
    if not any(g["logGroupName"] == LOG_GROUP for g in grupos):
        raise PrecondicionNoCumplida(f"INF-1.3: no existe el log group {LOG_GROUP}")
    return (
        f"clúster ACTIVE, familia {FAMILIA_TAREA} (última :{ultima['revision']}), "
        f"log group {LOG_GROUP}"
    )


def p1_emb21(ctx) -> str:
    estado = estado_lote("EMB-2.1")
    if estado != "Hecho":
        raise PrecondicionNoCumplida(f"EMB-2.1 está «{estado}» en PLAN §3, no «Hecho»")
    ecs = ctx.aws.client("ecs")
    respuesta = ecs.describe_services(cluster=CLUSTER, services=[SERVICIO_ECS])
    if respuesta["failures"] or not respuesta["services"]:
        raise PrecondicionNoCumplida(f"INF-1.3: no existe el servicio {SERVICIO_ECS}")
    servicio = respuesta["services"][0]
    definicion = ecs.describe_task_definition(taskDefinition=servicio["taskDefinition"])[
        "taskDefinition"
    ]
    nombre = f"{definicion['family']}:{definicion['revision']}"
    if definicion["family"] != FAMILIA_TAREA:
        raise PrecondicionNoCumplida(f"el servicio usa {nombre}, no la familia {FAMILIA_TAREA}")
    contenedor = next(
        (c for c in definicion["containerDefinitions"] if c["name"] == CONTENEDOR), None
    )
    if contenedor is None:
        raise PrecondicionNoCumplida(f"{nombre} no tiene un contenedor llamado {CONTENEDOR}")
    coincidencia = PATRON_IMAGEN_CI.search(contenedor["image"])
    if coincidencia is None:
        raise PrecondicionNoCumplida(
            f"{nombre} usa {contenedor['image']}: no es una imagen de CI con etiqueta SHA "
            "(despliega con embedding.yml)"
        )
    sha = coincidencia.group(1)
    codigo = archivo_en_commit(sha, RUTA_BENCHMARK)
    if codigo is None or PREFIJO_JSON.strip() not in codigo:
        raise PrecondicionNoCumplida(
            f"la imagen desplegada ({sha[:7]}) trae el {RUTA_BENCHMARK} provisional, anterior a "
            "EMB-3.1: lleva EMB-3.1 a main para que embedding.yml publique y registre su imagen "
            "(validation-3-1 §5, preparación)"
        )
    registro = (contenedor.get("logConfiguration") or {}).get("options") or {}
    ctx.datos["desplegada"] = {
        "arn": definicion["taskDefinitionArn"],
        "nombre": nombre,
        "sha": sha,
        "red": servicio["networkConfiguration"],
        "prefijo_log": registro.get("awslogs-stream-prefix", "embedding"),
    }
    return f"EMB-2.1 Hecho; servicio {SERVICIO_ECS} con {nombre}, imagen {sha[:7]} (con benchmark)"


# --- Comprobaciones -------------------------------------------------------------------------------


def _esperar_detenida(ecs, arn: str) -> dict:
    tarea_id = arn.rsplit("/", 1)[-1]
    limite = time.monotonic() + PLAZO_TAREA_S
    while True:
        tarea = ecs.describe_tasks(cluster=CLUSTER, tasks=[arn])["tasks"][0]
        if tarea["lastStatus"] == "STOPPED":
            return tarea
        if time.monotonic() > limite:
            raise Falla(
                f"tarea {tarea_id} sin terminar en {PLAZO_TAREA_S // 60} min "
                f"(lastStatus={tarea['lastStatus']}); la limpieza la detiene"
            )
        time.sleep(PAUSA_TAREA_S)


def _segundos(tarea: dict, desde: str, hasta: str) -> int | None:
    if tarea.get(desde) is None or tarea.get(hasta) is None:
        return None
    return round((tarea[hasta] - tarea[desde]).total_seconds())


def c1a_tarea_suelta(ctx) -> str:
    desplegada = ctx.datos["desplegada"]
    ecs = ctx.aws.client("ecs")
    respuesta = ecs.run_task(
        cluster=CLUSTER,
        taskDefinition=desplegada["arn"],
        launchType="FARGATE",
        startedBy=STARTED_BY,
        networkConfiguration=desplegada["red"],
        overrides={"containerOverrides": [{"name": CONTENEDOR, "command": COMANDO_BENCHMARK}]},
        count=1,
    )
    if respuesta["failures"] or not respuesta["tasks"]:
        motivos = "; ".join(f.get("reason", "?") for f in respuesta["failures"]) or "sin tareas"
        raise Falla(f"run-task falló: {motivos}")
    arn = respuesta["tasks"][0]["taskArn"]
    ctx.datos.setdefault("tareas", []).append(arn)
    ctx.datos["tarea"] = arn
    tarea_id = arn.rsplit("/", 1)[-1]

    tarea = _esperar_detenida(ecs, arn)
    ctx.datos.setdefault("detenidas", set()).add(arn)
    contenedor = next((c for c in tarea.get("containers", []) if c["name"] == CONTENEDOR), {})
    familia = tarea.get("taskDefinitionArn", "").rsplit("/", 1)[-1]
    errores = []
    if contenedor.get("exitCode") != 0:
        errores.append(
            f"salida de {CONTENEDOR}={contenedor.get('exitCode')}"
            f"{' (' + contenedor['reason'] + ')' if contenedor.get('reason') else ''}, "
            f"stopCode={tarea.get('stopCode')}, motivo={tarea.get('stoppedReason')}"
        )
    if familia.rsplit(":", 1)[0] != FAMILIA_TAREA:
        errores.append(f"la tarea usó {familia}, no la familia {FAMILIA_TAREA}")
    if (tarea.get("cpu"), tarea.get("memory")) != (CPU_TAREA, MEMORIA_TAREA):
        errores.append(
            f"tamaño {tarea.get('cpu')} CPU / {tarea.get('memory')} MB, "
            f"se espera {CPU_TAREA} / {MEMORIA_TAREA} (infra §3.4)"
        )
    if errores:
        raise Falla(f"tarea {tarea_id}: " + "; ".join(errores) + f"; log en {LOG_GROUP}")
    descarga = _segundos(tarea, "pullStartedAt", "pullStoppedAt")
    ejecucion = _segundos(tarea, "startedAt", "stoppedAt")
    return (
        f"tarea {tarea_id}: {familia}, {CPU_TAREA} CPU / {MEMORIA_TAREA} MB, salida 0; "
        f"descarga de la imagen {descarga} s, ejecución {ejecucion} s"
    )


def _leer_log(logs, stream: str) -> list[str]:
    mensajes: list[str] = []
    token = None
    for _ in range(200):  # páginas; el log de una ejecución cabe en pocas
        pedido: dict[str, Any] = {
            "logGroupName": LOG_GROUP,
            "logStreamName": stream,
            "startFromHead": True,
        }
        if token is not None:
            pedido["nextToken"] = token
        pagina = logs.get_log_events(**pedido)
        mensajes.extend(e["message"] for e in pagina["events"])
        if pagina.get("nextForwardToken") in (None, token):
            break
        token = pagina["nextForwardToken"]
    return mensajes


def extraer_resultado(mensajes: list[str]) -> dict | None:
    """El JSON de la última línea `BENCHMARK_JSON …` del log, o None si no hay."""
    for mensaje in reversed(mensajes):
        texto = mensaje.strip()
        if texto.startswith(PREFIJO_JSON.strip()):
            return json.loads(texto[len(PREFIJO_JSON.strip()) :])
    return None


def revisar_resultado(datos: dict, sha: str | None) -> list[str]:
    """Lo que C1b exige a la salida de benchmark.py; devuelve los errores (vacío = pasa)."""
    errores = []
    if datos.get("version_vector") != VERSION_VECTOR:
        errores.append(
            f"version_vector={datos.get('version_vector')!r}, se espera {VERSION_VECTOR}"
        )
    if sha is not None and datos.get("commit") != sha[:7]:
        errores.append(f"commit={datos.get('commit')!r}: no es la imagen desplegada ({sha[:7]})")
    por_lote = {r.get("lote"): r for r in datos.get("resultados") or [] if isinstance(r, dict)}
    for lote in LOTES_EXIGIDOS:
        r = por_lote.get(lote)
        if r is None:
            errores.append(f"falta el lote de {lote}")
            continue
        p50, p95, repeticiones = r.get("p50_ms"), r.get("p95_ms"), r.get("repeticiones")
        if not all(isinstance(v, int | float) for v in (p50, p95)) or not 0 < p50 <= p95:
            errores.append(f"lote {lote}: p50={p50!r}, p95={p95!r} (se exige 0 < p50 ≤ p95)")
        if not isinstance(repeticiones, int) or repeticiones < REPETICIONES_MIN:
            errores.append(
                f"lote {lote}: {repeticiones!r} repeticiones (mínimo {REPETICIONES_MIN})"
            )
    return errores


def describir(datos: dict) -> str:
    por_lote = {r["lote"]: r for r in datos["resultados"]}
    lotes = " · ".join(
        f"lote {lote}: p50 {r['p50_ms']} ms, p95 {r['p95_ms']} ms"
        for lote, r in sorted(por_lote.items())
    )
    memoria = datos.get("memoria_proceso_mb") or {}
    p95_5 = por_lote[5]["p95_ms"]
    c3 = (
        f"C3: p95 del lote de 5 = {p95_5} ms > {OBJETIVO_P95_LOTE5_MS} ms → decidir la palanca "
        "(ARCHITECTURE §4.4) y registrarla como ADR"
        if p95_5 > OBJETIVO_P95_LOTE5_MS
        else f"C3: p95 del lote de 5 = {p95_5} ms ≤ {OBJETIVO_P95_LOTE5_MS} ms → no aplica"
    )
    return (
        f"{lotes}; {datos.get('hilos')} hilos, {datos.get('vcpu')} vCPU / "
        f"{datos.get('memoria_mb')} MiB ({datos.get('limites_de')}), CPU {datos.get('cpu')} "
        f"({datos.get('capacidad_cpu_torch')}); memoria del proceso: reposo "
        f"{memoria.get('reposo')} MiB, pico {memoria.get('pico')} MiB; {c3}"
    )


def c1b_resultado(ctx) -> str:
    arn = ctx.datos.get("tarea")
    if arn is None:
        raise Falla("no hay tarea de C1a: C1b lee su log (usa --solo C1)")
    tarea_id = arn.rsplit("/", 1)[-1]
    stream = f"{ctx.datos['desplegada']['prefijo_log']}/{CONTENEDOR}/{tarea_id}"
    logs = ctx.aws.client("logs")
    limite = time.monotonic() + PLAZO_LOG_S
    while True:
        try:
            mensajes = _leer_log(logs, stream)
        except logs.exceptions.ResourceNotFoundException:
            mensajes = []
        datos = extraer_resultado(mensajes)
        if datos is not None:
            break
        if time.monotonic() > limite:
            cola = " | ".join(m.strip() for m in mensajes[-5:]) or "stream vacío o inexistente"
            raise Falla(
                f"el log {LOG_GROUP}:{stream} no trae la línea {PREFIJO_JSON.strip()}; "
                f"últimas líneas: {cola[-1200:]}"
            )
        time.sleep(PAUSA_LOG_S)
    errores = revisar_resultado(datos, ctx.datos["desplegada"]["sha"])
    if errores:
        raise Falla("; ".join(errores))
    DIR_INFORMES.mkdir(parents=True, exist_ok=True)
    ruta = DIR_INFORMES / f"EMB-3.1-benchmark-{tarea_id}.json"
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"{describir(datos)}; JSON completo en {ruta.name} (stream {stream})"


# --- Limpieza (§4 de la validación) -------------------------------------------------------------


def limpiar(ctx) -> None:
    if ctx.aws is None:
        return
    ecs = ctx.aws.client("ecs")
    detenidas = ctx.datos.get("detenidas", set())
    tareas = {arn for arn in ctx.datos.get("tareas", []) if arn not in detenidas}
    for pagina in ecs.get_paginator("list_tasks").paginate(cluster=CLUSTER, startedBy=STARTED_BY):
        tareas.update(pagina["taskArns"])
    pendientes = []
    for arn in sorted(tareas):
        try:
            ecs.stop_task(cluster=CLUSTER, task=arn, reason=f"{STARTED_BY}: limpieza")
        except Exception as error:
            pendientes.append(f"{arn.rsplit('/', 1)[-1]} ({type(error).__name__})")
    if pendientes:
        raise RuntimeError(f"no se pudieron detener: {', '.join(pendientes)}")


LOTE = Lote(
    lote="EMB-3.1",
    validacion="validation-3-1",
    entornos=DEV,
    descripcion="Rendimiento en CPU (benchmark en una tarea suelta de dev).",
    precondiciones=[
        Paso("P3", DEV, p3_credenciales),
        Paso("P2", DEV, p2_inf13),
        Paso("P1", DEV, p1_emb21),
    ],
    comprobaciones=[
        Paso("C1a", DEV, c1a_tarea_suelta),
        Paso("C1b", DEV, c1b_resultado),
    ],
    manuales=[
        Manual(
            "C2",
            "Copia p50 y p95 de los lotes de 1, 5 y 8 (detalle de C1b) a la tabla «Latencias "
            "medidas» de ARCHITECTURE §5.7, sube la versión (menor: parámetros medidos) y añade la "
            "entrada en CHANGELOG.md; adjunta al PR este informe y EMB-3.1-benchmark-<tarea>.json",
        ),
        Manual(
            "C3",
            f"Si el p95 del lote de 5 (detalle de C1b) supera {OBJETIVO_P95_LOTE5_MS} ms, elige la "
            "palanca con la tabla de ARCHITECTURE §4.4 y regístrala como ADR nuevo en §6 (ONNX "
            "Runtime o int8 exigen version_vector nueva, ADR-EMB-08); si no, anota «no aplica»",
        ),
    ],
    limpiar=limpiar,
)


if __name__ == "__main__":
    raise SystemExit(ejecutar(LOTE))
