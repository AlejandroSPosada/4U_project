"""Validador de EMB-3.2 — Conjunto de evaluación y calibración (docs/validation/validation-3-2.md).

    uv run --group ops python src/ops/validate32.py --entorno dev

Solo lee: el conjunto de `evaluacion/` del bucket del dataset, el informe que dejó
`tools/evaluacion` y el dataset indexado a través de la API del backend. No lanza tareas, no
enciende `embedding` y no escribe nada en AWS. Solo `dev`.
"""

from __future__ import annotations

import json
import os
import re
import sys

from comun import (
    DIR_PROYECTO,
    VERSION_VECTOR,
    ErrorConfiguracion,
    Falla,
    Lote,
    Manual,
    Paso,
    PrecondicionNoCumplida,
    ejecutar,
    entornos,
    estado_lote,
    sesion_aws,
)

sys.path.insert(0, str(DIR_PROYECTO / "tools"))

from evaluacion import conjunto as cj
from evaluacion import metricas
from evaluacion.fuentes import ClienteBackend, ErrorFuente, preparar_foto

BUCKET = "campus-locator-dev-dataset-648617469176"  # infra §5.5
PREFIJO = "evaluacion/"
SECRETO_ADMIN = "campus-locator/dev/admin-inicial"  # backend §5.11 (claves correo y password)
IMAGEN_P2B = DIR_PROYECTO / "tests" / "golden" / "validacion-01-campus.jpg"
PATRON_INFORME = re.compile(
    r"^evaluacion/(?P<version>[^/]+)/informes/"
    + re.escape(VERSION_VECTOR.replace("/", "_"))
    + r"-(?P<fecha>\d{8})\.json$"
)

DEV = entornos("dev")


# --- Ayudas ---------------------------------------------------------------------------------------


def _codigo_s3(error: Exception) -> str | None:
    respuesta = getattr(error, "response", None)
    return respuesta.get("Error", {}).get("Code") if isinstance(respuesta, dict) else None


def _claves(s3, prefijo: str) -> list[str]:
    claves, token = [], None
    while True:
        pedido = {"Bucket": BUCKET, "Prefix": prefijo}
        if token:
            pedido["ContinuationToken"] = token
        pagina = s3.list_objects_v2(**pedido)
        claves.extend(o["Key"] for o in pagina.get("Contents", []))
        token = pagina.get("NextContinuationToken")
        if not pagina.get("IsTruncated") or not token:
            return claves


def _leer_json(s3, clave: str) -> dict:
    try:
        cuerpo = s3.get_object(Bucket=BUCKET, Key=clave)["Body"].read()
    except Exception as error:
        if _codigo_s3(error) in {"NoSuchKey", "404"}:
            raise Falla(f"no existe s3://{BUCKET}/{clave}") from error
        raise
    try:
        return json.loads(cuerpo)
    except ValueError as error:
        raise Falla(f"{clave} no es JSON válido ({error})") from error


def _credenciales_admin(ctx) -> tuple[str, str]:
    correo = os.environ.get("VALIDACION_ADMIN_CORREO")
    password = os.environ.get("VALIDACION_ADMIN_PASSWORD")
    if correo and password:
        return correo, password
    try:
        secreto = ctx.aws.client("secretsmanager").get_secret_value(SecretId=SECRETO_ADMIN)
        datos = json.loads(secreto["SecretString"])
        return datos["correo"], datos["password"]
    except (KeyError, ValueError) as error:
        raise ErrorConfiguracion(
            f"el secreto {SECRETO_ADMIN} no tiene correo y password"
        ) from error


def _imagenes_dataset(ctx):
    if "imagenes" not in ctx.datos:
        ctx.datos["imagenes"] = ctx.datos["cliente"].imagenes()
    return ctx.datos["imagenes"]


def _informe_reciente(ctx) -> tuple[str, dict] | None:
    """(clave, informe) del informe más reciente de esta version_vector, o None."""
    if "informe" not in ctx.datos:
        candidatos = []
        for clave in _claves(ctx.aws.client("s3"), PREFIJO):
            m = PATRON_INFORME.match(clave)
            if m:
                candidatos.append((m.group("fecha"), m.group("version"), clave))
        if not candidatos:
            ctx.datos["informe"] = None
        else:
            clave = max(candidatos)[2]
            ctx.datos["informe"] = (clave, _leer_json(ctx.aws.client("s3"), clave))
    return ctx.datos["informe"]


def _version_a_revisar(ctx) -> str:
    informe = _informe_reciente(ctx)
    citada = (informe[1].get("version_conjunto") if informe else None) or None
    if citada in ctx.datos["versiones"]:
        return citada
    return max(ctx.datos["versiones"])


