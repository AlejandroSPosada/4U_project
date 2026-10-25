"""tools/evaluacion (EMB-3.2; ARCHITECTURE §4.5, §5.9 y ADR-EMB-14) con datos sintéticos.

Sin dataset real ni backend: un «campus» de 10 puntos a ~110 m entre sí más uno lejano, con
imágenes sintéticas (un patrón por lugar) y un vectorizador falso que reconoce el patrón. El
cliente del backend se prueba con `httpx.MockTransport`. Con los pesos en `.modelo/` (o
`MODELO_DIR`), el extractor de las variantes reproduce los vectores dorados de pp-v1.
"""

from __future__ import annotations

import io
import json
import math
import os
import sys
from pathlib import Path

import httpx
import numpy as np
import pytest
from PIL import Image

PROYECTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROYECTO / "tools"))

from evaluacion import (  # noqa: E402
    cli,
    fuentes,
    metricas,
    variantes,
)
from evaluacion import conjunto as cj  # noqa: E402

LAT0, LNG0 = 6.2000, -75.5790
VV = "dinov2-vits14/pp-v1"


# --- Campus sintético -----------------------------------------------------------------------------


def patron(lugar: int, ancho: int, alto: int, ruido: int) -> bytes:
    """JPEG con un patrón 8 × 8 propio del lugar, ampliado y con ruido."""
    rng = np.random.default_rng(lugar)
    base = rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)
    imagen = Image.fromarray(base).resize((ancho, alto), Image.Resampling.NEAREST)
    if ruido:
        pix = np.asarray(imagen, dtype=np.int16)
        pix = pix + np.random.default_rng(ruido).integers(-12, 13, size=pix.shape)
        imagen = Image.fromarray(np.clip(pix, 0, 255).astype(np.uint8))
    salida = io.BytesIO()
    imagen.save(salida, "JPEG", quality=90)
    return salida.getvalue()


def vector_falso(datos: bytes) -> np.ndarray:
    """Reconoce el patrón: la imagen reducida a 8 × 8, centrada y normalizada."""
    imagen = Image.open(io.BytesIO(datos)).convert("RGB").resize((8, 8), Image.Resampling.BOX)
    v = np.asarray(imagen, dtype=np.float64).reshape(-1)
    v = v - v.mean()
    return (v / np.linalg.norm(v)).astype(np.float32)


def coord(i: int) -> tuple[float, float]:
    return LAT0 + 0.001 * i, LNG0  # ~111 m entre puntos


LEJANO = (LAT0 + 0.001 * 5, LNG0 + 0.005)  # ~550 m al este del más cercano


def crear_campus(tmp_path: Path, escribir: bool = True):
    """Conjunto en tmp/conjunto y dataset en tmp/dataset (3 imágenes por punto, a ≤ 3 m). Con
    `escribir=False` solo devuelve el `puntos.json` (las pruebas de estructura no leen fotos)."""
    dir_c, dir_d = tmp_path / "conjunto", tmp_path / "dataset"
    puntos, fotos, dataset = [], [], []

    def guardar(ruta: Path, imagen) -> None:
        if escribir:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(imagen())

    for i in range(1, 11):
        pid = f"P{i:02d}"
        lat, lng = coord(i)
        puntos.append({"id": pid, "lat": lat, "lng": lng, "descripcion": f"lugar {i}"})
        for n in range(1, 6):
            archivo = f"fotos/{pid}/{n}.jpg"
            guardar(dir_c / archivo, lambda i=i, n=n: patron(i, 640, 480, ruido=100 * i + n))
            hora = "manana" if n <= 3 else "tarde"
            fotos.append({"archivo": archivo, "punto": pid, "rumbo": (72.0 * n) % 360,
                          "capturada_en": "2026-11-05T14:02:10Z" if hora == "manana"
                          else "2026-11-05T19:30:00Z", "hora": hora})  # fmt: skip
        for j in range(3):
            nombre = f"{pid}-{j}.jpg"
            guardar(dir_d / nombre, lambda i=i, j=j: patron(i, 512, 384, ruido=7000 + 10 * i + j))
            dataset.append({"imagen_id": f"{pid}-{j}", "archivo": nombre,
                            "lat": lat + 0.00001 * j, "lng": lng, "rumbo": 90.0})  # fmt: skip
    puntos.append({"id": "P11", "lat": LEJANO[0], "lng": LEJANO[1], "descripcion": "lejos"})
    for n in range(1, 4):
        archivo = f"fotos/P11/{n}.jpg"
        guardar(dir_c / archivo, lambda n=n: patron(99, 640, 480, ruido=9000 + n))
        fotos.append({"archivo": archivo, "punto": "P11", "rumbo": None,
                      "capturada_en": "2026-11-05T14:30:00Z", "hora": "manana",
                      "vuelta": 1})  # fmt: skip
    puntos_json = {"version_conjunto": "2026-11a", "creado_en": "2026-11-05T20:00:00Z",
                   "puntos": puntos, "fotos": fotos}  # fmt: skip
    if escribir:
        (dir_c / "puntos.json").write_text(json.dumps(puntos_json), encoding="utf-8")
        (dir_d / "dataset.json").write_text(json.dumps({"imagenes": dataset}), encoding="utf-8")
    return dir_c, dir_d, puntos_json


