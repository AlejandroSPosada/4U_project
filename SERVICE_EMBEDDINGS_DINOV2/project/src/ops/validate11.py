"""Validador de EMB-1.1 — Servicio base e imagen (docs/validation/validation-1-1.md).

    uv run --group ops python src/ops/validate11.py --entorno dev
    EMBEDDING_IMAGEN=<ecr_embedding_url>:<sha> \
        uv run --group ops python src/ops/validate11.py --entorno local

`dev` cubre C1 (C1a, C1b); `local` cubre C2 y C3. Cierran el lote las dos ejecuciones con código 0,
la de `local` con EMBEDDING_IMAGEN = la imagen que identifica C1a.
"""

from __future__ import annotations

import os
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from comun import (
    CLUSTER,
    COMANDO_SALUD,
    CONTENEDOR,
    FAMILIA_TAREA,
    LOG_GROUP,
    MODELO_ID,
    PLAZO_ARRANQUE_S,
    PUERTO,
    SERVICIO_ECS,
    URL_LOCAL,
    VERSION_VECTOR,
    ErrorConfiguracion,
    Falla,
    Lote,
    Paso,
    PrecondicionNoCumplida,
    borrar_contenedores,
    docker,
    ejecutar,
    entornos,
    es_imagen_ecr,
    login_ecr,
    logs_contenedor,
    puerto_ocupado,
    revision_architecture,
    sesion_aws,
)

STARTED_BY = "validacion-emb11"
CONTENEDOR_LOCAL = "validacion-emb11"
CONTENEDOR_SIN_RED = "validacion-emb11-sinred"
PLAZO_TAREA_S = 600
PAUSA_TAREA_S = 5
PAUSA_LOCAL_S = 5
PATRON_IMAGEN_CI = re.compile(r"/campus-locator/embedding:[0-9a-f]{40}$")

DEV = entornos("dev")
LOCAL = entornos("local")


# --- dev -----------------------------------------------------------------------------------------


def p2_credenciales(ctx) -> str:
    ctx.aws = sesion_aws()
    return "AWS_PROFILE de la cuenta del proyecto"


def p1_inf13(ctx) -> str:
    from botocore.exceptions import ClientError

    ctx.limpiar_restos()
    ecs = ctx.aws.client("ecs")
    clusters = ecs.describe_clusters(clusters=[CLUSTER])["clusters"]
    if not clusters or clusters[0]["status"] != "ACTIVE":
        raise PrecondicionNoCumplida(f"INF-1.3: el clúster {CLUSTER} no existe o no está ACTIVE")
    try:
        respuesta = ecs.describe_services(cluster=CLUSTER, services=[SERVICIO_ECS])
    except ClientError as error:
        raise PrecondicionNoCumplida(f"INF-1.3: {error.response['Error']['Code']}") from error
    if respuesta["failures"] or not respuesta["services"]:
        motivo = respuesta["failures"][0].get("reason") if respuesta["failures"] else "sin datos"
        raise PrecondicionNoCumplida(f"INF-1.3: no existe el servicio {SERVICIO_ECS} ({motivo})")
    servicio = respuesta["services"][0]
    revision = servicio["taskDefinition"].rsplit("/", 1)[-1]
    if revision.rsplit(":", 1)[0] != FAMILIA_TAREA:
        raise PrecondicionNoCumplida(
            f"INF-1.3: el servicio usa {revision}, no la familia {FAMILIA_TAREA}"
        )
    grupos = ctx.aws.client("logs").describe_log_groups(logGroupNamePrefix=LOG_GROUP)["logGroups"]
    if not any(g["logGroupName"] == LOG_GROUP for g in grupos):
        raise PrecondicionNoCumplida(f"INF-1.3: no existe el log group {LOG_GROUP}")
    ctx.datos["servicio"] = servicio
    return f"clúster ACTIVE, servicio {SERVICIO_ECS} con {revision}, log group {LOG_GROUP}"


