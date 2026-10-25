"""Órdenes de `uv run python tools/evaluacion <orden>` (ARCHITECTURE §5.9).

    revisar   DIR                       estructura de puntos.json y que las fotos existen
    cobertura DIR [--dataset-local D]   distancia de cada punto al dataset y criterio C1
    evaluar   DIR [--dataset-local D]   vecinos de cada foto → informe JSON y Markdown
    variantes DIR --informe RUTA [...]  añade al informe la comparación de variantes

DIR es la carpeta local del conjunto con la forma del bucket (`puntos.json` y `fotos/`). Sin
`--dataset-local`, el dataset y los vecinos son los del backend: `VALIDACION_API_URL` (con `/v1`),
`VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` (backend §5.11).

Códigos de salida: 0 hecho; 1 el conjunto no es válido o no cumple C1; 2 uso, variables que
faltan, error del backend o algo pendiente de otro lote (BE-4.1 para las variantes).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from evaluacion import conjunto as cj
from evaluacion import metricas
from evaluacion.fuentes import (
    K_POR_DEFECTO,
    BuscadorVecinos,
    ClienteBackend,
    ErrorFuente,
    FuenteCarpeta,
    PendienteBE41,
    indexar,
    preparar_foto,
)

VERSION_VECTOR = "dinov2-vits14/pp-v1"  # la de ARCHITECTURE §5.3 (app.config.VERSION_VECTOR)


class ErrorUso(RuntimeError):
    pass


def avisar(texto: str) -> None:
    print(texto, file=sys.stderr, flush=True)


def cliente_desde_entorno() -> ClienteBackend:
    faltan = [
        v
        for v in ("VALIDACION_API_URL", "VALIDACION_ADMIN_CORREO", "VALIDACION_ADMIN_PASSWORD")
        if not os.environ.get(v)
    ]
    if faltan:
        raise ErrorUso(f"faltan las variables {', '.join(faltan)} (o usa --dataset-local)")
    return ClienteBackend(
        os.environ["VALIDACION_API_URL"],
        os.environ["VALIDACION_ADMIN_CORREO"],
        os.environ["VALIDACION_ADMIN_PASSWORD"],
    )


def lector(conjunto: cj.Conjunto):
    return lambda foto: preparar_foto((conjunto.directorio / foto.archivo).read_bytes())


def nombre_informe(version_vector: str, fecha: str) -> str:
    return f"{version_vector.replace('/', '_')}-{fecha}.json"


def evaluar(
    conjunto: cj.Conjunto,
    coordenadas: list[tuple[float, float]],
    buscador: BuscadorVecinos,
    fuente: str,
    salida: Path,
    fecha: str | None = None,
    k: int = K_POR_DEFECTO,
) -> tuple[Path, dict]:
    """Cobertura → vecinos → informe en `salida/<version_vector>-<AAAAMMDD>.json` (y `.md`)."""
    cobertura = cj.cobertura(conjunto, coordenadas)
    resultados = metricas.consultar(conjunto, cobertura, buscador, lector(conjunto), k, avisar)
    version = buscador.version_vector or VERSION_VECTOR
    ahora = datetime.now(UTC)
    informe = metricas.construir_informe(
        conjunto, cobertura, resultados, version, ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), fuente, k
    )
    salida.mkdir(parents=True, exist_ok=True)
    ruta = salida / nombre_informe(version, fecha or ahora.strftime("%Y%m%d"))
    escribir(ruta, informe)
    return ruta, informe


def escribir(ruta: Path, informe: dict) -> None:
    ruta.write_text(json.dumps(informe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ruta.with_suffix(".md").write_text(markdown(informe), encoding="utf-8")


def _num(v) -> str:
    return "—" if v is None else f"{v}"


def markdown(informe: dict) -> str:
    s = informe["similitud"]
    r = informe["recomendado"]
    actual = informe.get("actual_backend") or {}
    lejanos = ", ".join(informe.get("puntos_lejanos") or []) or "—"
    lineas = [
        f"# Evaluación {informe['version_conjunto']} · {informe['version_vector']}",
        "",
        f"Creado {informe.get('creado_en')} con {informe.get('herramienta')} "
        f"(vecinos: {informe.get('fuente_vecinos')}, k = {informe.get('k')}).",
        "",
        f"- Fotos con dataset: {informe['fotos']} en {informe['puntos']} puntos; "
        f"fotos lejanas: {informe.get('fotos_lejanas')} ({lejanos}).",
        f"- recall@1 a 15 m: {_num(informe['recall_1_15m'])} · recall@5 a 15 m: "
        f"{_num(informe['recall_5_15m'])}",
        "",
        "| Similitud | p10 | p50 | p90 | n |",
        "|---|---|---|---|---|",
    ]
    for clave in ("mismo_lugar", "otro_lugar", "lejos_del_dataset"):
        d = s.get(clave) or {}
        lineas.append(
            f"| {clave} | {_num(d.get('p10'))} | {_num(d.get('p50'))} | {_num(d.get('p90'))} "
            f"| {d.get('n', '—')} |"
        )
    lineas += ["", "| Parámetro | Recomendado | Actual (backend §5.10) |", "|---|---|---|"]
    for clave in ("LOC_SIM_MIN", "LOC_SIM_ALTA", "corte_alta", "corte_media"):
        lineas.append(f"| {clave} | {_num(r.get(clave))} | {_num(actual.get(clave))} |")
    lineas += ["", "| Variante | recall@1 | recall@5 |", "|---|---|---|"]
    for v in informe.get("variantes") or []:
        lineas.append(f"| {v['nombre']} | {_num(v['recall_1_15m'])} | {_num(v['recall_5_15m'])} |")
    sim = informe.get("simulacion") or {}
    lineas += [
        "",
        f"Simulación de /v1/localize: {sim.get('consultas')} consultas, error mediano "
        f"{_num(sim.get('error_mediano_m'))} m; puntos lejanos sin coincidencias: "
        f"{sim.get('lejanas_sin_coincidencias')}. Por nivel: "
        f"`{json.dumps(sim.get('por_nivel'), ensure_ascii=False)}`.",
        "",
    ]
    return "\n".join(lineas)


# --- Órdenes -------------------------------------------------------------------------------------


def _cargar(directorio: str) -> cj.Conjunto:
    conjunto, revision = cj.cargar(Path(directorio))
    for aviso in revision.avisos:
        avisar(f"[AVISO] {aviso}")
    return conjunto


def _dataset(args):
    """(coordenadas, fuente, cliente) del dataset local o del backend."""
    if args.dataset_local:
        fuente = FuenteCarpeta(Path(args.dataset_local))
        return [(i.lat, i.lng) for i in fuente.imagenes()], fuente, None
    cliente = cliente_desde_entorno()
    imagenes = cliente.imagenes()
    avisar(f"dataset del backend: {len(imagenes)} imágenes procesadas")
    return [(i.lat, i.lng) for i in imagenes], cliente, cliente


def orden_revisar(args) -> int:
    try:
        conjunto = _cargar(args.directorio)
    except cj.ConjuntoInvalido as error:
        for e in error.revision.errores:
            print(f"[ERROR] {e}")
        return 1
    print(
        f"conjunto {conjunto.version_conjunto}: {len(conjunto.puntos)} puntos, "
        f"{len(conjunto.fotos)} fotos; estructura válida"
    )
    return 0


def orden_cobertura(args) -> int:
    conjunto = _cargar(args.directorio)
    coordenadas, _, _ = _dataset(args)
    cob = cj.cobertura(conjunto, coordenadas)
    for c in cob:
        clase = "con dataset" if c.con_dataset else ("lejano" if c.lejano else "intermedio")
        distancia = "—" if c.distancia_m is None else f"{c.distancia_m:.1f} m"
        print(f"{c.punto}: {c.fotos} fotos, dataset más cercano a {distancia} ({clase})")
    errores, resumen = cj.revisar_c1(cob)
    print(json.dumps(resumen, ensure_ascii=False))
    for e in errores:
        print(f"[NO CUMPLE C1] {e}")
    return 1 if errores else 0


def orden_evaluar(args) -> int:
    conjunto = _cargar(args.directorio)
    coordenadas, fuente, cliente = _dataset(args)
    if cliente is not None:
        buscador, nombre = cliente, "backend"
    else:
        from evaluacion.variantes import VARIANTES, ExtractorDinov2, vectorizador

        extractor = ExtractorDinov2(args.modelo)
        vec = vectorizador(VARIANTES["pp-v1"], extractor)
        buscador = indexar(fuente, lambda d: vec(preparar_foto(d)), VERSION_VECTOR)
        buscador.vectorizar = vec
        nombre = "fuerza_bruta_local"
    salida = Path(args.salida) if args.salida else conjunto.directorio / "informes"
    ruta, informe = evaluar(conjunto, coordenadas, buscador, nombre, salida, args.fecha, args.k)
    errores, _ = cj.revisar_c1(cj.cobertura(conjunto, coordenadas))
    for e in errores:
        avisar(f"[AVISO] el conjunto aún no cumple C1: {e}")
    print(f"informe: {ruta} (y {ruta.with_suffix('.md').name})")
    print(json.dumps({k: informe[k] for k in ("recall_1_15m", "recall_5_15m", "recomendado")}))
    return 0


def orden_variantes(args) -> int:
    from evaluacion.variantes import VARIANTES, ExtractorDinov2, comparar

    conjunto = _cargar(args.directorio)
    ruta = Path(args.informe)
    informe = json.loads(ruta.read_text(encoding="utf-8"))
    nombres = [n for n in args.nombres.split(",") if n]
    desconocidas = [n for n in nombres if n not in VARIANTES]
    if desconocidas:
        raise ErrorUso(f"variantes desconocidas: {', '.join(desconocidas)}")
    coordenadas, fuente, _ = _dataset(args)
    cobertura = cj.cobertura(conjunto, coordenadas)
    filas = comparar(
        conjunto, cobertura, fuente, [VARIANTES[n] for n in nombres],
        ExtractorDinov2(args.modelo), lector(conjunto), avisar,
    )  # fmt: skip
    referencia = [v for v in informe.get("variantes", []) if v["nombre"] == "pp-v1"][:1]
    informe["variantes"] = referencia + filas
    escribir(ruta, informe)
    print(f"informe actualizado: {ruta}")
    for fila in informe["variantes"]:
        print(f"{fila['nombre']}: recall@1 {fila['recall_1_15m']}, recall@5 {fila['recall_5_15m']}")
    return 0


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="tools/evaluacion", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="orden", required=True)

    def comun(p, dataset=True):
        p.add_argument("directorio", help="carpeta local del conjunto (puntos.json y fotos/)")
        if dataset:
            p.add_argument("--dataset-local", help="carpeta con dataset.json en vez del backend")

    p = sub.add_parser("revisar", help="estructura del conjunto")
    comun(p, dataset=False)
    p.set_defaults(funcion=orden_revisar)
    p = sub.add_parser("cobertura", help="distancia de cada punto al dataset y C1")
    comun(p)
    p.set_defaults(funcion=orden_cobertura)
    p = sub.add_parser("evaluar", help="informe de recall, similitudes y recomendaciones")
    comun(p)
    p.add_argument("--salida", help="carpeta del informe (por defecto DIR/informes)")
    p.add_argument("--fecha", help="AAAAMMDD del nombre del informe (por defecto hoy, UTC)")
    p.add_argument("--k", type=int, default=K_POR_DEFECTO, help="vecinos por foto (1–50)")
    p.add_argument("--modelo", help="pesos para --dataset-local (por defecto .modelo/)")
    p.set_defaults(funcion=orden_evaluar)
    p = sub.add_parser("variantes", help="añade la comparación de variantes al informe")
    comun(p)
    p.add_argument("--informe", required=True, help="informe JSON de `evaluar`")
    p.add_argument("--nombres", default="pp-v1,sin-recorte,res-448,media-parches")
    p.add_argument("--modelo", help="pesos (por defecto MODELO_DIR o .modelo/)")
    p.set_defaults(funcion=orden_variantes)

    args = parser.parse_args(argv)
    if args.orden == "evaluar" and not 5 <= args.k <= 50:
        parser.error("--k debe estar entre 5 y 50 (recall@5 necesita 5 vecinos)")
    try:
        return args.funcion(args)
    except cj.ConjuntoInvalido as error:
        for e in error.revision.errores:
            print(f"[ERROR] {e}")
        return 1
    except PendienteBE41 as error:
        print(f"[PENDIENTE] {error}")
        return 2
    except (ErrorUso, ErrorFuente) as error:
        print(f"[ERROR] {error}")
        return 2
