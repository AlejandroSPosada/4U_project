# Validación 3-1 — FE-3.1 Lugares públicos y entrada al mapa

| Campo | Valor |
|---|---|
| Lote | `FE-3.1` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate31.py` |
| Entornos | `dev` con dispositivo físico (cierra el lote, junto con la evidencia de C2c); `local` (sin teléfono ni backend: C1a, C2a y C2b) |
| Criterios | Automáticos: C1 (C1b; apoyo C1a), C2 (apoyo: C2a y C2b) · Manuales: C2 (C2c, solo por voz desde el 2026-10-26) |
| Resultado | **Hecho** el 2026-10-26: `validate31.py --entorno dev` con código 0 sobre `b553390` y C2c por voz (§3 y el final de §5) |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta
(dónde corren, variables, `comun.py`, detalles de `validate31.py`, trampas): `ARCHITECTURE.md` §5.11. Piezas que se
comprueban: `ARCHITECTURE.md` §4.5 (lo construido en FE-3.1), §5.2 (`ComandoParser`, `PdrTracker`,
`ObservadorPrimerPlano`), §5.5 (Inicio, `FilaLugar`, `MapaPublicoScreen`), §5.6 (`LugaresRepository`), §5.8 (rutas
`inicio` y `mapa`) y §5.10 («Lugares»). Contrato del backend que se consume: `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5.3
(`GET /v1/places`) y §5.5 (`/v1/admin/places`, solo para el lugar de prueba).

Desde el 2026-10-25 este lote no lleva alertas (decisión del usuario: «No necesitamos las alertas por el momento»): sus
comprobaciones de caché, sincronización y anuncio pasaron a [`validation-3-6`](./validation-3-6.md) (FE-3.6).

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla (las siguientes quedan «no evaluada»). Las de la máquina y
las credenciales dan **3**; las de otros lotes, **2** (lote `Bloqueado`). En `local` solo se evalúa P1. En `dev`, P2–P5
solo hacen falta para C1b: con `--solo` sin C1b quedan «no evaluada».

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Gradle y un JDK que lo ejecute | `<VALIDACION_GRADLE> --version` termina con 0 (detalle: versión de Gradle y JVM). Si no → 3 |
| P2 | Dispositivo físico conectado (solo `dev`) | `adb devices` muestra uno en estado `device` (el de `ANDROID_SERIAL` si hay varios) y `adb shell getprop ro.kernel.qemu` no es `1`; lee modelo, versión de Android y SDK. Si no → 3 |
| P3 | `FE-1.1` en «Hecho»: la app usa la API de `dev` (solo `dev`) | La fila de `FE-1.1` en `PLAN.md` §3 dice `Hecho`; `ApiConfig.BASE_URL` (leído de `ApiConfig.kt`) es igual a la URL vigente = `terraform output -raw api_base_url` + `/v1` (sin Terraform, `VALIDACION_API_URL`; sin ninguna de las dos → 3); `GET <URL>/health` responde 200 con `"estado": "ok"`. Si no → 2 |
| P4 | Credenciales de admin para el lugar de prueba (solo `dev`) | `VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` si están las dos; si no, el secreto `campus-locator/dev/admin-inicial` (`AWS_PROFILE`). `POST <URL>/auth/login` → 200 con `token` y `usuario.rol = "admin"`. `401` o rol distinto → 3; otro código o sin respuesta → 2 (BE-1.3). El token nunca se imprime |
| P5 | `BE-3.1` en «Hecho»: lugares (solo `dev`) | La fila de `BE-3.1` en `BACKEND_FASTAPI/docs/PLAN.md` §3 dice `Hecho` y `GET <URL>/places` responde 200 con `items` (anota cuántos; **no** exige ≥ 1: en `dev` puede no haber lugares). Si no → 2 |

## 2. Comprobaciones automáticas

