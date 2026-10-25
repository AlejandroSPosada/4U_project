"""Cola con prioridad (alta antes que baja) y el hilo único de inferencia (ARCHITECTURE §4.3).

- Dos colas FIFO, una por prioridad. El hilo toma siempre de `alta` si tiene algo; la prioridad no
  interrumpe el lote en curso (ADR-EMB-07).
- Admisión: una petición entra solo si, con ella, las imágenes en espera no superan
  `COLA_MAX_IMAGENES` (el lote en curso no cuenta, §5.7); si no, `Saturado` (503 SATURADO).
- Cada petición se calcula como **un solo lote** con `procesar(imagenes)` (preproceso pp-v1 +
  red), en el orden de entrada. `cola_ms` va de que entra en la cola a que el hilo la toma;
  `inferencia_ms`, de ahí a que tiene los vectores (preproceso incluido).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from dataclasses import dataclass

import numpy as np

PRIORIDADES = ("alta", "baja")  # en orden de atención
PRIORIDAD_POR_DEFECTO = "baja"

Procesar = Callable[[Sequence[bytes]], np.ndarray]


class Saturado(Exception):
    """La cola no admite la petición (503 SATURADO)."""

    def __init__(self, en_espera: int, pedidas: int, maximo: int) -> None:
        super().__init__(
            f"Hay {en_espera} imágenes en espera; con {pedidas} más se superaría el máximo de "
            f"{maximo}"
        )


class Detenido(Exception):
    """El planificador se detuvo (el proceso termina) y ya no atiende peticiones."""


@dataclass(frozen=True)
class Resultado:
    vectores: np.ndarray
    cola_ms: int
    inferencia_ms: int


@dataclass
class _Trabajo:
    imagenes: Sequence[bytes]
    futuro: Future[Resultado]
    encolado: float


def _ms(segundos: float) -> int:
    return round(segundos * 1000)


class Planificador:
    def __init__(
        self,
        procesar: Procesar,
        cola_max_imagenes: int,
        reloj: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._procesar = procesar
        self.cola_max_imagenes = cola_max_imagenes
        self._reloj = reloj
        self._colas: dict[str, deque[_Trabajo]] = {p: deque() for p in PRIORIDADES}
        self._en_espera = 0
        self._detenido = False
        self._condicion = threading.Condition()
        self._hilo = threading.Thread(target=self._bucle, name="inferencia", daemon=True)

    def iniciar(self) -> Planificador:
        self._hilo.start()
        return self

    @property
    def imagenes_en_espera(self) -> int:
        with self._condicion:
            return self._en_espera

    def enviar(self, imagenes: Sequence[bytes], prioridad: str) -> Future[Resultado]:
        """Encola la petición; el futuro se resuelve con su `Resultado` o con la excepción."""
        if prioridad not in PRIORIDADES:
            raise ValueError(f"prioridad desconocida: {prioridad!r}")
        if not imagenes:
            raise ValueError("una petición necesita al menos una imagen")
        futuro: Future[Resultado] = Future()
        with self._condicion:
            if self._detenido:
                raise Detenido("el servicio se está deteniendo")
            if self._en_espera + len(imagenes) > self.cola_max_imagenes:
                raise Saturado(self._en_espera, len(imagenes), self.cola_max_imagenes)
            self._colas[prioridad].append(_Trabajo(list(imagenes), futuro, self._reloj()))
            self._en_espera += len(imagenes)
            self._condicion.notify()
        return futuro

    def detener(self, espera_s: float = 5.0) -> None:
        """Deja de admitir, falla lo que esperaba y espera a que termine el lote en curso."""
        with self._condicion:
            self._detenido = True
            pendientes = [trabajo for cola in self._colas.values() for trabajo in cola]
            for cola in self._colas.values():
                cola.clear()
            self._en_espera = 0
            self._condicion.notify_all()
        for trabajo in pendientes:
            if trabajo.futuro.set_running_or_notify_cancel():
                trabajo.futuro.set_exception(Detenido("el servicio se está deteniendo"))
        if self._hilo.is_alive() and self._hilo is not threading.current_thread():
            self._hilo.join(espera_s)

    def _siguiente(self) -> _Trabajo | None:
        with self._condicion:
            while not self._detenido:
                for prioridad in PRIORIDADES:
                    if self._colas[prioridad]:
                        trabajo = self._colas[prioridad].popleft()
                        self._en_espera -= len(trabajo.imagenes)
                        return trabajo
                self._condicion.wait()
            return None

    def _bucle(self) -> None:
        while (trabajo := self._siguiente()) is not None:
            tomado = self._reloj()
            # Si quien esperaba ya canceló, no se calcula.
            if not trabajo.futuro.set_running_or_notify_cancel():
                continue
            try:
                vectores = self._procesar(trabajo.imagenes)
            except BaseException as error:  # el hilo no muere: el error es de esa petición
                trabajo.futuro.set_exception(error)
                continue
            fin = self._reloj()
            trabajo.futuro.set_result(
                Resultado(vectores, _ms(tomado - trabajo.encolado), _ms(fin - tomado))
            )