def _desplegada(ctx) -> dict:
    """Revisión, imagen y red del servicio `embedding` (lo que comprueba C1a y usa C1b)."""
    if "desplegada" not in ctx.datos:
        servicio = ctx.datos["servicio"]
        definicion = ctx.aws.client("ecs").describe_task_definition(
            taskDefinition=servicio["taskDefinition"]
        )["taskDefinition"]
        contenedor = next(
            (c for c in definicion["containerDefinitions"] if c["name"] == CONTENEDOR), None
        )
        ctx.datos["desplegada"] = {
            "arn": definicion["taskDefinitionArn"],
            "familia": definicion["family"],
            "revision": definicion["revision"],
            "imagen": contenedor["image"] if contenedor else None,
            "red": servicio["networkConfiguration"],
        }
    return ctx.datos["desplegada"]


def c1a_revision_desplegada(ctx) -> str:
    datos = _desplegada(ctx)
    nombre = f"{datos['familia']}:{datos['revision']}"
    if datos["familia"] != FAMILIA_TAREA:
        raise Falla(f"la revisión {nombre} no es de la familia {FAMILIA_TAREA}")
    if datos["imagen"] is None:
        raise Falla(f"{nombre} no tiene un contenedor llamado {CONTENEDOR}")
    if not PATRON_IMAGEN_CI.search(datos["imagen"]):
        raise Falla(f"{nombre} usa {datos['imagen']}: no es una imagen de CI con etiqueta SHA")
    return f"{nombre} con {datos['imagen']} (úsala como EMBEDDING_IMAGEN en local)"


def c1b_arranque_en_dev(ctx) -> str:
    datos = _desplegada(ctx)
    if datos["imagen"] is None or not PATRON_IMAGEN_CI.search(datos["imagen"]):
        raise Falla("la imagen desplegada no es de CI (ver C1a): medir su arranque no cierra C1")
    ecs = ctx.aws.client("ecs")
    respuesta = ecs.run_task(
        cluster=CLUSTER,
        taskDefinition=datos["arn"],
        launchType="FARGATE",
        startedBy=STARTED_BY,
        networkConfiguration=datos["red"],
        count=1,
    )
    if respuesta["failures"] or not respuesta["tasks"]:
        motivos = "; ".join(f.get("reason", "?") for f in respuesta["failures"]) or "sin tareas"
        raise Falla(f"run-task falló: {motivos}")
    arn = respuesta["tasks"][0]["taskArn"]
    ctx.datos.setdefault("tareas", []).append(arn)
    tarea_id = arn.rsplit("/", 1)[-1]

    limite = time.monotonic() + PLAZO_TAREA_S
    while True:
        consulta = ecs.describe_tasks(cluster=CLUSTER, tasks=[arn])
        tarea = consulta["tasks"][0]
        if tarea.get("healthStatus") == "HEALTHY":
            # Hora del servidor de AWS (encabezado Date): no depende del reloj de esta máquina.
            observado = _hora_respuesta(consulta)
            inicio = tarea.get("startedAt")
            if inicio is None:
                raise Falla(f"tarea {tarea_id} HEALTHY sin startedAt")
            segundos = (observado - inicio).total_seconds()
            if segundos >= PLAZO_ARRANQUE_S:
                raise Falla(
                    f"tarea {tarea_id}: HEALTHY a los {segundos:.0f} s de startedAt (≥ 180 s)"
                )
            return (
                f"tarea {tarea_id}: HEALTHY a los {segundos:.0f} s de startedAt "
                "(cota superior: el health check corre cada 30 s)"
            )
        if tarea["lastStatus"] == "STOPPED":
            contenedor = next(
                (c for c in tarea.get("containers", []) if c["name"] == CONTENEDOR), {}
            )
            raise Falla(
                f"tarea {tarea_id} STOPPED: stopCode={tarea.get('stopCode')}, "
                f"motivo={tarea.get('stoppedReason')}, "
                f"salida de {CONTENEDOR}={contenedor.get('exitCode')}"
                f"{' (' + contenedor['reason'] + ')' if contenedor.get('reason') else ''}"
                f"; logs en {LOG_GROUP}"
            )
        if time.monotonic() > limite:
            raise Falla(
                f"tarea {tarea_id} sin HEALTHY en {PLAZO_TAREA_S // 60} min "
                f"(lastStatus={tarea['lastStatus']}, healthStatus={tarea.get('healthStatus')})"
            )
        time.sleep(PAUSA_TAREA_S)


