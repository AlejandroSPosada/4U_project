"""validate31.py (EMB-3.1) con dobles de ECS y CloudWatch Logs: no toca AWS.

Cubre el recorrido completo (P3 → P2 → P1 → C1a → C1b → limpieza), los bloqueos de P1 (imagen
`bootstrap` o con el benchmark provisional, que no lanzan ninguna tarea), el fallo de la tarea y
la coherencia con validation-3-1.md y con PLAN §3.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# botocore viene del grupo `ops`; CI (`embedding.yml`) instala solo `dev`, así que allí se omite.
ClientError = pytest.importorskip("botocore.exceptions").ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "ops"))

import validate31

import comun

SHA = "b" * 40
IMAGEN_CI = f"648617469176.dkr.ecr.us-east-1.amazonaws.com/campus-locator/embedding:{SHA}"
ARN_TD = "arn:aws:ecs:us-east-1:648617469176:task-definition/campus-locator-dev-embedding:5"
ARN_TAREA = "arn:aws:ecs:us-east-1:648617469176:task/campus-locator-dev/0f3c9a1e"
RED = {"awsvpcConfiguration": {"subnets": ["subnet-1"], "securityGroups": ["sg-1"],
                               "assignPublicIp": "ENABLED"}}  # fmt: skip


def resultado_benchmark(**cambios) -> dict:
    datos = {
        "version_vector": "dinov2-vits14/pp-v1", "commit": SHA[:7], "hilos": 2, "vcpu": 2,
        "memoria_mb": 4096, "limites_de": "ecs", "cpu": "Intel Xeon",
        "capacidad_cpu_torch": "AVX512",
        "memoria_proceso_mb": {"reposo": 700, "final": 800, "pico": 900},
        "resultados": [
            {"lote": lote, "repeticiones": 30, "p50_ms": 100 * lote, "p95_ms": 110 * lote}
            for lote in (1, 4, 5, 8)
        ],
    }  # fmt: skip
    datos.update(cambios)
    return datos


class ECSFalso:
    def __init__(self, imagen=IMAGEN_CI, salida=0, cpu="2048"):
        self.imagen, self.salida, self.cpu = imagen, salida, cpu
        self.lanzadas: list[dict] = []
        self.detenidas: list[str] = []

    def describe_clusters(self, clusters):
        return {"clusters": [{"status": "ACTIVE"}]}

    def describe_task_definition(self, taskDefinition):
        return {
            "taskDefinition": {
                "taskDefinitionArn": ARN_TD, "family": "campus-locator-dev-embedding",
                "revision": 5,
                "containerDefinitions": [{
                    "name": "app", "image": self.imagen,
                    "logConfiguration": {"options": {"awslogs-stream-prefix": "embedding"}},
                }],
            }
        }  # fmt: skip

    def describe_services(self, cluster, services):
        return {
            "failures": [],
            "services": [{"taskDefinition": ARN_TD, "networkConfiguration": RED}],
        }

    def run_task(self, **pedido):
        self.lanzadas.append(pedido)
        return {"failures": [], "tasks": [{"taskArn": ARN_TAREA}]}

    def describe_tasks(self, cluster, tasks):
        inicio = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
        return {
            "tasks": [{
                "lastStatus": "STOPPED", "taskDefinitionArn": ARN_TD, "cpu": self.cpu,
                "memory": "4096", "stopCode": "EssentialContainerExited",
                "containers": [{"name": "app", "exitCode": self.salida}],
                "pullStartedAt": inicio, "pullStoppedAt": inicio + timedelta(seconds=70),
                "startedAt": inicio + timedelta(seconds=75),
                "stoppedAt": inicio + timedelta(seconds=275),
            }]
        }  # fmt: skip

    def stop_task(self, cluster, task, reason):
        self.detenidas.append(task)

    def get_paginator(self, nombre):
        class Paginador:
            def paginate(self, **_):
                return [{"taskArns": []}]

        return Paginador()


class LogsFalso:
    class exceptions:  # imita el atributo `exceptions` de un cliente de boto3
        class ResourceNotFoundException(Exception):
            pass

    def __init__(self, mensajes):
        self.mensajes = mensajes
        self.streams: list[str] = []

    def describe_log_groups(self, logGroupNamePrefix):
        return {"logGroups": [{"logGroupName": "/campus-locator/dev/embedding"}]}

    def get_log_events(self, logGroupName, logStreamName, startFromHead, nextToken=None):
        self.streams.append(logStreamName)
        if nextToken is None:  # dos páginas para probar la paginación
            return {"events": [{"message": m} for m in self.mensajes[:1]], "nextForwardToken": "f1"}
        if nextToken == "f1":
            return {"events": [{"message": m} for m in self.mensajes[1:]], "nextForwardToken": "f2"}
        return {"events": [], "nextForwardToken": nextToken}


class SesionFalsa:
    def __init__(self, ecs, logs):
        self.clientes = {"ecs": ecs, "logs": logs}

    def client(self, nombre):
        return self.clientes[nombre]


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    def preparar(ecs=None, mensajes=None, benchmark_real=True):
        ecs = ecs or ECSFalso()
        if mensajes is None:
            mensajes = ['{"evento": "modelo_listo"}',
                        validate31.PREFIJO_JSON + json.dumps(resultado_benchmark())]  # fmt: skip
        logs = LogsFalso(mensajes)
        monkeypatch.setattr(validate31, "sesion_aws", lambda: SesionFalsa(ecs, logs))
        monkeypatch.setattr(
            validate31,
            "archivo_en_commit",
            lambda sha, ruta: 'PREFIJO_JSON = "BENCHMARK_JSON "' if benchmark_real else "pendiente",
        )
        monkeypatch.setattr(validate31, "DIR_INFORMES", tmp_path)
        monkeypatch.setattr(validate31, "PAUSA_TAREA_S", 0)
        monkeypatch.setattr(validate31, "PLAZO_LOG_S", 0)
        return ecs, logs

    return preparar


def correr(tmp_path) -> tuple[int, dict]:
    informe = tmp_path / "informe.json"
    codigo = comun.ejecutar(validate31.LOTE, ["--entorno", "dev", "--informe", str(informe)])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def test_recorrido_completo_pasa(entorno, tmp_path):
    ecs, logs = entorno()
    codigo, informe = correr(tmp_path)
    assert codigo == 0, informe
    assert [(p["id"], p["estado"]) for p in informe["precondiciones"]] == [
        ("P1", "pasa"), ("P2", "pasa"), ("P3", "pasa")
    ]  # fmt: skip
    lanzada = ecs.lanzadas[0]
    assert lanzada["launchType"] == "FARGATE" and lanzada["startedBy"] == "validacion-emb31"
    assert lanzada["networkConfiguration"] == RED and lanzada["taskDefinition"] == ARN_TD
    assert lanzada["overrides"] == {
        "containerOverrides": [
            {"name": "app", "command": ["python", "tools/benchmark.py", "--salida", "json"]}
        ]
    }
    assert logs.streams[0] == "embedding/app/0f3c9a1e"
    c1a, c1b = informe["comprobaciones"]
    assert "descarga de la imagen 70 s, ejecución 200 s" in c1a["detalle"]
    assert "lote 5: p50 500 ms, p95 550 ms" in c1b["detalle"]
    assert "no aplica" in c1b["detalle"]
    assert (tmp_path / "EMB-3.1-benchmark-0f3c9a1e.json").is_file()
    assert [m["id"] for m in informe["manuales"]] == ["C2", "C3"]
    assert ecs.detenidas == []  # ya estaba STOPPED: la limpieza no la vuelve a detener


def test_p95_del_lote_5_por_encima_del_objetivo_pide_c3(entorno, tmp_path):
    datos = resultado_benchmark()
    datos["resultados"][2]["p95_ms"] = 950
    entorno(mensajes=[validate31.PREFIJO_JSON + json.dumps(datos)])
    codigo, informe = correr(tmp_path)
    assert codigo == 0  # C1 solo exige medir; la decisión es C3 (manual)
    assert "950 ms > 800 ms" in informe["comprobaciones"][1]["detalle"]


@pytest.mark.parametrize(
    ("imagen", "benchmark_real", "motivo"),
    [
        ("648617469176.dkr.ecr.us-east-1.amazonaws.com/campus-locator/embedding:bootstrap", True,
         "no es una imagen de CI"),
        (IMAGEN_CI, False, "provisional"),
    ],
)  # fmt: skip
def test_imagen_sin_benchmark_bloquea_sin_lanzar_nada(
    entorno, tmp_path, imagen, benchmark_real, motivo
):
    ecs, _ = entorno(ecs=ECSFalso(imagen=imagen), benchmark_real=benchmark_real)
    codigo, informe = correr(tmp_path)
    assert codigo == 2
    p1 = next(p for p in informe["precondiciones"] if p["id"] == "P1")
    assert p1["estado"] == "falla" and motivo in p1["detalle"]
    assert ecs.lanzadas == []


def test_tarea_que_falla_da_1_y_muestra_el_log(entorno, tmp_path):
    entorno(ecs=ECSFalso(salida=1), mensajes=['{"evento": "benchmark_fallido", "motivo": "x"}'])
    codigo, informe = correr(tmp_path)
    assert codigo == 1
    c1a, c1b = informe["comprobaciones"]
    assert c1a["estado"] == "falla" and "salida de app=1" in c1a["detalle"]
    assert c1b["estado"] == "falla" and "benchmark_fallido" in c1b["detalle"]


def test_tamano_de_tarea_distinto_falla(entorno, tmp_path):
    entorno(ecs=ECSFalso(cpu="1024"))
    codigo, informe = correr(tmp_path)
    assert codigo == 1
    assert "1024 CPU" in informe["comprobaciones"][0]["detalle"]


def test_familia_inexistente_bloquea(entorno, tmp_path):
    ecs, _ = entorno()

    def no_existe(taskDefinition):
        raise ClientError({"Error": {"Code": "ClientException"}}, "DescribeTaskDefinition")

    ecs.describe_task_definition = no_existe
    codigo, _ = correr(tmp_path)
    assert codigo == 2


def _lotes(repeticiones: int, p50: int, p95: int, lotes=(1, 5, 8)) -> list[dict]:
    return [{"lote": n, "repeticiones": repeticiones, "p50_ms": p50, "p95_ms": p95} for n in lotes]


@pytest.mark.parametrize(
    ("cambios", "error"),
    [
        ({"version_vector": "otra"}, "version_vector"),
        ({"commit": "c0ffee0"}, "no es la imagen desplegada"),
        ({"resultados": _lotes(30, 1, 2, lotes=(1,))}, "falta el lote de 5"),
        ({"resultados": _lotes(30, 9, 5)}, "0 < p50 ≤ p95"),
        ({"resultados": _lotes(30, 0, 5)}, "0 < p50 ≤ p95"),
        ({"resultados": _lotes(10, 1, 2)}, "repeticiones"),
    ],
)
def test_revisar_resultado(cambios, error):
    errores = validate31.revisar_resultado(resultado_benchmark(**cambios), SHA)
    assert any(error in e for e in errores), errores


def test_estado_lote_lee_la_tabla_3_del_plan():
    assert comun.estado_lote("EMB-2.1") == "Hecho"
    assert comun.estado_lote("EMB-3.1") in {"Pendiente", "En curso", "Bloqueado", "Hecho"}
    with pytest.raises(comun.ErrorConfiguracion):
        comun.estado_lote("EMB-9.9")


def test_archivo_en_commit_lee_git():
    if comun.shutil.which("git") is None:
        pytest.skip("sin git")
    try:
        actual = comun.archivo_en_commit("HEAD", "pyproject.toml")
    except comun.ErrorConfiguracion:
        pytest.skip("no es un clon de git")
    assert actual is not None and "campus-locator-embedding" in actual
    assert comun.archivo_en_commit("HEAD", "no-existe.txt") is None
    with pytest.raises(comun.ErrorConfiguracion):
        comun.archivo_en_commit("0" * 40, "pyproject.toml")


def test_validate31_cubre_lo_que_declara_su_documento():
    documento = (comun.DIR_PROYECTO.parent / "docs" / "validation" / "validation-3-1.md").read_text(
        encoding="utf-8"
    )
    filas = re.findall(r"^\| ([PC]\d[a-z]?) \|", documento, flags=re.MULTILINE)
    precondiciones = [p.id for p in validate31.LOTE.precondiciones]
    automaticas = [p.id for p in validate31.LOTE.comprobaciones]
    manuales = [m.id for m in validate31.LOTE.manuales]
    assert precondiciones == ["P3", "P2", "P1"]  # orden de evaluación (§1 de la validación)
    assert filas == ["P1", "P2", "P3", *automaticas, *manuales]
    assert automaticas == ["C1a", "C1b"] and manuales == ["C2", "C3"]
    assert validate31.LOTE.entornos == {"dev"}
    assert " ".join(validate31.COMANDO_BENCHMARK) in documento


def test_validate31_y_benchmark_comparten_el_contrato():
    sys.path.insert(0, str(comun.DIR_PROYECTO / "tools"))
    import benchmark

    assert validate31.PREFIJO_JSON == benchmark.PREFIJO_JSON
    assert set(validate31.LOTES_EXIGIDOS) <= set(benchmark.LOTES)
    assert all(benchmark.REPETICIONES[n] >= validate31.REPETICIONES_MIN for n in benchmark.LOTES)
    assert validate31.PREFIJO_JSON.strip() in (
        comun.DIR_PROYECTO / "tools" / "benchmark.py"
    ).read_text(encoding="utf-8")
