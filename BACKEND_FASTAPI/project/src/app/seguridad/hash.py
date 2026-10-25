"""Hash de contraseñas con argon2id (ARCHITECTURE §4.4, §5.7 `usuarios.hash_password`).

Parámetros por defecto de `argon2-cffi` (RFC 9106, perfil de baja memoria: 64 MiB, 3 pasadas, 4 hilos), que caben en
la tarea de 0,5 GB. El hash guarda sus parámetros: si se cambian, los hashes viejos se siguen verificando.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


def calcular(password: str) -> str:
    """Hash argon2id de `password` (con sal aleatoria). Nunca registrar ni el texto ni el hash."""
    return _hasher.hash(password)


def verificar(hash_guardado: str, password: str) -> bool:
    """`True` si `password` corresponde al hash. Un hash mal formado cuenta como «no corresponde»."""
    try:
        return _hasher.verify(hash_guardado, password)
    except (VerificationError, InvalidHashError):
        return False
