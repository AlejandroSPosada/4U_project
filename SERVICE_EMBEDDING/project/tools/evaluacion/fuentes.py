"""De dónde salen los vecinos y el dataset (interfaces enchufables, ARCHITECTURE §5.9).

- `BuscadorVecinos.vecinos(foto, k)`: los `k` vecinos de una foto, de mayor a menor similitud.
  `ClienteBackend` usa `POST /v1/admin/diagnostico/vecinos` (backend §5.5, BE-2.4);
  `BuscadorFuerzaBruta`, vectores calculados aquí (variantes y pruebas).
- `FuenteDataset.imagenes()` / `.descargar(imagen)`: las imágenes indexadas con su coordenada.
  `ClienteBackend` las lista con `GET /v1/admin/videos` y `GET /v1/admin/videos/{id}` (BE-2.1);
  sus bytes solo se pueden bajar cuando BE-4.1 rellene `url`. `FuenteCarpeta`, una carpeta local.

Nunca imprime ni guarda el token ni las URL prefirmadas.
"""

from __future__ import annotations

import io
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image, ImageOps

LADO_MAYOR_PX = 1024  # como las fotos de /v1/localize (backend §5.3, recomendado)
CALIDAD_JPEG = 85
BYTES_MAX_FOTO = 1_572_864  # LOC_MAX_BYTES_FOTO (backend §5.10)
K_POR_DEFECTO = 10  # LOC_TOP_K (backend §5.10): recall usa los 1 y 5 primeros
REINTENTOS = 4
PREFIJO_VALIDACION = "validacion-"  # datos de los validadores (infra §5.11): no son dataset


@dataclass(frozen=True)
class Vecino:
    imagen_id: str
    lat: float
    lng: float
    rumbo: float | None
    similitud: float


@dataclass(frozen=True)
class ImagenDataset:
    imagen_id: str
    lat: float
    lng: float
    rumbo: float | None = None
    video_id: str | None = None
    url: str | None = None  # prefirmada (BE-4.1); nunca se imprime


class BuscadorVecinos(Protocol):
    version_vector: str | None

    def vecinos(self, foto: bytes, k: int) -> list[Vecino]: ...


class FuenteDataset(Protocol):
    def imagenes(self) -> list[ImagenDataset]: ...

    def descargar(self, imagen: ImagenDataset) -> bytes: ...


class ErrorFuente(RuntimeError):
    """Fallo al hablar con el backend o al leer el dataset (mensaje sin secretos)."""

    def __init__(self, mensaje: str, estado: int | None = None) -> None:
        super().__init__(mensaje)
        self.estado = estado  # código HTTP, si lo hubo


class PendienteBE41(ErrorFuente):
    """Las URL GET de las imágenes llegan con BE-4.1 (backend §5.5): hoy son `null`."""


def preparar_foto(datos: bytes) -> bytes:
    """Como una foto de `/v1/localize`: orientación EXIF aplicada, lado mayor ≤ 1024 px, JPEG
    calidad 85 y sin metadatos (se descarta el EXIF, también la posición GPS)."""
    imagen = ImageOps.exif_transpose(Image.open(io.BytesIO(datos))).convert("RGB")
    if max(imagen.size) > LADO_MAYOR_PX:
        escala = LADO_MAYOR_PX / max(imagen.size)
        tamano = (max(1, round(imagen.width * escala)), max(1, round(imagen.height * escala)))
        imagen = imagen.resize(tamano, Image.Resampling.LANCZOS)
    salida = io.BytesIO()
    imagen.save(salida, "JPEG", quality=CALIDAD_JPEG)
    resultado = salida.getvalue()
    if len(resultado) > BYTES_MAX_FOTO:
        raise ErrorFuente(f"la foto reducida pesa {len(resultado)} bytes (> {BYTES_MAX_FOTO})")
    return resultado


# --- Backend (BE-2.1 / BE-2.4) -------------------------------------------------------------------


