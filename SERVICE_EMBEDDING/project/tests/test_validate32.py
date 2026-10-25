"""validate32.py (EMB-3.2) con dobles de S3, Secrets Manager y del backend: no toca AWS ni la red.

Cubre el recorrido completo (P4 → P1 → P2 → P2b → P3 → C1 → C2), los bloqueos (sin conjunto, sin
dataset real, sin el endpoint de vecinos), la falta de variables (3), los fallos de C1 y C2 y la
coherencia con validation-3-2.md y con el nombre de informe de tools/evaluacion.
"""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path
from typing import ClassVar

import pytest

PROYECTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROYECTO / "src" / "ops"))

import validate32  # noqa: E402

import comun  # noqa: E402
from evaluacion import cli  # noqa: E402
from evaluacion.fuentes import ErrorFuente, ImagenDataset  # noqa: E402

LAT0, LNG0 = 6.2000, -75.5790
VERSION = "2026-11a"
CLAVE_INFORME = f"evaluacion/{VERSION}/informes/dinov2-vits14_pp-v1-20261105.json"


def puntos_json(fotos_por_punto=5, con_lejano=True) -> dict:
    puntos, fotos = [], []
    for i in range(1, 11):
        pid = f"P{i:02d}"
        puntos.append({"id": pid, "lat": LAT0 + 0.001 * i, "lng": LNG0})
        fotos += [{"archivo": f"fotos/{pid}/{n}.jpg", "punto": pid, "rumbo": None,
                   "capturada_en": "2026-11-05T14:02:10Z", "hora": "manana"}
                  for n in range(1, fotos_por_punto + 1)]  # fmt: skip
    if con_lejano:
        puntos.append({"id": "P11", "lat": LAT0, "lng": LNG0 + 0.005})
        fotos += [{"archivo": f"fotos/P11/{n}.jpg", "punto": "P11", "rumbo": 10.0,
                   "capturada_en": "2026-11-05T14:30:00Z", "hora": "manana"}
                  for n in range(1, 4)]  # fmt: skip
    return {"version_conjunto": VERSION, "creado_en": "2026-11-05T20:00:00Z",
            "puntos": puntos, "fotos": fotos}  # fmt: skip


def informe(**cambios) -> dict:
    datos = {
        "version_conjunto": VERSION, "version_vector": "dinov2-vits14/pp-v1", "fotos": 50,
        "puntos": 10, "recall_1_15m": 0.62, "recall_5_15m": 0.84,
        "similitud": {"mismo_lugar": {"p10": 0.55, "p50": 0.71, "p90": 0.86},
                      "otro_lugar": {"p10": 0.2, "p50": 0.33, "p90": 0.48}},
        "variantes": [{"nombre": "pp-v1", "recall_1_15m": 0.62, "recall_5_15m": 0.84}],
        "recomendado": {"LOC_SIM_MIN": 0.5, "LOC_SIM_ALTA": 0.78, "corte_alta": 0.7,
                        "corte_media": 0.45},
    }  # fmt: skip
    datos.update(cambios)
    return datos


class ErrorS3(Exception):
    def __init__(self, codigo):
        super().__init__(codigo)
        self.response = {"Error": {"Code": codigo}}


class S3Falso:
    def __init__(self, objetos: dict[str, bytes]):
        self.objetos = objetos
        self.escrituras = 0

    def list_objects_v2(self, Bucket, Prefix, Delimiter=None, ContinuationToken=None):
        assert Bucket == "campus-locator-dev-dataset-648617469176"
        claves = sorted(k for k in self.objetos if k.startswith(Prefix))
        if Delimiter:
            prefijos = sorted({Prefix + k[len(Prefix) :].split(Delimiter)[0] + Delimiter
                               for k in claves if Delimiter in k[len(Prefix) :]})  # fmt: skip
            return {"CommonPrefixes": [{"Prefix": p} for p in prefijos]}
        inicio = int(ContinuationToken or 0)  # páginas de 20 para probar la paginación
        pagina = claves[inicio : inicio + 20]
        truncada = inicio + 20 < len(claves)
        return {"Contents": [{"Key": k} for k in pagina], "IsTruncated": truncada,
                **({"NextContinuationToken": str(inicio + 20)} if truncada else {})}  # fmt: skip

    def head_object(self, Bucket, Key):
        if Key not in self.objetos:
            raise ErrorS3("404")
        return {}

    def get_object(self, Bucket, Key):
        if Key not in self.objetos:
            raise ErrorS3("NoSuchKey")
        return {"Body": io.BytesIO(self.objetos[Key])}

    def put_object(self, **_):  # nunca debe llamarse
        self.escrituras += 1