# --- Conjunto ------------------------------------------------------------------------------------


def test_haversine_y_franjas():
    assert cj.haversine_m(LAT0, LNG0, LAT0 + 0.001, LNG0) == pytest.approx(111.2, abs=0.2)
    assert cj.franja(cj.leer_fecha("2026-11-05T14:02:10Z")) == "manana"  # 09:02 en Bogotá
    assert cj.franja(cj.leer_fecha("2026-11-05T19:30:00Z")) == "tarde"  # 14:30
    assert cj.franja(cj.leer_fecha("2026-11-06T00:30:00Z")) == "noche"  # 19:30


def test_revisar_acepta_el_ejemplo_de_la_arquitectura(tmp_path):
    _, _, datos = crear_campus(tmp_path, escribir=False)
    revision = cj.revisar(datos)
    assert revision.valido, revision.errores
    assert revision.avisos == []


@pytest.mark.parametrize(
    ("cambio", "error"),
    [
        (lambda d: d["fotos"][0].update(hora="madrugada"), "hora="),
        (lambda d: d["fotos"][0].update(rumbo=360.0), "rumbo="),
        (lambda d: d["fotos"][0].update(punto="P99"), "no está en puntos"),
        (lambda d: d["fotos"][0].update(archivo="fotos/P02/9.jpg"), "carpeta de otro punto"),
        (lambda d: d["fotos"][0].update(archivo="fotos/P01/1.png"), "fotos/<punto>/<n>.jpg"),
        (lambda d: d["fotos"][0].update(capturada_en="2026-11-05 14:02"), "UTC con Z"),
        (lambda d: d["fotos"][0].update(vuelta=0), "vuelta="),
        (lambda d: d["fotos"].append(dict(d["fotos"][0])), "repetido"),
        (lambda d: d["puntos"][0].update(lat=91), "WGS84"),
        (lambda d: d["puntos"][0].update(lat=0, lng=0), "(0, 0)"),
        (lambda d: d.update(version_conjunto="nov"), "version_conjunto"),
    ],
)
def test_revisar_detecta_errores(tmp_path, cambio, error):
    _, _, datos = crear_campus(tmp_path, escribir=False)
    cambio(datos)
    revision = cj.revisar(datos)
    assert any(error in e for e in revision.errores), revision.errores


def test_hora_que_no_cuadra_con_la_fecha_es_un_aviso(tmp_path):
    _, _, datos = crear_campus(tmp_path, escribir=False)
    datos["fotos"][0]["hora"] = "noche"
    revision = cj.revisar(datos)
    assert revision.valido and any("Bogotá" in a for a in revision.avisos)


def test_cargar_exige_que_existan_las_fotos(tmp_path):
    dir_c, _, _ = crear_campus(tmp_path)
    (dir_c / "fotos/P03/2.jpg").unlink()
    with pytest.raises(cj.ConjuntoInvalido, match=r"P03/2\.jpg"):
        cj.cargar(dir_c)