En este orden. En `local`, C1b queda `omitida` («solo en dev»).

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | Borra los XML anteriores y ejecuta una vez `<VALIDACION_GRADLE> testDebugUnitTest --tests '*.RemoteLugaresRepositoryTest'` (junto con C2a si está incluida); lee `app/build/test-results/testDebugUnitTest/TEST-*.RemoteLugaresRepositoryTest.xml` | Gradle sale con 0 y la clase tiene su XML, 0 fallos, errores ni omitidos y ≥ 6 casos (hoy 9). Cubren `GET /v1/places` sin y con posición, sin `Authorization`, el mapeo a `LugarDestino`, lugares descartados y los errores (`ARCHITECTURE.md` §5.10, «Lugares»); lo confirma la revisión del PR |
| C1b | (`dev`) `installDebug` (**conserva los datos**) y `pm grant` de los permisos de Inicio (como `validate12`). Con el token de P4: borra el lugar `validacion-3-1-lugar` que haya dejado una ejecución anterior (§4) y lo crea con `POST /v1/admin/places`. `am force-stop` + `am start` y espera Inicio («Acceso administrador»). **Paso guiado:** pide a la persona abrir Selección de destino (voz «dos», o la acción de TalkBack «Ir a un lugar» y después desactivar TalkBack) y pulsar Enter. Espera hasta 20 s la pantalla («¿A dónde quieres ir?» y alguna fila), lee los nombres de las filas (`content-desc` de `FilaLugar`) con `uiautomator dump`, desplazando la lista con `adb shell input swipe` hasta que dos desplazamientos seguidos no traen filas nuevas, y la compara con `GET /v1/places` | Los nombres de las filas son exactamente los de `items[].nombre`, sin faltantes ni sobrantes, e incluyen `validacion-3-1-lugar`. Falla en el acto si Destino muestra «No se pudo cargar la lista de lugares.» o «No hay lugares con estos filtros», y si no se ve Selección de destino en 20 s (con lo que se veía). Sin terminal para el paso guiado (EOF) → `error` (3) |
| C2a | Como C1a, con `--tests '*.ComandoParserTest' --tests '*.ObservadorPrimerPlanoTest'` | XML con 0 fallos, errores ni omitidos y ≥ 4 casos cada una (hoy 5 y 6): la voz «mapa» (palabra completa, sola) y que el PDR del mapa no vuelve a leer sensores si el mapa sigue en la pila sin verse aunque el proceso vuelva al primer plano (hallazgo de FE-2.3, ADR-FE-22) |
| C2b | Lee `MainActivity.kt`, `InicioScreen.kt`, `InicioViewModel.kt` y `MapaPublicoScreen.kt` | La ruta `inicio` pasa a `InicioScreen` un `onVerMapa` que navega a `"mapa"`; la ruta `mapa` compone `MapaPublicoScreen(`; el orbe tiene `CustomAccessibilityAction("Ver mapa") { onVerMapa()`; `InicioEvento.VerMapa -> onVerMapa()`; `Comando.VER_MAPA -> navegar(InicioEvento.VerMapa)`; y `MapaPublicoScreen` crea el `PdrTracker` con `cicloDeVida =` el `LocalLifecycleOwner.current.lifecycle`. (La acción «Ver mapa» se comprueba aquí en el código; su prueba con TalkBack en el teléfono es de FE-3.6, §3) |

## 3. Comprobaciones manuales

La evidencia se guarda en [`evidencia/fe-3-1/`](./evidencia/fe-3-1/) y se cita en el PR. En los comandos, `adb` es
`$VALIDACION_ADB` en WSL (§5) y `EVID=../docs/validation/evidencia/fe-3-1` desde `FRONTEND_KOTLIN/project`. El script
la imprime como `[MANUAL] C2c`.

**Desde el 2026-10-26 C2c es solo por voz** (decisión del usuario al validar en `dev`, PLAN §2.2 FE-3.1: «Si, por
favor. Cambialo y demos por hecho lo que llevamos.»). Lo que llevaba además —abrir el mapa con TalkBack y la acción
«Ver mapa», fijar un punto de inicio y pulsar ▶, y comprobar después con `dumpsys sensorservice` y las líneas `Pdr`
que el mapa deja de leer sensores al volver a Inicio— pasó a [`validation-3-6`](./validation-3-6.md) §3 (FE-3.6 C5),
junto con el punto de inicio del mapa sin tocarlo. **Trampa:** el texto que imprime `validate31.py` para `[MANUAL] C2c`
todavía menciona TalkBack, ▶ y `dumpsys` (es el del código validado en `b553390`); se corrige en el próximo cambio de
código de la app. Para cerrar FE-3.1 vale el procedimiento de abajo.

