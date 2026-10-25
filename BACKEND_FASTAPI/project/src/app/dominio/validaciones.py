"""Reglas de validación y normalización sin infraestructura (ARCHITECTURE §4.1)."""

from __future__ import annotations


def normalizar_correo(correo: str) -> str:
    """Correo como se guarda y se busca (§4.4, §5.7 `usuarios.correo`): sin espacios alrededor y en minúsculas."""
    return correo.strip().lower()
