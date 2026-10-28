"""Pruebas de validate41.py con un teléfono, Gradle y la API simulados.

El backend falso guarda videos e imágenes (`/v1/admin/videos`, `/v1/admin/images`, la recolección de §5.4 con sus URLs
`PUT` prefirmadas y el `DELETE` de BE-4.1). El teléfono falso dibuja Inicio, Login, el Panel (tarjetas «Videos» e
«Imágenes»), la Lista 7.13 (encabezado «N videos», «M sin subir en este teléfono», buscador y filas con el
`content-desc` de `TextosVideos.descripcionFila`), el detalle 7.14 y la Galería 7.11 («N imágenes», buscador, tarjetas
«Foto N, video <nombre>»), con `files/recoleccion` por `run-as`. Los pasos guiados (`comun.esperar_enter`) se
sustituyen por lo que hace la persona en la app (renombrar y eliminar contra el backend falso).
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from xml.sax.saxutils import quoteattr

import comun
import pytest
import validate41

URL = "https://api.example.com/v1"
ADMIN = ("admin@campus.edu.co", "Clave Segura$1")
TOKEN = "eyJ.token.secreto"
FIRMA = "FIRMA-S3-SECRETA"
NOMBRE_ADMIN = "Alejandro Gómez"
PLAN_APP = (
    "| FE-2.1 | 2 | Hecho | [2-1](x) | `a69a79a` 2026-10-26 | 0.7.2 | | |\n| FE-4.1 | 4 | Pendiente | | | | | |\n"
)
PLAN_BACKEND = (
    "| BE-2.1 | 2 | Hecho | [2-1](x) | `x` | 0.6.0 | |\n| BE-4.1 | 4 | Hecho | [4-1](x) | `c5f6517` | 0.15.1 | |\n"
)


LANZADOR = "com.miui.home"
APPS_DEL_USUARIO = ("DaviPlata", "SoundWireFree", "Instagram", "My Application")  # nunca deben salir en el informe


def _nodo(
    texto="", desc="", clase="android.widget.TextView", limites=(0, 0, 10, 10), paquete=comun.PAQUETE, foco=False
):
    x1, y1, x2, y2 = limites
    return (
        f"<node text={quoteattr(texto)} content-desc={quoteattr(desc)} class={quoteattr(clase)} "
        f'package={quoteattr(paquete)} focused="{str(foco).lower()}" '
        f'bounds="[{x1},{y1}][{x2},{y2}]" enabled="true" password="false"/>'
    )


def _manifest(nombre: str, estado: str = "finalizado", remoto: str | None = None) -> str:
    m = {
        "name": nombre,
        "estado": estado,
        "photos": [{"id": "0001", "file": "photos/0001.jpg", "lat": 6.2, "lng": -75.5}],
    }
    if remoto:
        m["remote_video_id"] = remoto
    return json.dumps(m)


class Api:
    """Backend falso: salud, login, recolección (§5.4) y administración de videos e imágenes (§5.5)."""

    def __init__(self) -> None:
        self.videos: dict[str, dict] = {}
        self.imagenes: dict[str, dict] = {}
        self.n = 0
        self.login_estado = 200
        self.puts: list[dict] = []
        self.borrados: list[str] = []
        self.falla_borrar = False
        # Un video real y uno que solo se *llama* como los de prueba (su ref_cliente no lo es): se quedan.
        self.real = self._video("Entrada norte", "rec_0001", fotos=2)
        self.ajeno = self._video("validacion-4-1-viejo", "rec_0002", fotos=1)

    def _id(self, prefijo: str) -> str:
        self.n += 1
        return f"{prefijo}-{self.n:04d}"

    def _video(self, nombre: str, ref: str, fotos: int = 0, estado: str = "procesado") -> dict:
        v = {
            "id": self._id("vid"), "numero": self.n, "nombre": nombre, "ref_cliente": ref, "estado": estado,
            "creado_en": f"2026-10-27T15:{self.n:02d}:00Z", "total_fotos": fotos, "eliminado": False,
        }  # fmt: skip
        self.videos[v["id"]] = v
        for orden in range(1, fotos + 1):
            self._imagen(v["id"], orden, "procesada")
        return v

    def _imagen(self, video_id: str, orden: int, estado: str) -> dict:
        i = {"id": self._id("img"), "video_id": video_id, "orden": orden, "lat": 1.0, "lng": -100.0, "estado": estado}
        self.imagenes[i["id"]] = i
        return i

    def visibles(self, q: str | None = None) -> list[dict]:
        vs = [v for v in self.videos.values() if not v["eliminado"] and (not q or q.lower() in v["nombre"].lower())]
        return sorted(vs, key=lambda v: v["creado_en"], reverse=True)

    def fotos_visibles(self, q: str | None = None, video_id: str | None = None) -> list[dict]:
        vivos = {v["id"]: v for v in self.visibles(q)}
        return [
            i for i in self.imagenes.values() if i["video_id"] in vivos and (not video_id or i["video_id"] == video_id)
        ]

    def renombrar(self, video_id: str, nombre: str) -> None:
        self.videos[video_id]["nombre"] = nombre

    def eliminar(self, video_id: str) -> None:
        self.videos[video_id]["eliminado"] = True
        self.borrados.append(video_id)

    def por_nombre(self, nombre: str) -> dict:
        return next(v for v in self.visibles() if v["nombre"] == nombre)

    @staticmethod
    def _r(estado: int, cuerpo: object = None) -> comun.RespuestaHttp:
        return comun.RespuestaHttp(estado, {}, json.dumps(cuerpo) if cuerpo is not None else "", 30)

    def _publico(self, v: dict) -> dict:
        return {k: val for k, val in v.items() if k != "eliminado"}

    def http_get(self, url, *, timeout=15.0, token=None):
        u = urlparse(url)
        ruta = u.path.removeprefix("/v1")
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if ruta == "/health":
            return self._r(200, {"estado": "ok"})
        assert token == TOKEN
        pagina, por = int(q.get("pagina", 1)), int(q.get("por_pagina", 24))
        if ruta == "/admin/videos":
            items = self.visibles(q.get("q"))
            return self._r(200, {"items": [self._publico(v) for v in items[(pagina - 1) * por : pagina * por]],
                                 "total": len(items), "pagina": pagina, "por_pagina": por})  # fmt: skip
        if ruta.startswith("/admin/videos/"):
            v = self.videos.get(unquote(ruta.rsplit("/", 1)[-1]))
            if v is None or v["eliminado"]:
                return self._r(404, {"error": {"codigo": "NO_ENCONTRADO", "mensaje": "No existe", "detalle": None}})
            fotos = [i for i in self.imagenes.values() if i["video_id"] == v["id"]]
            return self._r(200, self._publico(v) | {"fotos": fotos})
        if ruta == "/admin/images":
            items = self.fotos_visibles(q.get("q"), q.get("video_id"))
            return self._r(200, {"items": items[(pagina - 1) * por : pagina * por], "total": len(items),
                                 "pagina": pagina, "por_pagina": por})  # fmt: skip
        raise AssertionError(url)

    def http_post_json(self, url, cuerpo, *, timeout=15.0, token=None):
        ruta = urlparse(url).path.removeprefix("/v1")
        if ruta == "/auth/login":
            if self.login_estado != 200:
                return self._r(401, {"error": {"codigo": "CREDENCIALES_INVALIDAS"}})
            assert (cuerpo["identificador"], cuerpo["password"]) == ADMIN
            usuario = {"id": "u1", "nombre": NOMBRE_ADMIN, "correo": ADMIN[0], "rol": "admin"}
            return self._r(200, {"token": TOKEN, "usuario": usuario})
        assert token == TOKEN
        if ruta == "/collect/videos":
            if not cuerpo:
                return self._r(422, {"error": {"codigo": "VALIDACION", "mensaje": "x", "detalle": {"campos": []}}})
            assert cuerpo["ref_cliente"].startswith(validate41.PREFIJO) and len(cuerpo["ref_cliente"]) <= 40
            v = self._video(cuerpo["nombre"], cuerpo["ref_cliente"], estado="pendiente")
            return self._r(201, self._publico(v))
        partes = ruta.split("/")  # ['', 'collect', 'videos', id, 'images'|'complete']
        video_id = partes[3]
        if partes[4] == "images":
            respuesta = []
            for e in cuerpo["imagenes"]:
                assert e["bytes"] > 0
                i = self._imagen(video_id, e["orden"], "pendiente_subida")
                subida = {
                    "metodo": "PUT", "url": f"https://s3.example.com/dataset/{video_id}/{i['id']}.jpg?X-Amz-Signature={FIRMA}",
                    "encabezados": {"Content-Type": "image/jpeg"}, "expira_en": "2026-10-27T16:00:00Z",
                }  # fmt: skip
                respuesta.append({"orden": e["orden"], "id": i["id"], "estado": "pendiente_subida", "subida": subida})
            return self._r(200, {"imagenes": respuesta})
        if partes[4] == "complete":
            fotos = [i for i in self.imagenes.values() if i["video_id"] == video_id]
            pendientes = sum(1 for i in fotos if i["estado"] == "pendiente_subida")
            self.videos[video_id]["estado"] = "procesando" if not pendientes else "pendiente"
            conteo = {"pendiente_subida": pendientes, "subida": len(fotos) - pendientes, "procesada": 0, "error": 0}
            return self._r(200, {"id": video_id, "estado": self.videos[video_id]["estado"], "conteo": conteo})
        raise AssertionError(url)

    def http_put_bytes(self, url, datos, encabezados, *, timeout=60.0):
        assert encabezados == {"Content-Type": "image/jpeg"}
        assert comun.dimensiones_jpeg(datos) == validate41.LADO_FOTOS
        imagen_id = urlparse(url).path.rsplit("/", 1)[-1].removesuffix(".jpg")
        self.imagenes[imagen_id]["estado"] = "subida"
        self.puts.append({"imagen": imagen_id, "bytes": len(datos)})
        return comun.RespuestaHttp(200, {}, "", 30)

    def http_delete(self, url, *, timeout=15.0, token=None):
        assert token == TOKEN
        video_id = unquote(urlparse(url).path.rsplit("/", 1)[-1])
        v = self.videos.get(video_id)
        if v is None:
            return self._r(404, {"error": {"codigo": "NO_ENCONTRADO"}})
        if not v["eliminado"]:
            self.eliminar(video_id)
        fotos = sum(1 for i in self.imagenes.values() if i["video_id"] == video_id)
        return self._r(202, {"id": video_id, "estado": "eliminado", "fotos_retiradas": fotos, "purga": "programada"})


class Telefono:
    """La app en un teléfono falso: Inicio, Login, Panel, 7.13, 7.14 y 7.11."""

    def __init__(self, api: Api) -> None:
        self.api = api
        self.ordenes: list[tuple[str, ...]] = []
        self.pantalla: str | None = None
        self.campos = ["", ""]
        self.foco: str | int | None = None
        self.busqueda_lista = ""
        self.busqueda_galeria = ""
        self.dialogo: tuple[str, str] | None = None
        self.manifests: dict[str, str] = {
            "rec_0010": _manifest("video_10"),
            "rec_0011": _manifest("video_11"),
            "rec_0012": _manifest("video_12", remoto="vid-0001"),  # ya subido: lo representa el servidor
            "rec_0013": _manifest("video_13", estado="en_curso"),
        }
        # Defectos que se pueden simular
        self.total_lista_de_mas = 0
        self.locales_de_menos = 0
        self.galeria_de_mas = 0
        # El Panel y el teclado como en el Xiaomi (FE-4.1, primera ejecución en dev)
        self.panel_alto = False  # «Videos» e «Imágenes» solo se ven tras bajar una vez (el saludo queda fuera)
        self.desplazado = 0  # cuánto bajó el Panel; se conserva al volver a él (rememberScrollState)
        self.teclado = False  # teclado abierto de verdad
        self.teclado_fantasma = False  # dumpsys input_method sigue diciendo que está abierto
        self.cierra_al_volver = False  # Atrás desde 7.13 cierra la app (una vez)
        self.atras_en_panel = 0  # Atrás pulsados con el Panel en pantalla (lo cierra: es la raíz)
        self.atras_fuera = 0  # Atrás pulsados con otra app en primer plano

    def _locales(self, q: str = "") -> list[str]:
        nombres = []
        for texto in self.manifests.values():
            m = json.loads(texto)
            if m["estado"] == "finalizado" and not m.get("remote_video_id") and q.lower() in m["name"].lower():
                nombres.append(m["name"])
        return nombres

    def _nodos(self) -> list[str]:
        p = self.pantalla
        if p == "inicio":
            return [_nodo(texto="Acceso administrador", limites=(300, 2020, 800, 2080))]
        if p == "login":
            return [
                _nodo(texto=self.campos[0], clase="android.widget.EditText", limites=(60, 900, 1020, 1060)),
                _nodo(texto="•" * len(self.campos[1]), clase="android.widget.EditText", limites=(60, 1100, 1020, 1260)),
                _nodo(texto="Iniciar sesión", limites=(300, 1380, 800, 1450)),
            ]
        if p == "panel":
            nodos = []
            if self.desplazado == 0:
                nodos += [
                    _nodo(texto=validate41.saludo_esperado(NOMBRE_ADMIN), limites=(100, 200, 900, 280)),
                    _nodo(texto="Panel de administración · Campus Navi", limites=(100, 290, 900, 330)),
                ]
            if self.desplazado >= 1 or not self.panel_alto:
                nodos += [
                    _nodo(texto="Videos", limites=(100, 1500, 500, 1560)),
                    _nodo(texto="Imágenes", limites=(600, 1500, 1000, 1560)),
                    _nodo(texto="Gestiona los videos del sistema.", limites=(100, 1570, 500, 1640)),
                ]
            if self.desplazado >= 1:
                nodos.append(_nodo(texto="Resumen rápido", limites=(100, 1800, 600, 1850)))
            return nodos
        if p == "lista":
            q = self.busqueda_lista
            servidor = self.api.visibles(q or None)
            locales = self._locales(q)
            nodos = [
                _nodo(texto=validate41.TITULO_LISTA, limites=(100, 100, 600, 160)),
                _nodo(texto=f"{len(servidor) + self.total_lista_de_mas} videos", limites=(100, 170, 400, 210)),
                _nodo(texto=q, clase="android.widget.EditText", limites=(40, 300, 1040, 400), foco=self.foco == p),
            ]
            if len(locales) - self.locales_de_menos > 0:
                nodos.append(
                    _nodo(
                        texto=f"{len(locales) - self.locales_de_menos} sin subir en este teléfono",
                        limites=(420, 170, 900, 210),
                    )
                )
            y = 500
            for nombre in locales:
                nodos.append(
                    _nodo(desc=f"Video {nombre}, en este teléfono, 1 foto, Sin subir", limites=(40, y, 1040, y + 150))
                )
                y += 160
            for v in servidor:
                nodos.append(
                    _nodo(desc=f"Video {v['nombre']}, 27/10/2026 · 3 fotos, Procesando", limites=(40, y, 1040, y + 150))
                )
                y += 160
            return nodos
        if p == "detalle":
            nodos = [_nodo(desc="Mapa con las fotos del video", limites=(0, 0, 1080, 2400))]
            if self.dialogo:
                nodos += [_nodo(texto=self.dialogo[0], limites=(100, 900, 900, 960)),
                          _nodo(texto=self.dialogo[1], limites=(100, 980, 900, 1100))]  # fmt: skip
            return nodos
        if p == "galeria":
            q = self.busqueda_galeria
            fotos = self.api.fotos_visibles(q or None)
            nombres = {v["id"]: v["nombre"] for v in self.api.videos.values()}
            total = len(fotos) + self.galeria_de_mas
            nodos = [
                _nodo(texto=validate41.TITULO_GALERIA, limites=(40, 100, 600, 160)),
                _nodo(
                    texto="1 imagen" if total == 1 else f"{total:,} imágenes".replace(",", "."),
                    limites=(40, 170, 400, 210),
                ),
                _nodo(texto=q, clase="android.widget.EditText", limites=(40, 300, 1040, 400), foco=self.foco == p),
            ]
            for i, f in enumerate(fotos[:6]):
                nodos.append(
                    _nodo(
                        desc=f"Foto {f['orden']}, video {nombres[f['video_id']]}, Subida",
                        limites=(40, 500 + i * 100, 500, 590 + i * 100),
                    )
                )
            return nodos
        # La pantalla de inicio del teléfono (app cerrada o en segundo plano): las apps del usuario.
        return [
            _nodo(desc=nombre, limites=(40 + 260 * i, 600, 260 + 260 * i, 860), paquete=LANZADOR)
            for i, nombre in enumerate(APPS_DEL_USUARIO)
        ]

    def _xml(self) -> str:
        return f"<?xml version='1.0' encoding='UTF-8'?><hierarchy rotation=\"0\">{''.join(self._nodos())}</hierarchy>"

    def _tocar(self, x: int, y: int) -> None:
        p = self.pantalla
        if p == "inicio" and 2000 <= y <= 2100:
            self.pantalla, self.campos = "login", ["", ""]
        elif p == "login":
            if 900 <= y <= 1060:
                self.foco, self.teclado = 0, True
            elif 1100 <= y <= 1260:
                self.foco, self.teclado = 1, True
            elif 1380 <= y <= 1450 and tuple(self.campos) == ADMIN:
                self.pantalla, self.foco, self.teclado = "panel", None, False
        elif p == "panel" and 1500 <= y <= 1560:
            if x < 550:
                self.pantalla, self.busqueda_lista = "lista", ""
            else:
                self.pantalla, self.busqueda_galeria = "galeria", ""
        elif p in ("lista", "galeria") and 300 <= y <= 400:
            self.foco, self.teclado = p, True

    def _atras(self) -> None:
        p = self.pantalla
        if p not in ("inicio", "login", "panel", "lista", "detalle", "galeria"):
            self.atras_fuera += 1
            return
        if self.teclado:
            self.teclado = False  # con el teclado abierto, Atrás solo lo cierra (el campo sigue con el foco)
            return
        if p == "panel":
            self.atras_en_panel += 1
        self.dialogo = None
        if p == "lista" and self.cierra_al_volver:
            self.cierra_al_volver = False
            nueva = "escritorio"
        else:
            nueva = {"detalle": "lista", "lista": "panel", "galeria": "panel", "panel": "escritorio"}.get(p, p)
        if nueva != p:
            self.pantalla, self.foco = nueva, None

    def _escribir(self, texto: str) -> None:
        if self.foco == "lista":
            self.busqueda_lista += texto
        elif self.foco == "galeria":
            self.busqueda_galeria += texto
        elif isinstance(self.foco, int):
            self.campos[self.foco] += texto

    def _borrar(self) -> None:
        if self.foco == "lista":
            self.busqueda_lista = self.busqueda_lista[:-1]
        elif self.foco == "galeria":
            self.busqueda_galeria = self.busqueda_galeria[:-1]

    def adb(self, *args: str, timeout: int = 0) -> comun.Resultado:
        self.ordenes.append(args)
        ok = comun.Resultado(0, "", "")
        if args[0] == "exec-out" and args[1].startswith("uiautomator dump"):
            return comun.Resultado(0, self._xml(), "")
        if args[:3] == ("exec-out", "run-as", comun.PAQUETE):
            orden = args[3:]
            if orden == ("ls", "-1", "files/recoleccion"):
                return comun.Resultado(0, "\n".join(sorted(self.manifests)) + "\n", "")
            if orden[0] == "cat":
                carpeta = orden[1].split("/")[2]
                texto = self.manifests.get(carpeta)
                return comun.Resultado(0, texto, "") if texto else comun.Resultado(1, "", "No such file")
            raise AssertionError(args)
        if args[0] != "shell":
            return ok
        orden = args[1:]
        if orden[:2] == ("getprop", "ro.product.model"):
            return comun.Resultado(0, "23028RA60L\n", "")
        if orden[:2] == ("getprop", "ro.build.version.release"):
            return comun.Resultado(0, "14\n", "")
        if orden[:2] == ("getprop", "ro.build.version.sdk"):
            return comun.Resultado(0, "34\n", "")
        if orden[:2] == ("am", "force-stop"):
            self.pantalla, self.foco, self.teclado, self.desplazado = None, None, False, 0
            return ok
        if orden[:2] == ("am", "start"):
            self.pantalla = "inicio"
            return comun.Resultado(0, "Status: ok\n", "")
        if orden[:2] == ("input", "tap"):
            self._tocar(int(orden[2]), int(orden[3]))
            return ok
        if orden[:2] == ("input", "text"):
            self._escribir(orden[2].replace("\\", "").replace("%s", " "))
            return ok
        if orden[:2] == ("input", "keyevent"):
            if orden[2] == comun.TECLA_ATRAS:
                self._atras()
            elif orden[2] == validate41.TECLA_BORRAR:
                self._borrar()
            return ok
        if orden[:2] == ("dumpsys", "input_method"):
            abierto = "true" if self.teclado or self.teclado_fantasma else "false"
            return comun.Resultado(0, f"  mInputShown={abierto}\n", "")
        if orden[:2] == ("input", "swipe"):
            if self.pantalla == "panel":  # de abajo arriba baja la página; de arriba abajo la sube
                bajar = int(orden[3]) > int(orden[5])
                self.desplazado = min(self.desplazado + 1, 2) if bajar else max(self.desplazado - 1, 0)
            return ok
        if orden[:2] == ("wm", "size"):
            return comun.Resultado(0, "Physical size: 1080x2400\n", "")
        if orden[:2] == ("pm", "grant"):
            return ok
        return ok


class Mundo:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.t = 1000.0
        self.api = Api()
        self.telefono = Telefono(self.api)
        self.casos = {"VideoRepositoryCompuestoTest": 11, "TextosVideosTest": 5, "RemoteVideoRepositoryTest": 15}
        self.gradle_ordenes: list[tuple[str, ...]] = []
        self.pasos_guiados: list[str] = []
        self.enter_eof = False
        self.be41_hecho = True
        # Lo que hace la persona en cada paso guiado
        self.renombra = True
        self.elimina = True
        self.error_al_borrar = False
        self.se_cierra_al_borrar = False

    def instalar(self, monkeypatch) -> None:
        plan = self.tmp / "PLAN.md"
        plan.write_text(PLAN_APP, encoding="utf-8")
        plan_be = self.tmp / "PLAN_BE.md"
        texto_be = (
            PLAN_BACKEND if self.be41_hecho else PLAN_BACKEND.replace("| BE-4.1 | 4 | Hecho", "| BE-4.1 | 4 | En curso")
        )
        plan_be.write_text(texto_be, encoding="utf-8")
        monkeypatch.setattr(comun, "PLAN_APP", plan)
        monkeypatch.setattr(comun, "PLAN_BACKEND", plan_be)
        monkeypatch.setattr(comun, "DIR_RESULTADOS_PRUEBAS", self.tmp)
        monkeypatch.setattr(comun, "gradle", self.gradle)
        monkeypatch.setattr(comun, "adb", self.telefono.adb)
        monkeypatch.setattr(comun, "dispositivo_fisico", lambda: "SERIAL1")
        monkeypatch.setattr(comun, "url_api_vigente", lambda: (URL, "terraform output api_base_url"))
        monkeypatch.setattr(comun, "url_api_config", lambda ruta=None: URL)
        monkeypatch.setattr(comun, "http_get", self.api.http_get)
        monkeypatch.setattr(comun, "http_post_json", self.api.http_post_json)
        monkeypatch.setattr(comun, "http_delete", self.api.http_delete)
        monkeypatch.setattr(comun, "http_put_bytes", self.api.http_put_bytes)
        monkeypatch.setattr(comun, "esperar_enter", self.esperar_enter)
        monkeypatch.setattr(comun, "reloj", lambda: self.t)
        monkeypatch.setattr(comun, "dormir", self.dormir)
        monkeypatch.setattr(comun, "commit_actual", lambda: "abc1234")
        monkeypatch.setenv("VALIDACION_ADMIN_CORREO", ADMIN[0])
        monkeypatch.setenv("VALIDACION_ADMIN_PASSWORD", ADMIN[1])

    def dormir(self, s: float) -> None:
        self.t += s

    def esperar_enter(self, instruccion: str) -> None:
        self.pasos_guiados.append(instruccion)
        if self.enter_eof:
            raise comun.ErrorConfiguracion(
                "el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)"
            )
        t = self.telefono
        t.foco, t.teclado = None, False  # la persona toca una fila: el buscador pierde el foco
        if validate41.RENOMBRADO in instruccion and "Renombrar" in instruccion:
            assert t.pantalla == "lista" and t.busqueda_lista == validate41.PREFIJO
            t.pantalla = "detalle"
            if self.renombra:
                self.api.renombrar(self.api.por_nombre(validate41.VIDEO_A)["id"], validate41.RENOMBRADO)
        elif "Eliminar video" in instruccion:
            assert t.pantalla == "lista" and t.busqueda_lista == validate41.PREFIJO
            t.pantalla = "detalle"
            if self.error_al_borrar:
                t.dialogo = (
                    "No se pudo eliminar el video",
                    "Sin conexión: no se pudo eliminar el video. Revisa tu conexión.",
                )
            elif self.elimina:
                self.api.eliminar(self.api.por_nombre(validate41.VIDEO_B)["id"])
                # la app vuelve sola a 7.13 (la misma entrada: conserva la búsqueda), salvo que se cierre al borrar
                t.pantalla = "escritorio" if self.se_cierra_al_borrar else "lista"
        else:
            raise AssertionError(instruccion)

    def gradle(self, *args, timeout=0):
        self.gradle_ordenes.append(args)
        if "--version" in args:
            return comun.Resultado(0, "Gradle 8.7\nJVM:          21.0.11\n", "")
        if "installDebug" in args:
            return comun.Resultado(0, "BUILD SUCCESSFUL", "")
        if "testDebugUnitTest" in args:
            for clase, casos in self.casos.items():
                if f"*.{clase}" in args:
                    (self.tmp / f"TEST-com.example.myapplication.x.{clase}.xml").write_text(
                        f'<testsuite tests="{casos}" failures="0" errors="0" skipped="0"/>', encoding="utf-8"
                    )
            return comun.Resultado(0, "BUILD SUCCESSFUL", "")
        return comun.Resultado(0, "", "")


def _correr(tmp_path, entorno, argv_extra=()):
    informe = tmp_path / "informe.json"
    codigo = validate41.main(["--entorno", entorno, "--informe", str(informe), *argv_extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def _estados(datos):
    return {c["id"]: c["estado"] for c in datos["comprobaciones"]}


def _detalle(datos, id_):
    return next(c["detalle"] for c in datos["comprobaciones"] + datos["precondiciones"] if c["id"] == id_)


# --- piezas puras ----------------------------------------------------------------------------------------------


def test_comentarios_y_usos_prohibidos():
    codigo = (
        '/** No hay `EdicionesLocales`. */\nval s = "// EdicionesLocales"\n// AssetsVideoRepository(\nfun f() = 1\n'
    )
    assert validate41.usos_prohibidos({"a.kt": codigo}) == []
    assert validate41.usos_prohibidos({"b.kt": "internal object EdicionesLocales {}"}) == ["b.kt: EdicionesLocales"]
    assert validate41.usos_prohibidos({"c.kt": 'val x = """\n// FuenteRecorridos\n"""'}) == []