| ID | Qué hace la persona | Evidencia |
|---|---|---|
| C2c | Desde Inicio abre el mapa público (ruta `mapa`, `MapaPublicoScreen`) con el comando de voz «mapa» y vuelve a Inicio con Atrás (procedimiento abajo) | Capturas o fotogramas de una grabación de pantalla: Inicio, el mapa abierto por la voz y la vuelta a Inicio. Un video que muestre algo privado (o pesado) no se versiona y se cita en el PR |

**C2c — procedimiento** (`ARCHITECTURE.md` §4.5 y §5.5 «Inicio»; el APK del commit que se valida ya instalado: lo
instala C1b o `installDebug`).
1. Abrir la app desde el lanzador (Inicio). Empezar a grabar la pantalla (en el Xiaomi, «Grabadora de pantalla», o
   `adb shell screenrecord /sdcard/fe31-c2.mp4`, que no graba audio y para con Ctrl+C).
2. Tras la bienvenida («…, o mapa para ver el mapa»), decir **«mapa»**: se abre el mapa público (la página
   «StepTracker», con «Comenzar»).
3. Pulsar **Atrás**: vuelve a Inicio, que repite la bienvenida y vuelve a escuchar («Te escucho…»).
4. Parar la grabación y guardar en `$EVID` las capturas (o fotogramas) de los tres momentos.
5. Pasa si se ven las tres pantallas en ese orden.

**Hecho el 2026-10-26** (09:24 de Bogotá, Xiaomi 23028RA60L, Android 14, APK de `b553390`): el usuario dijo «mapa» →
mapa público («StepTracker · Comenzar») → Atrás → Inicio («Te escucho…»). Evidencia:
[`c2-1-inicio.png`](./evidencia/fe-3-1/c2-1-inicio.png), [`c2-2-mapa-por-voz.png`](./evidencia/fe-3-1/c2-2-mapa-por-voz.png)
y [`c2-3-atras-a-inicio.png`](./evidencia/fe-3-1/c2-3-atras-a-inicio.png), fotogramas de un `screenrecord` de 74 s
(sin audio, 14 MB, no versionado). No se fijó un punto ni se pulsó ▶: no hubo líneas `Pdr` ni se tomó
`dumpsys sensorservice` (eso queda en FE-3.6 C5). Con TalkBack no se completó (hallazgos con TalkBack 17 en
`ARCHITECTURE.md` §4.5).

## 4. Datos de prueba y limpieza

Crea con la API el lugar `validacion-3-1-lugar` (`POST /v1/admin/places`, categoría `bloque`, `alias` vacío y una
`descripcion` que dice que es de prueba), 0,0002° al norte del primer lugar de `GET /v1/places` o, si no hay ninguno,
en (6.2006, −75.5783). Al terminar, también si algo falló, lo borra con `DELETE /v1/admin/places/{id}` (la limpieza se
registra en cuanto el `POST` devuelve el id). Al empezar, borra los restos de una ejecución anterior: los de
`GET /v1/admin/places?q=validacion-3-1` cuyo nombre es **exactamente** `validacion-3-1-lugar` (sin distinguir mayúsculas
ni tildes, como el backend); nunca otros lugares. Con `--sin-limpieza` el lugar queda hasta la siguiente ejecución
completa. Cada cambio deja su fila en `auditoria` del backend (`lugar.crear`, `lugar.eliminar`; es registro y se
conserva).

