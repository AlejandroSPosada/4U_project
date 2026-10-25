"""Ayudas comunes de los validadores del backend (`validate<fase><n>.py`).

Implementa el contrato común de `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11 (argumentos, orden de
ejecución, estados, códigos de salida e informe JSON) y lo propio del backend de `BACKEND_FASTAPI/docs/ARCHITECTURE.md`
§5.11 (URL de la API, credenciales de AWS).

Uso típico en un validador:

    validador = Validador(lote="BE-1.1", validacion="validation-1-1", entornos=("dev",), descripcion=__doc__)
    ctx = validador.iniciar()
    sys.exit(validador.ejecutar(
        precondiciones=[("P1", lambda: ...)],
        comprobaciones=[("C1", lambda: ...)],
        manuales=[],
        limpieza=None,
    ))

Cada función de precondición o comprobación devuelve un texto corto (el `detalle`) y señala problemas lanzando:
- `Falla` → la comprobación queda en `falla` (código 1);
- `PrecondicionNoCumplida` → otro lote no está listo (código 2);
- `ErrorConfiguracion` → uso, configuración, credenciales o herramientas (código 3).

Reglas (§5.11): nunca imprimir secretos, tokens ni URLs prefirmadas; ser idempotente; limpiar siempre lo creado.

Además (tabla completa en backend §5.11): tareas sueltas de ECS (BE-1.2) y, desde BE-1.3, secretos y credenciales del
admin, `ClienteApi` (login con pausa y reintentos de 429 de API Gateway), `EntornoBackend` (`python -m app.cli` y SQL
en `local` o `dev`) y el usuario de prueba `validacion+user@campus.edu.co`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# --- Constantes del proyecto (infra §3.1, §5.1) -------------------------------------------------------------------
CUENTA_AWS = "648617469176"
REGION_AWS = "us-east-1"

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]  # BACKEND_FASTAPI/project
RAIZ_CARPETA = RAIZ_PROYECTO.parent  # BACKEND_FASTAPI
RAIZ_REPO = RAIZ_CARPETA.parent  # raíz del monorepo
DIR_TERRAFORM_DEV = RAIZ_REPO / "INFRASTRUCTURA_TERRAFORM" / "project" / "envs" / "dev"
DIR_INFORMES = RAIZ_PROYECTO / ".validacion"

PASA, FALLA, MANUAL, OMITIDA = "pasa", "falla", "manual", "omitida"
CODIGO_RESULTADO = {0: "pasa", 1: "falla", 2: "bloqueado", 3: "error"}


# --- Excepciones -------------------------------------------------------------------------------------------------
class Falla(Exception):
    """La comprobación no se cumple."""


class PrecondicionNoCumplida(Exception):
    """Otro lote no está listo: código 2 (`Bloqueado`)."""


class ErrorConfiguracion(Exception):
    """Error de uso, configuración, credenciales o herramientas: código 3."""


def exigir(condicion: object, mensaje: str) -> None:
    """Lanza `Falla(mensaje)` si `condicion` es falsa."""
    if not condicion:
        raise Falla(mensaje)


# --- Resultados e informe ----------------------------------------------------------------------------------------
@dataclass
class Resultado:
    id: str
    estado: str
    detalle: str = ""
    duracion_ms: int | None = None


@dataclass
class Manual:
    id: str
    instruccion: str


@dataclass
class _Estado:
    precondiciones: list[Resultado] = field(default_factory=list)
    comprobaciones: list[Resultado] = field(default_factory=list)
    manuales: list[Manual] = field(default_factory=list)
    codigo_precondicion: int = 0


def _ahora() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _imprimir(estado: str, id_: str, detalle: str) -> None:
    print(f"[{estado.upper()}] {id_} {detalle}".rstrip(), flush=True)


def _criterio(id_: str) -> str:
    """`C2a` → `C2` (las comprobaciones con letra pertenecen al criterio del PLAN)."""
    coincidencia = re.match(r"([A-Z]+\d+)", id_)
    return coincidencia.group(1) if coincidencia else id_


class Validador:
    def __init__(self, *, lote: str, validacion: str, entornos: Sequence[str], descripcion: str | None = None) -> None:
        self.lote = lote
        self.validacion = validacion
        self.entornos = tuple(entornos)
        self.descripcion = (descripcion or "").strip()
        self.args: argparse.Namespace | None = None
        self._estado = _Estado()
        self._inicio = _ahora()
        self._solo: set[str] | None = None

    # -- argumentos ----------------------------------------------------------------------------------------------
    def crear_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description=f"Validador de {self.lote} ({self.validacion}.md). {self.descripcion}".strip(),
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("--entorno", required=True, choices=("local", "dev"), help="Entorno a validar")
        parser.add_argument("--informe", type=Path, help="Ruta del informe JSON (por defecto, project/.validacion/)")
        parser.add_argument("--solo", help="Solo estas comprobaciones, separadas por comas (p. ej. C1,C3)")
        parser.add_argument("--sin-limpieza", action="store_true", help="No borrar los datos de prueba al terminar")
        return parser

    def iniciar(self, argv: Sequence[str] | None = None, parser: argparse.ArgumentParser | None = None):
        """Lee los argumentos. Termina con código 3 si el entorno no está admitido por el documento."""
        _utf8_en_consola()
        parser = parser or self.crear_parser()
        try:
            self.args = parser.parse_args(argv)
        except SystemExit as salida:  # argparse sale con 2 en error de uso; el contrato pide 3
            raise SystemExit(0 if salida.code == 0 else 3) from None
        if self.args.entorno not in self.entornos:
            print(f"{self.lote} solo admite el entorno: {', '.join(self.entornos)} (ver {self.validacion}.md).")
            raise SystemExit(3)
        if self.args.solo:
            self._solo = {parte.strip() for parte in self.args.solo.split(",") if parte.strip()}
        print(f"== {self.lote} · {self.validacion} · entorno {self.args.entorno}", flush=True)
        return self.args

    def _incluida(self, id_: str) -> bool:
        return self._solo is None or id_ in self._solo or _criterio(id_) in self._solo

    # -- ejecución -----------------------------------------------------------------------------------------------
    def ejecutar(
        self,
        *,
        precondiciones: Iterable[tuple[str, Callable[[], str | None]]],
        comprobaciones: Iterable[tuple[str, Callable[[], str | None]]],
        manuales: Iterable[tuple[str, str]] = (),
        limpieza: Callable[[], str | None] | None = None,
    ) -> int:
        """Orden de §5.11: precondiciones → automáticas → manuales → limpieza (siempre) → informe."""
        if self.args is None:
            raise RuntimeError("Llama a iniciar() antes de ejecutar()")
        try:
            if self._precondiciones(precondiciones):
                for id_, funcion in comprobaciones:
                    self._comprobacion(id_, funcion)
                for id_, instruccion in manuales:
                    self._estado.manuales.append(Manual(id_, instruccion))
                    _imprimir(MANUAL, id_, instruccion)
        finally:
            self._limpiar(limpieza)
        return self._informe()

    def _precondiciones(self, precondiciones: Iterable[tuple[str, Callable[[], str | None]]]) -> bool:
        for id_, funcion in precondiciones:
            try:
                detalle = funcion() or ""
            except PrecondicionNoCumplida as exc:
                self._registrar_precondicion(id_, FALLA, f"{exc} (bloqueado)", 2)
                return False
            except ErrorConfiguracion as exc:
                self._registrar_precondicion(id_, FALLA, f"{exc} (configuración)", 3)
                return False
            except Exception as exc:
                self._registrar_precondicion(id_, FALLA, f"error inesperado: {_resumen(exc)}", 3)
                traceback.print_exc()
                return False
            self._registrar_precondicion(id_, PASA, detalle, 0)
        return True

    def _registrar_precondicion(self, id_: str, estado: str, detalle: str, codigo: int) -> None:
        self._estado.precondiciones.append(Resultado(id_, estado, detalle))
        self._estado.codigo_precondicion = max(self._estado.codigo_precondicion, codigo)
        _imprimir(estado, id_, detalle)

    def _comprobacion(self, id_: str, funcion: Callable[[], str | None]) -> None:
        if not self._incluida(id_):
            resultado = Resultado(id_, OMITIDA, "excluida con --solo")
        else:
            inicio = time.perf_counter()
            try:
                resultado = Resultado(id_, PASA, funcion() or "")
            except Falla as exc:
                resultado = Resultado(id_, FALLA, str(exc))
            except Exception as exc:
                resultado = Resultado(id_, FALLA, f"error inesperado: {_resumen(exc)}")
            resultado.duracion_ms = int((time.perf_counter() - inicio) * 1000)
        self._estado.comprobaciones.append(resultado)
        _imprimir(resultado.estado, id_, resultado.detalle)

    def _limpiar(self, limpieza: Callable[[], str | None] | None) -> None:
        if limpieza is None:
            return
        if self.args is not None and self.args.sin_limpieza:
            print("[LIMPIEZA] omitida (--sin-limpieza)", flush=True)
            return
        try:
            detalle = limpieza() or "hecha"
            print(f"[LIMPIEZA] {detalle}", flush=True)
        except Exception as exc:
            print(f"[LIMPIEZA] falló: {_resumen(exc)}", flush=True)

    # -- informe -------------------------------------------------------------------------------------------------
    def codigo_salida(self) -> int:
        if self._estado.codigo_precondicion:
            return self._estado.codigo_precondicion
        return 1 if any(r.estado == FALLA for r in self._estado.comprobaciones) else 0

    def _informe(self) -> int:
        codigo = self.codigo_salida()
        assert self.args is not None  # noqa: S101 (iniciar() ya se llamó)
        datos: dict[str, Any] = {
            "lote": self.lote,
            "validacion": self.validacion,
            "entorno": self.args.entorno,
            "commit": commit_local(),
            "inicio": self._inicio,
            "fin": _ahora(),
            "resultado": CODIGO_RESULTADO[codigo],
            "precondiciones": [_sin_nulos(asdict(r)) for r in self._estado.precondiciones],
            "comprobaciones": [_sin_nulos(asdict(r)) for r in self._estado.comprobaciones],
            "manuales": [asdict(m) for m in self._estado.manuales],
        }
        ruta = self.args.informe or DIR_INFORMES / f"{self.lote}-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            destino = str(ruta)
        except OSError as exc:
            destino = f"no se pudo escribir ({exc})"
        print(f"== Resultado: {datos['resultado']} (código {codigo}) · informe: {destino}", flush=True)
        return codigo


def _sin_nulos(datos: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in datos.items() if v is not None}


def _resumen(exc: BaseException) -> str:
    texto = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    return f"{type(exc).__name__}: {texto}" if texto else type(exc).__name__


def _utf8_en_consola() -> None:
    """En Windows la consola puede no ser UTF-8: evita que un acento rompa la salida."""
    for flujo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(flujo, "reconfigure", None)
        if reconfigurar is not None:
            try:
                reconfigurar(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


# --- Procesos externos (git, terraform, docker) ------------------------------------------------------------------
def ejecutar_proceso(
    argumentos: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: float = 600,
    entorno: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Como `ejecutar_comando`, pero devuelve el resultado con su código en vez de lanzar si no es 0.

    `entorno` añade variables al entorno del proceso hijo (sobre el actual): así un secreto llega al proceso sin
    aparecer en la línea de comandos (p. ej. `docker compose run -e VARIABLE`, que toma el valor de ahí).
    """
    ejecutable = shutil.which(argumentos[0])
    if ejecutable is None:
        raise ErrorConfiguracion(f"no se encontró `{argumentos[0]}` en el PATH")
    try:
        return subprocess.run(
            [ejecutable, *argumentos[1:]],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env={**os.environ, **entorno} if entorno else None,
        )
    except subprocess.TimeoutExpired:
        raise Falla(f"`{' '.join(argumentos[:4])} …` no terminó en {int(timeout)} s") from None


