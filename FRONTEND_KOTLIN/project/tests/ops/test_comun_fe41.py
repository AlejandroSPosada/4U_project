"""Pruebas de las ayudas de `comun.py` que añadió FE-4.1: `jpeg_sintetico`, `http_put_bytes` y, para la interfaz del
teléfono, el `package` y el `focused` de los nodos, `app_en_primer_plano`, `de_la_app`, `desplazar_hacia_arriba` y
`textos_visibles` sin los textos de otras apps."""

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


def _ui(*nodos: tuple[str, str, str]) -> list[comun.Nodo]:
    """(texto, package, extra) → nodos de un volcado de uiautomator."""
    partes = "".join(
        f'<node text="{t}" content-desc="" class="android.widget.TextView" package="{p}" {extra} '
        'bounds="[0,0][10,10]" enabled="true" password="false"/>'
        for t, p, extra in nodos
    )
    return comun.parsear_ui(f"<hierarchy>{partes}</hierarchy>")


def test_los_nodos_traen_su_paquete_y_el_foco():
    a, b = _ui(("Hola", comun.PAQUETE, 'focused="true"'), ("DaviPlata", "com.miui.home", ""))
    assert (a.paquete, a.enfocado, a.de_la_app) == (comun.PAQUETE, True, True)
    assert (b.paquete, b.enfocado, b.de_la_app) == ("com.miui.home", False, False)
    # Un nodo sin `package` (hecho a mano, como en las pruebas de los otros validadores) cuenta como de la app.
    sin = comun.Nodo("x", "", "android.widget.TextView", (0, 0, 1, 1), True, False)
    assert sin.de_la_app and not sin.enfocado
    assert comun.de_la_app([a, b, sin]) == [a, sin]


def test_app_en_primer_plano():
    assert comun.app_en_primer_plano(_ui(("Videos de recolección", comun.PAQUETE, "")))
    assert not comun.app_en_primer_plano(_ui(("DaviPlata", "com.miui.home", ""), ("Instagram", "com.miui.home", "")))
    assert not comun.app_en_primer_plano([])


def test_textos_visibles_no_lista_otras_apps():
    inicio = _ui(
        ("DaviPlata", "com.miui.home", ""), ("Instagram", "com.miui.home", ""), ("My Application", "com.miui.home", "")
    )
    texto = comun.textos_visibles(inicio)
    assert "la app no está en primer plano" in texto
    for nombre in ("DaviPlata", "Instagram", "My Application", "com.miui.home"):
        assert nombre not in texto
    mezcla = _ui(("Videos de recolección", comun.PAQUETE, ""), ("DaviPlata", "com.miui.home", ""))
    assert comun.textos_visibles(mezcla) == "«Videos de recolección» (y 1 textos de otra app, omitidos)"
    # Un diálogo del sistema sí se lee (sirve para el diagnóstico).
    dialogo = _ui(("¿Permitir que My Application tome fotos?", "com.android.permissioncontroller", ""))
    assert "Permitir" in comun.textos_visibles(dialogo)
    assert comun.textos_visibles([]) == "(nada legible)"


def test_desplazar_hacia_arriba_desliza_de_arriba_abajo(monkeypatch):
    ordenes: list[tuple[str, ...]] = []

    def adb(*args, timeout=0):
        ordenes.append(args)
        if args[:3] == ("shell", "wm", "size"):
            return comun.Resultado(0, "Physical size: 1080x2400\n", "")
        return comun.Resultado(0, "", "")

    monkeypatch.setattr(comun, "adb", adb)
    comun.desplazar_hacia_arriba()
    comun.desplazar_hacia_abajo()
    arriba, abajo = (o for o in ordenes if o[:3] == ("shell", "input", "swipe"))
    assert arriba[3:7] == ("540", "720", "540", "1680")  # del 30 % al 70 %: la página sube
    assert abajo[3:7] == ("540", "1680", "540", "720")
