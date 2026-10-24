"""Ayudas de los validadores de SERVICE_EMBEDDING (validate<fase><n>.py).

Contrato común: INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md §5.11 (argumentos, estados, códigos de
salida e informe). Lo propio de este servicio: ARCHITECTURE.md §5.8 (entornos `local` y `dev`).

Cada validador declara un `Lote` (precondiciones, comprobaciones, manuales y limpieza) y llama a
`ejecutar(lote)`. Las comprobaciones devuelven el detalle si pasan y lanzan `Falla` si no.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# --- Nombres del contrato (infra §5.1, §5.7; embeddings §5.2, §5.3, §5.5) ------------------------

CUENTA_AWS = "648617469176"
REGION = "us-east-1"
CLUSTER = "campus-locator-dev"
SERVICIO_ECS = "embedding"
FAMILIA_TAREA = "campus-locator-dev-embedding"
LOG_GROUP = "/campus-locator/dev/embedding"
CONTENEDOR = "app"
REPOSITORIO_ECR = "campus-locator/embedding"
PUERTO = 8080
URL_LOCAL = f"http://localhost:{PUERTO}"
MODELO_ID = "facebook/dinov2-small"
VERSION_VECTOR = "dinov2-vits14/pp-v1"
PLAZO_ARRANQUE_S = 180
# Comando del health check del contenedor `embedding` (infra §5.7).
COMANDO_SALUD = (
    "import urllib.request,sys; "
    "urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=3)"
)

DIR_PROYECTO = Path(__file__).resolve().parents[2]
ARCHITECTURE = DIR_PROYECTO.parent / "docs" / "ARCHITECTURE.md"
DIR_INFORMES = DIR_PROYECTO / ".validacion"

ENTORNOS = ("local", "dev")
_PATRON_ECR = re.compile(r"^(\d{12})\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com/")


# --- Errores que mapean a estados y códigos de salida -------------------------------------------


class Falla(Exception):
    """Una comprobación no pasa (código 1)."""


class PrecondicionNoCumplida(Exception):
    """Otro lote no está listo (código 2, `Bloqueado`)."""


class ErrorConfiguracion(Exception):
    """Faltan credenciales, herramientas o variables, o están mal (código 3)."""


# --- Declaración de un lote ---------------------------------------------------------------------

Funcion = Callable[["Contexto"], str]


@dataclass(frozen=True)
class Paso:
    id: str
    entornos: frozenset[str]
    funcion: Funcion
    descripcion: str = ""


@dataclass(frozen=True)
class Manual:
    id: str
    instruccion: str
    entornos: frozenset[str] = frozenset(ENTORNOS)


@dataclass
class Lote:
    lote: str
    validacion: str
    entornos: frozenset[str]
    # En orden de ejecución (el informe las ordena por ID).
    precondiciones: Sequence[Paso]
    comprobaciones: Sequence[Paso]
    manuales: Sequence[Manual] = ()
    limpiar: Callable[[Contexto], None] | None = None
    descripcion: str = ""


@dataclass
class Resultado:
    id: str
    estado: str
    detalle: str = ""
    duracion_ms: int | None = None


@dataclass
class Contexto:
    entorno: str
    lote: Lote
    sin_limpieza: bool = False
    datos: dict[str, Any] = field(default_factory=dict)
    aws: Any = None
    _restos_limpios: bool = False

    def limpiar_restos(self) -> None:
        """Limpia lo que haya dejado una ejecución anterior (una vez por ejecución)."""
        if self._restos_limpios or self.lote.limpiar is None:
            return
        self._restos_limpios = True
        self.lote.limpiar(self)


def entornos(*nombres: str) -> frozenset[str]:
    return frozenset(nombres)


# --- Ejecución -----------------------------------------------------------------------------------


def _argumentos(lote: Lote, argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Validador de {lote.lote} ({lote.validacion}). {lote.descripcion}".strip(),
        epilog="Salida: 0 pasa · 1 falla · 2 bloqueado · 3 error de uso o de configuración",
    )
    parser.add_argument("--entorno", required=True, choices=sorted(lote.entornos))
    parser.add_argument("--informe", type=Path, help="Ruta del informe JSON")
    parser.add_argument("--solo", help="Comprobaciones a ejecutar, p. ej. C1,C3 (C1 incluye C1a…)")
    parser.add_argument("--sin-limpieza", action="store_true", help="No borra lo que se creó")
    return parser.parse_args(argv)


def _seleccion(solo: str | None, ids: Iterable[str]) -> set[str]:
    ids = list(ids)
    if not solo:
        return set(ids)
    elegidas: set[str] = set()
    for pedido in (p.strip() for p in solo.split(",") if p.strip()):
        coinciden = [
            i for i in ids if i == pedido or (i.startswith(pedido) and i[len(pedido) :].isalpha())
        ]
        if not coinciden:
            raise ErrorConfiguracion(
                f"--solo: {pedido} no es una comprobación de este lote ({', '.join(ids)})"
            )
        elegidas.update(coinciden)
    return elegidas


def _commit() -> str:
    try:
        salida = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=DIR_PROYECTO,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return salida.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "desconocido"


def _ahora() -> datetime:
    return datetime.now(UTC)


def _iso(instante: datetime) -> str:
    return instante.isoformat(timespec="seconds").replace("+00:00", "Z")


def _imprimir(resultado: Resultado) -> None:
    linea = f"[{resultado.estado.upper()}] {resultado.id}"
    if resultado.detalle:
        linea += f" {resultado.detalle}"
    print(linea, flush=True)


def ejecutar(lote: Lote, argv: Sequence[str] | None = None) -> int:
    """Precondiciones → comprobaciones → manuales → limpieza → informe. Devuelve el código."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _argumentos(lote, argv)
    ctx = Contexto(entorno=args.entorno, lote=lote, sin_limpieza=args.sin_limpieza)
    inicio = _ahora()
    precondiciones: list[Resultado] = []
    comprobaciones: list[Resultado] = []
    manuales = [m for m in lote.manuales if ctx.entorno in m.entornos]
    resultado = "pasa"
    print(f"{lote.lote} · {lote.validacion} · entorno {ctx.entorno}", flush=True)

    try:
        seleccion = _seleccion(args.solo, (c.id for c in lote.comprobaciones))

        # 1) Precondiciones: a la primera que no se cumple, se para.
        for paso in lote.precondiciones:
            if ctx.entorno not in paso.entornos:
                precondiciones.append(
                    Resultado(paso.id, "omitida", f"solo en {_lista(paso.entornos)}")
                )
            elif resultado != "pasa":
                precondiciones.append(Resultado(paso.id, "omitida", "no se evaluó"))
            else:
                try:
                    precondiciones.append(Resultado(paso.id, "pasa", paso.funcion(ctx)))
                except PrecondicionNoCumplida as error:
                    precondiciones.append(Resultado(paso.id, "falla", str(error)))
                    resultado = "bloqueado"
                except ErrorConfiguracion as error:
                    precondiciones.append(Resultado(paso.id, "falla", str(error)))
                    resultado = "error"
                except Exception as error:
                    precondiciones.append(Resultado(paso.id, "falla", _describir(error)))
                    resultado = "error"
            _imprimir(precondiciones[-1])

        # 2) Comprobaciones automáticas.
        for paso in lote.comprobaciones:
            if ctx.entorno not in paso.entornos:
                comprobaciones.append(
                    Resultado(paso.id, "omitida", f"solo en {_lista(paso.entornos)}")
                )
            elif paso.id not in seleccion:
                comprobaciones.append(Resultado(paso.id, "omitida", "excluida con --solo"))
            elif resultado not in ("pasa", "falla"):
                comprobaciones.append(Resultado(paso.id, "omitida", "no se evaluó"))
            else:
                try:
                    comprobaciones.append(_comprobar(paso, ctx))
                    if comprobaciones[-1].estado == "falla":
                        resultado = "falla"
                except ErrorConfiguracion as error:
                    comprobaciones.append(Resultado(paso.id, "falla", str(error)))
                    resultado = "error"
            _imprimir(comprobaciones[-1])

        # 3) Manuales: se listan; las hace una persona.
        for manual in manuales:
            _imprimir(Resultado(manual.id, "manual", manual.instruccion))
    except ErrorConfiguracion as error:
        print(f"[ERROR] {error}", flush=True)
        resultado = "error"
    finally:
        # 4) Limpieza: siempre, también si algo falló.
        if not args.sin_limpieza and lote.limpiar is not None:
            try:
                lote.limpiar(ctx)
            except Exception as error:  # la limpieza no cambia el resultado, pero se avisa
                print(f"[AVISO] limpieza incompleta: {type(error).__name__}: {error}", flush=True)

    fin = _ahora()
    informe = {
        "lote": lote.lote,
        "validacion": lote.validacion,
        "entorno": ctx.entorno,
        "commit": _commit(),
        "inicio": _iso(inicio),
        "fin": _iso(fin),
        "resultado": resultado,
        "precondiciones": [
            {"id": r.id, "estado": r.estado, "detalle": r.detalle}
            for r in sorted(precondiciones, key=lambda r: r.id)
        ],
        "comprobaciones": [
            {"id": r.id, "estado": r.estado, "detalle": r.detalle, "duracion_ms": r.duracion_ms}
            for r in comprobaciones
        ],
        "manuales": [{"id": m.id, "instruccion": m.instruccion} for m in manuales],
    }
    ruta = args.informe or DIR_INFORMES / f"{lote.lote}-{fin.strftime('%Y%m%d-%H%M%S')}.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(informe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    codigo = {"pasa": 0, "falla": 1, "bloqueado": 2, "error": 3}[resultado]
    print(f"Resultado: {resultado} (código {codigo}) · informe: {ruta}", flush=True)
    return codigo


