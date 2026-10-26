"""Pruebas de validate22.py con un teléfono, Gradle y la API simulados.

El teléfono falso dibuja Inicio, Login y el Panel como los vuelca uiautomator: el «Resumen rápido» está más abajo (hay
que desplazar) y cada dato lleva el `content-desc` de `TileDato` («2.842 fotos en el dataset», «12 último video
recolectado. Hoy, 09:24»). Guarda los `manifest.json` de `files/recoleccion/` (run-as ls, cat y rm) y su hora (`date`).
El Panel toma `GET /v1/admin/stats` y las fotos pendientes al abrirse y, como la app desde FE-2.2, recalcula las
pendientes al volver a él (se puede apagar para simular el error). El paso guiado (`comun.esperar_enter`) se sustituye
por «la persona graba un recorrido y vuelve al Panel».
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from xml.sax.saxutils import quoteattr

import comun
import pytest
import validate22

URL = "https://api.example.com/v1"
ADMIN = ("admin@campus.edu.co", "Clave Segura$1")
TOKEN = "eyJ.token.secreto"
NOMBRE_ADMIN = "Alejandro Gómez"
PLAN_APP = "| FE-2.1 | 2 | Hecho | [2-1](x) | `a69a79a` 2026-10-26 | 0.7.2 | | |\n| FE-2.2 | 2 | En curso | | | | | |\n"
PLAN_BACKEND = "| BE-2.3 | 2 | Hecho | [2-3](x) | `abc1234` 2026-10-27 | 0.13.0 | |\n"
BOGOTA = timezone(timedelta(hours=-5))
HORA_INICIAL = datetime(2026, 10, 26, 10, 0, 0, tzinfo=BOGOTA)  # hora del teléfono cuando reloj = 1000
MESES = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sept.", "oct.", "nov.", "dic."]


class Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def reloj(self) -> float:
        return self.t

    def dormir(self, s: float) -> None:
        self.t += s


def _nodo(texto="", desc="", clase="android.widget.TextView", limites=(0, 0, 10, 10), enabled=True):
    x1, y1, x2, y2 = limites
    return (
        f"<node text={quoteattr(texto)} content-desc={quoteattr(desc)} class={quoteattr(clase)} "
        f'bounds="[{x1},{y1}][{x2},{y2}]" enabled="{str(enabled).lower()}" password="false"/>'
    )


def manifest(nombre, *, estado="finalizado", fotos=3, subidas=0, remoto=None, subida_estado=None) -> str:
    datos: dict = {
        "video_id": "x",
        "name": nombre,
        "created_at": "2026-10-26T09:00:00-05:00",
        "estado": estado,
        "photos": [
            {"id": f"{i:04d}", "file": f"photos/{i:04d}.jpg", "lat": 6.2, "lng": -75.578}
            | {"sync": "subida" if i <= subidas else "pendiente"}
            for i in range(1, fotos + 1)
        ],
    }
    if remoto:
        datos["remote_video_id"] = remoto
    if subida_estado:
        datos["subida_estado"] = subida_estado
    return json.dumps(datos)


def pendientes(manifests: dict[str, str]) -> int:
    """Lo que cuenta la app (escrito aparte del validador): fotos sin `sync = subida` de los `finalizado`."""
    total = 0
    for texto in manifests.values():
        d = json.loads(texto)
        if d.get("estado") == "finalizado":
            total += sum(1 for p in d["photos"] if p.get("sync") != "subida")
    return total


class Api:
    """Backend falso: salud, login, `GET /v1/admin/stats`, lugares públicos y de administración."""

    def __init__(self) -> None:
        self.lugares: dict[str, dict] = {}
        self.siguiente = 1
        self.total_fotos = 2842
        self.alertas = 0
        self.ultimo_video: dict | None = {"numero": 12, "creado_en": "2026-10-26T14:24:05Z"}  # 09:24 en Bogotá
        self.login_estado = 200
        self.stats_estado = 200
        self.stats_cuerpo: object | None = None  # si no es None, lo que responde stats (fuera de contrato)
        self.cambia_en_lectura: int | None = None  # desde esa lectura de stats, total_fotos sube en 1
        self.lecturas_stats = 0
        self.creados: list[dict] = []
        self.borrados: list[str] = []
        for nombre in ("Biblioteca Central", "Cafetería Principal"):
            self._crear({"nombre": nombre, "categoria": "bloque", "lat": 6.2009, "lng": -75.5783})

    def _crear(self, cuerpo: dict) -> dict:
        lugar = {**cuerpo, "id": f"uuid-{self.siguiente}"}
        self.siguiente += 1
        self.lugares[lugar["id"]] = lugar
        return lugar

    def stats(self) -> dict:
        return {
            "total_fotos": self.total_fotos,
            "total_lugares": len(self.lugares),
            "alertas_activas": self.alertas,
            "ultimo_video": self.ultimo_video,
        }

    def http_get(self, url, *, timeout=15.0, token=None):
        u = urlparse(url)
        ruta = u.path.removeprefix("/v1")
        if ruta == "/health":
            return comun.RespuestaHttp(200, {}, json.dumps({"estado": "ok"}), 30)
        if ruta == "/admin/stats":
            assert token == TOKEN
            self.lecturas_stats += 1
            if self.cambia_en_lectura is not None and self.lecturas_stats >= self.cambia_en_lectura:
                self.total_fotos += 1
                self.cambia_en_lectura = None
            if self.stats_estado != 200:
                cuerpo = {"error": {"codigo": "NO_ENCONTRADO"}}
                return comun.RespuestaHttp(self.stats_estado, {}, json.dumps(cuerpo), 30)
            cuerpo = self.stats_cuerpo if self.stats_cuerpo is not None else self.stats()
            return comun.RespuestaHttp(200, {}, json.dumps(cuerpo), 30)
        if ruta == "/places":
            items = sorted(self.lugares.values(), key=lambda lug: lug["nombre"])
            return comun.RespuestaHttp(200, {}, json.dumps({"items": items, "total": len(items)}), 30)
        if ruta == "/admin/places":
            assert token == TOKEN
            q = parse_qs(u.query)["q"][0].casefold()
            items = [lug for lug in self.lugares.values() if q in lug["nombre"].casefold()]
            return comun.RespuestaHttp(200, {}, json.dumps({"items": items, "total": len(items)}), 30)
        raise AssertionError(url)

    def http_post_json(self, url, cuerpo, *, timeout=15.0, token=None):
        ruta = urlparse(url).path.removeprefix("/v1")
        if ruta == "/auth/login":
            if self.login_estado != 200:
                return comun.RespuestaHttp(401, {}, json.dumps({"error": {"codigo": "CREDENCIALES_INVALIDAS"}}), 30)
            assert (cuerpo["identificador"], cuerpo["password"]) == ADMIN
            usuario = {"id": "u1", "nombre": NOMBRE_ADMIN, "correo": ADMIN[0], "rol": "admin"}
            return comun.RespuestaHttp(200, {}, json.dumps({"token": TOKEN, "usuario": usuario}), 30)
        if ruta == "/admin/places":
            assert token == TOKEN
            lugar = self._crear(dict(cuerpo))
            self.creados.append(lugar)
            return comun.RespuestaHttp(201, {}, json.dumps(lugar), 30)
        raise AssertionError(url)

    def http_delete(self, url, *, timeout=15.0, token=None):
        assert token == TOKEN
        lugar_id = unquote(urlparse(url).path.rsplit("/", 1)[-1])
        self.lugares.pop(lugar_id, None)
        self.borrados.append(lugar_id)
        return comun.RespuestaHttp(204, {}, "", 30)


class Telefono:
    """La app en un teléfono falso: Inicio, Login y el Panel con su «Resumen rápido», y `files/recoleccion/`."""

    def __init__(self, reloj: Reloj, api: Api, *, desfase_fotos=0, error_resumen=False, refresca=True) -> None:
        self.reloj = reloj
        self.api = api
        self.desfase_fotos = desfase_fotos
        self.error_resumen = error_resumen
        self.refresca = refresca
        self.manifests: dict[str, str] = {}
        self.ordenes: list[tuple[str, ...]] = []
        self.pantalla: str | None = None
        self.campos = ["", ""]
        self.foco: int | None = None
        self.desplazamientos = 0
        self.resumen: dict | None = None
        self.cargado_en = 0.0
        self.login_en: float | None = None

    def ahora(self) -> datetime:
        return HORA_INICIAL + timedelta(seconds=self.reloj.t - 1000.0)

    # --- lo que hace la app

    def _abrir_panel(self) -> None:
        self.pantalla = "panel"
        self.desplazamientos = 0
        self.resumen = {**self.api.stats(), "pendientes": pendientes(self.manifests)}
        self.cargado_en = self.reloj.t + 1.0

    def volver_al_panel(self, pantalla: str = "panel") -> None:
        """La persona vuelve al Panel tras el paso guiado (ON_RESUME: la app relee los recorridos)."""
        self.pantalla = pantalla
        if self.refresca and self.resumen is not None:
            self.resumen["pendientes"] = pendientes(self.manifests)

    def _fecha(self, creado_en: str) -> str:
        local = datetime.strptime(creado_en, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).astimezone(BOGOTA)
        hoy = self.ahora().date()
        if local.date() == hoy:
            return f"Hoy, {local:%H:%M}"
        if local.date() == hoy - timedelta(days=1):
            return f"Ayer, {local:%H:%M}"
        return f"{local.day} {MESES[local.month - 1]}, {local:%H:%M}"

    def _datos(self) -> list[tuple[str, str, str | None]]:
        r = self.resumen if self.reloj.t >= self.cargado_en and not self.error_resumen else None

        def num(n: int | None) -> str:
            return "—" if n is None else f"{n:,}".replace(",", ".")

        video = r["ultimo_video"] if r else None
        return [
            (num(r["total_fotos"] + self.desfase_fotos if r else None), "fotos en el dataset", None),
            (num(r["total_lugares"] if r else None), "lugares registrados", None),
            (num(r["alertas_activas"] if r else None), "alertas activas", None),
            (num(video["numero"] if video else None), "último video recolectado",
             self._fecha(video["creado_en"]) if video else None),
            (num(r["pendientes"] if r else None), "fotos pendientes de subir", None),
        ]  # fmt: skip

    # --- pantallas

    def _nodos(self) -> list[str]:
        if self.login_en is not None and self.reloj.t >= self.login_en:
            self.login_en = None
            self._abrir_panel()
        if self.pantalla == "inicio":
            return [
                _nodo(desc="Acceso administrador", clase="android.view.View", limites=(100, 2000, 980, 2100)),
                _nodo(texto="Acceso administrador", limites=(300, 2020, 800, 2080)),
            ]
        if self.pantalla == "login":
            puede = bool(self.campos[0]) and bool(self.campos[1])
            return [
                _nodo(texto=self.campos[0], clase="android.widget.EditText", limites=(60, 900, 1020, 1060)),
                _nodo(texto="•" * len(self.campos[1]), clase="android.widget.EditText", limites=(60, 1100, 1020, 1260)),
                _nodo(clase="android.widget.Button", limites=(60, 1330, 1020, 1500), enabled=puede),
                _nodo(texto="Iniciar sesión", limites=(300, 1380, 800, 1450)),
            ]
        if self.pantalla == "panel":
            nodos = []
            if self.desplazamientos == 0:
                nodos.append(_nodo(texto=validate22.saludo_esperado(NOMBRE_ADMIN), limites=(100, 200, 900, 280)))
                nodos.append(_nodo(desc="Recolector de imágenes. Captura…", limites=(60, 500, 520, 900)))
            else:
                nodos.append(_nodo(texto="Resumen rápido", limites=(100, 1200, 700, 1260)))
                if self.error_resumen and self.reloj.t >= self.cargado_en:
                    nodos.append(_nodo(texto="No se pudo cargar el resumen.", limites=(60, 1300, 800, 1350)))
                for i, (valor, etiqueta, detalle) in enumerate(self._datos()):
                    desc = f"{valor} {etiqueta}" + (f". {detalle}" if detalle else "")
                    x = 40 + i * 200
                    nodos.append(_nodo(desc=desc, clase="android.view.View", limites=(x, 1400, x + 190, 1700)))
                    nodos.append(_nodo(texto=valor, limites=(x + 10, 1480, x + 180, 1530)))
            return nodos
        if self.pantalla == "resumen-video":
            return [_nodo(texto="Resumen de video", limites=(100, 200, 900, 280))]
        return [_nodo(texto="Escritorio", limites=(0, 0, 1080, 2400))]

    def _xml(self) -> str:
        return f"<?xml version='1.0' encoding='UTF-8'?><hierarchy rotation=\"0\">{''.join(self._nodos())}</hierarchy>"

    def _tocar(self, x: int, y: int) -> None:
        if self.pantalla == "inicio" and 2000 <= y <= 2100:
            self.pantalla, self.campos = "login", ["", ""]
        elif self.pantalla == "login":
            if 900 <= y <= 1060:
                self.foco = 0
            elif 1100 <= y <= 1260:
                self.foco = 1
            elif 1330 <= y <= 1500 and tuple(self.campos) == ADMIN:
                self.login_en = self.reloj.t + 1.0

    # --- adb

    def adb(self, *args: str, timeout: int = 0) -> comun.Resultado:
        self.reloj.t += 0.3
        self.ordenes.append(args)
        ok = comun.Resultado(0, "", "")
        if args[0] == "exec-out" and args[1].startswith("uiautomator dump"):
            return comun.Resultado(0, self._xml(), "")
        if args[:3] == ("exec-out", "run-as", comun.PAQUETE):
            orden = args[3:]
            if orden == ("ls", "-1", validate22.DIR_RECOLECCION):
                return comun.Resultado(0, "".join(f"{c}\n" for c in sorted(self.manifests)), "")
            if orden[0] == "cat":
                m = re.fullmatch(r"files/recoleccion/([^/]+)/manifest\.json", orden[1])
                if m and m.group(1) in self.manifests:
                    return comun.Resultado(0, self.manifests[m.group(1)], "")
                return comun.Resultado(1, "", "No such file or directory")
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
        if orden == ("date", "+%Y-%m-%dT%H:%M:%S%z"):
            return comun.Resultado(0, self.ahora().strftime("%Y-%m-%dT%H:%M:%S%z") + "\n", "")
        if orden[:3] == ("run-as", comun.PAQUETE, "rm"):
            assert orden[3] == "-rf"
            self.manifests.pop(orden[4].removeprefix("files/recoleccion/"), None)
            return ok
        if orden[:2] == ("am", "force-stop"):
            self.pantalla, self.resumen, self.login_en = None, None, None
            return ok
        if orden[:2] == ("am", "start"):
            self.pantalla = "inicio"
            return comun.Resultado(0, "Status: ok\n", "")
        if orden[:2] == ("input", "tap"):
            self._tocar(int(orden[2]), int(orden[3]))
            return ok
        if orden[:2] == ("input", "text"):
            if self.foco is not None:
                self.campos[self.foco] += re.sub(r"\\(.)", r"\1", orden[2]).replace("%s", " ")
            return ok
        if orden[:2] == ("input", "swipe"):
            if self.pantalla == "panel":
                self.desplazamientos += 1
            return ok
        if orden[:2] == ("dumpsys", "input_method"):
            return comun.Resultado(0, "  mInputShown=false\n", "")
        if orden[:2] == ("wm", "size"):
            return comun.Resultado(0, "Physical size: 1080x2400\n", "")
        return ok


class Mundo:
    def __init__(self, tmp_path: Path, **opciones_telefono) -> None:
        self.tmp = tmp_path
        self.reloj = Reloj()
        self.api = Api()
        self.telefono = Telefono(self.reloj, self.api, **opciones_telefono)
        self.telefono.manifests = {
            "rec_0001": manifest("Entrada norte", fotos=5, subidas=2),  # 3 pendientes
            "rec_0002": manifest("Bloque 19", fotos=4, subidas=4, remoto="v2", subida_estado="completada"),
            "rec_0003": manifest("Sin terminar", estado="en_curso", fotos=4),  # no cuenta
        }
        self.casos = {"RemoteAdminRepositoryTest": 11, "TextosResumenTest": 6, "PendientesPanelTest": 5}
        self.gradle_ordenes: list[tuple[str, ...]] = []
        self.pasos_guiados: list[str] = []
        self.enter_eof = False
        self.graba: str | None = validate22.VIDEO_PRUEBA  # nombre del recorrido que graba la persona (None: nada)
        self.grabado = {"estado": "finalizado", "fotos": 4}
        self.pantalla_final = "panel"
        self.be23_hecho = True

    def instalar(self, monkeypatch) -> None:
        plan = self.tmp / "PLAN.md"
        plan.write_text(PLAN_APP, encoding="utf-8")
        plan_be = self.tmp / "PLAN_BE.md"
        plan_be.write_text(PLAN_BACKEND if self.be23_hecho else PLAN_BACKEND.replace("Hecho", "En curso"), "utf-8")
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
        monkeypatch.setattr(comun, "esperar_enter", self.esperar_enter)
        monkeypatch.setattr(comun, "reloj", self.reloj.reloj)
        monkeypatch.setattr(comun, "dormir", self.reloj.dormir)
        monkeypatch.setattr(comun, "commit_actual", lambda: "abc1234")
        monkeypatch.setenv("VALIDACION_ADMIN_CORREO", ADMIN[0])
        monkeypatch.setenv("VALIDACION_ADMIN_PASSWORD", ADMIN[1])

    def esperar_enter(self, instruccion: str) -> None:
        self.pasos_guiados.append(instruccion)
        if self.enter_eof:
            raise comun.ErrorConfiguracion(
                "el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)"
            )
        if self.graba is not None:
            numero = 1 + max(int(c.removeprefix("rec_")) for c in self.telefono.manifests)
            self.telefono.manifests[f"rec_{numero:04d}"] = manifest(self.graba, **self.grabado)
            self.reloj.t += 60
        self.telefono.volver_al_panel(self.pantalla_final)

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

    def borrados_del_telefono(self) -> list[str]:
        return [o[5] for o in self.telefono.ordenes if o[:5] == ("shell", "run-as", comun.PAQUETE, "rm", "-rf")]


def _correr(tmp_path, entorno, argv_extra=()):
    informe = tmp_path / "informe.json"
    codigo = validate22.main(["--entorno", entorno, "--informe", str(informe), *argv_extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def _estados(datos):
    return {c["id"]: c["estado"] for c in datos["comprobaciones"]}


def _detalle(datos, id_):
    return next(c["detalle"] for c in datos["comprobaciones"] + datos["precondiciones"] if c["id"] == id_)


# --- piezas puras ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("desc", "esperado"),
    [
        ("2.842 fotos en el dataset", ("fotos", "2.842", None)),
        ("2,842 fotos en el dataset", ("fotos", "2,842", None)),
        ("— lugares registrados", ("lugares", "—", None)),
        ("0 alertas activas", ("alertas", "0", None)),
        ("12 último video recolectado. Hoy, 09:24", ("video", "12", "Hoy, 09:24")),
        ("— último video recolectado", ("video", "—", None)),
        ("27 fotos pendientes de subir", ("pendientes", "27", None)),
        ("Recolector de imágenes. Captura y gestiona", None),
        ("fotos en el dataset", None),
    ],
)
def test_leer_dato(desc, esperado):
    leido = validate22.leer_dato(desc)
    if esperado is None:
        assert leido is None
    else:
        assert leido == (esperado[0], validate22.Dato(esperado[1], esperado[2]))


def test_valor_numerico():
    assert validate22.valor_numerico("2.842") == 2842
    assert validate22.valor_numerico("2,842") == 2842
    assert validate22.valor_numerico("2 842") == 2842
    assert validate22.valor_numerico("—") is None
    with pytest.raises(comun.Falla):
        validate22.valor_numerico("abc")


def test_fecha_esperada_en_la_zona_del_telefono():
    ahora = validate22.hora_telefono("2026-10-26T10:00:00-0500")
    patron, desc = validate22.fecha_esperada("2026-10-26T14:24:05Z", ahora)
    assert desc == "Hoy, 09:24" and re.fullmatch(patron, "Hoy, 09:24")
    # 04:59 UTC del 26 son las 23:59 del 25 en Bogotá: «Ayer», aunque en UTC sea el mismo día.
    patron, desc = validate22.fecha_esperada("2026-10-26T04:59:00.250Z", ahora)
    assert desc == "Ayer, 23:59" and re.fullmatch(patron, "Ayer, 23:59")
    patron, desc = validate22.fecha_esperada("2026-10-23T15:04:05Z", ahora)
    assert re.fullmatch(patron, "23 oct., 10:04") and re.fullmatch(patron, "23 oct, 10:04")
    assert not re.fullmatch(patron, "24 oct., 10:04") and not re.fullmatch(patron, "23 oct., 15:04")
    with pytest.raises(comun.Falla):
        validate22.fecha_esperada("2026-10-23T15:04:05+00:00", ahora)


def test_leer_estadisticas_y_contrato():
    totales = {"total_fotos": 5, "total_lugares": 2, "alertas_activas": 0}
    s = validate22.leer_estadisticas(totales | {"ultimo_video": {"numero": 3, "creado_en": "2026-10-26T14:24:05Z"}})
    assert (s.total_fotos, s.total_lugares, s.alertas_activas, s.ultimo_numero) == (5, 2, 0, 3)
    sin = validate22.leer_estadisticas(totales | {"ultimo_video": None})
    assert sin.ultimo_numero is None and sin.ultimo_creado_en is None
    malos = [
        {"total_fotos": 1, "total_lugares": 0, "ultimo_video": None},
        totales | {"total_fotos": "1", "ultimo_video": None},
        totales,
        totales | {"ultimo_video": {"creado_en": "2026-10-26T14:24:05Z"}},
        totales | {"ultimo_video": {"numero": 1, "creado_en": "ayer"}},
        totales | {"ultimo_video": {"numero": -1, "creado_en": "2026-10-26T14:24:05Z"}},
        [],
    ]
    for cuerpo in malos:
        with pytest.raises(ValueError):
            validate22.leer_estadisticas(cuerpo)


def test_leer_recorrido_como_la_app():
    r = validate22.leer_recorrido("rec_0001", manifest("Entrada norte", fotos=5, subidas=2))
    assert (r.nombre, r.finalizado, r.fotos, r.pendientes, r.remoto) == ("Entrada norte", True, 5, 3, False)
    sin_sync = json.loads(manifest("x", fotos=2))
    del sin_sync["photos"][0]["sync"]  # sin `sync` cuenta como pendiente (la app cuenta lo que no es `subida`)
    assert validate22.leer_recorrido("rec_0002", json.dumps(sin_sync)).pendientes == 2
    sin_nombre = validate22.leer_recorrido("rec_0003", manifest("  ", estado="en_curso"))
    assert sin_nombre.nombre == "rec_0003" and not sin_nombre.finalizado
    sin_lat = json.loads(manifest("x", fotos=2))
    del sin_lat["photos"][1]["lat"]
    assert validate22.leer_recorrido("rec_0004", json.dumps(sin_lat)) is None  # la app salta el manifest entero
    assert validate22.leer_recorrido("rec_0005", "{roto") is None
    assert validate22.leer_recorrido("rec_0006", None) is None


# --- validador completo ------------------------------------------------------------------------------------------


def test_dev_todo_bien_y_limpia_sin_imprimir_secretos(tmp_path, monkeypatch, capsys):
    m = Mundo(tmp_path)
    resto = m.api._crear({"nombre": "Validacion-2-2-Lugar", "categoria": "bloque", "lat": 6.2, "lng": -75.5})
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 0, datos
    assert [p["id"] for p in datos["precondiciones"]] == ["P1", "P2", "P3", "P4", "P5", "P6"]
    assert _estados(datos) == {"C1a": "pasa", "C1b": "pasa", "C2a": "pasa", "C2b": "pasa"}
    c1b = _detalle(datos, "C1b")
    assert "2.842 fotos, 3 lugares (incluye validacion-2-2-lugar), 0 alertas, último video 12 · «Hoy, 09:24»" in c1b
    assert "«Fotos pendientes de subir» = 7" in _detalle(datos, "C2b")
    assert "antes de grabar: 3" in _detalle(datos, "C2b")
    # Lugar: el resto se borró al empezar y el creado al terminar.
    assert m.api.borrados == [resto["id"], m.api.creados[0]["id"]]
    assert validate22.LUGAR_PRUEBA not in [lug["nombre"] for lug in m.api.lugares.values()]
    # Teléfono: solo se borró el recorrido de la prueba; los demás siguen; la app quedó cerrada.
    assert m.borrados_del_telefono() == ["files/recoleccion/rec_0004"]
    assert sorted(m.telefono.manifests) == ["rec_0001", "rec_0002", "rec_0003"]
    assert m.telefono.pantalla is None
    assert len(m.pasos_guiados) == 1 and f"«{validate22.VIDEO_PRUEBA}»" in m.pasos_guiados[0]
    assert "Guardar y subir después" in m.pasos_guiados[0]
    assert not any(o[:3] == ("shell", "pm", "clear") for o in m.telefono.ordenes)
    assert ("installDebug",) in m.gradle_ordenes
    pruebas = [o for o in m.gradle_ordenes if "testDebugUnitTest" in o]
    assert pruebas == [
        (
            "testDebugUnitTest",
            "--tests",
            "*.RemoteAdminRepositoryTest",
            "--tests",
            "*.TextosResumenTest",
            "--tests",
            "*.PendientesPanelTest",
        )
    ]
    salida = capsys.readouterr()
    informe = json.dumps(datos, ensure_ascii=False)
    for secreto in (ADMIN[1], TOKEN):
        assert secreto not in salida.out
        assert secreto not in salida.err
        assert secreto not in informe


def test_local_sin_telefono_ni_backend(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "local")
    assert codigo == 0, datos
    assert [p["id"] for p in datos["precondiciones"]] == ["P1"]
    assert _estados(datos) == {"C1a": "pasa", "C1b": "omitida", "C2a": "pasa", "C2b": "omitida"}
    assert m.telefono.ordenes == [] and m.api.creados == [] and m.pasos_guiados == []


def test_sin_video_el_panel_muestra_raya(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.api.ultimo_video = None
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 0, datos
    assert "sin video («—»)" in _detalle(datos, "C1b")
    assert m.pasos_guiados == []
    assert m.borrados_del_telefono() == []


def test_video_de_ayer_en_la_zona_del_telefono(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.api.ultimo_video = {"numero": 9, "creado_en": "2026-10-26T04:30:00Z"}  # 25 oct, 23:30 en Bogotá
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 0, datos
    assert "último video 9 · «Ayer, 23:30»" in _detalle(datos, "C1b")


def test_panel_distinto_de_la_api_falla_c1b_y_borra_el_lugar(tmp_path, monkeypatch):
    m = Mundo(tmp_path, desfase_fotos=1)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1"])
    assert codigo == 1
    assert "fotos en el dataset: Panel «2.843», API 2842" in _detalle(datos, "C1b")
    assert _estados(datos)["C1a"] == "pasa"
    assert m.api.creados and validate22.LUGAR_PRUEBA not in [lug["nombre"] for lug in m.api.lugares.values()]


def test_stats_que_cambia_durante_la_lectura_falla_c1b(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.api.cambia_en_lectura = 3  # P6 = 1, antes = 2, después = 3
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1
    assert "cambió mientras se leía el Panel" in _detalle(datos, "C1b")


def test_error_del_resumen_en_el_panel_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path, error_resumen=True)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1
    assert "No se pudo cargar el resumen." in _detalle(datos, "C1b")


def test_panel_que_no_relee_al_volver_falla_c2b(tmp_path, monkeypatch):
    m = Mundo(tmp_path, refresca=False)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 1
    assert "«Fotos pendientes de subir» del Panel = «3», pero los manifests del teléfono dan 7 y 7" in _detalle(
        datos, "C2b"
    )
    assert m.borrados_del_telefono() == ["files/recoleccion/rec_0004"]  # se limpia igual


def test_c2b_con_otro_nombre_falla_y_no_borra_nada(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.graba = "Mi prueba"
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 1
    assert "no hay un recorrido nuevo «validacion-2-2»" in _detalle(datos, "C2b")
    assert "rec_0004 «Mi prueba»" in _detalle(datos, "C2b")
    assert m.borrados_del_telefono() == []
    assert "rec_0004" in m.telefono.manifests


def test_c2b_sin_finalizar_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.grabado = {"estado": "en_curso", "fotos": 4}
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 1
    assert "está en_curso" in _detalle(datos, "C2b")
    assert m.borrados_del_telefono() == ["files/recoleccion/rec_0004"]


def test_c2b_sin_volver_al_panel_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.pantalla_final = "resumen-video"
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 1
    assert "no apareció el Panel" in _detalle(datos, "C2b")


def test_c2b_borra_restos_locales_pero_no_los_subidos(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.telefono.manifests["rec_0004"] = manifest(validate22.VIDEO_PRUEBA, fotos=2)  # resto: se borra
    m.telefono.manifests["rec_0005"] = manifest(
        validate22.VIDEO_PRUEBA, fotos=2, subidas=2, remoto="v5", subida_estado="completada"
    )  # se subió: se queda
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 0, datos
    assert m.borrados_del_telefono() == ["files/recoleccion/rec_0004", "files/recoleccion/rec_0006"]
    assert sorted(m.telefono.manifests) == ["rec_0001", "rec_0002", "rec_0003", "rec_0005"]
    assert "«Fotos pendientes de subir» = 7" in _detalle(datos, "C2b")


def test_be23_sin_hecho_es_bloqueo(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.be23_hecho = False
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 2
    assert "BE-2.3 no está «Hecho»" in _detalle(datos, "P6")
    assert m.telefono.ordenes[:1] and not m.pasos_guiados and not m.api.creados


@pytest.mark.parametrize(
    ("estado", "cuerpo", "mensaje"),
    [
        (404, None, "GET /v1/admin/stats respondió 404"),
        (200, {"total_fotos": 1, "total_lugares": 0, "alertas_activas": 0}, "falta ultimo_video"),
    ],
)
def test_stats_ausente_o_fuera_de_contrato_es_bloqueo(tmp_path, monkeypatch, estado, cuerpo, mensaje):
    m = Mundo(tmp_path)
    m.api.stats_estado = estado
    m.api.stats_cuerpo = cuerpo
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 2
    assert mensaje in _detalle(datos, "P6")


def test_credenciales_malas_son_3(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.api.login_estado = 401
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 3
    assert "credenciales del admin no sirven" in _detalle(datos, "P5")


def test_dev_solo_jvm_no_usa_telefono_ni_backend(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1a,C2a"])
    assert codigo == 0, datos
    estados = {p["id"]: p["estado"] for p in datos["precondiciones"]}
    assert estados == {"P1": "pasa", "P2": "no evaluada", "P3": "no evaluada", "P4": "no evaluada",
                       "P5": "no evaluada", "P6": "no evaluada"}  # fmt: skip
    assert m.telefono.ordenes == [] and m.api.lecturas_stats == 0


def test_si_falla_la_jvm_no_usa_el_telefono(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.casos["TextosResumenTest"] = 2
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1
    assert _estados(datos) == {"C1a": "falla", "C1b": "omitida", "C2a": "pasa", "C2b": "omitida"}
    assert "no se hace: falló C1a" in _detalle(datos, "C1b")
    assert m.pasos_guiados == [] and not m.api.creados


def test_sin_terminar_el_paso_guiado_es_3_y_limpia(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.enter_eof = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 3
    assert _estados(datos)["C1b"] == "pasa" and _estados(datos)["C2b"] == "error"
    assert validate22.LUGAR_PRUEBA not in [lug["nombre"] for lug in m.api.lugares.values()]
    assert m.telefono.pantalla is None