def test_js_eliminar_no_debe_salir_solo():
    viejo = (
        "function eliminarVideo() {\n  call('eliminarVideo'); toast('Video eliminado');\n"
        "  setTimeout(() => { call('salir') }, 900);\n}"
    )
    with pytest.raises(comun.Falla, match="sale sola"):
        validate41.comprobar_js_eliminar(viejo)
    nuevo = (
        "// salir() no\nfunction eliminarVideo() {\n  if (!call('eliminarVideo')) toast('demo');\n}\n"
        "function x() { salir(); }"
    )
    assert "no sale sola" in validate41.comprobar_js_eliminar(nuevo)
    with pytest.raises(comun.Falla, match="no llama al puente"):
        validate41.comprobar_js_eliminar("function eliminarVideo() { }")
    # El de la app (assets/video_detalle.js) cumple.
    assert "no sale sola" in validate41.comprobar_js_eliminar(validate41.JS_DETALLE.read_text(encoding="utf-8"))


def test_estatica_del_codigo_real_pasa():
    archivos = {
        str(p.relative_to(validate41.DIR_KOTLIN)): p.read_text(encoding="utf-8")
        for p in validate41.DIR_KOTLIN.rglob("*.kt")
    }
    assert validate41.usos_prohibidos(archivos) == []
    assert not (validate41.DIR_ASSETS / "videos").exists()


