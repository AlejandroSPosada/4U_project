"""Contrato común de los validadores (infra §5.11): estados, códigos de salida e informe."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "ops"))

import comun
from comun import (
    ErrorConfiguracion,
    Falla,
    Lote,
    Manual,
    Paso,
    PrecondicionNoCumplida,
    entornos,
)

AMBOS = entornos("local", "dev")


def pasa(_ctx):
    return "bien"


def falla(_ctx):
    raise Falla("mal")


def bloquea(_ctx):
    raise PrecondicionNoCumplida("INF-1.3 no está hecho")


def sin_credenciales(_ctx):
    raise ErrorConfiguracion("falta AWS_PROFILE")


def lote(precondiciones=(), comprobaciones=(), limpiezas=None, manuales=()):
    def limpiar(_ctx):
        if limpiezas is not None:
            limpiezas.append(1)

    return Lote(
        lote="EMB-9.9",
        validacion="validation-9-9",
        entornos=AMBOS,
        precondiciones=list(precondiciones),
        comprobaciones=list(comprobaciones),
        manuales=list(manuales),
        limpiar=limpiar,
    )


def correr(tmp_path, lote_, *extra):
    informe = tmp_path / "informe.json"
    codigo = comun.ejecutar(lote_, ["--entorno", "local", "--informe", str(informe), *extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def test_todo_pasa_da_0_y_un_informe_completo(tmp_path):
    limpiezas = []
    codigo, informe = correr(
        tmp_path,
        lote(
            [Paso("P1", AMBOS, pasa)],
            [Paso("C1", AMBOS, pasa), Paso("C2", entornos("dev"), falla)],
            limpiezas,
            [Manual("C3", "revisar a mano")],
        ),
    )
    assert codigo == 0
    assert informe["resultado"] == "pasa"
    assert set(informe) == {
        "lote", "validacion", "entorno", "commit", "inicio", "fin", "resultado",
        "precondiciones", "comprobaciones", "manuales",
    }  # fmt: skip
    assert [(c["id"], c["estado"]) for c in informe["comprobaciones"]] == [
        ("C1", "pasa"),
        ("C2", "omitida"),
    ]
    assert informe["manuales"] == [{"id": "C3", "instruccion": "revisar a mano"}]
    assert limpiezas == [1]


def test_una_comprobacion_que_falla_da_1_y_sigue_con_las_demas(tmp_path):
    codigo, informe = correr(
        tmp_path, lote([], [Paso("C1", AMBOS, falla), Paso("C2", AMBOS, pasa)])
    )
    assert codigo == 1
    assert [c["estado"] for c in informe["comprobaciones"]] == ["falla", "pasa"]


def test_precondicion_de_otro_lote_da_2_y_no_ejecuta_comprobaciones(tmp_path):
    limpiezas = []
    codigo, informe = correr(
        tmp_path,
        lote(
            [Paso("P1", AMBOS, bloquea), Paso("P2", AMBOS, pasa)],
            [Paso("C1", AMBOS, pasa)],
            limpiezas,
        ),
    )
    assert codigo == 2
    assert informe["resultado"] == "bloqueado"
    assert [p["estado"] for p in informe["precondiciones"]] == ["falla", "omitida"]
    assert informe["comprobaciones"][0]["estado"] == "omitida"
    assert limpiezas == [1]


def test_falta_de_credenciales_da_3(tmp_path):
    codigo, informe = correr(tmp_path, lote([Paso("P1", AMBOS, sin_credenciales)], []))
    assert codigo == 3
    assert informe["resultado"] == "error"


def test_error_inesperado_en_una_comprobacion_es_falla(tmp_path):
    def explota(_ctx):
        raise ValueError("inesperado")

    codigo, informe = correr(tmp_path, lote([], [Paso("C1", AMBOS, explota)]))
    assert codigo == 1
    assert "ValueError" in informe["comprobaciones"][0]["detalle"]


def test_solo_selecciona_subcomprobaciones(tmp_path):
    codigo, informe = correr(
        tmp_path,
        lote([], [Paso("C1a", AMBOS, pasa), Paso("C1b", AMBOS, pasa), Paso("C2", AMBOS, falla)]),
        "--solo",
        "C1",
    )
    assert codigo == 0
    assert [c["estado"] for c in informe["comprobaciones"]] == ["pasa", "pasa", "omitida"]


def test_solo_con_un_id_desconocido_da_3(tmp_path):
    codigo, _ = correr(tmp_path, lote([], [Paso("C1", AMBOS, pasa)]), "--solo", "C9")
    assert codigo == 3


def test_sin_limpieza(tmp_path):
    limpiezas = []
    correr(tmp_path, lote([], [Paso("C1", AMBOS, pasa)], limpiezas), "--sin-limpieza")
    assert limpiezas == []


def test_revision_architecture_lee_la_fila_de_la_seccion_5_3():
    assert len(comun.revision_architecture()) == 40


def test_revision_architecture_falla_si_no_esta_anotada(tmp_path, monkeypatch):
    doc = tmp_path / "ARCHITECTURE.md"
    doc.write_text("| Revisión | SHA de commit fijo; se elige en EMB-1.1 |\n", encoding="utf-8")
    monkeypatch.setattr(comun, "ARCHITECTURE", doc)
    with pytest.raises(Falla):
        comun.revision_architecture()


def test_validate11_cubre_lo_que_declara_su_documento():
    import validate11

    documento = (comun.DIR_PROYECTO.parent / "docs" / "validation" / "validation-1-1.md").read_text(
        encoding="utf-8"
    )
    pasos = [*validate11.LOTE.precondiciones, *validate11.LOTE.comprobaciones]
    assert sorted(p.id for p in validate11.LOTE.precondiciones) == ["P1", "P2", "P3", "P4"]
    assert [p.id for p in validate11.LOTE.comprobaciones] == ["C1a", "C1b", "C2", "C3"]
    for paso in pasos:
        assert f"| {paso.id} |" in documento


def test_validate21_cubre_lo_que_declara_su_documento():
    import validate21

    documento = (comun.DIR_PROYECTO.parent / "docs" / "validation" / "validation-2-1.md").read_text(
        encoding="utf-8"
    )
    filas = re.findall(r"^\| ([PC]\d[a-z]?) \|", documento, flags=re.MULTILINE)
    assert [p.id for p in validate21.LOTE.precondiciones] == ["P1", "P2", "P3"]
    assert [p.id for p in validate21.LOTE.comprobaciones] == [
        "C1", "C2", "C3", "C4", "C5a", "C5b", "C5c",
    ]  # fmt: skip
    assert filas == [
        p.id for p in (*validate21.LOTE.precondiciones, *validate21.LOTE.comprobaciones)
    ]
    assert validate21.LOTE.entornos == {"local"}


def test_validate21_usa_los_parametros_del_servicio(monkeypatch):
    import validate21

    from app.config import DIM, VERSION_VECTOR, Settings

    for variable in ("LOTE_MAX", "BYTES_MAX_IMAGEN", "BYTES_MAX_PETICION", "COLA_MAX_IMAGENES"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.delenv("RETRY_AFTER_S", raising=False)
    settings = Settings()
    assert settings.lote_max == validate21.LOTE_MAX
    assert settings.bytes_max_imagen == validate21.BYTES_MAX_IMAGEN
    assert settings.bytes_max_peticion == validate21.BYTES_MAX_PETICION
    assert settings.cola_max_imagenes == validate21.COLA_MAX_IMAGENES
    assert str(settings.retry_after_s) == validate21.RETRY_AFTER_S
    assert (validate21.DIM, validate21.VERSION_VECTOR) == (DIM, VERSION_VECTOR)


def test_imagenes_de_prueba_de_validate21():
    import validate21

    from app.preproceso import ImagenInvalida, preprocesar

    assert preprocesar(validate21.sintetica(1)).shape == (3, 224, 224)
    with pytest.raises(ImagenInvalida):
        preprocesar(validate21.jpeg_truncado())
    assert validate21.gif().startswith(b"GIF8")
    # C5a: una de más de 4 MB y cinco de menos de 4 MB que juntas pasan de 16 MB.
    assert len(validate21.ruido_png(1300, 1)) > validate21.BYTES_MAX_IMAGEN
    medianas = [len(validate21.ruido_png(1100, s)) for s in range(5)]
    assert max(medianas) < validate21.BYTES_MAX_IMAGEN
    assert sum(medianas) > validate21.BYTES_MAX_PETICION
    # C4: 4 × 8 + 1 = 33 imágenes caben en la cola aunque cuente el lote en curso; C5c no.
    assert 4 * 8 + 1 <= validate21.COLA_MAX_IMAGENES < 8 * 8 - 8
    # Las doradas que usan C1 y C2 son las versionadas.
    assert len(validate21.doradas()) == 5


def test_imagenes_de_ecr():
    assert comun.es_imagen_ecr(
        "648617469176.dkr.ecr.us-east-1.amazonaws.com/campus-locator/embedding:" + "a" * 40
    )
    assert not comun.es_imagen_ecr("campus-locator/embedding:local")