def test_cobertura_y_criterio_c1(tmp_path):
    dir_c, dir_d, _ = crear_campus(tmp_path)
    conjunto, _ = cj.cargar(dir_c)
    coords = [(i.lat, i.lng) for i in fuentes.FuenteCarpeta(dir_d).imagenes()]
    cob = cj.cobertura(conjunto, coords)
    errores, resumen = cj.revisar_c1(cob)
    assert errores == []
    assert resumen["fotos_con_dataset"] == 50 and len(resumen["puntos_con_dataset"]) == 10
    assert resumen["puntos_lejanos"] == ["P11"]
    # Sin el punto lejano, o con menos fotos, no cumple.
    sin_lejano = [c for c in cob if c.punto != "P11"]
    assert any("150 m" in e for e in cj.revisar_c1(sin_lejano)[0])
    pocas = [cj.CoberturaPunto(c.punto, c.distancia_m, 4) for c in cob]
    assert any("mínimo 50" in e for e in cj.revisar_c1(pocas)[0])


# --- Métricas ------------------------------------------------------------------------------------


def test_percentil_por_rango_mas_cercano():
    valores = list(range(1, 61))
    assert metricas.percentil(valores, 95) == 57  # como benchmark.py (§5.9)
    assert metricas.percentil([], 50) is None
    assert metricas.percentil([0.3], 10) == 0.3


def test_recomendacion_de_sim_min_supera_al_mejor_lejano():
    d = metricas.Distribuciones(
        mismo_lugar=[0.7, 0.75, 0.8, 0.85, 0.9], otro_lugar=[0.3, 0.4, 0.5, 0.55], lejos_top1=[0.62]
    )
    assert metricas.umbral_youden(d.mismo_lugar, d.otro_lugar) == 0.56
    valor, detalle = metricas.recomendar_sim_min(d)
    assert valor == 0.63 and detalle["youden"] == 0.56 and detalle["lejos_max"] == 0.62
    alta, detalle_alta = metricas.recomendar_sim_alta(d, valor)
    assert valor < alta <= 1 and detalle_alta["metodo"] == "precision"


def V(lat, lng, s):
    return fuentes.Vecino("x", lat, lng, None, s)


def test_localizar_sigue_el_algoritmo_v1():
    cerca = [V(LAT0, LNG0, 0.9), V(LAT0 + 0.00005, LNG0, 0.8)]  # a ~5,6 m: mismo grupo
    lejos = [V(LAT0 + 0.002, LNG0, 0.6)]  # ~222 m: otro grupo
    posicion, confianza = metricas.localizar([cerca, lejos, []], sim_min=0.5, sim_alta=1.0)
    # s = (0,9 − 0,5)/0,5 = 0,8; c = 1/3 (solo la 1.ª foto aporta al grupo); m = (0,9 − 0,6)/0,9
    assert confianza == pytest.approx(0.5 * 0.8 + 0.3 / 3 + 0.2 * (0.3 / 0.9))
    assert cj.haversine_m(LAT0, LNG0, *posicion) < 5
    assert metricas.localizar([[V(LAT0, LNG0, 0.4)]], 0.5, 0.8) == (None, 0.0)


def test_consultas_agrupan_por_vuelta_o_por_franja(tmp_path):
    dir_c, _, _ = crear_campus(tmp_path)
    conjunto, _ = cj.cargar(dir_c)
    resultados = [metricas.ResultadoFoto(f, "con_dataset", [], []) for f in conjunto.fotos]
    grupos = metricas.consultas(resultados)
    # 10 puntos × (3 de mañana + 2 de tarde) y el lejano (vuelta 1): 21 consultas
    assert len(grupos) == 21 and all(len(g) <= 5 for g in grupos)