def ejecutar_comando(argumentos: Sequence[str], *, cwd: Path | None = None, timeout: float = 120) -> str:
    """Ejecuta un comando y devuelve su salida estándar. Herramienta ausente → `ErrorConfiguracion`.

    Un código distinto de 0 lanza `subprocess.CalledProcessError` (cada validador decide qué significa).
    """
    ejecutable = shutil.which(argumentos[0])
    if ejecutable is None:
        raise ErrorConfiguracion(f"no se encontró `{argumentos[0]}` en el PATH")
    resultado = subprocess.run(
        [ejecutable, *argumentos[1:]],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if resultado.returncode != 0:
        raise subprocess.CalledProcessError(resultado.returncode, argumentos, resultado.stdout, resultado.stderr)
    return resultado.stdout


def git(*argumentos: str, timeout: float = 120) -> str:
    return ejecutar_comando(["git", *argumentos], cwd=RAIZ_REPO, timeout=timeout).strip()


def commit_local() -> str | None:
    """SHA corto del `HEAD` local (para el informe)."""
    try:
        return git("rev-parse", "--short", "HEAD") or None
    except (ErrorConfiguracion, subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return None


def outputs_terraform(directorio: Path = DIR_TERRAFORM_DEV) -> dict[str, Any]:
    """`terraform -chdir=<dir> output -json` → `{nombre: valor}`.

    Requiere `terraform init` hecho en ese directorio con acceso al estado remoto (infra §3.9).
    """
    if not directorio.is_dir():
        raise ErrorConfiguracion(f"no existe {directorio}")
    try:
        salida = ejecutar_comando(["terraform", f"-chdir={directorio}", "output", "-json"], timeout=180)
    except subprocess.CalledProcessError as exc:
        error = (exc.stderr or "").strip().splitlines()
        raise ErrorConfiguracion(
            f"`terraform output` falló en {directorio} ({error[-1] if error else exc.returncode}); "
            "¿falta `terraform init` o credenciales del estado?"
        ) from None
    except subprocess.TimeoutExpired:
        raise ErrorConfiguracion("`terraform output` no respondió a tiempo") from None
    datos = json.loads(salida or "{}")
    return {nombre: valor.get("value") for nombre, valor in datos.items()}


# --- AWS ---------------------------------------------------------------------------------------------------------
def sesion_aws():
    """Sesión de boto3 con `AWS_PROFILE` (obligatoria en `dev`, backend §5.11) en `us-east-1`."""
    perfil = os.environ.get("AWS_PROFILE", "").strip()
    if not perfil:
        raise ErrorConfiguracion("falta la variable AWS_PROFILE")
    try:
        import boto3
        from botocore.exceptions import ProfileNotFound
    except ImportError:
        raise ErrorConfiguracion("falta boto3: ejecuta con `uv run --group ops …`") from None
    try:
        return boto3.Session(profile_name=perfil, region_name=REGION_AWS)
    except ProfileNotFound:
        raise ErrorConfiguracion(f"el perfil de AWS `{perfil}` no existe") from None


def verificar_cuenta(sesion) -> str:
    """Comprueba que las credenciales sean de la cuenta del proyecto. Devuelve el ARN de quien llama."""
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        identidad = sesion.client("sts").get_caller_identity()
    except (BotoCoreError, ClientError) as exc:
        raise ErrorConfiguracion(f"credenciales de AWS no válidas: {_resumen(exc)}") from None
    if identidad.get("Account") != CUENTA_AWS:
        raise ErrorConfiguracion(f"las credenciales son de la cuenta {identidad.get('Account')}, no de {CUENTA_AWS}")
    return identidad.get("Arn", "")


def codigo_error_aws(exc: BaseException) -> str:
    """Código de un `ClientError` de botocore (`AccessDenied`, `RepositoryNotFoundException`…), o ''."""
    respuesta = getattr(exc, "response", None) or {}
    return str(respuesta.get("Error", {}).get("Code", ""))


def es_acceso_denegado(exc: BaseException) -> bool:
    codigo = codigo_error_aws(exc)
    return codigo in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation", "ExpiredToken"} or (
        "AccessDenied" in codigo
    )


# --- Tareas sueltas de ECS (backend §5.11) -----------------------------------------------------------------------
CLUSTER = "campus-locator-dev"
CONTENEDOR = "app"
FAMILIA_MIGRATE = "campus-locator-dev-migrate"
FAMILIA_VALIDACION = "campus-locator-dev-validacion"
#: Log group y `awslogs-stream-prefix` de cada familia (infra §5.1): el stream es `<prefijo>/app/<id de la tarea>`.
LOGS_TAREA = {
    FAMILIA_MIGRATE: ("/campus-locator/dev/migrate", "migrate"),
    FAMILIA_VALIDACION: ("/campus-locator/dev/validacion", "validacion"),
}
ESPERA_TAREA_S = 900
PAUSA_LOGS_S = 5.0
INTENTOS_LOGS = 12


@dataclass
class ResultadoTarea:
    """Una tarea suelta ya detenida: código de salida del contenedor `app` (None si no llegó a correr) y su log."""

    arn: str
    definicion: str
    codigo: int | None
    motivo: str
    lineas: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.arn.rsplit("/", 1)[-1]

    def eventos(self, nombre: str | None = None) -> list[dict[str, Any]]:
        """Líneas JSON del log (§5.10), opcionalmente solo las de un `evento`."""
        encontrados = []
        for linea in self.lineas:
            try:
                datos = json.loads(linea)
            except ValueError:
                continue
            if isinstance(datos, dict) and (nombre is None or datos.get("evento") == nombre):
                encontrados.append(datos)
        return encontrados


def red_tareas(outputs: dict[str, Any]) -> dict[str, Any]:
    """`networkConfiguration` de `run-task` con los outputs `subredes_tareas` y `sg_migrate` (infra §5.2)."""
    subredes, grupo = outputs.get("subredes_tareas"), outputs.get("sg_migrate")
    if not subredes or not grupo:
        raise PrecondicionNoCumplida("INF-1.1: faltan los outputs `subredes_tareas` o `sg_migrate`")
    if isinstance(subredes, str):
        subredes = [s for s in subredes.split(",") if s]
    return {"awsvpcConfiguration": {"subnets": list(subredes), "securityGroups": [grupo], "assignPublicIp": "ENABLED"}}


def _error_aws_tarea(exc: Exception, que: str) -> Exception:
    if es_acceso_denegado(exc):
        return ErrorConfiguracion(f"sin permiso para {que}: {codigo_error_aws(exc)}")
    return Falla(f"{que}: {codigo_error_aws(exc) or _resumen(exc)}")


def lanzar_tarea(
    ecs: Any,
    logs: Any,
    *,
    definicion: str,
    red: dict[str, Any],
    familia: str,
    comando: Sequence[str] | None = None,
    iniciada_por: str = "validacion",
    espera_s: float = ESPERA_TAREA_S,
    dormir: Callable[[float], None] = time.sleep,
    entorno: Mapping[str, str] | None = None,
) -> ResultadoTarea:
    """`ecs run-task` (Fargate) de `definicion` (familia o ARN de una revisión), espera a que pare y lee su log.

    Con `comando`, sobrescribe el del contenedor `app`; con `entorno`, le añade variables (`environment` del
    *override*). Los valores de `entorno` no se imprimen, pero quedan en la descripción de la tarea (`describe-tasks`)
    para quien tenga acceso a la cuenta: solo valores de prueba. `familia` elige el log group y el prefijo de §5.1.
    """
    from botocore.exceptions import ClientError, WaiterError

    peticion: dict[str, Any] = {
        "cluster": CLUSTER,
        "launchType": "FARGATE",
        "taskDefinition": definicion,
        "networkConfiguration": red,
        "count": 1,
        "startedBy": iniciada_por[:36],
    }
    sobrescritura: dict[str, Any] = {"name": CONTENEDOR}
    if comando is not None:
        sobrescritura["command"] = list(comando)
    if entorno:
        sobrescritura["environment"] = [{"name": nombre, "value": valor} for nombre, valor in entorno.items()]
    if len(sobrescritura) > 1:
        peticion["overrides"] = {"containerOverrides": [sobrescritura]}
    try:
        respuesta = ecs.run_task(**peticion)
    except ClientError as exc:
        raise _error_aws_tarea(exc, f"lanzar {definicion.rsplit('/', 1)[-1]}") from None
    tareas = respuesta.get("tasks") or []
    if not tareas:
        fallos = "; ".join(f"{f.get('arn', '')} {f.get('reason', '')}".strip() for f in respuesta.get("failures", []))
        raise Falla(f"run-task no lanzó la tarea ({fallos or 'sin motivo'})")
    arn = tareas[0]["taskArn"]
    try:
        ecs.get_waiter("tasks_stopped").wait(
            cluster=CLUSTER, tasks=[arn], WaiterConfig={"Delay": 6, "MaxAttempts": max(1, int(espera_s // 6))}
        )
    except WaiterError:
        raise Falla(f"la tarea {arn.rsplit('/', 1)[-1]} no se detuvo en {int(espera_s)} s") from None
    descrita = ecs.describe_tasks(cluster=CLUSTER, tasks=[arn])["tasks"][0]
    contenedor = next((c for c in descrita.get("containers", []) if c.get("name") == CONTENEDOR), {})
    resultado = ResultadoTarea(
        arn=arn,
        definicion=descrita.get("taskDefinitionArn", definicion),
        codigo=contenedor.get("exitCode"),
        motivo=contenedor.get("reason") or descrita.get("stoppedReason", ""),
    )
    grupo, prefijo = LOGS_TAREA[familia]
    resultado.lineas = leer_log(logs, grupo, f"{prefijo}/{CONTENEDOR}/{resultado.id}", dormir=dormir)
    return resultado


def leer_log(
    logs: Any,
    grupo: str,
    stream: str,
    *,
    intentos: int = INTENTOS_LOGS,
    pausa_s: float = PAUSA_LOGS_S,
    dormir: Callable[[float], None] = time.sleep,
) -> list[str]:
    """Mensajes de un stream de CloudWatch Logs, desde el principio. El log de una tarea tarda unos segundos en
    aparecer tras detenerse: reintenta mientras el stream no exista o esté vacío. Devuelve [] si nunca aparece."""
    from botocore.exceptions import ClientError

    for intento in range(intentos):
        mensajes: list[str] = []
        token: str | None = None
        try:
            while True:
                argumentos = {"logGroupName": grupo, "logStreamName": stream, "startFromHead": True}
                if token:
                    argumentos["nextToken"] = token
                pagina = logs.get_log_events(**argumentos)
                mensajes += [evento.get("message", "") for evento in pagina.get("events", [])]
                siguiente = pagina.get("nextForwardToken")
                if not siguiente or siguiente == token:
                    break
                token = siguiente
        except ClientError as exc:
            if codigo_error_aws(exc) != "ResourceNotFoundException":
                raise _error_aws_tarea(exc, f"leer {grupo} {stream}") from None
        if mensajes:
            return mensajes
        if intento < intentos - 1:
            dormir(pausa_s)
    return []


# --- API del backend ---------------------------------------------------------------------------------------------
def url_api(outputs: dict[str, Any] | None = None) -> str:
    """URL base con `/v1` (backend §5.11): `VALIDACION_API_URL` o el output `api_base_url` de infra + `/v1`."""
    explicita = os.environ.get("VALIDACION_API_URL", "").strip()
    if explicita:
        return explicita.rstrip("/")
    base = (outputs or {}).get("api_base_url")
    if not base:
        raise PrecondicionNoCumplida("INF-1.4: falta el output `api_base_url`")
    return str(base).rstrip("/") + "/v1"


# --- Secretos y credenciales (BE-1.3) -----------------------------------------------------------------------------
SECRETO_ADMIN = "campus-locator/dev/admin-inicial"
SECRETO_JWT = "campus-locator/dev/jwt"


def leer_secreto(sesion: Any, secreto: str, *, lote: str = "INF-1.2") -> dict[str, Any]:
    """JSON de un secreto de Secrets Manager (infra §5.4). Sin permiso → `ErrorConfiguracion`; no existe o no se
    puede leer → `PrecondicionNoCumplida` del `lote` que lo crea. Nunca imprime el valor."""
    from botocore.exceptions import ClientError

    try:
        texto = sesion.client("secretsmanager").get_secret_value(SecretId=secreto)["SecretString"]
    except ClientError as exc:
        if es_acceso_denegado(exc):
            raise ErrorConfiguracion(f"sin permiso para leer el secreto `{secreto}`: {codigo_error_aws(exc)}") from None
        raise PrecondicionNoCumplida(
            f"{lote}: no se pudo leer el secreto `{secreto}` ({codigo_error_aws(exc)})"
        ) from None
    try:
        datos = json.loads(texto)
    except ValueError:
        raise ErrorConfiguracion(f"el secreto `{secreto}` no es un objeto JSON") from None
    if not isinstance(datos, dict):
        raise ErrorConfiguracion(f"el secreto `{secreto}` no es un objeto JSON")
    return datos


def credenciales_admin(entorno: str, sesion: Any = None) -> tuple[str, str]:
    """`(correo, contraseña)` del admin (backend §5.11): `VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD`; si
    falta alguna y el entorno es `dev`, las claves `correo` y `password` del secreto `admin-inicial`."""
    correo = os.environ.get("VALIDACION_ADMIN_CORREO", "").strip()
    password = os.environ.get("VALIDACION_ADMIN_PASSWORD", "")
    if correo and password:
        return correo, password
    if entorno == "dev" and sesion is not None:
        datos = leer_secreto(sesion, SECRETO_ADMIN)
        correo, password = str(datos.get("correo", "")).strip(), str(datos.get("password", ""))
        if not (correo and password):
            raise ErrorConfiguracion(f"el secreto `{SECRETO_ADMIN}` no tiene las claves `correo` y `password`")
        return correo, password
    raise ErrorConfiguracion("faltan VALIDACION_ADMIN_CORREO y VALIDACION_ADMIN_PASSWORD")


# --- Cliente de la API (BE-1.3) -----------------------------------------------------------------------------------
PAUSA_LOGIN_S = 0.6  # throttling de POST /v1/auth/login en dev: 2 req/s, ráfaga 5 (infra §5.10)
ESPERAS_429_S = (1.0, 2.0, 4.0, 8.0)
#: `500 {"message": "Internal Server Error"}` de API Gateway = `api` sin instancias en Cloud Map (infra §5.13): la
#: petición no llegó al backend y repetirla es seguro. Los 500 del backend (formato §5.1) no se repiten.
ESPERAS_500_GW_S = (2.0, 4.0, 8.0)
TIMEOUT_HTTP_S = 15.0


def es_respuesta_api_gateway(respuesta: Any) -> bool:
    """¿La generó API Gateway (`{"message": …}`, infra §5.13) y no el backend (`{"error": …}`, backend §5.1)?"""
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return False
    return isinstance(cuerpo, dict) and "message" in cuerpo and "error" not in cuerpo


def codigo_error(respuesta: Any) -> str | None:
    """`error.codigo` de una respuesta con el formato del backend (§5.1); `None` si no lo tiene."""
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return None
    error = cuerpo.get("error") if isinstance(cuerpo, dict) else None
    return error.get("codigo") if isinstance(error, dict) else None


def describir_respuesta(respuesta: Any) -> str:
    """`401 CREDENCIALES_INVALIDAS`, `429 (API Gateway)` o `502`: para los detalles, sin el cuerpo."""
    if es_respuesta_api_gateway(respuesta):
        return f"{respuesta.status_code} (API Gateway)"
    codigo = codigo_error(respuesta)
    return f"{respuesta.status_code} {codigo}" if codigo else str(respuesta.status_code)


class ClienteApi:
    """Peticiones a la API del backend con los reintentos que exige `dev` (backend §5.11).

    - `pedir(metodo, ruta, token=None, **kwargs)`: `ruta` relativa a la URL base con `/v1` (p. ej. `/auth/login`);
      con `token`, añade `Authorization: Bearer`. Un `429` **de API Gateway** se reintenta tras 1, 2, 4 y 8 s, y un
      `500` **de API Gateway** (sin instancias de `api`) tras 2, 4 y 8 s; los del backend (formato §5.1), no. Devuelve
      la respuesta de httpx (la última, si los reintentos se agotan). `ultima_duracion_ms` es lo que tardó el último
      intento; `reintentos_429` y `reintentos_500` cuentan los repetidos.
    - `login(correo, password)`: `POST /auth/login`, con al menos `PAUSA_LOGIN_S` entre dos logins (el throttling de
      esa ruta en dev es de 2 req/s). `logins_ok` y `logins_fallidos` cuentan los 200 y los 401.
    - `token(correo, password, quien=…)`: el `token` de un login con 200, o `Falla` con el código recibido.
    Nunca imprime tokens, contraseñas ni cuerpos.
    """

    def __init__(
        self,
        url_base: str,
        *,
        http: Any = None,
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self.url_base = url_base.rstrip("/")
        self._http = http
        self.dormir = dormir
        self.reloj = reloj
        self._ultimo_login: float | None = None
        self.reintentos_429 = 0
        self.reintentos_500 = 0
        self.ultima_duracion_ms: int | None = None
        self.logins_ok = 0
        self.logins_fallidos = 0

    @property
    def http(self) -> Any:
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=TIMEOUT_HTTP_S, follow_redirects=False)
        return self._http

    def pedir(self, metodo: str, ruta: str, *, token: str | None = None, **kwargs: Any) -> Any:
        encabezados = dict(kwargs.pop("headers", None) or {})
        if token is not None:
            encabezados["Authorization"] = f"Bearer {token}"
        esperas = {429: list(ESPERAS_429_S), 500: list(ESPERAS_500_GW_S)}
        while True:
            inicio = self.reloj()
            respuesta = self.http.request(metodo, f"{self.url_base}{ruta}", headers=encabezados, **kwargs)
            self.ultima_duracion_ms = int((self.reloj() - inicio) * 1000)
            pendientes = esperas.get(respuesta.status_code)
            if pendientes and es_respuesta_api_gateway(respuesta):
                if respuesta.status_code == 429:
                    self.reintentos_429 += 1
                else:
                    self.reintentos_500 += 1
                self.dormir(pendientes.pop(0))
                continue
            return respuesta

    def login(self, correo: str, password: str) -> Any:
        if self._ultimo_login is not None:
            espera = self._ultimo_login + PAUSA_LOGIN_S - self.reloj()
            if espera > 0:
                self.dormir(espera)
        try:
            respuesta = self.pedir("POST", "/auth/login", json={"identificador": correo, "password": password})
        finally:
            self._ultimo_login = self.reloj()
        if respuesta.status_code == 200:
            self.logins_ok += 1
        elif respuesta.status_code == 401:
            self.logins_fallidos += 1
        return respuesta

    def token(self, correo: str, password: str, *, quien: str = "el usuario") -> str:
        respuesta = self.login(correo, password)
        if respuesta.status_code == 404:
            raise Falla(f"POST /v1/auth/login respondió 404: ¿está desplegado BE-1.3? (login de {quien})")
        if respuesta.status_code != 200:
            raise Falla(f"el login de {quien} respondió {describir_respuesta(respuesta)}")
        token = respuesta.json().get("token")
        if not isinstance(token, str) or not token:
            raise Falla(f"el login de {quien} respondió 200 sin `token`")
        return token

    def cerrar(self) -> None:
        if self._http is not None:
            self._http.close()


# --- Comandos de la CLI y SQL en local o dev (BE-1.3) ---------------------------------------------------------------
SERVICIO_API = "api"
CLI_COMPOSE = ["docker", "compose", "run", "--rm", "-T"]
PSQL_COMPOSE = ["docker", "compose", "exec", "-T", "db", "psql", "-U", "campus_app", "-d", "campus_locator", "-tAc"]
#: Eventos de la CLI (§5.10) que explican un código distinto de 0, en orden de preferencia.
EVENTOS_DE_FALLO = (
    "base_no_disponible",
    "configuracion_incompleta",
    "comando_fallido",
    "usuario_rechazado",
    "usuario_no_encontrado",
    "migracion_fallida",
    "verificacion_fallida",
)


def motivo_cli(resultado: ResultadoTarea) -> str:
    """Por qué un `python -m app.cli` no terminó con 0, a partir de sus eventos (sin secretos)."""
    for nombre in EVENTOS_DE_FALLO:
        for evento in resultado.eventos(nombre):
            extra = evento.get("motivo") or ", ".join(evento.get("faltan", []))
            return f"{nombre}: {extra}".rstrip(": ")[:300]
    if resultado.codigo is None:
        return f"la tarea no llegó a ejecutar el contenedor ({resultado.motivo or 'sin motivo'})"
    return resultado.motivo[:300] if resultado.motivo else "sin eventos en el log"


class EntornoBackend:
    """`python -m app.cli …` y consultas SQL de solo lectura en el entorno del validador (backend §5.11).

    - `local`: `docker compose run --rm -T [-e VAR…] api python -m app.cli …` y `docker compose exec -T db psql …`,
      desde `project/` (el compose tiene que estar levantado).
    - `dev`: tarea suelta con la última revisión de `campus-locator-dev-migrate` (que tiene que llevar la misma imagen
      que el servicio `api`: si no, `Falla`, porque `backend.yml` no terminó) y, para SQL, con
      `campus-locator-dev-validacion` (`psql -tAc`).

    `cli(argumentos, entorno=None)` devuelve un `ResultadoTarea` (`codigo`, `lineas`, `eventos()`); los valores de
    `entorno` llegan al proceso sin pasar por la línea de comandos en local y como `environment` del *override* en
    dev. `sql(consulta)` devuelve las líneas de `psql` o lanza `Falla` si `psql` no termina con 0.
    """

    def __init__(
        self,
        entorno: str,
        *,
        sesion: Any = None,
        outputs: Callable[[], dict[str, Any]] | None = None,
        iniciada_por: str = "validacion",
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.entorno = entorno
        self.sesion = sesion
        self._outputs = outputs or outputs_terraform
        self.iniciada_por = iniciada_por
        self.dormir = dormir
        self._clientes: dict[str, Any] = {}
        self._revision_migrate: str | None = None

    def aws(self, servicio: str) -> Any:
        if servicio not in self._clientes:
            self._clientes[servicio] = self.sesion.client(servicio)
        return self._clientes[servicio]

    def imagen(self, definicion: str) -> tuple[str, str]:
        """(ARN de la revisión, imagen del contenedor `app`) de una familia o revisión."""
        datos = self.aws("ecs").describe_task_definition(taskDefinition=definicion)["taskDefinition"]
        contenedores = {c.get("name"): c for c in datos.get("containerDefinitions", [])}
        exigir(CONTENEDOR in contenedores, f"{definicion} no tiene contenedor `{CONTENEDOR}`")
        return datos["taskDefinitionArn"], contenedores[CONTENEDOR].get("image", "")

    def revision_migrate(self) -> str:
        if self._revision_migrate is None:
            arn, imagen = self.imagen(FAMILIA_MIGRATE)
            servicios = self.aws("ecs").describe_services(cluster=CLUSTER, services=[SERVICIO_API])["services"]
            exigir(servicios, f"el servicio `{SERVICIO_API}` no aparece en `{CLUSTER}`")
            desplegada = self.imagen(servicios[0]["taskDefinition"])[1]
            exigir(
                imagen == desplegada,
                f"{arn.rsplit('/', 1)[-1]} y el servicio `api` usan imágenes distintas: ¿terminó backend.yml en main?",
            )
            self._revision_migrate = arn
        return self._revision_migrate

    def cli(self, argumentos: Sequence[str], *, entorno: Mapping[str, str] | None = None) -> ResultadoTarea:
        comando = ["python", "-m", "app.cli", *argumentos]
        if self.entorno == "local":
            variables = [parte for nombre in (entorno or {}) for parte in ("-e", nombre)]
            proceso = ejecutar_proceso(
                [*CLI_COMPOSE, *variables, SERVICIO_API, *comando], cwd=RAIZ_PROYECTO, entorno=entorno
            )
            error = [linea for linea in proceso.stderr.splitlines() if linea.strip()]
            return ResultadoTarea(
                arn="local",
                definicion="docker compose",
                codigo=proceso.returncode,
                motivo=error[-1].strip() if error else "",
                lineas=proceso.stdout.splitlines(),
            )
        return lanzar_tarea(
            self.aws("ecs"),
            self.aws("logs"),
            definicion=self.revision_migrate(),
            red=red_tareas(self._outputs()),
            familia=FAMILIA_MIGRATE,
            comando=comando,
            iniciada_por=self.iniciada_por,
            dormir=self.dormir,
            entorno=entorno,
        )

    def sql(self, consulta: str) -> list[str]:
        if self.entorno == "local":
            proceso = ejecutar_proceso([*PSQL_COMPOSE, consulta], cwd=RAIZ_PROYECTO)
            codigo, lineas, motivo = proceso.returncode, proceso.stdout.splitlines(), proceso.stderr
        else:
            resultado = lanzar_tarea(
                self.aws("ecs"),
                self.aws("logs"),
                definicion=FAMILIA_VALIDACION,
                red=red_tareas(self._outputs()),
                familia=FAMILIA_VALIDACION,
                comando=["psql", "-tAc", consulta],
                iniciada_por=self.iniciada_por,
                dormir=self.dormir,
            )
            codigo, lineas, motivo = resultado.codigo, resultado.lineas, resultado.motivo
        if codigo != 0:
            texto = [linea.strip() for linea in (motivo or "\n".join(lineas)).splitlines() if linea.strip()]
            raise Falla(f"psql terminó con {codigo}: {(texto[-1] if texto else 'sin salida')[:200]}")
        return lineas


# --- Usuario de prueba `validacion+user@campus.edu.co` (backend §5.11) ------------------------------------------------
USUARIO_VALIDACION = "validacion+user@campus.edu.co"
NOMBRE_USUARIO_VALIDACION = "validacion-usuario"


def crear_usuario_validacion(backend: EntornoBackend) -> str:
    """Crea o reactiva el usuario de prueba (rol `user`) con una contraseña aleatoria `validacion-pw-<uuid>`, que pasa
    en `CREAR_USUARIO_PASSWORD` y devuelve (nunca se imprime). `Falla` si `crear-usuario` no termina con 0."""
    import uuid

    password = f"validacion-pw-{uuid.uuid4()}"
    resultado = backend.cli(
        ["crear-usuario", "--correo", USUARIO_VALIDACION, "--nombre", NOMBRE_USUARIO_VALIDACION, "--rol", "user"],
        entorno={"CREAR_USUARIO_PASSWORD": password},
    )
    if resultado.codigo != 0:
        raise Falla(f"crear-usuario terminó con {resultado.codigo}: {motivo_cli(resultado)}")
    return password


def desactivar_usuario_validacion(backend: EntornoBackend, *, tolerar_inexistente: bool = False) -> str:
    """`desactivar-usuario` del usuario de prueba; devuelve un detalle corto o lanza `Falla`.

    Con `tolerar_inexistente` (la limpieza), que el usuario no exista (código 1 con `usuario_no_encontrado`: el
    `crear-usuario` falló antes de crearlo) no es un fallo."""
    resultado = backend.cli(["desactivar-usuario", "--correo", USUARIO_VALIDACION])
    if tolerar_inexistente and resultado.codigo == 1 and resultado.eventos("usuario_no_encontrado"):
        return f"{USUARIO_VALIDACION} no existe: nada que desactivar"
    if resultado.codigo != 0:
        raise Falla(f"desactivar-usuario terminó con {resultado.codigo}: {motivo_cli(resultado)}")
    evento = next(iter(resultado.eventos("usuario_desactivado")), {})
    previo = " (ya lo estaba)" if evento.get("ya_estaba_inactivo") else ""
    return f"{USUARIO_VALIDACION} desactivado{previo}"