class SecretosFalso:
    def get_secret_value(self, SecretId):
        assert SecretId == "campus-locator/dev/admin-inicial"
        return {"SecretString": json.dumps({"correo": "admin@campus.edu.co", "password": "x"})}


class SesionFalsa:
    def __init__(self, s3):
        self.clientes = {"s3": s3, "secretsmanager": SecretosFalso()}

    def client(self, nombre):
        return self.clientes[nombre]


class Respuesta:
    def __init__(self, estado, cuerpo):
        self.status_code, self._cuerpo = estado, cuerpo

    def json(self):
        return self._cuerpo


class ClienteFalso:
    """Lo que validate32 usa de evaluacion.fuentes.ClienteBackend."""

    estado_vecinos = 200
    videos_reales = True
    instancias: ClassVar[list] = []

    def __init__(self, url, correo, password):
        self.url, self.correo = url, correo
        ClienteFalso.instancias.append(self)

    login_estado = 200

    def token(self):
        if self.login_estado != 200:
            raise ErrorFuente(f"POST /auth/login → {self.login_estado}", self.login_estado)
        return "tok"

    def videos(self):
        nombre = "Entrada norte" if self.videos_reales else "validacion-20261105"
        return [{"id": "v1", "nombre": nombre, "conteo": {"procesada": 30}}]

    def imagenes(self):
        return [ImagenDataset(f"i{i}", LAT0 + 0.001 * i, LNG0) for i in range(1, 11)]

    def vecinos_crudo(self, foto, k):
        assert foto[:2] == b"\xff\xd8" and k == 5
        if self.estado_vecinos == 200:
            return Respuesta(200, {"version_vector": "dinov2-vits14/pp-v1", "k": 5,
                                   "vecinos": [{"imagen_id": "i1"}]})  # fmt: skip
        codigo = {503: "EMBEDDING_NO_DISPONIBLE", 404: "NO_ENCONTRADO"}[self.estado_vecinos]
        return Respuesta(self.estado_vecinos, {"error": {"codigo": codigo}})


def objetos(conjunto=None, informe_=None, sin_fotos=()) -> dict[str, bytes]:
    conjunto = conjunto or puntos_json()
    salida = {f"evaluacion/{VERSION}/puntos.json": json.dumps(conjunto).encode()}
    for f in conjunto["fotos"]:
        if f["archivo"] not in sin_fotos:
            salida[f"evaluacion/{VERSION}/{f['archivo']}"] = b"\xff\xd8jpeg"
    if informe_ is not False:
        salida[CLAVE_INFORME] = json.dumps(informe_ or informe()).encode()
    return salida


@pytest.fixture
def entorno(monkeypatch):
    def preparar(
        objetos_s3=None, estado_vecinos=200, videos_reales=True, variables=True, login=200
    ):
        s3 = S3Falso(objetos() if objetos_s3 is None else objetos_s3)
        monkeypatch.setattr(validate32, "sesion_aws", lambda: SesionFalsa(s3))
        monkeypatch.setattr(ClienteFalso, "estado_vecinos", estado_vecinos)
        monkeypatch.setattr(ClienteFalso, "videos_reales", videos_reales)
        monkeypatch.setattr(ClienteFalso, "login_estado", login)
        monkeypatch.setattr(ClienteFalso, "instancias", [])
        monkeypatch.setattr(validate32, "ClienteBackend", ClienteFalso)
        monkeypatch.delenv("VALIDACION_ADMIN_CORREO", raising=False)
        monkeypatch.delenv("VALIDACION_ADMIN_PASSWORD", raising=False)
        if variables:
            monkeypatch.setenv("VALIDACION_API_URL", "https://api.ejemplo/v1")
        else:
            monkeypatch.delenv("VALIDACION_API_URL", raising=False)
        return s3

    return preparar


def correr(tmp_path) -> tuple[int, dict]:
    ruta = tmp_path / "informe.json"
    codigo = comun.ejecutar(validate32.LOTE, ["--entorno", "dev", "--informe", str(ruta)])
    return codigo, json.loads(ruta.read_text(encoding="utf-8"))


def estados(informe_: dict, clave: str) -> dict:
    return {p["id"]: (p["estado"], p["detalle"]) for p in informe_[clave]}


def test_recorrido_completo_pasa(entorno, tmp_path):
    s3 = entorno()
    codigo, inf = correr(tmp_path)
    assert codigo == 0, inf
    assert [p["estado"] for p in inf["precondiciones"]] == ["pasa"] * 5
    c = estados(inf, "comprobaciones")
    assert "50 fotos en 10 puntos con dataset" in c["C1"][1] and "P11" in c["C1"][1]
    assert "recall@1 0.62" in c["C2"][1] and "LOC_SIM_MIN 0.5" in c["C2"][1]
    assert [m["id"] for m in inf["manuales"]] == ["C3"]
    assert ClienteFalso.instancias[0].correo == "admin@campus.edu.co"  # del secreto
    assert s3.escrituras == 0