def test_informe_de_punta_a_punta_con_fuerza_bruta(tmp_path):
    dir_c, dir_d, _ = crear_campus(tmp_path)
    conjunto, _ = cj.cargar(dir_c)
    fuente = fuentes.FuenteCarpeta(dir_d)
    buscador = fuentes.indexar(fuente, vector_falso, VV)
    coords = [(i.lat, i.lng) for i in fuente.imagenes()]
    ruta, informe = cli.evaluar(conjunto, coords, buscador, "fuerza_bruta_local",
                                dir_c / "informes", fecha="20261105")  # fmt: skip
    assert ruta.name == "dinov2-vits14_pp-v1-20261105.json"
    assert ruta.with_suffix(".md").is_file()
    assert json.loads(ruta.read_text(encoding="utf-8")) == informe
    assert metricas.revisar_informe(informe, VV, 50) == []
    assert (informe["fotos"], informe["puntos"]) == (50, 10)
    assert informe["recall_1_15m"] == 1.0 and informe["recall_5_15m"] == 1.0
    assert informe["variantes"][0]["nombre"] == "pp-v1"
    r = informe["recomendado"]
    assert 0 < r["LOC_SIM_MIN"] < r["LOC_SIM_ALTA"] <= 1
    assert 0 < r["corte_media"] < r["corte_alta"] < 1
    assert r["LOC_SIM_MIN"] > informe["similitud"]["lejos_del_dataset"]["max"]
    assert informe["simulacion"]["lejanas_sin_coincidencias"] == "1/1"
    assert set(informe["por_hora"]) == {"manana", "tarde"}
    s = informe["similitud"]
    assert s["mismo_lugar"]["p50"] > s["otro_lugar"]["p90"]


@pytest.mark.parametrize(
    ("cambio", "error"),
    [
        ({"version_vector": "otra"}, "version_vector"),
        ({"recall_1_15m": 0.9, "recall_5_15m": 0.8}, "> recall_5_15m"),
        ({"recall_1_15m": 1.2}, "[0, 1]"),
        ({"fotos": 49}, "fotos=49"),
        ({"similitud": {"mismo_lugar": {"p10": 0.9, "p50": 0.5, "p90": 0.95},
                        "otro_lugar": {"p10": 0.1, "p50": 0.2, "p90": 0.3}}}, "mismo_lugar"),
        ({"recomendado": {"LOC_SIM_MIN": 0.6, "LOC_SIM_ALTA": None}}, "LOC_SIM_ALTA"),
    ],
)  # fmt: skip
def test_revisar_informe_detecta_errores(cambio, error):
    informe = {
        "version_conjunto": "2026-11a", "version_vector": VV, "fotos": 50,
        "recall_1_15m": 0.6, "recall_5_15m": 0.8,
        "similitud": {"mismo_lugar": {"p10": 0.5, "p50": 0.7, "p90": 0.9},
                      "otro_lugar": {"p10": 0.1, "p50": 0.3, "p90": 0.5}},
        "recomendado": {"LOC_SIM_MIN": 0.55, "LOC_SIM_ALTA": 0.8, "corte_alta": 0.7,
                        "corte_media": 0.45},
    }  # fmt: skip
    assert metricas.revisar_informe(informe, VV, 50) == []
    informe.update(cambio)
    assert any(error in e for e in metricas.revisar_informe(informe, VV, 50))


# --- CLI ------------------------------------------------------------------------------------------


