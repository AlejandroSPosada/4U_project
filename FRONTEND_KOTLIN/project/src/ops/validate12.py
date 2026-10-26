"""Validador de FE-1.2 — Login contra el backend.

Documento: FRONTEND_KOTLIN/docs/validation/validation-1-2.md. Entornos: local (C3 y C4, pruebas en la JVM) y dev
(todo, con un dispositivo físico). En dev: inicia sesión como admin con POST /v1/auth/login (P5), crea o reactiva la
cuenta validacion+user@campus.edu.co con una tarea suelta de campus-locator-dev-migrate y la desactiva al terminar
(también si algo falla); en el teléfono instala el APK de depuración (conserva los datos), concede los permisos de
Inicio y maneja la interfaz con adb (uiautomator dump, input tap/text). Nunca imprime contraseñas ni tokens.
"""

from __future__ import annotations

import re
import sys

import comun

CLASE_C3 = "SesionVencidaTest"
CLASE_C4 = "RemoteAuthRepositoryTest"
MINIMO_CASOS = {CLASE_C3: 4, CLASE_C4: 3}
LIMITE_LOGIN_S = 15  # C1 y C2: desde el toque en «Iniciar sesión» (validation-1-2 §2)
INTENTOS_DESPLAZAR = 4  # C1: veces que baja el Panel buscando «Cerrar sesión»
PERMISOS_INICIO = ["android.permission.CAMERA", "android.permission.RECORD_AUDIO"]
PERMISO_ACTIVIDAD = "android.permission.ACTIVITY_RECOGNITION"  # Permisos.INICIALES desde Android 10 (SDK 29)
ERRORES_LOGIN = ("Credenciales inválidas", "Sin conexión", "Algo salió mal")  # títulos del banner de Login (5.5)


def saludo_esperado(nombre: str) -> str:
    """Lo que dibuja el Panel (7.2): «Hola, <lo que hay antes del primer espacio del nombre>» o «Hola» sin nombre."""
    primero = nombre.strip().split(" ")[0]
    return f"Hola, {primero}" if primero else "Hola"


class Contexto:
    def __init__(self, v: comun.Validador) -> None:
        self.v = v
        self.url: str | None = None
        self.sdk: int = 0
        self.admin: tuple[str, str] | None = None
        self.nombre_admin = ""
        self.outputs: dict[str, object] | None = None
        self.password_user: str | None = None
        self.telefono_listo = False
        self.gradle_pruebas: comun.Resultado | None = None

    # --- teléfono

    def preparar_telefono(self) -> None:
        """Una vez: `installDebug` (conserva los datos) y `pm grant` de los permisos de Inicio (Permisos.INICIALES)."""
        if self.telefono_listo:
            return
        self.v.al_limpiar(
            "cerrar la app (am force-stop)", lambda: comun.adb("shell", "am", "force-stop", comun.PAQUETE)
        )
        r = comun.gradle("installDebug", timeout=1800)
        if "INSTALL_FAILED_USER_RESTRICTED" in r.texto:
            raise comun.ErrorConfiguracion(
                "installDebug: INSTALL_FAILED_USER_RESTRICTED — en MIUI/HyperOS activa «Instalar vía USB» en Opciones "
                "de desarrollador y acepta el diálogo de instalación en el teléfono"
            )
        if r.codigo != 0:
            raise comun.Falla(f"installDebug falló: {comun.resumir(r.texto[-600:], 300)}")
        permisos = PERMISOS_INICIO + ([PERMISO_ACTIVIDAD] if self.sdk >= 29 else [])
        for permiso in permisos:
            g = comun.adb("shell", "pm", "grant", comun.PAQUETE, permiso, timeout=30)
            comun.exigir_adb_permitido(g, f"conceder {permiso.rsplit('.', 1)[-1]} (pm grant)")
            if g.codigo != 0:
                raise comun.Falla(f"pm grant {permiso} falló: {comun.resumir(g.texto, 200)}")
        self.telefono_listo = True

    # --- cuenta user de prueba

    def asegurar_usuario(self) -> str:
        """Crea o reactiva la cuenta `user` de prueba (una vez). La limpieza la desactiva aunque algo falle: se
        registra antes de lanzar `crear-usuario` (si no llegó a crearla, «no existe» se tolera)."""
        if self.password_user is None:
            outputs = self.outputs
            if outputs is None:
                raise comun.ErrorConfiguracion("sin outputs de Terraform (P3 no se evaluó)")
            self.v.al_limpiar(
                f"desactivar {comun.USUARIO_VALIDACION}",
                lambda: comun.desactivar_usuario_validacion(outputs, tolerar_inexistente=True),
            )
            comun.avisar(f"creando o reactivando {comun.USUARIO_VALIDACION} (tarea suelta de migrate, ~2 min)")
            self.password_user = comun.crear_usuario_validacion(outputs)
        return self.password_user

    # --- pruebas en la JVM (C3 y C4 comparten una sola ejecución de Gradle)

    def pruebas(self) -> comun.Resultado:
        if self.gradle_pruebas is None:
            clases = [c for c, i in ((CLASE_C3, "C3"), (CLASE_C4, "C4")) if self.v.incluida(i)]
            comun.borrar_resultados(clases)
            argumentos = ["testDebugUnitTest"]
            for clase in clases:
                argumentos += ["--tests", f"*.{clase}"]
            self.gradle_pruebas = comun.gradle(*argumentos, timeout=1800)
        return self.gradle_pruebas