def test_es_de_prueba_exige_nombre_y_ref_cliente():
    assert validate41.es_de_prueba({"nombre": "validacion-4-1-a", "ref_cliente": "validacion-4-1-a-20261027-150000"})
    assert validate41.es_de_prueba({"nombre": "validacion-4-1-renombrado", "ref_cliente": "validacion-4-1-a-x"})
    assert not validate41.es_de_prueba({"nombre": "validacion-4-1-viejo", "ref_cliente": "rec_0002"})
    assert not validate41.es_de_prueba({"nombre": "Entrada norte", "ref_cliente": "validacion-4-1-a"})


def test_contadores_y_manifests():
    nodos = comun.parsear_ui(
        "<hierarchy>" + _nodo(texto="12 videos") + _nodo(texto="3 sin subir en este teléfono")
        + _nodo(texto="2.842 imágenes") + _nodo(desc="Video validacion-4-1-a, 27/10/2026 · 3 fotos, Procesando")
        + "</hierarchy>"
    )  # fmt: skip
    assert validate41.total_en_pantalla(nodos, validate41.PATRON_TOTAL_VIDEOS) == 12
    assert validate41.total_en_pantalla(nodos, validate41.PATRON_SIN_SUBIR) == 3
    assert validate41.total_en_pantalla(nodos, validate41.PATRON_TOTAL_IMAGENES) == 2842
    uno = comun.parsear_ui("<hierarchy>" + _nodo(texto="1 imagen") + _nodo(texto="1 video") + "</hierarchy>")
    assert validate41.total_en_pantalla(uno, validate41.PATRON_TOTAL_IMAGENES) == 1
    assert validate41.total_en_pantalla(uno, validate41.PATRON_TOTAL_VIDEOS) == 1
    filas = validate41.filas_videos(nodos)
    assert validate41.hay_fila(filas, "validacion-4-1-a") and not validate41.hay_fila(filas, "validacion-4-1")
    manifests = [_manifest("a"), _manifest("b", remoto="uuid"), _manifest("c", estado="en_curso"), "{roto", "[]"]
    assert validate41.sin_subir_en_manifests(manifests) == 1


