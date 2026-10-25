"""Ayudas comunes de los validadores de la app (FRONTEND_KOTLIN).

Contrato común: INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md §5.11. Lo propio de la app y la tabla de esta API:
FRONTEND_KOTLIN/docs/ARCHITECTURE.md §5.11. Si algo cambia aquí, esa tabla se actualiza en el mismo cambio.

Solo biblioteca estándar. Nunca imprime secretos, tokens ni URLs prefirmadas.
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
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# --- Constantes -------------------------------------------------------------------------------------------------

PROYECTO = Path(__file__).resolve().parents[2]  # FRONTEND_KOTLIN/project/
RAIZ_REPO = PROYECTO.parents[1]
DIR_INFORMES = PROYECTO / ".validacion"
DIR_TF_DEV = RAIZ_REPO / "INFRASTRUCTURA_TERRAFORM" / "project" / "envs" / "dev"
API_CONFIG = PROYECTO / "app" / "src" / "main" / "java" / "com" / "example" / "myapplication" / "ApiConfig.kt"
DIR_RESULTADOS_PRUEBAS = PROYECTO / "app" / "build" / "test-results" / "testDebugUnitTest"
PAQUETE = "com.example.myapplication"
ACTIVIDAD = f"{PAQUETE}/.MainActivity"
LOG_APP = "files/logs/app.log"  # relativo a los datos privados de la app (run-as)
ENTORNOS = ("local", "dev")

# --- Excepciones que deciden el código de salida ---------------------------------------------------------------


class Falla(Exception):  # noqa: N818 — nombres del contrato común
    """La comprobación no pasa (código 1). En una precondición, también cuenta como bloqueo (2)."""


class Bloqueo(Exception):  # noqa: N818
    """Otro lote no está listo (código 2)."""


class ErrorConfiguracion(Exception):
    """Falta una herramienta, variable, dispositivo o credencial (código 3)."""


# --- Utilidades ------------------------------------------------------------------------------------------------


def avisar(mensaje: str) -> None:
    """Progreso a stderr (stdout queda para las líneas `[PASA] …`)."""
    print(f"· {mensaje}", file=sys.stderr, flush=True)


def resumir(texto: str, limite: int = 300) -> str:
    texto = " ".join((texto or "").split())
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


@dataclass
class Resultado:
    codigo: int
    salida: str
    error: str

    @property
    def texto(self) -> str:
        return (self.salida + "\n" + self.error).strip()


def ejecutar(
    comando: list[str],
    *,
    entrada: str | None = None,
    timeout: int = 300,
    cwd: Path | None = None,
    entorno: dict[str, str] | None = None,
) -> Resultado:
    """Ejecuta un programa (lista de argumentos) desde `project/` sin imprimir nada.

    Si no está instalado → ErrorConfiguracion. Si no termina en `timeout` s → Falla.
    """
    env = dict(os.environ)
    env.update({"TF_IN_AUTOMATION": "1", "TF_INPUT": "0", "NO_COLOR": "1", "GH_PAGER": "", "PAGER": "cat"})
    if entorno:
        env.update(entorno)
    try:
        r = subprocess.run(
            comando,
            input=entrada,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(cwd or PROYECTO),
            env=env,
            check=False,
        )
    except FileNotFoundError as e:
        raise ErrorConfiguracion(f"no se encontró el programa {comando[0]!r}") from e
    except subprocess.TimeoutExpired as e:
        raise Falla(f"{' '.join(comando[:3])}… no terminó en {timeout} s") from e
    return Resultado(r.returncode, r.stdout or "", r.stderr or "")


def commit_actual() -> str:
    """Commit corto de HEAD, con `-dirty` si hay cambios sin commit en archivos versionados de `project/`.

    `core.autocrlf=input`: la copia de trabajo la sacó el Git de Windows (`autocrlf=true`, archivos con CRLF) y el Git
    de WSL, sin esa opción, vería todos esos archivos como modificados.
    """
    r = ejecutar(["git", "rev-parse", "--short", "HEAD"])
    if r.codigo != 0:
        return "desconocido"
    sucio = ejecutar(["git", "-c", "core.autocrlf=input", "status", "--porcelain", "--untracked-files=no", "--", "."])
    return r.salida.strip() + ("-dirty" if sucio.salida.strip() else "")


# --- URL de la API ---------------------------------------------------------------------------------------------

_PATRON_API_BASE = re.compile(r'const\s+val\s+API_BASE_URL\s*=\s*"([^"]*)"')
_PATRON_BASE = re.compile(r'const\s+val\s+BASE_URL\s*=\s*"([^"]*)"')


def url_api_config(ruta: Path = API_CONFIG) -> str:
    """URL base que usa la app (`ApiConfig.BASE_URL`, con `/v1`), leída del código fuente.

    Exige la forma de FE-1.1: `API_BASE_URL = "https://…"` y `BASE_URL = "$API_BASE_URL/v1"` (o una URL literal).
    Si no tiene esa forma → Falla.
    """
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError as e:
        raise Falla(f"no se pudo leer {ruta.name}: {e}") from e
    base = _PATRON_BASE.search(texto)
    if not base:
        raise Falla(f"{ruta.name} no define const val BASE_URL")
    valor = base.group(1)
    if "$API_BASE_URL" in valor or "${API_BASE_URL}" in valor:
        api_base = _PATRON_API_BASE.search(texto)
        if not api_base:
            raise Falla(f"{ruta.name}: BASE_URL usa API_BASE_URL, pero no está definida")
        valor = valor.replace("${API_BASE_URL}", api_base.group(1)).replace("$API_BASE_URL", api_base.group(1))
    if "$" in valor:
        raise Falla(f"{ruta.name}: BASE_URL tiene una plantilla que el validador no sabe resolver: {valor}")
    return valor


def normalizar_url(url: str) -> str:
    return url.strip().rstrip("/")


def comprobar_forma_url(url: str, origen: str) -> str:
    """`https://…/v1` sin barra final; si no → ErrorConfiguracion (es una variable o un output mal puesto)."""
    u = normalizar_url(url)
    if not u.startswith("https://") or not u.endswith("/v1"):
        raise ErrorConfiguracion(f"{origen} debe empezar por https:// y terminar en /v1 (es {u!r})")
    return u


def terraform_output_raw(nombre: str, directorio: Path = DIR_TF_DEV) -> str:
    """`terraform -chdir=<directorio> output -raw <nombre>` (una lectura del estado; no cambia nada).

    Sin terraform, sin `init` o sin credenciales → ErrorConfiguracion. El valor no se imprime aquí.
    """
    if not directorio.is_dir():
        raise ErrorConfiguracion(f"no existe {directorio}")
    r = ejecutar(["terraform", f"-chdir={directorio}", "output", "-raw", nombre], timeout=120)
    if r.codigo != 0:
        raise ErrorConfiguracion(f"terraform output -raw {nombre} falló: {resumir(r.error or r.salida, 200)}")
    valor = r.salida.strip()
    if not valor:
        raise ErrorConfiguracion(f"el output {nombre} está vacío")
    return valor


def url_api_vigente() -> tuple[str, str]:
    """URL base vigente con `/v1` y de dónde salió: el output `api_base_url` + `/v1`, o `VALIDACION_API_URL`.

    Terraform manda (es la fuente de verdad, infra §5.2); `VALIDACION_API_URL` solo se usa si Terraform no está
    disponible. Ninguna de las dos → ErrorConfiguracion.
    """
    try:
        base = terraform_output_raw("api_base_url")
        return comprobar_forma_url(normalizar_url(base) + "/v1", "api_base_url + /v1"), "terraform output api_base_url"
    except ErrorConfiguracion as e_tf:
        variable = os.environ.get("VALIDACION_API_URL", "").strip()
        if variable:
            return comprobar_forma_url(variable, "VALIDACION_API_URL"), "VALIDACION_API_URL"
        raise ErrorConfiguracion(f"sin URL de la API: {e_tf}; define VALIDACION_API_URL") from e_tf


@dataclass
class RespuestaHttp:
    estado: int
    encabezados: dict[str, str]
    cuerpo: str
    duracion_ms: int

    def json(self) -> object:
        try:
            return json.loads(self.cuerpo)
        except ValueError:
            return None


class ErrorRed(Exception):
    """No hubo respuesta HTTP: DNS, TLS, conexión o tiempo agotado."""


def http_get(url: str, *, timeout: float = 15.0) -> RespuestaHttp:
    """`GET` con `X-Request-Id` propio (como la app). Una respuesta 4xx/5xx se devuelve; sin respuesta → ErrorRed."""
    peticion = urllib.request.Request(url, headers={"X-Request-Id": str(uuid.uuid4()), "User-Agent": "validacion-app"})
    inicio = time.monotonic()
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as r:  # noqa: S310 — URL https comprobada
            cuerpo = r.read().decode("utf-8", errors="replace")
            return RespuestaHttp(r.status, dict(r.headers.items()), cuerpo, _ms(inicio))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", errors="replace")
        return RespuestaHttp(e.code, dict(e.headers.items()), cuerpo, _ms(inicio))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        motivo = getattr(e, "reason", e)
        raise ErrorRed(f"{type(motivo).__name__}: {resumir(str(motivo), 150)}") from e


def _ms(inicio: float) -> int:
    return int((time.monotonic() - inicio) * 1000)


# --- Gradle y pruebas unitarias --------------------------------------------------------------------------------


def comando_gradle() -> list[str]:
    """Cómo invocar Gradle.

    `VALIDACION_GRADLE` (separado por espacios; p. ej. `cmd.exe /c .\\gradlew.bat` desde WSL), si no `gradlew.bat`
    en Windows y `bash gradlew` en el resto (el wrapper no tiene el bit de ejecución en Git).
    """
    propio = os.environ.get("VALIDACION_GRADLE", "").strip()
    if propio:
        return propio.split()
    if os.name == "nt":
        return ["cmd", "/c", "gradlew.bat"]
    return ["bash", "gradlew"]


def gradle(*argumentos: str, timeout: int = 1800) -> Resultado:
    return ejecutar([*comando_gradle(), "--console=plain", *argumentos], timeout=timeout)


@dataclass
class ResultadoClase:
    clase: str
    pruebas: int
    fallos: int
    errores: int
    omitidas: int

    @property
    def ok(self) -> bool:
        return self.pruebas >= 1 and self.fallos == 0 and self.errores == 0


def archivo_resultados(clase: str, directorio: Path | None = None) -> Path | None:
    """`TEST-<paquete>.<clase>.xml` de una clase de prueba (por nombre simple), o None."""
    directorio = directorio or DIR_RESULTADOS_PRUEBAS
    candidatos = sorted(directorio.glob(f"TEST-*.{clase}.xml")) if directorio.is_dir() else []
    return candidatos[0] if candidatos else None


def resultados_clase(clase: str, directorio: Path | None = None) -> ResultadoClase | None:
    """Lee el XML JUnit que escribe `testDebugUnitTest` para una clase; None si no existe."""
    archivo = archivo_resultados(clase, directorio)
    if archivo is None:
        return None
    raiz = ET.parse(archivo).getroot()
    return ResultadoClase(
        clase=clase,
        pruebas=int(raiz.get("tests", "0")),
        fallos=int(raiz.get("failures", "0")),
        errores=int(raiz.get("errors", "0")),
        omitidas=int(raiz.get("skipped", "0")),
    )


def borrar_resultados(clases: list[str], directorio: Path | None = None) -> None:
    """Borra los XML de esas clases para no leer los de una ejecución anterior (y obligar a Gradle a repetirlas)."""
    for clase in clases:
        archivo = archivo_resultados(clase, directorio)
        if archivo is not None:
            archivo.unlink()


# --- adb y dispositivo -----------------------------------------------------------------------------------------


def comando_adb() -> list[str]:
    """`VALIDACION_ADB` (p. ej. el `adb.exe` de Windows desde WSL), `adb` del PATH o `$ANDROID_HOME/platform-tools`."""
    propio = os.environ.get("VALIDACION_ADB", "").strip()
    if propio:
        return propio.split()
    encontrado = shutil.which("adb")
    if encontrado:
        return [encontrado]
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk = os.environ.get(variable)
        if sdk:
            for nombre in ("adb", "adb.exe"):
                ruta = Path(sdk) / "platform-tools" / nombre
                if ruta.is_file():
                    return [str(ruta)]
    raise ErrorConfiguracion("no se encontró adb: ponlo en el PATH o define VALIDACION_ADB")


def adb(*argumentos: str, timeout: int = 120) -> Resultado:
    """adb contra el dispositivo de `ANDROID_SERIAL` si está definida (si no, el único conectado)."""
    serial = os.environ.get("ANDROID_SERIAL", "").strip()
    prefijo = ["-s", serial] if serial else []
    return ejecutar([*comando_adb(), *prefijo, *argumentos], timeout=timeout)


def dispositivos(texto_adb_devices: str) -> list[tuple[str, str]]:
    """`[(serial, estado)]` a partir de la salida de `adb devices`."""
    lista = []
    for linea in texto_adb_devices.splitlines()[1:]:
        partes = linea.split()
        if len(partes) >= 2:
            lista.append((partes[0], partes[1]))
    return lista


def dispositivo_fisico() -> str:
    """Serial del dispositivo físico listo, o ErrorConfiguracion (sin dispositivo, varios sin `ANDROID_SERIAL`,
    estado distinto de `device` o un emulador)."""
    r = ejecutar([*comando_adb(), "devices"], timeout=60)
    if r.codigo != 0:
        raise ErrorConfiguracion(f"adb devices falló: {resumir(r.texto, 200)}")
    lista = dispositivos(r.salida)
    serial = os.environ.get("ANDROID_SERIAL", "").strip()
    if serial:
        lista = [d for d in lista if d[0] == serial]
        if not lista:
            raise ErrorConfiguracion(f"ANDROID_SERIAL={serial} no aparece en adb devices")
    if not lista:
        raise ErrorConfiguracion("adb devices no muestra ningún dispositivo")
    if len(lista) > 1:
        raise ErrorConfiguracion("hay varios dispositivos: define ANDROID_SERIAL")
    serial, estado = lista[0]
    if estado != "device":
        raise ErrorConfiguracion(f"el dispositivo está en estado {estado!r} (¿autorizaste la depuración USB?)")
    qemu = adb("shell", "getprop", "ro.kernel.qemu", timeout=30).salida.strip()
    if qemu == "1":
        raise ErrorConfiguracion("el dispositivo es un emulador: los lotes de la app se validan en uno físico")
    return serial


def leer_archivo_app(ruta_relativa: str) -> str | None:
    """Contenido de un archivo privado de la app (`run-as`, solo APK de depuración), o None si no existe."""
    r = adb("exec-out", "run-as", PAQUETE, "cat", ruta_relativa, timeout=60)
    if r.codigo != 0:
        return None
    return r.salida


# --- Validador -------------------------------------------------------------------------------------------------


@dataclass
class _Entrada:
    id: str
    estado: str
    detalle: str = ""
    duracion_ms: int | None = None


@dataclass
class Validador:
    """Ciclo de vida de un validador (contrato común, infra §5.11). Uso: `sys.exit(Validador(...).correr(cuerpo))`."""

    lote: str
    validacion: str
    descripcion: str
    comprobaciones: list[str]
    entornos: tuple[str, ...] = ENTORNOS
    grupos: dict[str, list[str]] = field(default_factory=dict)
    # Estado de la ejecución
    entorno: str = ""
    sello: str = ""
    _solo: set[str] | None = None
    _sin_limpieza: bool = False
    _informe: Path | None = None
    _precondiciones: list[_Entrada] = field(default_factory=list)
    _comprobaciones: list[_Entrada] = field(default_factory=list)
    _manuales: list[dict[str, str]] = field(default_factory=list)
    _limpiezas: list[tuple[str, Callable[[], object]]] = field(default_factory=list)
    _codigo_pre: int = 0

    # --- argumentos

    def _leer_argumentos(self, argv: list[str] | None) -> None:
        p = argparse.ArgumentParser(description=self.descripcion, formatter_class=argparse.RawDescriptionHelpFormatter)
        p.add_argument("--entorno", required=True, choices=ENTORNOS)
        p.add_argument("--informe", type=Path, default=None)
        p.add_argument("--solo", default=None, help="IDs separados por comas: " + ", ".join(self.comprobaciones))
        p.add_argument("--sin-limpieza", action="store_true")
        a = p.parse_args(argv)
        if a.entorno not in self.entornos:
            raise ErrorConfiguracion(f"{self.lote} no admite --entorno {a.entorno} (admite {', '.join(self.entornos)})")
        self.entorno = a.entorno
        self._informe = a.informe
        self._sin_limpieza = a.sin_limpieza
        if a.solo:
            pedidos = [s.strip() for s in a.solo.split(",") if s.strip()]
            solo: set[str] = set()
            for s in pedidos:
                if s in self.grupos:
                    solo.update(self.grupos[s])
                elif s in self.comprobaciones:
                    solo.add(s)
                else:
                    raise ErrorConfiguracion(f"--solo {s}: no existe (válidos: {', '.join(self.comprobaciones)})")
            self._solo = solo

    # --- API para el cuerpo

    def incluida(self, id_: str) -> bool:
        return self._solo is None or id_ in self._solo

    def alguna_incluida(self, *ids: str) -> bool:
        return any(self.incluida(i) for i in ids)

    def precondicion(self, id_: str, fn: Callable[[], str]) -> bool:
        try:
            detalle = fn()
            self._anotar(self._precondiciones, _Entrada(id_, "pasa", detalle or ""))
            return True
        except (Bloqueo, Falla) as e:
            self._codigo_pre = max(self._codigo_pre, 2)
            self._anotar(self._precondiciones, _Entrada(id_, "falla", str(e)))
        except ErrorConfiguracion as e:
            self._codigo_pre = 3
            self._anotar(self._precondiciones, _Entrada(id_, "falla", str(e)))
        return False

    def precondicion_no_evaluada(self, id_: str, motivo: str) -> None:
        self._anotar(self._precondiciones, _Entrada(id_, "no evaluada", motivo))

    def precondiciones_cumplidas(self) -> bool:
        return self._codigo_pre == 0

    def comprobacion(self, id_: str, fn: Callable[[], str]) -> None:
        if not self.incluida(id_):
            self._anotar(self._comprobaciones, _Entrada(id_, "omitida", "excluida con --solo"))
            return
        inicio = time.monotonic()
        try:
            detalle = fn()
            entrada = _Entrada(id_, "pasa", detalle or "")
        except Falla as e:
            entrada = _Entrada(id_, "falla", str(e))
        except ErrorConfiguracion as e:
            entrada = _Entrada(id_, "error", str(e))
        except Exception as e:  # noqa: BLE001 — cualquier imprevisto es código 3, con su traza en stderr
            traceback.print_exc(file=sys.stderr)
            entrada = _Entrada(id_, "error", f"error inesperado: {type(e).__name__}: {resumir(str(e), 200)}")
        entrada.duracion_ms = _ms(inicio)
        self._anotar(self._comprobaciones, entrada)

    def omitir(self, id_: str, motivo: str) -> None:
        """Comprobación que no aplica en este entorno (p. ej. la que necesita dispositivo en `local`)."""
        self._anotar(self._comprobaciones, _Entrada(id_, "omitida", motivo))

    def manual(self, id_: str, instruccion: str) -> None:
        self._manuales.append({"id": id_, "instruccion": instruccion})
        print(f"[MANUAL] {id_} {instruccion}", flush=True)

    def al_limpiar(self, descripcion: str, fn: Callable[[], object]) -> None:
        self._limpiezas.append((descripcion, fn))

    # --- ciclo

    def correr(self, cuerpo: Callable[[Validador], None], argv: list[str] | None = None) -> int:
        inicio = datetime.now(UTC)
        self.sello = inicio.strftime("%Y%m%d-%H%M%S")
        try:
            self._leer_argumentos(argv)
        except SystemExit as e:  # argparse: --help (0) o error de uso (2 → 3)
            return 0 if e.code == 0 else 3
        except ErrorConfiguracion as e:
            print(f"[ERROR] {e}", flush=True)
            return 3
        error_cuerpo = None
        try:
            cuerpo(self)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            error_cuerpo = f"{type(e).__name__}: {resumir(str(e), 200)}"
            print(f"[ERROR] {error_cuerpo}", flush=True)
        finally:
            self._limpiar()
        codigo = self._codigo(error_cuerpo)
        self._escribir_informe(inicio, codigo)
        return codigo

    def _limpiar(self) -> None:
        if self._sin_limpieza:
            if self._limpiezas:
                avisar("--sin-limpieza: no se limpia")
            return
        for descripcion, fn in reversed(self._limpiezas):
            try:
                fn()
                avisar(f"limpieza: {descripcion}")
            except Exception as e:  # noqa: BLE001
                print(f"[LIMPIEZA] falló {descripcion}: {resumir(str(e), 200)}", flush=True)

    def _codigo(self, error_cuerpo: str | None) -> int:
        if error_cuerpo is not None or self._codigo_pre == 3:
            return 3
        if self._codigo_pre == 2:
            return 2
        estados = {c.estado for c in self._comprobaciones}
        if "error" in estados:
            return 3
        if "falla" in estados:
            return 1
        return 0

    def _anotar(self, lista: list[_Entrada], entrada: _Entrada) -> None:
        lista.append(entrada)
        etiqueta = {"pasa": "PASA", "falla": "FALLA", "error": "ERROR", "omitida": "OMITIDA"}.get(
            entrada.estado, entrada.estado.upper()
        )
        print(f"[{etiqueta}] {entrada.id} {entrada.detalle}".rstrip(), flush=True)

    def _escribir_informe(self, inicio: datetime, codigo: int) -> None:
        resultado = {0: "pasa", 1: "falla", 2: "bloqueado"}.get(codigo, "error")
        datos = {
            "lote": self.lote,
            "validacion": self.validacion,
            "entorno": self.entorno,
            "commit": commit_actual(),
            "inicio": inicio.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fin": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "resultado": resultado,
            "precondiciones": [{"id": p.id, "estado": p.estado, "detalle": p.detalle} for p in self._precondiciones],
            "comprobaciones": [
                {"id": c.id, "estado": c.estado, "detalle": c.detalle, "duracion_ms": c.duracion_ms}
                for c in self._comprobaciones
            ],
            "manuales": self._manuales,
        }
        ruta = self._informe or DIR_INFORMES / f"{self.lote}-{self.sello}.json"
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            avisar(f"informe: {ruta}")
        except OSError as e:
            print(f"[ERROR] no se pudo escribir el informe: {e}", flush=True)
        print(f"Resultado: {resultado} (código {codigo})", flush=True)