class ClienteBackend:
    """Cliente mínimo de la API del backend con un token de admin (backend §5.2, §5.5)."""

    def __init__(self, url_base: str, correo: str, password: str, cliente=None) -> None:
        import httpx

        self.url_base = url_base.rstrip("/")
        self._correo, self._password = correo, password
        self._http = cliente or httpx.Client(timeout=60.0)
        self._token: str | None = None
        self.version_vector: str | None = None

    # Peticiones ------------------------------------------------------------------------------
    def _pedir(self, metodo: str, ruta: str, autenticado: bool = True, **kwargs):
        cabeceras = kwargs.pop("headers", {})
        for intento in range(REINTENTOS):
            if autenticado:
                cabeceras["Authorization"] = f"Bearer {self.token()}"
            respuesta = self._http.request(
                metodo, self.url_base + ruta, headers=cabeceras, **kwargs
            )
            reintentable = respuesta.status_code == 429 or (
                respuesta.status_code == 503 and _codigo(respuesta) == "SERVICIO_OCUPADO"
            )
            if reintentable and intento < REINTENTOS - 1:
                time.sleep(_espera(respuesta, intento))
                continue
            return respuesta
        return respuesta  # pragma: no cover (el bucle siempre devuelve)

    def token(self) -> str:
        if self._token is None:
            respuesta = self._pedir(
                "POST",
                "/auth/login",
                autenticado=False,
                json={"identificador": self._correo, "password": self._password},
            )
            if respuesta.status_code != 200:
                raise ErrorFuente(
                    f"POST /auth/login → {respuesta.status_code} {_codigo(respuesta)}",
                    respuesta.status_code,
                )
            self._token = respuesta.json()["token"]
        return self._token

    def _json(self, metodo: str, ruta: str, **kwargs) -> dict:
        respuesta = self._pedir(metodo, ruta, **kwargs)
        if respuesta.status_code != 200:
            raise ErrorFuente(
                f"{metodo} {ruta.split('?')[0]} → {respuesta.status_code} {_codigo(respuesta)}",
                respuesta.status_code,
            )
        return respuesta.json()

    # Dataset (BE-2.1) --------------------------------------------------------------------------
    def videos(self) -> list[dict]:
        """Todos los `VideoResumen` no eliminados, de todas las páginas."""
        videos, pagina = [], 1
        while True:
            datos = self._json("GET", f"/admin/videos?pagina={pagina}&por_pagina=100")
            videos.extend(datos["items"])
            if not datos["items"] or len(videos) >= datos["total"]:
                return videos
            pagina += 1

    def imagenes(self) -> list[ImagenDataset]:
        """Imágenes `procesada` de los videos reales (no `validacion-…`) con su coordenada."""
        imagenes = []
        for video in self.videos():
            if (video.get("nombre") or "").startswith(PREFIJO_VALIDACION):
                continue
            if not (video.get("conteo") or {}).get("procesada"):
                continue
            detalle = self._json("GET", f"/admin/videos/{video['id']}")
            for foto in detalle.get("fotos") or []:
                if foto.get("estado") != "procesada" or foto.get("lat") is None:
                    continue
                imagenes.append(
                    ImagenDataset(
                        foto["id"], float(foto["lat"]), float(foto["lng"]), foto.get("rumbo"),
                        video["id"], foto.get("url"),
                    )
                )  # fmt: skip
        return imagenes

    def descargar(self, imagen: ImagenDataset) -> bytes:
        if not imagen.url:
            raise PendienteBE41(
                "las imágenes del dataset no traen url (llega con BE-4.1, backend §5.5): "
                "la comparación de variantes necesita bajarlas"
            )
        import httpx

        respuesta = httpx.get(imagen.url, timeout=60.0)  # prefirmada: sin token
        if respuesta.status_code != 200:
            raise ErrorFuente(f"descarga de la imagen {imagen.imagen_id} → {respuesta.status_code}")
        return respuesta.content

    # Vecinos (BE-2.4) --------------------------------------------------------------------------
    def vecinos_crudo(self, foto: bytes, k: int = K_POR_DEFECTO):
        """La respuesta HTTP tal cual (la usa validate32 P2b para distinguir 404 de 503)."""
        return self._pedir(
            "POST",
            f"/admin/diagnostico/vecinos?k={k}",
            files={"foto": ("consulta.jpg", foto, "image/jpeg")},
        )

    def vecinos(self, foto: bytes, k: int = K_POR_DEFECTO) -> list[Vecino]:
        respuesta = self.vecinos_crudo(foto, k)
        if respuesta.status_code != 200:
            raise ErrorFuente(
                f"POST /admin/diagnostico/vecinos → {respuesta.status_code} {_codigo(respuesta)}"
                + (
                    " (enciende embedding: infra embedding.py encender)"
                    if _codigo(respuesta) == "EMBEDDING_NO_DISPONIBLE"
                    else ""
                )
            )
        datos = respuesta.json()
        version = datos.get("version_vector")
        if self.version_vector is None:
            self.version_vector = version
        elif version != self.version_vector:
            raise ErrorFuente(f"version_vector cambió a mitad: {self.version_vector} → {version}")
        return [
            Vecino(v["imagen_id"], float(v["lat"]), float(v["lng"]), v.get("rumbo"),
                   float(v["similitud"]))
            for v in datos.get("vecinos") or []
        ]  # fmt: skip