# --- validador completo ------------------------------------------------------------------------------------------


def test_dev_todo_bien_limpia_solo_lo_suyo_y_no_imprime_secretos(tmp_path, monkeypatch, capsys):
    m = Mundo(tmp_path)
    resto = m.api._video("validacion-4-1-a", "validacion-4-1-a-20261026-120000", fotos=3)  # de una ejecución anterior
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 0, datos
    assert [p["id"] for p in datos["precondiciones"]] == ["P1", "P2", "P3", "P4", "P5", "P6"]
    assert [c["id"] for c in datos["comprobaciones"]] == ["C1a", "C2a", "C3a", "C1b", "C3b", "C2b"]
    assert set(_estados(datos).values()) == {"pasa"}
    assert "«2 sin subir en este teléfono» = manifests" in _detalle(datos, "C1b")
    # «validacion-4-1-viejo» también contiene el prefijo: el total con q es 3 (y no se borra: su ref_cliente no es
    # de prueba).
    assert "validacion-4-1-a y validacion-4-1-b (3 = total con q)" in _detalle(datos, "C1b")
    assert "nombre «validacion-4-1-renombrado»" in _detalle(datos, "C3b")
    assert "-> 404" in _detalle(datos, "C2b") and "muestra 4 imágenes" in _detalle(datos, "C2b")
    assert [x["id"] for x in datos["manuales"]] == ["C2c"]
    # Se subieron 6 fotos (3 + 3) y se completaron los dos videos.
    assert len(m.api.puts) == 6
    # Limpieza: el resto al empezar; al terminar, el renombrado (b ya lo borró la app); el real y el ajeno se quedan.
    assert m.api.borrados[0] == resto["id"]
    vivos = [v["nombre"] for v in m.api.visibles()]
    assert vivos == ["validacion-4-1-viejo", "Entrada norte"]
    assert m.telefono.pantalla is None  # am force-stop
    assert len(m.pasos_guiados) == 2
    assert not any(o[:3] == ("shell", "pm", "clear") for o in m.telefono.ordenes)
    salida = capsys.readouterr()
    informe = json.dumps(datos, ensure_ascii=False)
    for secreto in (ADMIN[1], TOKEN, FIRMA):
        assert secreto not in salida.out
        assert secreto not in salida.err
        assert secreto not in informe


