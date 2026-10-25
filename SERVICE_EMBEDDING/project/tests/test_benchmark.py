"""tools/benchmark.py (EMB-3.1; ARCHITECTURE §4.4, §5.9 y ADR-EMB-13).

La medida real necesita los pesos y la CPU de `dev`; aquí se prueba lo demás: imágenes, cuerpo
multipart (lo lee el propio servicio), percentiles, límites del contenedor y el bucle completo
contra el servicio HTTP real con un modelo falso, cuya salida debe aceptar validate31.
"""

from __future__ import annotations

import io
import json
import socket
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import uvicorn
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "ops"))

import validate31

import benchmark
from app.config import DIM, Settings
from app.main import crear_app, leer_imagenes
from app.preproceso import preprocesar


def test_imagen_sintetica_es_como_una_foto_de_localize():
    datos = benchmark.imagen_sintetica(0)
    imagen = Image.open(io.BytesIO(datos))
    assert (imagen.format, imagen.size) == ("JPEG", (1024, 768))
    # Peso de una foto real de 1024 px en calidad 85, no ruido puro ni un color plano.
    assert 80_000 < len(datos) < 450_000
    assert preprocesar(datos).shape == (3, 224, 224)
    assert benchmark.imagen_sintetica(0) == datos  # semilla fija
    assert benchmark.imagen_sintetica(1) != datos


def test_el_servicio_lee_el_cuerpo_multipart():
    imagenes = [benchmark.imagen_sintetica(s, 128, 96) for s in range(5)]
    cuerpo, tipo = benchmark.cuerpo_multipart(imagenes)
    partes = leer_imagenes(cuerpo, tipo, 8)
    assert [p.datos for p in partes] == imagenes
    assert {p.tipo for p in partes} == {"image/jpeg"}


@pytest.mark.parametrize(
    ("valores", "p50", "p95"),
    [
        ([5.0], 5.0, 5.0),
        (list(range(1, 21)), 10, 19),  # ⌈0,5·20⌉ = 10 y ⌈0,95·20⌉ = 19
        (list(range(60, 0, -1)), 30, 57),  # desordenados
    ],
)
def test_percentil_por_rango_mas_cercano(valores, p50, p95):
    assert benchmark.percentil(valores, 50) == p50
    assert benchmark.percentil(valores, 95) == p95


def test_argumentos_por_defecto_y_validacion(monkeypatch):
    monkeypatch.setenv("TORCH_NUM_THREADS", "2")
    args = benchmark.argumentos([])
    assert args.lotes == [1, 4, 5, 8]
    assert args.repeticiones == [40, 30, 60, 30]
    assert (args.hilos, args.calentamiento, args.prioridad) == (2, 3, "alta")
    assert benchmark.argumentos(["--lotes", "1,5", "--repeticiones", "7"]).repeticiones == [7, 7]
    for malos in (
        ["--lotes", "9"],
        ["--lotes", "1,5", "--repeticiones", "1,2,3"],
        ["--hilos", "0"],
    ):
        with pytest.raises(SystemExit):
            benchmark.argumentos(malos)


def test_limites_del_cgroup_v2_y_v1(tmp_path):
    v2 = tmp_path / "v2"
    v2.mkdir()
    (v2 / "cpu.max").write_text("200000 100000\n")
    (v2 / "memory.max").write_text(f"{4 * 2**30}\n")
    assert benchmark.limites_cgroup(v2) == (2, 4096)
    (v2 / "cpu.max").write_text("max 100000\n")
    (v2 / "memory.max").write_text("max\n")
    assert benchmark.limites_cgroup(v2) == (None, None)

    v1 = tmp_path / "v1"
    (v1 / "cpu").mkdir(parents=True)
    (v1 / "memory").mkdir()
    (v1 / "cpu" / "cpu.cfs_quota_us").write_text("150000\n")
    (v1 / "cpu" / "cpu.cfs_period_us").write_text("100000\n")
    (v1 / "memory" / "memory.limit_in_bytes").write_text(f"{2**30}\n")
    assert benchmark.limites_cgroup(v1) == (1.5, 1024)
    assert benchmark.limites_cgroup(tmp_path / "no-existe") == (None, None)


def test_limites_de_ecs_sin_endpoint():
    assert benchmark.limites_ecs(None) is None
    assert benchmark.limites_ecs("http://127.0.0.1:9/v4/no-hay") is None


# --- Bucle completo contra el servicio HTTP con un modelo falso ---------------------------------


class ModeloFalso:
    def cargar(self) -> None: ...

    def calentar(self) -> None: ...

    def inferir(self, lote: np.ndarray) -> np.ndarray:
        time.sleep(0.002 * len(lote))
        vectores = np.zeros((len(lote), DIM), dtype=np.float32)
        vectores[:, 0] = 1.0
        return vectores


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def servicio_falso():
    settings = Settings(app_env="test", torch_num_threads=1, git_commit="a" * 40)
    app = crear_app(
        settings=settings, fabrica_modelo=lambda _: ModeloFalso(), configurar_registro=False
    )
    puerto = _puerto_libre()
    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="warning", access_log=False)
    )
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{puerto}"
    servidor.should_exit = True
    hilo.join(10)


def test_salida_json_contra_el_servicio_y_validate31_la_acepta(servicio_falso, capsys):
    codigo = benchmark.main(
        ["--url", servicio_falso, "--salida", "json", "--lotes", "1,5,8", "--repeticiones", "20",
         "--calentamiento", "1"]
    )  # fmt: skip
    salida = capsys.readouterr()
    assert codigo == 0
    lineas = [ln for ln in salida.out.splitlines() if ln.startswith(benchmark.PREFIJO_JSON)]
    assert len(lineas) == 1 and len(lineas[0]) < 4096  # una línea, escritura atómica en el log
    datos = validate31.extraer_resultado(["otra línea", lineas[0]])
    assert datos["commit"] == "aaaaaaa"
    assert [r["lote"] for r in datos["resultados"]] == [1, 5, 8]
    assert {r["repeticiones"] for r in datos["resultados"]} == {20}
    for r in datos["resultados"]:
        assert 0 < r["p50_ms"] <= r["p95_ms"] <= r["max_ms"]
        assert r["inferencia_p50_ms"] <= r["p50_ms"]
    assert datos["hilos"] is None and datos["memoria_proceso_mb"] is None  # --url
    assert datos["imagen"]["ancho"] == 1024 and datos["preproceso_ms_por_imagen"] > 0
    assert validate31.revisar_resultado(datos, "a" * 40) == []
    # El progreso va a stderr en JSON por línea, como el log del servicio.
    eventos = [json.loads(ln)["evento"] for ln in salida.err.splitlines() if ln.startswith("{")]
    assert eventos[0] == "benchmark_inicio" and eventos.count("benchmark_lote") == 3


def test_salida_de_texto(servicio_falso, capsys):
    codigo = benchmark.main(["--url", servicio_falso, "--lotes", "1", "--repeticiones", "2"])
    assert codigo == 0
    assert "p95_ms" in capsys.readouterr().out


def test_sin_servicio_termina_con_1(capsys):
    codigo = benchmark.main(
        ["--url", f"http://127.0.0.1:{_puerto_libre()}", "--lotes", "1", "--plazo-arranque", "0"]
    )
    assert codigo == 1
    assert "benchmark_fallido" in capsys.readouterr().err