En el teléfono: `installDebug` conserva los datos de la app (recorridos, calibración, `app.log`) y no se usa
`pm clear`; los permisos concedidos con `pm grant` son los mismos que pide Inicio. Al terminar, `am force-stop` (la
lista de Destino con el lugar de prueba no queda abierta). El volcado de pantalla se borra del teléfono en la misma
orden que lo crea. Los archivos de `evidencia/fe-3-1/` no llevan secretos (`dumpsys` y las líneas `Pdr` no tienen
tokens).

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate31.py --entorno dev
```

Sin argumentos propios. El paso guiado de C1b lee la entrada estándar: hay que correrlo en una terminal interactiva
(sin redirigir la entrada, p. ej. `< /dev/null`, ni lanzarlo desde un script sin terminal).

**Variables** (detalle en `ARCHITECTURE.md` §5.11). En la máquina del equipo el validador corre en WSL y usa el Gradle y
el `adb` de Windows (ARCHITECTURE §4.1):

| Variable | Valor en WSL | Obligatoria |
|---|---|---|
| `VALIDACION_GRADLE` | `cmd.exe /c .\gradlew.bat` | Sí en WSL (WSL no tiene JDK ni SDK) |
| `JAVA_HOME` | `C:\Users\frank\.jdks\jbr-21.0.11` (el JBR 21; el de Android Studio es Java 25 y Gradle 8.7 no lo admite) | Sí en WSL |
| `WSLENV` | `JAVA_HOME:ANDROID_SERIAL` (pasa esas dos a los procesos de Windows) | Sí en WSL |
| `VALIDACION_ADB` | `/mnt/c/Users/frank/AppData/Local/Android/Sdk/platform-tools/adb.exe` | Sí en WSL, en `dev` |
| `AWS_PROFILE` | `campus-admin` (`terraform output api_base_url`, cuyo estado está en S3, y el secreto del admin si no se dan `VALIDACION_ADMIN_*`) | Sí en `dev`, salvo que estén `VALIDACION_API_URL` y las dos `VALIDACION_ADMIN_*` |
| `VALIDACION_ADMIN_CORREO`, `VALIDACION_ADMIN_PASSWORD` | Las del admin de `dev`, leídas sin eco (paso 1); sin ellas, el secreto `campus-locator/dev/admin-inicial` | No |
| `VALIDACION_API_URL` | No hace falta: solo se usa si `terraform output` falla | No |
| `ANDROID_SERIAL` | Solo si hay varios dispositivos | No |
| `UV_PROJECT_ENVIRONMENT` | `/root/.cache/uv-envs/fe-ops` (el `.venv` fuera de `/mnt/c`, más rápido) | No |

Herramientas: `uv`, `terraform` con `terraform init` hecho en `INFRASTRUCTURA_TERRAFORM/project/envs/dev`, la CLI `aws`
v2 en WSL (si se usa el secreto) y, en Windows, el JBR 21 y el Android SDK. Duración aproximada en `dev`: 5–8 min
(Gradle 1–3 min; `installDebug` 1–2 min; el paso guiado y la lectura de la lista, 1–2 min), más 5–10 min de la manual
C2c. No necesita `embedding` (sin hora límite). El informe queda en
`project/.validacion/FE-3.1-<AAAAMMDD-HHMMSS>.json` (hora UTC) o en `--informe RUTA`.

**Preparación.**

1. Variables del entorno (en la misma terminal de WSL donde se ejecutará el validador). Las credenciales del admin se
   leen sin eco y no quedan en el historial (si se prefiere el secreto, saltar las dos líneas `read` y el `export` de
   `VALIDACION_ADMIN_*`):
   ```bash
   cd /mnt/c/Users/frank/Documents/baul/uni/2026-2/P2/4U_project/FRONTEND_KOTLIN/project
   export AWS_PROFILE=campus-admin
   export JAVA_HOME='C:\Users\frank\.jdks\jbr-21.0.11'
   export WSLENV=JAVA_HOME:ANDROID_SERIAL
   export VALIDACION_GRADLE='cmd.exe /c .\gradlew.bat'
   export VALIDACION_ADB=/mnt/c/Users/frank/AppData/Local/Android/Sdk/platform-tools/adb.exe
   export UV_PROJECT_ENVIRONMENT=/root/.cache/uv-envs/fe-ops
   export EVID=../docs/validation/evidencia/fe-3-1
   read -r -p 'Correo del admin de dev: ' VALIDACION_ADMIN_CORREO
   read -r -s -p 'Contraseña del admin de dev: ' VALIDACION_ADMIN_PASSWORD; echo
   export VALIDACION_ADMIN_CORREO VALIDACION_ADMIN_PASSWORD
   ```
   Esperado: solo las dos preguntas (la contraseña no se ve al escribirla).
2. Pruebas y estilo de los validadores:
   ```bash
   uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen pytest -q
   ```
   Esperado: `All checks passed!`, `14 files already formatted` y `159 passed`.
3. Compilación y pruebas unitarias de la app:
   ```bash
   cmd.exe /c '.\gradlew.bat' --console=plain testDebugUnitTest assembleDebug
   ```
   Esperado: `BUILD SUCCESSFUL` (171 casos, sin fallos). Si dice `Unable to delete directory '…\app\build\…'`, borrar
   `app/build` (`rm -rf app/build`) y repetir (ARCHITECTURE §4.1, «Trampas»).
4. Copia de trabajo limpia (si no, el informe sale con `-dirty`; ARCHITECTURE §5.11, «Trampas»):
   ```bash
   git -c core.autocrlf=input status --short -- .
   ```
   Esperado: sin salida.
5. Teléfono: conectado por USB a Windows, con la depuración USB autorizada, **desbloqueado, con la pantalla encendida**
   («Pantalla activa» en Opciones de desarrollador mientras carga), con Wi-Fi o datos y **TalkBack desactivado** (con
   TalkBack activo `input swipe` puede no desplazar la lista; sin comprobar):
   ```bash
   $VALIDACION_ADB devices
   ```
   Esperado: una línea `<serial>	device` (no `unauthorized` ni `offline`).
6. Solo en Xiaomi (MIUI/HyperOS): «Instalar vía USB» y «Depuración USB (Configuración de seguridad)» activadas
   (`validation-1-2` §5, paso 5). **MIUI puede apagar «Instalar vía USB» por su cuenta** entre sesiones: así falló el
   primer intento del 2026-10-26 (C1b `INSTALL_FAILED_USER_RESTRICTED`, código 3); mirarlo antes de cada validación.
   Esta orden solo comprueba la segunda (la primera se ve al instalar):
   ```bash
   $VALIDACION_ADB shell input keyevent 0
   ```
   Esperado: sin salida. Si sale una `java.lang.SecurityException` que menciona `INJECT_EVENTS`, falta «Depuración USB
   (Configuración de seguridad)».
7. Que `dev` responde y cuántos lugares tiene:
   ```bash
   API="$(terraform -chdir=../../INFRASTRUCTURA_TERRAFORM/project/envs/dev output -raw api_base_url)/v1"
   curl -s "$API/health"; echo
   curl -s "$API/places" | python3 -c 'import json,sys; print(json.load(sys.stdin)["total"], "lugares")'
   mkdir -p $EVID && ls -d $EVID
   ```
   Esperado: `{"estado":"ok","version":"…","commit":"<SHA corto>"}`, `<n> lugares` (puede ser `0`) y
   `../docs/validation/evidencia/fe-3-1`.

**Ejecución.** En una terminal interactiva, con el teléfono a mano: el validador instala la app, la abre en Inicio y se
detiene en el **paso guiado** (líneas `· PASO GUIADO — …` por stderr). Entonces, en el teléfono, decir **«dos»**,
esperar a ver «¿A dónde quieres ir?» y la lista **sin tocar el buscador ni los filtros**, y pulsar **Enter** en la
terminal. Después no tocar el teléfono: el validador desliza la lista solo. (La instrucción del script ofrece también
la acción de TalkBack «Ir a un lugar», pero con TalkBack 17 en el Xiaomi no se encontró cómo abrir las acciones:
usar la voz; `ARCHITECTURE.md` §4.5.)

```bash
uv run --group ops python src/ops/validate31.py --entorno dev
```

Esperado (código 0; por stderr salen además líneas `· …` de progreso —el lugar creado, el paso guiado, la limpieza— y
la ruta del informe):

```
[PASA] P1 Gradle 8.7, JVM 21.0.11 (JetBrains s.r.o. 21.0.11+1-b1163.116)
[PASA] P2 23028RA60L (Android 14, SDK 34, serial <serial>)
[PASA] P3 FE-1.1 Hecho; ApiConfig = terraform output api_base_url; GET /v1/health -> 200
[PASA] P4 200: <correo del admin>, rol admin
[PASA] P5 BE-3.1 Hecho; GET /v1/places -> 200 (<n> lugares)
[PASA] C1a RemoteLugaresRepositoryTest 9/9 (mínimos 6)
[PASA] C1b <n+1> lugares en Selección de destino = GET /v1/places (incluye «validacion-3-1-lugar»; <k> desplazamientos)
[PASA] C2a ComandoParserTest 5/5, ObservadorPrimerPlanoTest 6/6 (mínimos 4, 4)
[PASA] C2b ruta inicio: onVerMapa → navigate("mapa"); voz «mapa» (Comando.VER_MAPA) y acción de TalkBack «Ver mapa» → InicioEvento.VerMapa; ruta mapa → MapaPublicoScreen con el ciclo de vida de su pantalla
[MANUAL] C2c [APK de este commit instalado por C1b] Con la app abierta desde el lanzador (Inicio), di «mapa»: …
Resultado: pasa (código 0)
```

Al terminar, en stderr: `· limpieza: cerrar la app (am force-stop)` y `· limpieza: borrar el lugar validacion-3-1-lugar`.
Después, hacer la manual C2c (§3) con el APK ya instalado: solo la parte por voz (el texto de `[MANUAL] C2c` todavía
pide también TalkBack, ▶ y `dumpsys`; eso es de FE-3.6, §3).

Casos previstos:
- `[ERROR] C1b el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)` (código 3) → correr el
  validador en una terminal interactiva, sin redirigir la entrada. La limpieza borra el lugar igual.
- `[FALLA] C1b en 20 s no se vio Selección de destino («¿A dónde quieres ir?»); en pantalla: …` → no se abrió Destino
  antes del Enter (la voz no entendió «dos»): repetir.
- `[FALLA] C1b la lista de Destino (<a>) no es la de GET /v1/places (<b>): faltan …` → si TalkBack seguía activo, la
  lista puede no haberse desplazado (solo leyó la primera pantalla): desactivarlo y repetir; o la app apunta a otra API (P3 lo habría visto) o
  descartó un lugar de una categoría que no conoce (línea `W/Lugares` en `app.log`).
- `[FALLA] C1b Selección de destino mostró «Sin conexión: No se pudo cargar la lista de lugares.» …` → el teléfono no
  llega a la API: mirar las líneas `I/Api` de `files/logs/app.log`.
- `[FALLA] C1b … uiautomator dump no devolvió la pantalla … «could not get idle state»` → la animación del micrófono de
  Destino no deja quieta la pantalla (**sin comprobar**): tocar el micrófono para que deje de escuchar y repetir; si
  sigue, avisar al maestro.
- `[ERROR] C1b el teléfono no deja a adb conceder CAMERA (pm grant) (SecurityException): …` o `installDebug:
  INSTALL_FAILED_USER_RESTRICTED …` (código 3) → paso 6 (visto el 2026-10-26: MIUI había apagado «Instalar vía USB»).
- `[FALLA] P4 las credenciales del admin no sirven (401 CREDENCIALES_INVALIDAS) …` (código 3) → revisar
  `VALIDACION_ADMIN_*` (paso 1) o el secreto.
- `[FALLA] P5 BE-3.1 …` (código 2) → el backend de lugares no está desplegado o la base no responde.

En `local` (sin teléfono, API ni AWS): `uv run --group ops python src/ops/validate31.py --entorno local` da código 0 con
`[PASA]` en P1, C1a, C2a y C2b, `[OMITIDA]` en C1b y la `[MANUAL]` C2c (comprobado el 2026-10-26). Sin teléfono en
`dev`, P2 falla y el código es 3 (`adb devices no muestra ningún dispositivo`).

Con el validador en `dev` con código 0 sobre un commit de `main` sin `-dirty` y la evidencia de C2c en
`evidencia/fe-3-1/`, la fila FE-3.1 de PLAN §3 pasa a «Hecho» y se quitan de ARCHITECTURE §4.5 los «a verificar en
dispositivo y en `dev`» que la evidencia confirme.

**Validado el 2026-10-26** (Xiaomi 23028RA60L, Android 14). El primer intento (14:17 UTC) dio código 3: C1b
`INSTALL_FAILED_USER_RESTRICTED` (paso 6). El segundo, sobre `b553390` sin `-dirty`, dio **código 0** (informe
`.validacion/FE-3.1-20261026-142022.json`, 14:20–14:23 UTC): P1–P5 (`GET /v1/places` → 0 lugares en `dev`, así que el
lugar de prueba se creó en `POSICION_CAMPUS`); C1a 9/9; C1b «1 lugares en Selección de destino = GET /v1/places
(incluye validacion-3-1-lugar; 2 desplazamientos)», con Destino abierto por el usuario con la voz «dos» y el Enter
mandado por el maestro; C2a 5/5 y 6/6; C2b; limpieza con el lugar borrado y `am force-stop`. `uiautomator dump` volcó
Destino sin «could not get idle state» justo después de abrirla, cuando pregunta y escucha (si el micrófono seguía
animado en ese instante no quedó registrado). C2c por voz: §3.