def test_local_sin_telefono_ni_backend(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "local")
    assert codigo == 0, datos
    assert [p["id"] for p in datos["precondiciones"]] == ["P1"]
    assert _estados(datos) == {
        "C1a": "pasa", "C2a": "pasa", "C3a": "pasa", "C1b": "omitida", "C3b": "omitida", "C2b": "omitida",
    }  # fmt: skip
    assert "las Factory de 7.11–7.14 usan el backend" in _detalle(datos, "C1a")
    assert "no sale sola" in _detalle(datos, "C2a")
    assert m.telefono.ordenes == [] and m.api.puts == [] and m.pasos_guiados == []


def test_la_lista_cuenta_otro_total_c1b_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.telefono.total_lista_de_mas = 1
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1, datos
    assert "pero GET /v1/admin/videos da total" in _detalle(datos, "C1b")
    assert all(not validate41.es_de_prueba(v) for v in m.api.visibles())  # la limpieza borró los dos de prueba


def test_sin_subir_distinto_de_los_manifests_c1b_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.telefono.locales_de_menos = 1
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1, datos
    assert "«1 sin subir en este teléfono», pero hay 2 recorridos" in _detalle(datos, "C1b")


def test_la_galeria_cuenta_otro_total_c1b_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.telefono.galeria_de_mas = 2
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1, datos
    assert "pero GET /v1/admin/images da total" in _detalle(datos, "C1b")