def _codigo(respuesta) -> str:
    try:
        return respuesta.json()["error"]["codigo"]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return ""


def _espera(respuesta, intento: int) -> float:
    try:
        return min(30.0, float(respuesta.headers.get("Retry-After", "")))
    except ValueError:
        return min(30.0, 2.0 * 2**intento)


# --- Fuerza bruta y carpeta local ----------------------------------------------------------------


class BuscadorFuerzaBruta:
    """Vecinos exactos por producto escalar sobre vectores L2-normalizados (coseno)."""

    def __init__(
        self,
        imagenes: Sequence[ImagenDataset],
        vectores: np.ndarray,
        vectorizar: Callable[[bytes], np.ndarray],
        version_vector: str | None = None,
    ) -> None:
        if len(imagenes) != len(vectores):
            raise ValueError("una fila de vectores por imagen")
        self.imagenes = list(imagenes)
        self.vectores = np.asarray(vectores, dtype=np.float32)
        self.vectorizar = vectorizar
        self.version_vector = version_vector

    def vecinos(self, foto: bytes, k: int = K_POR_DEFECTO) -> list[Vecino]:
        if not self.imagenes:
            return []
        consulta = np.asarray(self.vectorizar(foto), dtype=np.float32).reshape(-1)
        similitudes = self.vectores @ consulta
        orden = np.argsort(-similitudes, kind="stable")[:k]
        return [
            Vecino(self.imagenes[i].imagen_id, self.imagenes[i].lat, self.imagenes[i].lng,
                   self.imagenes[i].rumbo, float(similitudes[i]))
            for i in orden
        ]  # fmt: skip


class FuenteCarpeta:
    """Dataset en una carpeta: `dataset.json` = `{"imagenes": [{"imagen_id", "archivo", "lat",
    "lng", "rumbo"}]}` y los JPEG al lado. Para pruebas y para evaluar sin el backend."""

    def __init__(self, directorio: Path) -> None:
        self.directorio = Path(directorio)
        datos = json.loads((self.directorio / "dataset.json").read_text(encoding="utf-8"))
        self._archivos = {i["imagen_id"]: i["archivo"] for i in datos["imagenes"]}
        self._imagenes = [
            ImagenDataset(i["imagen_id"], float(i["lat"]), float(i["lng"]), i.get("rumbo"))
            for i in datos["imagenes"]
        ]

    def imagenes(self) -> list[ImagenDataset]:
        return list(self._imagenes)

    def descargar(self, imagen: ImagenDataset) -> bytes:
        return (self.directorio / self._archivos[imagen.imagen_id]).read_bytes()


def indexar(
    fuente: FuenteDataset,
    vectorizar: Callable[[bytes], np.ndarray],
    version_vector: str | None = None,
) -> BuscadorFuerzaBruta:
    """Baja y vectoriza todo el dataset de `fuente` con `vectorizar` (una variante)."""
    imagenes = fuente.imagenes()
    filas = [np.asarray(vectorizar(fuente.descargar(i)), dtype=np.float32) for i in imagenes]
    vectores = np.stack(filas) if filas else np.zeros((0, 1), dtype=np.float32)
    return BuscadorFuerzaBruta(imagenes, vectores, vectorizar, version_vector)