def _hora_respuesta(respuesta: dict) -> datetime:
    fecha = respuesta.get("ResponseMetadata", {}).get("HTTPHeaders", {}).get("date")
    return parsedate_to_datetime(fecha) if fecha else datetime.now(UTC)


# --- local ---------------------------------------------------------------------------------------


def p3_docker(ctx) -> str:
    info = docker("info", "--format", "{{.ServerVersion}}", timeout=60)
    if info.returncode != 0:
        raise ErrorConfiguracion("Docker no responde (docker info); ¿está arrancado?")
    ctx.limpiar_restos()
    if puerto_ocupado(PUERTO):
        raise ErrorConfiguracion(f"el puerto {PUERTO} está ocupado en esta máquina")
    return f"Docker {info.stdout.strip()}; puerto {PUERTO} libre"


def p4_imagen(ctx) -> str:
    imagen = os.environ.get("EMBEDDING_IMAGEN", "").strip()
    if not imagen:
        raise ErrorConfiguracion("falta la variable EMBEDDING_IMAGEN (ARCHITECTURE §5.8)")
    if es_imagen_ecr(imagen):
        login_ecr(imagen)
        descargar = True
    else:
        descargar = docker("image", "inspect", imagen, timeout=60).returncode != 0
    if descargar:
        salida = docker("pull", imagen, timeout=1800)
        if salida.returncode != 0:
            raise ErrorConfiguracion(f"docker pull {imagen} falló: {salida.stderr.strip()[-300:]}")
    plataforma = docker(
        "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", imagen, timeout=60
    ).stdout.strip()
    if plataforma != "linux/amd64":
        raise PrecondicionNoCumplida(
            f"{imagen} es {plataforma or '?'}, se exige linux/amd64 (infra §5.9)"
        )
    ctx.datos["imagen"] = imagen
    return f"{imagen} ({plataforma})"


def _arrancar(nombre: str, *opciones: str, imagen: str) -> float:
    salida = docker(
        "run", "-d", "--name", nombre, *opciones, "-e", "TORCH_NUM_THREADS=1", imagen, timeout=300
    )
    if salida.returncode != 0:
        raise Falla(f"docker run falló: {salida.stderr.strip()[-300:]}")
    return time.monotonic()


def _en_marcha(nombre: str) -> bool:
    estado = docker("inspect", "--format", "{{.State.Running}}", nombre, timeout=60)
    return estado.stdout.strip() == "true"


def c2_info_local(ctx) -> str:
    imagen = ctx.datos["imagen"]
    inicio = _arrancar(CONTENEDOR_LOCAL, "-p", f"{PUERTO}:{PUERTO}", imagen=imagen)
    try:
        with httpx.Client(base_url=URL_LOCAL, timeout=5) as cliente:
            listo = _esperar_listo_http(cliente, inicio)
            respuesta = cliente.get("/v1/info", headers={"X-Request-Id": "validacion-emb11-info"})
        if respuesta.status_code != 200:
            raise Falla(f"GET /v1/info respondió {respuesta.status_code}")
        info = respuesta.json()
    finally:
        # Libera memoria y el puerto antes de C3; la limpieza final lo repite sin efecto.
        borrar_contenedores(CONTENEDOR_LOCAL)

    errores = []
    if info.get("version_vector") != VERSION_VECTOR:
        errores.append(
            f"version_vector={info.get('version_vector')!r}, se espera {VERSION_VECTOR!r}"
        )
    if info.get("modelo") != MODELO_ID:
        errores.append(f"modelo={info.get('modelo')!r}, se espera {MODELO_ID!r}")
    try:
        anotada = revision_architecture()
        if info.get("revision") != anotada:
            errores.append(
                f"revision={info.get('revision')!r}, ARCHITECTURE §5.3 anota {anotada!r}"
            )
    except Falla as error:
        errores.append(str(error))
    if errores:
        raise Falla("; ".join(errores))
    return (
        f"/health/ready a los {listo:.0f} s; version_vector={info['version_vector']}, "
        f"modelo={info['modelo']}, revision={info['revision']}, commit={info.get('commit')}"
    )