def test_embedding_apagado_no_bloquea_p2b(entorno, tmp_path):
    entorno(estado_vecinos=503)
    codigo, inf = correr(tmp_path)
    assert codigo == 0
    assert "EMBEDDING_NO_DISPONIBLE" in estados(inf, "precondiciones")["P2b"][1]


@pytest.mark.parametrize(
    ("preparacion", "id_", "texto"),
    [
        ({"estado_vecinos": 404}, "P2b", "BE-2.4"),
        ({"videos_reales": False}, "P2", "FE-2.1 + BE-2.2"),
        ({"objetos_s3": {}}, "P3", "no hay ningún conjunto"),
    ],
)
def test_lo_que_falta_de_otros_lotes_bloquea(entorno, tmp_path, preparacion, id_, texto):
    entorno(**preparacion)
    codigo, inf = correr(tmp_path)
    assert codigo == 2
    estado, detalle = estados(inf, "precondiciones")[id_]
    assert estado == "falla" and texto in detalle


@pytest.mark.parametrize(
    ("preparacion", "codigo_esperado", "texto"),
    [
        ({"variables": False}, 3, "VALIDACION_API_URL"),
        ({"login": 401}, 3, "credenciales de admin rechazadas"),
        ({"login": 404}, 2, "BE-1.3"),
    ],
)
def test_url_o_login_del_backend(entorno, tmp_path, preparacion, codigo_esperado, texto):
    entorno(**preparacion)
    codigo, inf = correr(tmp_path)
    assert codigo == codigo_esperado
    assert texto in estados(inf, "precondiciones")["P2"][1]


@pytest.mark.parametrize(
    ("objetos_s3", "texto"),
    [
        (objetos(sin_fotos=("fotos/P02/3.jpg",)), "no están en el bucket"),
        (objetos(conjunto=puntos_json(con_lejano=False)), "150 m"),
        (objetos(conjunto=puntos_json(fotos_por_punto=4), informe_=informe(fotos=40)),
         "mínimo 50"),
    ],
)  # fmt: skip
def test_c1_falla_si_el_conjunto_no_cumple(entorno, tmp_path, objetos_s3, texto):
    entorno(objetos_s3=objetos_s3)
    codigo, inf = correr(tmp_path)
    assert codigo == 1
    estado, detalle = estados(inf, "comprobaciones")["C1"]
    assert estado == "falla" and texto in detalle


@pytest.mark.parametrize(
    ("informe_", "texto"),
    [
        (False, "no hay informe"),
        (informe(fotos=53), "fotos=53"),
        (informe(recall_1_15m=0.9, recall_5_15m=0.5), "> recall_5_15m"),
        (informe(recomendado={"LOC_SIM_MIN": 0.5}), "recomendado sin"),
    ],
)
def test_c2_falla_si_el_informe_no_cumple(entorno, tmp_path, informe_, texto):
    entorno(objetos_s3=objetos(informe_=informe_))
    codigo, inf = correr(tmp_path)
    assert codigo == 1
    c = estados(inf, "comprobaciones")
    assert c["C1"][0] == "pasa"
    assert c["C2"][0] == "falla" and texto in c["C2"][1]


def test_validate32_cubre_lo_que_declara_su_documento():
    documento = (PROYECTO.parent / "docs" / "validation" / "validation-3-2.md").read_text(
        encoding="utf-8"
    )
    filas = re.findall(r"^\| ([PC]\d[a-z]?) \|", documento, flags=re.MULTILINE)
    precondiciones = [p.id for p in validate32.LOTE.precondiciones]
    automaticas = [p.id for p in validate32.LOTE.comprobaciones]
    manuales = [m.id for m in validate32.LOTE.manuales]
    assert precondiciones == ["P4", "P1", "P2", "P2b", "P3"]  # orden de evaluación (§1)
    assert filas == sorted(precondiciones) + automaticas + manuales
    assert automaticas == ["C1", "C2"] and manuales == ["C3"]
    assert validate32.LOTE.entornos == {"dev"}
    assert validate32.BUCKET in documento and validate32.SECRETO_ADMIN in documento


def test_validate32_y_la_herramienta_comparten_el_nombre_del_informe():
    nombre = cli.nombre_informe("dinov2-vits14/pp-v1", "20261105")
    assert validate32.PATRON_INFORME.match(f"evaluacion/{VERSION}/informes/{nombre}")
    assert cli.VERSION_VECTOR == comun.VERSION_VECTOR