def _cobertura(ctx, version: str) -> dict:
    """Revisión de `puntos.json` de `version` contra el bucket y el dataset (cacheada)."""
    cache = ctx.datos.setdefault("cobertura", {})
    if version in cache:
        return cache[version]
    s3 = ctx.aws.client("s3")
    base = f"{PREFIJO}{version}/"
    datos = _leer_json(s3, base + "puntos.json")
    revision = cj.revisar(datos)
    errores = list(revision.errores)
    resultado: dict = {"errores": errores, "fotos_con_dataset": None, "resumen": None}
    if revision.valido:
        en_bucket = set(_claves(s3, base + "fotos/"))
        faltan = [f["archivo"] for f in datos["fotos"] if base + f["archivo"] not in en_bucket]
        if faltan:
            errores.append(
                f"{len(faltan)} archivos de puntos.json no están en el bucket "
                f"({', '.join(faltan[:5])}{'…' if len(faltan) > 5 else ''})"
            )
        conjunto = cj.desde_dict(datos)
        coordenadas = [(i.lat, i.lng) for i in _imagenes_dataset(ctx)]
        errores_c1, resumen = cj.revisar_c1(cj.cobertura(conjunto, coordenadas))
        errores.extend(errores_c1)
        resultado["fotos_con_dataset"] = resumen["fotos_con_dataset"]
        resultado["resumen"] = resumen
        resultado["dataset"] = len(coordenadas)
    cache[version] = resultado
    return resultado


# --- Precondiciones (orden: P4, P1, P2, P2b, P3) --------------------------------------------------


def p4_credenciales(ctx) -> str:
    ctx.aws = sesion_aws()
    return "AWS_PROFILE de la cuenta del proyecto"


def p1_emb21(ctx) -> str:
    estado = estado_lote("EMB-2.1")
    if estado != "Hecho":
        raise PrecondicionNoCumplida(f"EMB-2.1 está «{estado}» en PLAN §3, no «Hecho»")
    return "EMB-2.1 Hecho"


def p2_dataset(ctx) -> str:
    url = os.environ.get("VALIDACION_API_URL")
    if not url:
        raise ErrorConfiguracion(
            "falta VALIDACION_API_URL (output api_base_url de infra + /v1, backend §5.11)"
        )
    correo, password = _credenciales_admin(ctx)
    cliente = ClienteBackend(url, correo, password)
    try:
        cliente.token()
    except ErrorFuente as error:
        if error.estado == 401:
            raise ErrorConfiguracion(f"credenciales de admin rechazadas: {error}") from error
        raise PrecondicionNoCumplida(f"BE-1.3: no se pudo iniciar sesión: {error}") from error
    ctx.datos["cliente"] = cliente
    try:
        videos = cliente.videos()
    except ErrorFuente as error:
        raise PrecondicionNoCumplida(f"BE-2.1: {error}") from error
    reales = [
        v
        for v in videos
        if not (v.get("nombre") or "").startswith("validacion-")
        and (v.get("conteo") or {}).get("procesada", 0) > 0
    ]
    if not reales:
        raise PrecondicionNoCumplida(
            f"ningún video real con imágenes procesadas ({len(videos)} videos en total): "
            "falta el dataset del campus (FE-2.1 + BE-2.2)"
        )
    procesadas = sum(v["conteo"]["procesada"] for v in reales)
    return f"{len(reales)} videos reales con {procesadas} imágenes procesadas"


def p2b_vecinos(ctx) -> str:
    foto = preparar_foto(IMAGEN_P2B.read_bytes())
    respuesta = ctx.datos["cliente"].vecinos_crudo(foto, 5)
    codigo = _codigo_respuesta(respuesta)
    if respuesta.status_code == 200:
        datos = respuesta.json()
        if datos.get("version_vector") != VERSION_VECTOR:
            raise PrecondicionNoCumplida(
                f"vecinos con version_vector={datos.get('version_vector')!r}, no {VERSION_VECTOR}"
            )
        if not datos.get("vecinos"):
            raise PrecondicionNoCumplida("vecinos vacío: el índice no tiene vectores")
        return f"POST /v1/admin/diagnostico/vecinos → 200, {VERSION_VECTOR}"
    if respuesta.status_code == 503 and codigo == "EMBEDDING_NO_DISPONIBLE":
        return (
            "POST /v1/admin/diagnostico/vecinos → 503 EMBEDDING_NO_DISPONIBLE: el endpoint existe; "
            "embedding apagado, version_vector no comprobada aquí (la comprueba tools/evaluacion "
            "en cada respuesta)"
        )
    raise PrecondicionNoCumplida(
        f"BE-2.4: POST /v1/admin/diagnostico/vecinos → {respuesta.status_code} {codigo}".rstrip()
    )


def _codigo_respuesta(respuesta) -> str:
    try:
        return respuesta.json()["error"]["codigo"]
    except (ValueError, KeyError, TypeError):
        return ""