def _esperar_listo_http(cliente: httpx.Client, inicio: float) -> float:
    while True:
        transcurrido = time.monotonic() - inicio
        try:
            respuesta = cliente.get("/health/ready")
            if respuesta.status_code == 200 and respuesta.json() == {"estado": "listo"}:
                return transcurrido
        except httpx.HTTPError:
            pass  # el servidor aún no escucha
        if not _en_marcha(CONTENEDOR_LOCAL):
            raise Falla(
                f"el contenedor terminó antes de estar listo: {logs_contenedor(CONTENEDOR_LOCAL)}"
            )
        if transcurrido > PLAZO_ARRANQUE_S:
            raise Falla(f"/health/ready no respondió 200 en {PLAZO_ARRANQUE_S} s")
        time.sleep(2)


def c3_sin_red(ctx) -> str:
    imagen = ctx.datos["imagen"]
    inicio = _arrancar(CONTENEDOR_SIN_RED, "--network", "none", imagen=imagen)
    while True:
        if not _en_marcha(CONTENEDOR_SIN_RED):
            raise Falla(f"sin red, el contenedor terminó: {logs_contenedor(CONTENEDOR_SIN_RED)}")
        salud = docker("exec", CONTENEDOR_SIN_RED, "python", "-c", COMANDO_SALUD, timeout=60)
        transcurrido = time.monotonic() - inicio
        if salud.returncode == 0:
            if transcurrido >= PLAZO_ARRANQUE_S:
                raise Falla(f"listo sin red a los {transcurrido:.0f} s (≥ {PLAZO_ARRANQUE_S} s)")
            if not _en_marcha(CONTENEDOR_SIN_RED):
                raise Falla("el health check pasó pero el contenedor ya no está en marcha")
            return f"health check de infra §5.7 con código 0 a los {transcurrido:.0f} s, sin red"
        if transcurrido > PLAZO_ARRANQUE_S:
            raise Falla(
                f"sin red, /health/ready no quedó listo en {PLAZO_ARRANQUE_S} s: "
                f"{logs_contenedor(CONTENEDOR_SIN_RED)}"
            )
        time.sleep(PAUSA_LOCAL_S)


# --- Limpieza (§4 de la validación) -------------------------------------------------------------


def limpiar(ctx) -> None:
    if ctx.entorno == "local":
        borrar_contenedores(CONTENEDOR_LOCAL, CONTENEDOR_SIN_RED)
        return
    if ctx.aws is None:
        return
    ecs = ctx.aws.client("ecs")
    tareas = set(ctx.datos.get("tareas", []))
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
    lote="EMB-1.1",
    validacion="validation-1-1",
    entornos=entornos("dev", "local"),
    descripcion="Servicio base e imagen.",
    precondiciones=[
        Paso("P2", DEV, p2_credenciales),
        Paso("P1", DEV, p1_inf13),
        Paso("P3", LOCAL, p3_docker),
        Paso("P4", LOCAL, p4_imagen),
    ],
    comprobaciones=[
        Paso("C1a", DEV, c1a_revision_desplegada),
        Paso("C1b", DEV, c1b_arranque_en_dev),
        Paso("C2", LOCAL, c2_info_local),
        Paso("C3", LOCAL, c3_sin_red),
    ],
    limpiar=limpiar,
)


if __name__ == "__main__":
    raise SystemExit(ejecutar(LOTE))