def main(argv: list[str] | None = None) -> int:
    v = comun.Validador(
        lote="FE-1.2",
        validacion="validation-1-2",
        descripcion=__doc__ or "",
        comprobaciones=["C1", "C2", "C3", "C4"],
    )
    ctx = Contexto(v)

    # --- precondiciones ----------------------------------------------------------------------------------------

    def p1_gradle() -> str:
        r = comun.gradle("--version", timeout=600)
        if r.codigo != 0:
            raise comun.ErrorConfiguracion(
                f"{' '.join(comun.comando_gradle())} --version falló: {comun.resumir(r.texto)}"
            )
        jvm = re.search(r"^JVM:\s+(.+)$", r.salida, re.MULTILINE)
        version = re.search(r"^Gradle (\S+)", r.salida, re.MULTILINE)
        return f"Gradle {version.group(1) if version else '?'}, JVM {jvm.group(1).strip() if jvm else '?'}"

    def p2_dispositivo() -> str:
        serial = comun.dispositivo_fisico()
        modelo = comun.adb("shell", "getprop", "ro.product.model", timeout=30).salida.strip()
        android = comun.adb("shell", "getprop", "ro.build.version.release", timeout=30).salida.strip()
        sdk = comun.adb("shell", "getprop", "ro.build.version.sdk", timeout=30).salida.strip()
        ctx.sdk = int(sdk) if sdk.isdigit() else 0
        return f"{modelo or '?'} (Android {android or '?'}, SDK {sdk or '?'}, serial {serial})"

    def p3_aws() -> str:
        arn = comun.cuenta_aws()
        outputs = comun.terraform_outputs()
        comun.salidas_tarea(outputs)  # exige ecs_cluster, familias_tarea.migrate, subredes_tareas y sg_migrate
        ctx.outputs = outputs
        return f"cuenta {comun.CUENTA} ({arn.rsplit(':', 1)[-1]}); outputs para la tarea suelta de migrate"

    def p4_fe11() -> str:
        texto = comun.PLAN_APP.read_text(encoding="utf-8")
        if not comun.lote_hecho(texto, "FE-1.1"):
            raise comun.Bloqueo("FE-1.1 no está «Hecho» en PLAN.md §3")
        url, origen = comun.url_api_vigente()
        ctx.url = url
        de_la_app = comun.normalizar_url(comun.url_api_config())
        if de_la_app != url:
            raise comun.Bloqueo(f"FE-1.1: ApiConfig.BASE_URL = {de_la_app}, pero {origen} da {url}")
        try:
            r = comun.http_get(f"{url}/health")
        except comun.ErrorRed as e:
            raise comun.Bloqueo(f"INF-1.4: GET /v1/health sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or cuerpo.get("estado") != "ok":
            raise comun.Bloqueo(f"BE-1.1: GET /v1/health respondió {r.estado}")
        return f"FE-1.1 Hecho; ApiConfig = {origen}; GET /v1/health -> 200"

    def p5_login_admin() -> str:
        correo, password = comun.credenciales_admin(v.entorno)
        ctx.admin = (correo, password)
        try:
            r = comun.http_post_json(f"{ctx.url}/auth/login", {"identificador": correo, "password": password})
        except comun.ErrorRed as e:
            raise comun.Bloqueo(f"INF-1.4: POST /v1/auth/login sin respuesta ({e})") from e
        codigo = comun.codigo_error(r)
        if r.estado == 401:
            raise comun.ErrorConfiguracion(
                f"las credenciales del admin no sirven (401 {codigo}): "
                f"revisa VALIDACION_ADMIN_* o {comun.SECRETO_ADMIN}"
            )
        if r.estado == 404:
            raise comun.Bloqueo("BE-1.3: POST /v1/auth/login responde 404 (¿desplegado?)")
        if r.estado != 200:
            cuerpo_error = r.json()
            de_api_gateway = isinstance(cuerpo_error, dict) and "message" in cuerpo_error
            descripcion = codigo or ("(API Gateway; ¿api sin tareas?)" if de_api_gateway else "")
            raise comun.Bloqueo(f"BE-1.3: POST /v1/auth/login respondió {r.estado} {descripcion}".rstrip())
        cuerpo = r.json()
        usuario = cuerpo.get("usuario") if isinstance(cuerpo, dict) else None
        if (
            not isinstance(cuerpo, dict)
            or not isinstance(cuerpo.get("token"), str)
            or not cuerpo["token"]
            or not isinstance(cuerpo.get("expira_en"), str)
            or not isinstance(usuario, dict)
        ):
            raise comun.Bloqueo("BE-1.3: el 200 del login no trae token, expira_en y usuario")
        if usuario.get("rol") != "admin":
            raise comun.ErrorConfiguracion(f"la cuenta {correo} no tiene rol admin (rol {usuario.get('rol')!r})")
        ctx.nombre_admin = str(usuario.get("nombre") or "")
        return f"200: {correo}, rol admin, expira_en {cuerpo['expira_en']}"

    def cuerpo(v: comun.Validador) -> None:
        dev = v.entorno == "dev"
        if not v.precondicion("P1", p1_gradle):
            return
        if dev:
            if not v.precondicion("P2", p2_dispositivo):
                for p in ("P3", "P4", "P5"):
                    v.precondicion_no_evaluada(p, "P2 no se cumple")
                return
            if v.incluida("C2"):
                if not v.precondicion("P3", p3_aws):
                    for p in ("P4", "P5"):
                        v.precondicion_no_evaluada(p, "P3 no se cumple")
                    return
            else:
                v.precondicion_no_evaluada("P3", "C2 excluida con --solo")
            if not v.precondicion("P4", p4_fe11):
                v.precondicion_no_evaluada("P5", "P4 no se cumple")
                return
            if not v.precondicion("P5", p5_login_admin):
                return

        # --- comprobaciones automáticas ------------------------------------------------------------------------

        if dev:
            v.comprobacion("C1", c1_admin_entra)
            v.comprobacion("C2", c2_user_sin_permisos)
        else:
            v.omitir("C1", "solo en dev (necesita el dispositivo y el backend)")
            v.omitir("C2", "solo en dev (necesita el dispositivo y el backend)")
        v.comprobacion("C3", lambda: pruebas_clase(CLASE_C3))
        v.comprobacion("C4", lambda: pruebas_clase(CLASE_C4))

    def error_en_login(nodos: list[comun.Nodo]) -> str | None:
        for titulo in ERRORES_LOGIN:
            if comun.primero(nodos, contiene=titulo) is not None:
                return titulo
        return None

    def c1_admin_entra() -> str:
        ctx.preparar_telefono()
        assert ctx.admin is not None
        correo, password = ctx.admin
        comun.abrir_login()
        inicio = comun.enviar_credenciales(correo, password)
        saludo = saludo_esperado(ctx.nombre_admin)

        def panel(nodos: list[comun.Nodo]) -> comun.Nodo | None:
            error = error_en_login(nodos)
            if error is not None:
                raise comun.Falla(f"la app mostró «{error}» en vez del Panel")
            if comun.primero(nodos, contiene="Sin permisos") is not None:
                raise comun.Falla("la app mostró «Sin permisos» con la cuenta admin")
            return comun.primero(nodos, dice=saludo)

        _, nodos = comun.esperar_nodo(panel, LIMITE_LOGIN_S, f"«{saludo}» (Panel)")
        for intento in range(INTENTOS_DESPLAZAR + 1):
            if comun.primero(nodos, dice="Cerrar sesión") is not None:
                break
            if intento == INTENTOS_DESPLAZAR:
                raise comun.Falla(f"el Panel no muestra «Cerrar sesión»; en pantalla: {comun.textos_visibles(nodos)}")
            comun.desplazar_hacia_abajo()
            nodos = comun.volcar_pantalla()
        segundos = comun.reloj() - inicio
        if segundos > LIMITE_LOGIN_S:
            raise comun.Falla(f"«{saludo}» y «Cerrar sesión» aparecieron a los {segundos:.1f} s (> {LIMITE_LOGIN_S})")
        return f"Panel con «{saludo}» y «Cerrar sesión» a los {segundos:.1f} s del toque"

    def c2_user_sin_permisos() -> str:
        password = ctx.asegurar_usuario()
        ctx.preparar_telefono()
        comun.abrir_login()
        inicio = comun.enviar_credenciales(comun.USUARIO_VALIDACION, password)

        def banner(nodos: list[comun.Nodo]) -> comun.Nodo | None:
            error = error_en_login(nodos)
            if error is not None:
                raise comun.Falla(f"la app mostró «{error}» en vez de «Sin permisos»")
            if comun.primero(nodos, dice="Cerrar sesión") or comun.primero(nodos, contiene="Hola,"):
                raise comun.Falla("la cuenta user abrió el Panel")
            return comun.primero(nodos, contiene="Sin permisos")

        _, nodos = comun.esperar_nodo(banner, LIMITE_LOGIN_S, "el banner «Sin permisos»")
        segundos = comun.reloj() - inicio
        if comun.primero(nodos, dice="Cerrar sesión") is not None:
            raise comun.Falla("aparece «Cerrar sesión» junto a «Sin permisos»")
        return f"«Sin permisos» a los {segundos:.1f} s, sin «Cerrar sesión»"

    def pruebas_clase(clase: str) -> str:
        r = ctx.pruebas()
        res = comun.resultados_clase(clase)
        if res is None:
            raise comun.Falla(
                f"{clase}: sin resultados; Gradle salió con {r.codigo}: {comun.resumir(r.texto[-600:], 300)}"
            )
        if not res.ok or res.pruebas < MINIMO_CASOS[clase]:
            raise comun.Falla(
                f"{clase}: {res.pruebas} casos (mínimo {MINIMO_CASOS[clase]}), "
                f"{res.fallos} fallos, {res.errores} errores"
            )
        return f"{clase} {res.pruebas}/{res.pruebas} (mínimo {MINIMO_CASOS[clase]})"

    return v.correr(cuerpo, argv)


if __name__ == "__main__":
    sys.exit(main())