class ExtractorFalso:
    """Sustituye a DINOv2: vector de la imagen preprocesada reducida a 8 × 8 por canal."""

    def __init__(self, *_):
        self.llamadas = 0

    def vector(self, tensor, extraccion):
        self.llamadas += 1
        c, h, w = tensor.shape
        bloques = tensor[:, : h - h % 8, : w - w % 8].reshape(c, 8, (h - h % 8) // 8, 8, -1)
        v = bloques.mean(axis=(2, 4)).reshape(-1).astype(np.float64)
        v = v - v.mean()
        return (v / np.linalg.norm(v)).astype(np.float32)


def test_cli_revisar_cobertura_evaluar_y_variantes(tmp_path, monkeypatch, capsys):
    dir_c, dir_d, _ = crear_campus(tmp_path)
    monkeypatch.setattr(variantes, "ExtractorDinov2", ExtractorFalso)
    assert cli.main(["revisar", str(dir_c)]) == 0
    assert cli.main(["cobertura", str(dir_c), "--dataset-local", str(dir_d)]) == 0
    assert "P11: 3 fotos" in capsys.readouterr().out
    assert cli.main(["evaluar", str(dir_c), "--dataset-local", str(dir_d),
                     "--fecha", "20261105"]) == 0  # fmt: skip
    ruta = dir_c / "informes" / "dinov2-vits14_pp-v1-20261105.json"
    informe = json.loads(ruta.read_text(encoding="utf-8"))
    assert informe["fuente_vecinos"] == "fuerza_bruta_local" and informe["recall_5_15m"] == 1.0
    codigo = cli.main(["variantes", str(dir_c), "--dataset-local", str(dir_d),
                       "--informe", str(ruta)])  # fmt: skip
    assert codigo == 0
    informe = json.loads(ruta.read_text(encoding="utf-8"))
    nombres = [v["nombre"] for v in informe["variantes"]]
    assert nombres == ["pp-v1", "pp-v1-local", "sin-recorte", "res-448", "media-parches"]
    assert all(0 <= v["recall_1_15m"] <= v["recall_5_15m"] <= 1 for v in informe["variantes"])
    assert "| sin-recorte |" in ruta.with_suffix(".md").read_text(encoding="utf-8")


def test_cli_sin_variables_del_backend_da_2(tmp_path, monkeypatch, capsys):
    dir_c, _, _ = crear_campus(tmp_path)
    for v in ("VALIDACION_API_URL", "VALIDACION_ADMIN_CORREO", "VALIDACION_ADMIN_PASSWORD"):
        monkeypatch.delenv(v, raising=False)
    assert cli.main(["cobertura", str(dir_c)]) == 2
    assert "VALIDACION_API_URL" in capsys.readouterr().out


def test_cli_conjunto_invalido_da_1(tmp_path, capsys):
    dir_c, _, _ = crear_campus(tmp_path)
    (dir_c / "fotos/P01/1.jpg").unlink()
    assert cli.main(["revisar", str(dir_c)]) == 1
    assert "P01/1.jpg" in capsys.readouterr().out


# --- Preparación de fotos y variantes -------------------------------------------------------------


def test_preparar_foto_reduce_orienta_y_quita_exif():
    imagen = Image.new("RGB", (4000, 3000), (10, 120, 200))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotada 90°: la foto real es vertical
    salida = io.BytesIO()
    imagen.save(salida, "JPEG", quality=95, exif=exif)
    preparada = Image.open(io.BytesIO(fuentes.preparar_foto(salida.getvalue())))
    assert preparada.size == (768, 1024)
    assert not preparada.getexif()


def test_preprocesado_de_las_variantes():
    apaisada, vertical = patron(1, 1600, 1200, 0), patron(1, 1200, 1600, 0)
    assert variantes.sin_recorte(apaisada).shape == (3, 224, 294)
    assert variantes.sin_recorte(vertical).shape == (3, 294, 224)
    assert variantes.resolucion_448(apaisada).shape == (3, 448, 448)
    assert variantes.VARIANTES["pp-v1"].preprocesar(apaisada).shape == (3, 224, 224)
    for v in variantes.VARIANTES.values():
        assert v.extraccion in {"cls", "media_parches"}


def _pesos() -> Path | None:
    directorio = Path(os.environ.get("MODELO_DIR") or PROYECTO / ".modelo")
    return directorio if (directorio / "model.safetensors").is_file() else None


def test_extractor_reproduce_los_vectores_dorados_de_pp_v1():
    directorio = _pesos()
    if directorio is None:
        if os.environ.get("DORADOS_OBLIGATORIOS") == "1":
            pytest.fail("DORADOS_OBLIGATORIOS=1 y no hay pesos en MODELO_DIR ni .modelo/")
        pytest.skip("sin pesos del modelo (ARCHITECTURE §5.9)")
    esperados = json.loads((PROYECTO / "tests/golden/esperados.json").read_text(encoding="utf-8"))
    extractor = variantes.ExtractorDinov2(directorio)
    pp = variantes.VARIANTES["pp-v1"]
    for imagen in esperados["imagenes"]:
        datos = (PROYECTO / "tests/golden" / imagen["archivo"]).read_bytes()
        vector = variantes.vectorizador(pp, extractor)(datos)
        assert np.max(np.abs(vector - np.asarray(imagen["vector"]))) <= esperados["tolerancia"]
    parches = extractor.vector(pp.preprocesar(datos), "media_parches")
    assert parches.shape == (384,) and math.isclose(float(np.linalg.norm(parches)), 1, abs_tol=1e-5)


# --- Cliente del backend --------------------------------------------------------------------------


def transporte(registro: list, vecinos_estado=200, fallos_429=0):
    estado = {"429": fallos_429}

    def responder(peticion: httpx.Request) -> httpx.Response:
        peticion.read()
        registro.append(peticion)
        ruta = peticion.url.path
        if ruta == "/v1/auth/login":
            return httpx.Response(200, json={"token": "tok-secreto", "expira_en": "…"})
        assert peticion.headers["Authorization"] == "Bearer tok-secreto"
        if ruta == "/v1/admin/videos":
            pagina = int(peticion.url.params["pagina"])
            items = [
                [{"id": "v1", "nombre": "Entrada", "conteo": {"procesada": 2}},
                 {"id": "v2", "nombre": "validacion-x", "conteo": {"procesada": 1}}],
                [{"id": "v3", "nombre": "Vacío", "conteo": {"procesada": 0}}],
            ][pagina - 1]  # fmt: skip
            return httpx.Response(200, json={"items": items, "total": 3, "pagina": pagina,
                                             "por_pagina": 100})  # fmt: skip
        if ruta == "/v1/admin/videos/v1":
            fotos = [
                {"id": "i1", "lat": LAT0, "lng": LNG0, "rumbo": 10.0, "estado": "procesada",
                 "url": None},
                {"id": "i2", "lat": LAT0, "lng": LNG0, "rumbo": None, "estado": "error",
                 "url": None},
                {"id": "i3", "lat": LAT0 + 0.001, "lng": LNG0, "rumbo": None,
                 "estado": "procesada", "url": None},
            ]  # fmt: skip
            return httpx.Response(200, json={"id": "v1", "fotos": fotos})
        if ruta == "/v1/admin/diagnostico/vecinos":
            if estado["429"]:
                estado["429"] -= 1
                return httpx.Response(429, json={"message": "Too Many Requests"})
            if vecinos_estado != 200:
                return httpx.Response(
                    vecinos_estado,
                    json={
                        "error": {
                            "codigo": "EMBEDDING_NO_DISPONIBLE",
                            "mensaje": "…",
                            "detalle": None,
                        }
                    },
                )
            return httpx.Response(200, json={"version_vector": VV, "k": 2, "latencia_ms": 9,
                "vecinos": [{"imagen_id": "i1", "video_id": "v1", "lat": LAT0, "lng": LNG0,
                             "rumbo": 10.0, "lugar_id": None, "similitud": 0.83}]})  # fmt: skip
        return httpx.Response(404, json={"error": {"codigo": "NO_ENCONTRADO"}})

    return httpx.MockTransport(responder)


def cliente(registro, **kwargs):
    return fuentes.ClienteBackend(
        "https://api.ejemplo/v1/", "admin@campus.edu.co", "x",
        cliente=httpx.Client(transport=transporte(registro, **kwargs)),
    )  # fmt: skip


def test_cliente_lista_el_dataset_real_y_pide_vecinos(monkeypatch):
    registro: list = []
    c = cliente(registro, fallos_429=2)
    monkeypatch.setattr(fuentes.time, "sleep", lambda s: None)
    imagenes = c.imagenes()
    assert [i.imagen_id for i in imagenes] == ["i1", "i3"]  # sin validacion-, solo procesadas
    vecinos = c.vecinos(b"jpeg", 10)
    assert vecinos[0].similitud == 0.83 and c.version_vector == VV
    pedido = next(p for p in registro if p.url.path.endswith("/vecinos"))
    assert pedido.url.params["k"] == "10" and b'name="foto"' in pedido.content
    assert sum(p.url.path == "/v1/auth/login" for p in registro) == 1  # un solo login
    with pytest.raises(fuentes.PendienteBE41):
        c.descargar(imagenes[0])


def test_cliente_sin_embedding_explica_que_hacer_sin_filtrar_el_token():
    c = cliente([], vecinos_estado=503)
    with pytest.raises(fuentes.ErrorFuente) as error:
        c.vecinos(b"jpeg")
    assert "EMBEDDING_NO_DISPONIBLE" in str(error.value) and "encender" in str(error.value)
    assert "tok-secreto" not in str(error.value)