def test_sin_renombrar_c3b_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.renombra = False
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C3b"])
    assert codigo == 1, datos
    assert "sigue con nombre «validacion-4-1-a», no «validacion-4-1-renombrado»" in _detalle(datos, "C3b")


def test_error_al_borrar_c2b_falla_con_el_texto_y_limpia(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.error_al_borrar = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 1, datos
    assert "«No se pudo eliminar el video»: «Sin conexión: no se pudo eliminar el video." in _detalle(datos, "C2b")
    assert all(not validate41.es_de_prueba(v) for v in m.api.visibles())


def test_la_app_no_borra_c2b_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.elimina = False
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 1, datos
    assert "no se vio la lista de videos (7.13) tras eliminar" in _detalle(datos, "C2b")


def test_be41_sin_hecho_bloquea(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.be41_hecho = False
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 2, datos
    assert "BE-4.1 no está «Hecho»" in _detalle(datos, "P6")
    assert ("installDebug",) not in m.gradle_ordenes and m.api.puts == []


def test_credenciales_malas_dan_3(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.api.login_estado = 401
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 3, datos
    assert "las credenciales del admin no sirven" in _detalle(datos, "P4")


def test_solo_jvm_en_dev_no_usa_telefono_ni_backend(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1a,C2a,C3a"])
    assert codigo == 0, datos
    assert [p["estado"] for p in datos["precondiciones"]] == ["pasa"] + ["no evaluada"] * 5
    assert m.telefono.ordenes == [] and m.pasos_guiados == [] and m.api.puts == []


def test_jvm_que_falla_omite_el_telefono(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.casos["RemoteVideoRepositoryTest"] = 3
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1, datos
    assert _estados(datos)["C3a"] == "falla"
    for id_ in ("C1b", "C3b", "C2b"):
        assert _estados(datos)[id_] == "omitida" and "falló C3a" in _detalle(datos, id_)
    assert ("installDebug",) not in m.gradle_ordenes and m.api.puts == []


def test_eof_en_el_paso_guiado_da_3_y_limpia(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.enter_eof = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C3b"])
    assert codigo == 3, datos
    assert _estados(datos)["C3b"] == "error"
    assert all(not validate41.es_de_prueba(v) for v in m.api.visibles()) and m.telefono.pantalla is None


def _sin_apps_del_usuario(capsys, datos) -> None:
    salida = capsys.readouterr()
    informe = json.dumps(datos, ensure_ascii=False)
    for nombre in APPS_DEL_USUARIO:
        assert nombre not in salida.out and nombre not in salida.err and nombre not in informe, nombre


def test_es_panel_por_el_saludo_o_por_sus_marcas():
    saludo = validate41.saludo_esperado(NOMBRE_ADMIN)

    def ui(*nodos):
        return comun.parsear_ui("<hierarchy>" + "".join(nodos) + "</hierarchy>")

    assert validate41.es_panel(ui(_nodo(texto=saludo)), saludo)
    # Desplazado: el saludo quedó arriba, fuera de la pantalla; lo reconoce una tarjeta (o «Resumen rápido»).
    assert validate41.es_panel(ui(_nodo(texto="Videos"), _nodo(texto="Gestiona los videos del sistema.")), saludo)
    assert validate41.es_panel(ui(_nodo(texto="Resumen rápido")), saludo)
    assert not validate41.es_panel(ui(_nodo(texto=validate41.TITULO_LISTA), _nodo(texto="Videos")), saludo)
    # Un texto igual en otra app no cuenta.
    assert not validate41.es_panel(ui(_nodo(texto=saludo, paquete=LANZADOR)), saludo)


def test_las_marcas_del_panel_estan_en_su_pantalla():
    """Si cambian los textos del Panel, hay que cambiar MARCAS_PANEL (si no, volver_al_panel no lo reconoce)."""
    panel = validate41.DIR_KOTLIN / "ui" / "admin" / "panel" / "PanelAdminScreen.kt"
    codigo = panel.read_text(encoding="utf-8")
    for marca in validate41.MARCAS_PANEL:
        assert f'"{marca}"' in codigo, marca


@pytest.mark.parametrize(
    ("panel_alto", "fantasma"),
    [(False, True), (True, False), (True, True)],
    ids=["dumpsys-no-suelta-el-teclado", "panel-desplazado", "las-dos"],
)
def test_nunca_pulsa_atras_en_el_panel(tmp_path, monkeypatch, panel_alto, fantasma):
    """La primera ejecución en dev (2026-10-27, sobre 01adb2e): C1b pasó y C3b y C2b fallaron con «no se volvió al
    Panel con Atrás», con la pantalla de inicio del teléfono. Con un Panel que se queda desplazado al volver y un
    `dumpsys input_method` que sigue diciendo que el teclado está abierto, el validador no pulsa Atrás en el Panel."""
    m = Mundo(tmp_path)
    m.telefono.panel_alto = panel_alto
    m.telefono.teclado_fantasma = fantasma
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 0, datos
    assert set(_estados(datos).values()) == {"pasa"}
    assert m.telefono.atras_en_panel == 0 and m.telefono.atras_fuera == 0
    if panel_alto:  # bajó para tocar «Videos» o «Imágenes» y volvió a subir al saludo
        swipes = [o for o in m.telefono.ordenes if o[:3] == ("shell", "input", "swipe")]
        assert any(int(o[4]) > int(o[6]) for o in swipes) and any(int(o[4]) < int(o[6]) for o in swipes)


def test_si_la_app_se_cierra_no_pulsa_atras_fuera_ni_imprime_otras_apps(tmp_path, monkeypatch, capsys):
    m = Mundo(tmp_path)
    m.telefono.cierra_al_volver = True  # Atrás desde 7.13 cierra la app (una vez), en C1b
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1, datos
    assert _estados(datos)["C1b"] == "falla"
    assert validate41.SALIO_DE_LA_APP in _detalle(datos, "C1b")
    assert m.telefono.atras_fuera == 0  # no pulsó nada en la pantalla de inicio
    # La siguiente comprobación vuelve a abrir la app e iniciar sesión, y sigue.
    assert _estados(datos)["C3b"] == "pasa" and _estados(datos)["C2b"] == "pasa"
    assert sum(1 for o in m.telefono.ordenes if o[:3] == ("shell", "am", "start")) == 2
    _sin_apps_del_usuario(capsys, datos)


def test_la_app_se_cierra_al_borrar_c2b_falla_sin_textos_de_otras_apps(tmp_path, monkeypatch, capsys):
    m = Mundo(tmp_path)
    m.se_cierra_al_borrar = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 1, datos
    detalle = _detalle(datos, "C2b")
    assert f"{validate41.SALIO_DE_LA_APP} mientras se esperaba la lista de videos (7.13) tras eliminar" in detalle
    assert m.telefono.atras_fuera == 0
    _sin_apps_del_usuario(capsys, datos)


def test_sin_ver_la_galeria_el_mensaje_no_lista_otras_apps(tmp_path, monkeypatch, capsys):
    """Una espera que vence fuera de la app (p. ej. «Imágenes» abre otra cosa) no imprime los textos de esa otra app."""
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    original = m.telefono._tocar

    def tocar(x, y):
        original(x, y)
        if m.telefono.pantalla == "galeria":
            m.telefono.pantalla = "escritorio"

    monkeypatch.setattr(m.telefono, "_tocar", tocar)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1, datos
    assert validate41.SALIO_DE_LA_APP in _detalle(datos, "C1b")
    _sin_apps_del_usuario(capsys, datos)


@pytest.mark.parametrize("instruccion", [validate41.INSTRUCCION_C3B, validate41.INSTRUCCION_C2B])
def test_instrucciones_cortas_y_con_enter(instruccion):
    assert "Enter" in instruccion
    assert len(instruccion) < 400
