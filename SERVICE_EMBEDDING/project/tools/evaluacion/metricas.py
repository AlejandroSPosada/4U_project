"""Recall a 15 m, distribución de similitudes, simulación de la localización y recomendaciones.

Método completo y por qué: ARCHITECTURE §4.5 y ADR-EMB-14. Todo es determinista: los mismos
vecinos dan el mismo informe.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from evaluacion.conjunto import (
    BOGOTA,
    HORAS,
    CoberturaPunto,
    Conjunto,
    Foto,
    haversine_m,
    leer_fecha,
)
from evaluacion.fuentes import BuscadorVecinos, Vecino

MISMO_LUGAR_M = 15.0  # vecino «correcto» (PLAN EMB-3.2: recall a 15 m)
OTRO_LUGAR_M = 50.0  # vecino «de otro lugar»; entre 15 y 50 m no cuenta en ninguna distribución
K_RECALL = (1, 5)

# Copia de los parámetros de backend §5.10 que usa la simulación del algoritmo v1 (§4.10). Si el
# backend los cambia, se actualizan aquí y en ARCHITECTURE §4.5.
LOC_TOP_K = 10
LOC_RADIO_GRUPO_M = 20.0
LOC_PESO_EXPONENTE = 4
LOC_SIM_MIN_ACTUAL, LOC_SIM_ALTA_ACTUAL = 0.55, 0.80
CORTE_ALTA_ACTUAL, CORTE_MEDIA_ACTUAL = 0.70, 0.45
FOTOS_POR_CONSULTA = 5  # una vuelta de /v1/localize (LOC_MAX_FOTOS)

# Objetivos de la recomendación (ADR-EMB-14).
MARGEN_LEJOS = 0.01  # LOC_SIM_MIN queda al menos así de por encima del mejor vecino lejano
PRECISION_SIM_ALTA = 0.95  # fracción de vecinos «mismo lugar» por encima de LOC_SIM_ALTA
SOPORTE_SIM_ALTA = 5  # vecinos mínimos por encima de LOC_SIM_ALTA para fiarse de la precisión
PRECISION_15M_ALTA = 0.90  # consultas con nivel alta a ≤ 15 m
ERROR_MAX_ALTA_M = 30.0  # ninguna consulta con nivel alta a más de 30 m (BE-3.2 C2)
PRECISION_15M_MEDIA = 0.60


def percentil(valores: Sequence[float], p: float) -> float | None:
    """Rango más cercano: el valor en la posición ⌈p/100 · n⌉ de los n ordenados (como §5.9)."""
    if not valores:
        return None
    ordenados = sorted(valores)
    return ordenados[max(1, math.ceil(p / 100 * len(ordenados))) - 1]


def resumen(valores: Sequence[float]) -> dict:
    def r(v):
        return None if v is None else round(v, 4)

    return {
        "p10": r(percentil(valores, 10)),
        "p50": r(percentil(valores, 50)),
        "p90": r(percentil(valores, 90)),
        "n": len(valores),
    }


def _techo2(x: float) -> float:
    return math.ceil(round(x * 100, 6)) / 100


def _rejilla(desde: float, hasta: float) -> list[float]:
    inicio, fin = round(desde * 100), round(hasta * 100)
    return [i / 100 for i in range(inicio, fin + 1)]


# --- Consultas -----------------------------------------------------------------------------------


@dataclass
class ResultadoFoto:
    foto: Foto
    clase: str  # "con_dataset" | "lejano"
    vecinos: list[Vecino]
    distancias_m: list[float]

    def acierto(self, k: int) -> bool:
        return any(d <= MISMO_LUGAR_M for d in self.distancias_m[:k])


def consultar(
    conjunto: Conjunto,
    cobertura: Sequence[CoberturaPunto],
    buscador: BuscadorVecinos,
    leer: Callable[[Foto], bytes],
    k: int = LOC_TOP_K,
    progreso: Callable[[str], None] | None = None,
) -> list[ResultadoFoto]:
    """Pide los vecinos de cada foto de los puntos con dataset y de los lejanos (los intermedios,
    entre 30 y 150 m, no se consultan: no cuentan en nada)."""
    clases = {c.punto: ("con_dataset" if c.con_dataset else "lejano") for c in cobertura
              if c.con_dataset or c.lejano}  # fmt: skip
    resultados = []
    fotos = [f for f in conjunto.fotos if f.punto in clases]
    for i, foto in enumerate(fotos, 1):
        punto = conjunto.puntos[foto.punto]
        vecinos = buscador.vecinos(leer(foto), k)
        distancias = [haversine_m(punto.lat, punto.lng, v.lat, v.lng) for v in vecinos]
        resultados.append(ResultadoFoto(foto, clases[foto.punto], vecinos, distancias))
        if progreso:
            progreso(f"{i}/{len(fotos)} {foto.archivo}")
    return resultados


def recall(resultados: Sequence[ResultadoFoto], k: int) -> float | None:
    evaluadas = [r for r in resultados if r.clase == "con_dataset"]
    if not evaluadas:
        return None
    return round(sum(r.acierto(k) for r in evaluadas) / len(evaluadas), 4)


@dataclass
class Distribuciones:
    mismo_lugar: list[float] = field(default_factory=list)
    otro_lugar: list[float] = field(default_factory=list)
    lejos_top1: list[float] = field(default_factory=list)


def distribuciones(resultados: Sequence[ResultadoFoto], k: int = 5) -> Distribuciones:
    """Similitudes de los `k` primeros vecinos de cada foto con dataset, separadas por distancia
    al punto real; y la del mejor vecino de cada foto de un punto lejano."""
    d = Distribuciones()
    for r in resultados:
        if r.clase == "lejano":
            if r.vecinos:
                d.lejos_top1.append(r.vecinos[0].similitud)
            continue
        for vecino, distancia in zip(r.vecinos[:k], r.distancias_m[:k], strict=True):
            if distancia <= MISMO_LUGAR_M:
                d.mismo_lugar.append(vecino.similitud)
            elif distancia > OTRO_LUGAR_M:
                d.otro_lugar.append(vecino.similitud)
    return d


# --- Recomendación de LOC_SIM_MIN y LOC_SIM_ALTA --------------------------------------------------


def umbral_youden(mismo: Sequence[float], otro: Sequence[float]) -> float | None:
    """Umbral t (rejilla de 0,01) que maximiza TPR − FPR; a igualdad, el menor."""
    if not mismo:
        return None
    mejor_t, mejor_j = None, -2.0
    for t in _rejilla(0.0, 1.0):
        tpr = sum(s >= t for s in mismo) / len(mismo)
        fpr = sum(s >= t for s in otro) / len(otro) if otro else 0.0
        if tpr - fpr > mejor_j + 1e-12:
            mejor_t, mejor_j = t, tpr - fpr
    return mejor_t


def recomendar_sim_min(d: Distribuciones) -> tuple[float | None, dict]:
    youden = umbral_youden(d.mismo_lugar, d.otro_lugar)
    lejos_max = max(d.lejos_top1) if d.lejos_top1 else None
    if youden is None:
        return None, {"youden": None, "lejos_max": lejos_max}
    candidato = youden
    if lejos_max is not None:
        candidato = max(candidato, _techo2(lejos_max + MARGEN_LEJOS))
    valor = min(max(candidato, 0.01), 0.98)
    retenidos = sum(s >= valor for s in d.mismo_lugar) / len(d.mismo_lugar)
    return round(valor, 2), {
        "youden": youden,
        "lejos_max": None if lejos_max is None else round(lejos_max, 4),
        "mismo_lugar_retenido": round(retenidos, 4),
    }


def recomendar_sim_alta(d: Distribuciones, sim_min: float) -> tuple[float | None, dict]:
    if sim_min is None or not d.mismo_lugar:
        return None, {"metodo": None}
    for t in _rejilla(sim_min + 0.01, 1.0):
        n_mismo = sum(s >= t for s in d.mismo_lugar)
        n_otro = sum(s >= t for s in d.otro_lugar)
        if n_mismo + n_otro >= SOPORTE_SIM_ALTA and n_mismo / (n_mismo + n_otro) >= (
            PRECISION_SIM_ALTA
        ):
            return t, {"metodo": "precision", "precision": round(n_mismo / (n_mismo + n_otro), 4)}
    respaldo = max(_techo2(percentil(d.mismo_lugar, 90)), round(sim_min + 0.05, 2))
    return min(respaldo, 1.0), {"metodo": "p90_mismo_lugar"}


# --- Simulación del algoritmo v1 de backend §4.10 ------------------------------------------------


@dataclass
class Simulacion:
    punto: str
    fotos: int
    confianza: float
    error_m: float  # inf si sin_coincidencias

    @property
    def sin_coincidencias(self) -> bool:
        return math.isinf(self.error_m)


def localizar(
    vecinos_por_foto: Sequence[Sequence[Vecino]], sim_min: float, sim_alta: float
) -> tuple[tuple[float, float] | None, float]:
    """Pasos 3–7 de backend §4.10 con los vecinos ya buscados → (posición, confianza).

    Donde §4.10 no fija la fórmula se asume (ADR-EMB-14, a confirmar con BE-3.2): el centroide de
    un grupo para unir vecinos es la media sin ponderar de sus miembros, y el margen
    m = (puntuación del 1.º − la del 2.º) / la del 1.º (1 si solo hay un grupo)."""
    candidatos = sorted(
        ((v, i) for i, vs in enumerate(vecinos_por_foto) for v in vs if v.similitud >= sim_min),
        key=lambda par: -par[0].similitud,
    )
    if not candidatos:
        return None, 0.0
    grupos: list[list[tuple[Vecino, int]]] = []
    for vecino, foto in candidatos:
        for grupo in grupos:
            clat = sum(v.lat for v, _ in grupo) / len(grupo)
            clng = sum(v.lng for v, _ in grupo) / len(grupo)
            if haversine_m(clat, clng, vecino.lat, vecino.lng) < LOC_RADIO_GRUPO_M:
                grupo.append((vecino, foto))
                break
        else:
            grupos.append([(vecino, foto)])

    def puntuacion(grupo) -> float:
        mejores: dict[int, float] = {}
        for v, f in grupo:
            mejores[f] = max(mejores.get(f, 0.0), v.similitud)
        return sum(mejores.values())

    puntuaciones = [puntuacion(g) for g in grupos]
    orden = sorted(range(len(grupos)), key=lambda i: -puntuaciones[i])  # estable: el 1.º creado
    mejor = grupos[orden[0]]
    pesos = [v.similitud**LOC_PESO_EXPONENTE for v, _ in mejor]
    lat = sum(p * v.lat for p, (v, _) in zip(pesos, mejor, strict=True)) / sum(pesos)
    lng = sum(p * v.lng for p, (v, _) in zip(pesos, mejor, strict=True)) / sum(pesos)
    s_max = max(v.similitud for v, _ in mejor)
    s = min(1.0, max(0.0, (s_max - sim_min) / (sim_alta - sim_min))) if sim_alta > sim_min else 1.0
    c = len({f for _, f in mejor}) / len(vecinos_por_foto)
    p1 = puntuaciones[orden[0]]
    m = 1.0 if len(grupos) == 1 else (p1 - puntuaciones[orden[1]]) / p1
    return (lat, lng), 0.5 * s + 0.3 * c + 0.2 * m


def _clave_consulta(foto: Foto) -> tuple:
    if foto.vuelta is not None:
        return (foto.punto, "v", foto.vuelta)
    local: datetime = leer_fecha(foto.capturada_en).astimezone(BOGOTA)
    return (foto.punto, local.date().isoformat(), foto.hora)


def consultas(resultados: Sequence[ResultadoFoto]) -> list[list[ResultadoFoto]]:
    """Agrupa las fotos en consultas como una vuelta de `/v1/localize`: por `vuelta` si la foto la
    trae; si no, por punto, día y franja; y en trozos de hasta 5 fotos, en orden de archivo."""
    grupos: dict[tuple, list[ResultadoFoto]] = {}
    for r in resultados:
        grupos.setdefault(_clave_consulta(r.foto), []).append(r)
    salida = []
    for clave in sorted(grupos, key=str):
        fotos = sorted(grupos[clave], key=lambda r: r.foto.archivo)
        for i in range(0, len(fotos), FOTOS_POR_CONSULTA):
            salida.append(fotos[i : i + FOTOS_POR_CONSULTA])
    return salida


def simular(
    conjunto: Conjunto,
    resultados: Sequence[ResultadoFoto],
    sim_min: float,
    sim_alta: float,
    clase: str = "con_dataset",
) -> list[Simulacion]:
    sims = []
    for consulta in consultas([r for r in resultados if r.clase == clase]):
        punto = conjunto.puntos[consulta[0].foto.punto]
        posicion, confianza = localizar([r.vecinos for r in consulta], sim_min, sim_alta)
        error = (
            math.inf
            if posicion is None
            else haversine_m(punto.lat, punto.lng, posicion[0], posicion[1])
        )
        sims.append(Simulacion(punto.id, len(consulta), round(confianza, 4), error))
    return sims


def recomendar_cortes(sims: Sequence[Simulacion]) -> tuple[float | None, float | None, dict]:
    """`corte_alta`: el menor (rejilla de 0,01 en [0,50; 0,99]) con el que ninguna consulta de nivel
    alta yerra más de 30 m y ≥ 90 % quedan a ≤ 15 m. `corte_media`: el menor por debajo con ≥ 60 %
    a ≤ 15 m entre las de confianza ≥ corte. Sin consultas, nada."""
    if not sims:
        return None, None, {"consultas": 0}

    def cumple(t: float, precision: float, error_max: float | None) -> bool:
        sub = [s for s in sims if s.confianza >= t]
        if not sub:
            return True  # nadie llega: el corte no se equivoca
        bien = sum(s.error_m <= MISMO_LUGAR_M for s in sub) / len(sub)
        return bien >= precision and (error_max is None or all(s.error_m <= error_max for s in sub))

    alta = next(
        (t for t in _rejilla(0.50, 0.99) if cumple(t, PRECISION_15M_ALTA, ERROR_MAX_ALTA_M)), 0.99
    )
    media = next(
        (t for t in _rejilla(0.05, round(alta - 0.01, 2)) if cumple(t, PRECISION_15M_MEDIA, None)),
        max(0.01, round(alta - 0.05, 2)),
    )
    return alta, media, {"consultas": len(sims)}


def por_nivel(sims: Sequence[Simulacion], alta: float, media: float) -> dict:
    niveles: dict[str, list[Simulacion]] = {"alta": [], "media": [], "baja": []}
    sin = 0
    for s in sims:
        if s.sin_coincidencias:
            sin += 1
        elif s.confianza >= alta:
            niveles["alta"].append(s)
        elif s.confianza >= media:
            niveles["media"].append(s)
        else:
            niveles["baja"].append(s)
    salida: dict = {"sin_coincidencias": sin}
    for nivel, lista in niveles.items():
        salida[nivel] = {
            "consultas": len(lista),
            "a_15m": sum(s.error_m <= MISMO_LUGAR_M for s in lista),
            "error_max_m": round(max((s.error_m for s in lista), default=0.0), 1),
        }
    return salida


# --- Informe -------------------------------------------------------------------------------------


def metricas_variante(nombre: str, resultados: Sequence[ResultadoFoto]) -> dict:
    return {
        "nombre": nombre,
        "recall_1_15m": recall(resultados, 1),
        "recall_5_15m": recall(resultados, 5),
    }


def construir_informe(
    conjunto: Conjunto,
    cobertura: Sequence[CoberturaPunto],
    resultados: Sequence[ResultadoFoto],
    version_vector: str,
    creado_en: str,
    fuente: str,
    k: int = LOC_TOP_K,
) -> dict:
    """Informe con el formato de ARCHITECTURE §5.9 (claves obligatorias primero, extras después)."""
    con = [r for r in resultados if r.clase == "con_dataset"]
    d = distribuciones(resultados)
    sim_min, detalle_min = recomendar_sim_min(d)
    sim_alta, detalle_alta = recomendar_sim_alta(d, sim_min)
    sims = simular(conjunto, resultados, sim_min, sim_alta) if sim_min is not None else []
    lejanas = (
        simular(conjunto, resultados, sim_min, sim_alta, "lejano") if sim_min is not None else []
    )
    corte_alta, corte_media, detalle_cortes = recomendar_cortes(sims)
    lejos = resumen(d.lejos_top1)
    lejos["max"] = None if not d.lejos_top1 else round(max(d.lejos_top1), 4)
    informe = {
        "version_conjunto": conjunto.version_conjunto,
        "version_vector": version_vector,
        "fotos": len(con),
        "puntos": len({r.foto.punto for r in con}),
        "recall_1_15m": recall(resultados, 1),
        "recall_5_15m": recall(resultados, 5),
        "similitud": {
            "mismo_lugar": resumen(d.mismo_lugar),
            "otro_lugar": resumen(d.otro_lugar),
            "lejos_del_dataset": lejos,
        },
        "variantes": [metricas_variante("pp-v1", resultados)],
        "recomendado": {
            "LOC_SIM_MIN": sim_min,
            "LOC_SIM_ALTA": sim_alta,
            "corte_alta": corte_alta,
            "corte_media": corte_media,
        },
        # Extras (no los exige validate32): cómo se llegó a lo de arriba.
        "creado_en": creado_en,
        "herramienta": "tools/evaluacion evaluar",
        "fuente_vecinos": fuente,
        "k": k,
        "puntos_lejanos": sorted({r.foto.punto for r in resultados if r.clase == "lejano"}),
        "fotos_lejanas": sum(r.clase == "lejano" for r in resultados),
        "por_hora": {
            hora: {
                "fotos": len(sub),
                "recall_1_15m": recall(sub, 1),
                "recall_5_15m": recall(sub, 5),
            }
            for hora in HORAS
            if (sub := [r for r in con if r.foto.hora == hora])
        },
        "actual_backend": {
            "LOC_SIM_MIN": LOC_SIM_MIN_ACTUAL,
            "LOC_SIM_ALTA": LOC_SIM_ALTA_ACTUAL,
            "corte_alta": CORTE_ALTA_ACTUAL,
            "corte_media": CORTE_MEDIA_ACTUAL,
        },
        "detalle_recomendacion": {
            "LOC_SIM_MIN": detalle_min,
            "LOC_SIM_ALTA": detalle_alta,
            "cortes": detalle_cortes,
        },
        "simulacion": {
            "consultas": len(sims),
            "error_mediano_m": _mediana_error(sims),
            "por_nivel": por_nivel(sims, corte_alta, corte_media) if sims else None,
            "lejanas_sin_coincidencias": f"{sum(s.sin_coincidencias for s in lejanas)}/"
            f"{len(lejanas)}",
        },
        "cobertura": {
            c.punto: None if c.distancia_m is None else round(c.distancia_m, 1) for c in cobertura
        },
    }
    return informe


def _mediana_error(sims: Sequence[Simulacion]) -> float | None:
    valor = percentil([s.error_m for s in sims], 50)
    return None if valor is None else (None if math.isinf(valor) else round(valor, 1))


def revisar_informe(informe: dict, version_vector: str, fotos_con_dataset: int | None) -> list[str]:
    """Lo que validate32 C2 exige al informe (validation-3-2 §2); vacío = pasa."""
    errores = []
    if not isinstance(informe, dict):
        return ["el informe no es un objeto JSON"]
    if not informe.get("version_conjunto"):
        errores.append("no cita version_conjunto")
    if informe.get("version_vector") != version_vector:
        errores.append(
            f"version_vector={informe.get('version_vector')!r}, se espera {version_vector}"
        )
    r1, r5 = informe.get("recall_1_15m"), informe.get("recall_5_15m")
    if not all(isinstance(v, int | float) and 0 <= v <= 1 for v in (r1, r5)):
        errores.append(f"recall_1_15m={r1!r}, recall_5_15m={r5!r}: se esperan en [0, 1]")
    elif r1 > r5:
        errores.append(f"recall_1_15m={r1} > recall_5_15m={r5}")
    if fotos_con_dataset is not None and informe.get("fotos") != fotos_con_dataset:
        errores.append(
            f"fotos={informe.get('fotos')!r} pero el conjunto tiene {fotos_con_dataset} fotos en "
            "puntos con dataset"
        )
    similitud = informe.get("similitud") or {}
    for clave in ("mismo_lugar", "otro_lugar"):
        dist = similitud.get(clave) or {}
        valores = [dist.get(p) for p in ("p10", "p50", "p90")]
        if not all(isinstance(v, int | float) for v in valores) or not (
            valores[0] <= valores[1] <= valores[2]
        ):
            errores.append(f"similitud.{clave}={dist!r}: se espera p10 ≤ p50 ≤ p90")
    recomendado = informe.get("recomendado") or {}
    faltan = [
        c
        for c in ("LOC_SIM_MIN", "LOC_SIM_ALTA", "corte_alta", "corte_media")
        if not isinstance(recomendado.get(c), int | float)
    ]
    if faltan:
        errores.append(f"recomendado sin {', '.join(faltan)}")
    return errores
