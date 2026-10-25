"""Conjunto de evaluación (`puntos.json`, ARCHITECTURE §5.9): carga, validación y cobertura.

Solo biblioteca estándar: lo usan la herramienta y `src/ops/validate32.py` (C1).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

RADIO_TIERRA_M = 6_371_008.8  # radio medio (el mismo que la validación de BE-3.2)
HORAS = ("manana", "tarde", "noche")
BOGOTA = timezone(timedelta(hours=-5))  # Colombia no tiene horario de verano
DATASET_CERCA_M = (
    30.0  # «punto con dataset»: alguna imagen del dataset a ≤ 30 m (validation-3-2 C1)
)
LEJOS_M = 150.0  # «punto lejano»: toda imagen del dataset a > 150 m (BE-3.2 C5)
FOTOS_MIN = 50  # PLAN EMB-3.2 C1
PUNTOS_CON_DATASET_MIN = 10
FOTOS_PUNTO_LEJANO_MIN = 3
PATRON_VERSION = re.compile(r"^\d{4}-\d{2}[a-z]$")  # 2026-11a
PATRON_PUNTO = re.compile(r"^P\d{2,3}$")  # P01
PATRON_ARCHIVO = re.compile(r"^fotos/(P\d{2,3})/(\d+)\.jpg$")


@dataclass(frozen=True)
class Punto:
    id: str
    lat: float
    lng: float
    descripcion: str = ""


@dataclass(frozen=True)
class Foto:
    archivo: str
    punto: str
    rumbo: float | None
    capturada_en: str
    hora: str
    vuelta: int | None = None


@dataclass
class Conjunto:
    version_conjunto: str
    creado_en: str
    puntos: dict[str, Punto]
    fotos: list[Foto]
    directorio: Path | None = None

    def fotos_de(self, punto: str) -> list[Foto]:
        return [f for f in self.fotos if f.punto == punto]


@dataclass
class Revision:
    errores: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.errores


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia en metros sobre la esfera de radio medio (WGS84 tratado como esfera)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_M * math.asin(min(1.0, math.sqrt(a)))


def franja(instante: datetime) -> str:
    """Franja de `hora` según la hora de Bogotá: 05–11 mañana, 12–17 tarde, el resto noche."""
    local = instante.astimezone(BOGOTA)
    if 5 <= local.hour < 12:
        return "manana"
    if 12 <= local.hour < 18:
        return "tarde"
    return "noche"


def leer_fecha(texto: str) -> datetime:
    """ISO-8601 en UTC con `Z` (convenciones de backend §5.1); `ValueError` si no lo es."""
    if not isinstance(texto, str) or not texto.endswith("Z"):
        raise ValueError(f"{texto!r} no es una fecha UTC con Z")
    return datetime.fromisoformat(texto[:-1] + "+00:00")


def _numero(valor) -> bool:
    return isinstance(valor, int | float) and not isinstance(valor, bool) and math.isfinite(valor)


def revisar(datos: dict) -> Revision:
    """Estructura de `puntos.json` (§5.9). No mira archivos ni el dataset."""
    r = Revision()
    if not isinstance(datos, dict):
        r.errores.append("puntos.json no es un objeto JSON")
        return r
    version = datos.get("version_conjunto")
    if not isinstance(version, str) or not PATRON_VERSION.match(version):
        r.errores.append(f"version_conjunto={version!r}: se espera AAAA-MM<letra> (2026-11a)")
    try:
        leer_fecha(datos.get("creado_en"))
    except (TypeError, ValueError):
        r.errores.append(f"creado_en={datos.get('creado_en')!r}: se espera ISO-8601 UTC con Z")
    puntos = datos.get("puntos")
    fotos = datos.get("fotos")
    if not isinstance(puntos, list) or not puntos:
        r.errores.append("puntos: falta o está vacío")
        puntos = []
    if not isinstance(fotos, list) or not fotos:
        r.errores.append("fotos: falta o está vacío")
        fotos = []

    ids: set[str] = set()
    for i, p in enumerate(puntos):
        if not isinstance(p, dict):
            r.errores.append(f"puntos[{i}] no es un objeto")
            continue
        pid = p.get("id")
        if not isinstance(pid, str) or not PATRON_PUNTO.match(pid):
            r.errores.append(f"puntos[{i}].id={pid!r}: se espera P01, P02…")
        elif pid in ids:
            r.errores.append(f"punto {pid} repetido")
        else:
            ids.add(pid)
        lat, lng = p.get("lat"), p.get("lng")
        if not (_numero(lat) and -90 <= lat <= 90 and _numero(lng) and -180 <= lng <= 180):
            r.errores.append(f"punto {pid}: lat={lat!r}, lng={lng!r} no es WGS84 válido")
        elif lat == 0 and lng == 0:
            r.errores.append(f"punto {pid}: coordenada (0, 0), probablemente sin rellenar")

    archivos: set[str] = set()
    for i, f in enumerate(fotos):
        if not isinstance(f, dict):
            r.errores.append(f"fotos[{i}] no es un objeto")
            continue
        archivo, punto = f.get("archivo"), f.get("punto")
        coincidencia = PATRON_ARCHIVO.match(archivo) if isinstance(archivo, str) else None
        if coincidencia is None:
            r.errores.append(f"fotos[{i}].archivo={archivo!r}: se espera fotos/<punto>/<n>.jpg")
        elif coincidencia.group(1) != punto:
            r.errores.append(f"{archivo}: está en la carpeta de otro punto que {punto!r}")
        if isinstance(archivo, str):
            if archivo in archivos:
                r.errores.append(f"{archivo} repetido")
            archivos.add(archivo)
        if punto not in ids:
            r.errores.append(f"{archivo}: punto {punto!r} no está en puntos")
        rumbo = f.get("rumbo")
        if rumbo is not None and not (_numero(rumbo) and 0 <= rumbo < 360):
            r.errores.append(f"{archivo}: rumbo={rumbo!r} fuera de [0, 360) (o null)")
        hora = f.get("hora")
        if hora not in HORAS:
            r.errores.append(f"{archivo}: hora={hora!r}, se espera una de {', '.join(HORAS)}")
        try:
            instante = leer_fecha(f.get("capturada_en"))
        except (TypeError, ValueError):
            r.errores.append(f"{archivo}: capturada_en={f.get('capturada_en')!r} no es UTC con Z")
        else:
            if hora in HORAS and franja(instante) != hora:
                r.avisos.append(
                    f"{archivo}: hora={hora} pero capturada_en es {franja(instante)} en Bogotá"
                )
        vuelta = f.get("vuelta")
        if vuelta is not None and not (
            isinstance(vuelta, int) and not isinstance(vuelta, bool) and vuelta >= 1
        ):
            r.errores.append(f"{archivo}: vuelta={vuelta!r}, se espera un entero ≥ 1 o nada")
    usados = {f.get("punto") for f in fotos if isinstance(f, dict)}
    for pid in sorted(ids - usados):
        r.avisos.append(f"punto {pid} sin fotos")
    return r


def desde_dict(datos: dict, directorio: Path | None = None) -> Conjunto:
    """`puntos.json` ya revisado → `Conjunto`. Llamar antes a `revisar`."""
    puntos = {
        p["id"]: Punto(p["id"], float(p["lat"]), float(p["lng"]), p.get("descripcion") or "")
        for p in datos["puntos"]
    }
    fotos = [
        Foto(
            archivo=f["archivo"],
            punto=f["punto"],
            rumbo=None if f.get("rumbo") is None else float(f["rumbo"]),
            capturada_en=f["capturada_en"],
            hora=f["hora"],
            vuelta=f.get("vuelta"),
        )
        for f in datos["fotos"]
    ]
    return Conjunto(datos["version_conjunto"], datos["creado_en"], puntos, fotos, directorio)


class ConjuntoInvalido(ValueError):
    def __init__(self, revision: Revision) -> None:
        super().__init__("; ".join(revision.errores))
        self.revision = revision


def cargar(directorio: Path) -> tuple[Conjunto, Revision]:
    """Carpeta local con la forma del bucket (`puntos.json` + `fotos/`): revisa y comprueba que
    cada `archivo` existe. Lanza `ConjuntoInvalido` si hay errores."""
    directorio = Path(directorio)
    ruta = directorio / "puntos.json"
    if not ruta.is_file():
        raise ConjuntoInvalido(Revision(errores=[f"no existe {ruta}"]))
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConjuntoInvalido(Revision(errores=[f"puntos.json no es JSON: {error}"])) from error
    revision = revisar(datos)
    for f in datos.get("fotos") or []:
        archivo = f.get("archivo") if isinstance(f, dict) else None
        if isinstance(archivo, str) and not (directorio / archivo).is_file():
            revision.errores.append(f"{archivo}: no está en {directorio}")
    if not revision.valido:
        raise ConjuntoInvalido(revision)
    return desde_dict(datos, directorio), revision


# --- Cobertura respecto al dataset ---------------------------------------------------------------


@dataclass(frozen=True)
class CoberturaPunto:
    punto: str
    distancia_m: float | None  # a la imagen del dataset más cercana (None: dataset vacío)
    fotos: int

    @property
    def con_dataset(self) -> bool:
        return self.distancia_m is not None and self.distancia_m <= DATASET_CERCA_M

    @property
    def lejano(self) -> bool:
        return self.distancia_m is None or self.distancia_m > LEJOS_M


def distancia_minima(lat: float, lng: float, coordenadas: Iterable[tuple[float, float]]):
    mejor = None
    for clat, clng in coordenadas:
        d = haversine_m(lat, lng, clat, clng)
        if mejor is None or d < mejor:
            mejor = d
    return mejor


def cobertura(
    conjunto: Conjunto, coordenadas_dataset: Sequence[tuple[float, float]]
) -> list[CoberturaPunto]:
    return [
        CoberturaPunto(
            p.id, distancia_minima(p.lat, p.lng, coordenadas_dataset), len(conjunto.fotos_de(p.id))
        )
        for p in sorted(conjunto.puntos.values(), key=lambda p: p.id)
    ]


def revisar_c1(cob: Sequence[CoberturaPunto]) -> tuple[list[str], dict]:
    """Criterio C1 de PLAN EMB-3.2 sobre la cobertura: (errores, resumen)."""
    con = [c for c in cob if c.con_dataset and c.fotos > 0]
    lejanos = [c for c in cob if c.lejano and c.fotos >= FOTOS_PUNTO_LEJANO_MIN]
    fotos_con = sum(c.fotos for c in con)
    errores = []
    if fotos_con < FOTOS_MIN:
        errores.append(
            f"{fotos_con} fotos en puntos con dataset (≤ {DATASET_CERCA_M:.0f} m); "
            f"mínimo {FOTOS_MIN}"
        )
    if len(con) < PUNTOS_CON_DATASET_MIN:
        errores.append(f"{len(con)} puntos con dataset; mínimo {PUNTOS_CON_DATASET_MIN}")
    if not lejanos:
        errores.append(
            f"ningún punto con ≥ {FOTOS_PUNTO_LEJANO_MIN} fotos a > {LEJOS_M:.0f} m del dataset"
        )
    intermedios = [c.punto for c in cob if not c.con_dataset and not c.lejano]
    resumen = {
        "fotos_con_dataset": fotos_con,
        "puntos_con_dataset": [c.punto for c in con],
        "puntos_lejanos": [c.punto for c in lejanos],
        "puntos_intermedios": intermedios,  # ni lo uno ni lo otro: no cuentan para nada
    }
    return errores, resumen