def _comprobar(paso: Paso, ctx: Contexto) -> Resultado:
    """Ejecuta una comprobación; `ErrorConfiguracion` sube para que el validador termine con 3."""
    inicio = time.monotonic()
    try:
        detalle = paso.funcion(ctx)
        estado = "pasa"
    except Falla as error:
        detalle, estado = str(error), "falla"
    except ErrorConfiguracion:
        raise
    except Exception as error:
        if _es_error_de_credenciales(error):
            raise ErrorConfiguracion(_describir(error)) from error
        detalle, estado = _describir(error), "falla"
    return Resultado(paso.id, estado, detalle, round((time.monotonic() - inicio) * 1000))


_CODIGOS_CREDENCIALES = {
    "AccessDenied",
    "AccessDeniedException",
    "ExpiredToken",
    "ExpiredTokenException",
    "UnrecognizedClientException",
    "InvalidClientTokenId",
}


def _es_error_de_credenciales(error: Exception) -> bool:
    respuesta = getattr(error, "response", None)
    codigo = respuesta.get("Error", {}).get("Code") if isinstance(respuesta, dict) else None
    return codigo in _CODIGOS_CREDENCIALES or type(error).__name__ in {
        "NoCredentialsError",
        "ProfileNotFound",
        "TokenRetrievalError",
        "SSOTokenLoadError",
    }


