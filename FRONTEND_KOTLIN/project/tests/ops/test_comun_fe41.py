"""Pruebas de las ayudas de `comun.py` que añadió FE-4.1: `jpeg_sintetico` y `http_put_bytes`."""

from __future__ import annotations

import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import comun
import pytest


def test_jpeg_sintetico_es_un_jpeg_de_las_medidas_pedidas():
    datos = comun.jpeg_sintetico(640, 480, semilla=3)
    assert datos[:2] == b"\xff\xd8" and datos[-2:] == b"\xff\xd9"
    assert comun.dimensiones_jpeg(datos) == (640, 480)
    assert len(datos) < 20_000
    # La misma semilla, los mismos bytes; otra semilla, otros (ETag distintos en S3).
    assert comun.jpeg_sintetico(640, 480, semilla=3) == datos
    assert comun.jpeg_sintetico(640, 480, semilla=4) != datos
    assert comun.dimensiones_jpeg(comun.jpeg_sintetico(64, 48)) == (64, 48)


def test_jpeg_sintetico_exige_multiplos_de_8():
    with pytest.raises(ValueError):
        comun.jpeg_sintetico(641, 480)


def test_jpeg_sintetico_lo_decodifica_libjpeg():
    imagen = pytest.importorskip("PIL.Image")  # en la máquina del equipo se comprobó con el Pillow del backend
    im = imagen.open(io.BytesIO(comun.jpeg_sintetico(640, 480, semilla=3)))
    im.load()
    assert im.size == (640, 480) and im.mode == "L"
    assert im.getpixel((0, 0)) == 28 + (3 * 37) % 200


def test_http_put_bytes_envia_exactamente_los_encabezados_y_no_imprime_la_url(capsys):
    recibidos: dict = {}

    class Manejador(BaseHTTPRequestHandler):
        def do_PUT(self):  # noqa: N802 — nombre de http.server
            recibidos["ruta"] = self.path
            recibidos["encabezados"] = {k.lower(): v for k, v in self.headers.items()}
            recibidos["cuerpo"] = self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("ETag", '"abc"')
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    url = f"http://127.0.0.1:{servidor.server_port}/dataset/v/i.jpg?X-Amz-Signature=FIRMA-SECRETA"
    try:
        r = comun.http_put_bytes(url, b"\xff\xd8datos\xff\xd9", {"Content-Type": "image/jpeg"})
    finally:
        servidor.shutdown()
    assert r.estado == 200
    assert recibidos["cuerpo"] == b"\xff\xd8datos\xff\xd9"
    assert recibidos["encabezados"]["content-type"] == "image/jpeg"
    assert "x-request-id" not in recibidos["encabezados"]
    assert "authorization" not in recibidos["encabezados"]
    salida = capsys.readouterr()
    assert "FIRMA-SECRETA" not in salida.out + salida.err


def test_http_put_bytes_sin_respuesta_no_dice_la_url():
    with pytest.raises(comun.ErrorRed) as e:
        comun.http_put_bytes("http://127.0.0.1:9/x.jpg?X-Amz-Signature=FIRMA-SECRETA", b"x", {}, timeout=2)
    assert "FIRMA-SECRETA" not in str(e.value)
    assert "127.0.0.1" not in str(e.value)