def p3_conjunto(ctx) -> str:
    s3 = ctx.aws.client("s3")
    pagina = s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIJO, Delimiter="/")
    versiones = sorted(
        p["Prefix"][len(PREFIJO) :].rstrip("/")
        for p in pagina.get("CommonPrefixes", [])
        if cj.PATRON_VERSION.match(p["Prefix"][len(PREFIJO) :].rstrip("/"))
    )
    if not versiones:
        raise PrecondicionNoCumplida(
            f"no hay ningún conjunto en s3://{BUCKET}/{PREFIJO} (sube el de la toma de fotos, "
            "ARCHITECTURE §4.5)"
        )
    try:
        s3.head_object(Bucket=BUCKET, Key=f"{PREFIJO}{versiones[-1]}/puntos.json")
    except Exception as error:
        if _codigo_s3(error) in {"404", "NoSuchKey", "NotFound"}:
            raise PrecondicionNoCumplida(
                f"{PREFIJO}{versiones[-1]}/ no tiene puntos.json"
            ) from error
        raise
    ctx.datos["versiones"] = versiones
    return f"conjuntos en {PREFIJO}: {', '.join(versiones)}"


# --- Comprobaciones -------------------------------------------------------------------------------


def c1_conjunto(ctx) -> str:
    version = _version_a_revisar(ctx)
    resultado = _cobertura(ctx, version)
    if resultado["errores"]:
        raise Falla(f"{version}: " + "; ".join(resultado["errores"]))
    resumen = resultado["resumen"]
    return (
        f"{version}: {resumen['fotos_con_dataset']} fotos en {len(resumen['puntos_con_dataset'])} "
        f"puntos con dataset (≤ {cj.DATASET_CERCA_M:.0f} m); puntos lejanos (> "
        f"{cj.LEJOS_M:.0f} m, ≥ {cj.FOTOS_PUNTO_LEJANO_MIN} fotos): "
        f"{', '.join(resumen['puntos_lejanos'])}; dataset de {resultado['dataset']} imágenes"
    )


def c2_informe(ctx) -> str:
    encontrado = _informe_reciente(ctx)
    if encontrado is None:
        raise Falla(
            f"no hay informe evaluacion/*/informes/{VERSION_VECTOR.replace('/', '_')}-"
            "<AAAAMMDD>.json (genera con tools/evaluacion evaluar y súbelo, validation-3-2 §5)"
        )
    clave, informe = encontrado
    version = informe.get("version_conjunto")
    if version not in ctx.datos["versiones"]:
        raise Falla(f"{clave} cita version_conjunto={version!r}, que no está en {PREFIJO}")
    fotos = _cobertura(ctx, version)["fotos_con_dataset"]
    errores = metricas.revisar_informe(informe, VERSION_VECTOR, fotos)
    if clave.split("/")[1] != version:
        errores.append(f"está en la carpeta de otro conjunto que {version}")
    if errores:
        raise Falla(f"{clave}: " + "; ".join(errores))
    r = informe["recomendado"]
    return (
        f"{clave}: recall@1 {informe['recall_1_15m']}, recall@5 {informe['recall_5_15m']} "
        f"({informe['fotos']} fotos); similitud mismo lugar p50 "
        f"{informe['similitud']['mismo_lugar']['p50']}, otro lugar p50 "
        f"{informe['similitud']['otro_lugar']['p50']}; recomendado LOC_SIM_MIN "
        f"{r['LOC_SIM_MIN']}, LOC_SIM_ALTA {r['LOC_SIM_ALTA']}, cortes alta {r['corte_alta']} / "
        f"media {r['corte_media']}"
    )


def limpiar(ctx) -> None:
    """Nada que limpiar: solo lee (validation-3-2 §4)."""


LOTE = Lote(
    lote="EMB-3.2",
    validacion="validation-3-2",
    entornos=DEV,
    descripcion="Conjunto de evaluación y calibración (solo lectura en dev).",
    precondiciones=[
        Paso("P4", DEV, p4_credenciales),
        Paso("P1", DEV, p1_emb21),
        Paso("P2", DEV, p2_dataset),
        Paso("P2b", DEV, p2b_vecinos),
        Paso("P3", DEV, p3_conjunto),
    ],
    comprobaciones=[
        Paso("C1", DEV, c1_conjunto),
        Paso("C2", DEV, c2_informe),
    ],
    manuales=[
        Manual(
            "C3",
            "Revisa en el informe de C2 (y su .md) los valores recomendados de LOC_SIM_MIN y "
            "LOC_SIM_ALTA (0 < MIN < ALTA ≤ 1) y de los cortes de nivel (0 < media < alta < 1) "
            "frente a los de backend §5.10, y entrégalos a quien lleva BE-3.2 (issue o PR del "
            "backend) con el enlace al informe",
        ),
    ],
    limpiar=limpiar,
)


if __name__ == "__main__":
    raise SystemExit(ejecutar(LOTE))