def _describir(error: Exception) -> str:
    if _es_error_de_credenciales(error):
        return f"credenciales o permisos de AWS insuficientes ({type(error).__name__}: {error})"
    return f"error inesperado: {type(error).__name__}: {error}"


def _lista(nombres: Iterable[str]) -> str:
    return ", ".join(sorted(nombres))


# --- Documentación -------------------------------------------------------------------------------


def revision_architecture() -> str:
    """SHA de la fila «Revisión» de ARCHITECTURE §5.3; `Falla` si no está anotado."""
    try:
        texto = ARCHITECTURE.read_text(encoding="utf-8")
    except OSError as error:
        raise Falla(f"no se pudo leer {ARCHITECTURE}: {error}") from error
    for linea in texto.splitlines():
        if linea.startswith("| Revisión |"):
            shas = re.findall(r"\b[0-9a-f]{40}\b", linea)
            if len(shas) == 1:
                return shas[0]
            break
    raise Falla("ARCHITECTURE §5.3 no tiene anotado el SHA de la revisión del modelo")


# --- AWS -----------------------------------------------------------------------------------------


def sesion_aws(region: str = REGION):
    """Sesión con AWS_PROFILE; se niega a seguir si la cuenta no es la del proyecto (código 3)."""
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    perfil = os.environ.get("AWS_PROFILE")
    if not perfil:
        raise ErrorConfiguracion("falta la variable AWS_PROFILE")
    try:
        sesion = boto3.Session(profile_name=perfil, region_name=region)
        cuenta = sesion.client("sts").get_caller_identity()["Account"]
    except (BotoCoreError, ClientError) as error:
        raise ErrorConfiguracion(
            f"credenciales de AWS no válidas ({type(error).__name__})"
        ) from error
    if cuenta != CUENTA_AWS:
        raise ErrorConfiguracion(f"AWS_PROFILE apunta a la cuenta {cuenta}, no a {CUENTA_AWS}")
    return sesion


def es_imagen_ecr(imagen: str) -> bool:
    return _PATRON_ECR.match(imagen) is not None


def login_ecr(imagen: str) -> None:
    """`docker login` en el registro de ECR de `imagen` sin imprimir la contraseña."""
    coincidencia = _PATRON_ECR.match(imagen)
    if coincidencia is None:
        return
    sesion = sesion_aws(region=coincidencia.group(2))
    datos = sesion.client("ecr").get_authorization_token()["authorizationData"][0]
    usuario, clave = base64.b64decode(datos["authorizationToken"]).decode().split(":", 1)
    registro = datos["proxyEndpoint"]
    salida = docker("login", "--username", usuario, "--password-stdin", registro, entrada=clave)
    if salida.returncode != 0:
        raise ErrorConfiguracion(f"docker login en {registro} falló: {_recortar(salida.stderr)}")


# --- Docker y red local --------------------------------------------------------------------------


def docker(
    *args: str, entrada: str | None = None, timeout: float = 900
) -> subprocess.CompletedProcess[str]:
    if shutil.which("docker") is None:
        raise ErrorConfiguracion("no se encuentra el comando docker")
    return subprocess.run(
        ["docker", *args],
        input=entrada,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def borrar_contenedores(*nombres: str) -> None:
    for nombre in nombres:
        docker("rm", "-f", nombre, timeout=120)


def puerto_ocupado(puerto: int, anfitrion: str = "localhost") -> bool:
    try:
        with socket.create_connection((anfitrion, puerto), timeout=1):
            return True
    except OSError:
        return False


def logs_contenedor(nombre: str, lineas: int = 15) -> str:
    salida = docker("logs", "--tail", str(lineas), nombre, timeout=60)
    return _recortar(salida.stdout + salida.stderr, 1500)


def _recortar(texto: str, maximo: int = 400) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= maximo else "…" + texto[-maximo:]
