"""Partes del validador de BE-1.1 que no necesitan AWS."""

from __future__ import annotations

import pytest

import validate11

SHA = "0123456789abcdef0123456789abcdef01234567"
REPO = "648617469176.dkr.ecr.us-east-1.amazonaws.com/campus-locator/backend"


@pytest.mark.parametrize(
    ("imagen", "etiqueta"),
    [
        (f"{REPO}:{SHA}", SHA),
        (f"{REPO}:bootstrap", "bootstrap"),
        (REPO, None),
        (f"{REPO}@sha256:abcd", None),
        ("localhost:5000/backend:v1", "v1"),
    ],
)
def test_etiqueta_de_la_imagen(imagen, etiqueta):
    assert validate11._etiqueta(imagen) == etiqueta


def test_solo_admite_dev():
    with pytest.raises(SystemExit) as salida:
        validate11.main(["--entorno", "local"])
    assert salida.value.code == 3


def test_sin_aws_profile_termina_con_3(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    assert validate11.main(["--entorno", "dev", "--informe", str(tmp_path / "i.json")]) == 3
