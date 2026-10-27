# Validación 3-4 — FE-3.4 Lugares de administración (7.6, 7.7)

| Campo | Valor |
|---|---|
| Lote | `FE-3.4` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate34.py` |
| Entornos | `dev` (cierra el lote): dispositivo físico conectado por `adb` y la API de `dev`; no usa `embedding`. `local` (sin teléfono ni backend: C1a, C2a y C3a) |
| Criterios | Automáticos: C1 (C1a, C1b y C1c), C2 (C2a y C2b), C3 (C3a y C3b), con tres pasos guiados · Manuales: ninguno |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta
(dónde corren, variables, `comun.py`, detalles de `validate34.py`, trampas): `ARCHITECTURE.md` §5.11. Piezas que se
comprueban: `ARCHITECTURE.md` §4.8 (lo construido en FE-3.4), §5.5 («Lugares de administración»: vistas 7.6 y 7.7, el pie
«Punto: …», `FormularioLugar`, `ErroresLugarMapeo`; «Selección de destino»: el `content-desc` de `FilaLugar`), §5.6
(`LugarAdmin`, `DatosLugar`, `LugaresAdminRepository`), §5.8 (rutas `admin/lugares` y `admin/lugares/form?id={id}`) y
§5.10 («Lugares de administración»). Contrato del backend que se consume: `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5.5,
«Lugares: `/v1/admin/places` (BE-3.1)» (`LugarEntrada`, `LugarAdmin`, `409 NOMBRE_DUPLICADO` con `detalle: null`), y
§5.3, `GET /v1/places` (`distancia_m` con posición). El validador no recalcula nada de eso: compara lo que mostró la app
con lo que responde la API.

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla (las siguientes quedan «no evaluada»). Las de la máquina y
las credenciales dan **3**; las de otros lotes, **2** (lote `Bloqueado`). En `local` solo se evalúa P1; en `dev`, P2–P6
solo si alguna de C1b, C2b, C1c o C3b está incluida.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Gradle y un JDK que lo ejecute | `<VALIDACION_GRADLE> --version` termina con 0 (detalle: versión de Gradle y JVM). Si no → 3 |
| P2 | Dispositivo físico | `adb devices` con uno en estado `device` (el de `ANDROID_SERIAL` si hay varios) y `ro.kernel.qemu` distinto de `1`; anota modelo, Android y SDK. Si no → 3 |
| P3 | La app apunta a la API vigente y responde | URL vigente = `terraform output -raw api_base_url` + `/v1` (sin Terraform, `VALIDACION_API_URL`; sin ninguna → 3), igual a `ApiConfig.BASE_URL` del código, y `GET <URL>/health` → 200 `"estado": "ok"` (si no → 2) |
| P4 | Login de admin contra `dev` | `POST <URL>/auth/login` con `VALIDACION_ADMIN_CORREO`/`VALIDACION_ADMIN_PASSWORD` o el secreto `campus-locator/dev/admin-inicial` → 200 con `token` y `usuario.rol = "admin"` (`401` o rol distinto → 3; otro código → 2). Guarda el token (nunca se imprime) y el nombre (para el saludo del Panel) |
| P5 | `FE-1.2` en «Hecho»: login de admin en la app | La fila de `FE-1.2` en `PLAN.md` §3 dice `Hecho`. Si no → 2 |
| P6 | `BE-3.1` en «Hecho»: lugares | La fila de `BE-3.1` en `BACKEND_FASTAPI/docs/PLAN.md` §3 dice `Hecho`, y `GET <URL>/admin/places` con el token y `GET <URL>/places` → 200 con `items`. Si no → 2 |

## 2. Comprobaciones automáticas

C1a, C2a y C3a corren en una sola ejecución de Gradle; si alguna falla, C1b, C2b, C1c y C3b quedan `omitida` («no se
hace: falló …»). En `local`, C1b, C2b, C1c y C3b quedan `omitida`. Orden en `dev`: C1a, C2a, C3a, C1b, C2b, C1c, C3b.
C2b y C1c usan el lugar que crea C1b: sin C1b incluida, o si C1b no lo creó, quedan `omitida`.

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | Borra los XML anteriores y ejecuta `<VALIDACION_GRADLE> testDebugUnitTest --tests '*.RemoteLugaresAdminRepositoryTest'` (junto con C2a y C3a); lee `app/build/test-results/testDebugUnitTest/TEST-*.<clase>.xml` | Gradle sale con 0 y la clase tiene su XML, 0 fallos, 0 errores, 0 omitidos y al menos 8 casos (hoy 11). Cubre `/v1/admin/places` con la sesión: listar y mapear todos los campos, crear con el cuerpo exacto (la coordenada del formulario sin cambios), `PUT`, `DELETE`, el `409` como `Validacion` sin campos, el `422` con campos, sin sesión y sin red (`ARCHITECTURE.md` §5.10) |
| C2a | Como C1a, con `--tests '*.FormularioLugarTest'` | XML con 0 fallos, errores ni omitidos y ≥ 8 casos (hoy 10): coordenada a 6 decimales y el pie «Punto: lat, lng» con punto decimal aunque el teléfono esté en español (lo que se ve es lo que se envía), límites del formulario, alias, editar un lugar guardado sin perder datos y el filtro de 7.6 |
| C3a | Como C1a, con `--tests '*.ErroresLugarTest'` | XML con 0 fallos, errores ni omitidos y ≥ 4 casos (hoy 5): el `409 NOMBRE_DUPLICADO` va bajo el campo nombre (y solo ahí), el `422` a cada campo, la sesión perdida no muestra nada, y sin red / lugar borrado / otros van al mensaje general |
| C1b | Borra los restos de una ejecución anterior (§4) e **inicia sesión por la interfaz** como `validation-2-2` C1b (`installDebug`, permisos de Inicio, «Acceso administrador», correo y contraseña con `input text`, espera «Hola, <nombre>»). **Paso guiado 1:** en el Panel, «Lugares» → «Nuevo lugar»: nombre `validacion-3-4-lugar`, alias `validacion`, categoría Bloque, tocar el mapa en un punto libre; **sin** pulsar «Guardar»; Enter. Después vuelca 7.7 con `uiautomator dump` (si el teclado tapa el pie, Atrás solo si está abierto), lee el pie «Punto: <lat>, <lng>» y el campo Nombre, **toca «Guardar»** y espera hasta 20 s a la lista 7.6 («Vista de lista»); lee `GET /v1/places` | El pie muestra un punto (6 decimales), el Nombre es exactamente `validacion-3-4-lugar` (si no, falla sin guardar nada), el formulario no muestra ningún error y vuelve a 7.6, y `GET /v1/places` tiene **un** `validacion-3-4-lugar` con `categoria = "bloque"` y `alias = ["validacion"]` |
| C2b | `GET /v1/places?lat=<lat>&lng=<lng>` con el punto **tal como lo mostró el pie** del formulario en C1b | El primer elemento es `validacion-3-4-lugar` y su `distancia_m` es < 1 (con el redondeo de la app, 0,0) |
| C1c | **Paso guiado 2:** volver a Inicio (Atrás hasta el Panel y «Volver al modo público») y decir «dos»; Enter. Espera hasta 20 s a Selección de destino («¿A dónde quieres ir?»), toca el buscador (lo busca con hasta 4 desplazamientos), escribe `validacion-3-4` (`input text`), cierra el teclado (Atrás solo si está abierto) y busca la fila con `uiautomator dump` (hasta 4 desplazamientos) | Hay una fila (`FilaLugar`, `content-desc` «…. Toca para elegir este destino.») con «validacion-3-4-lugar, Bloque» |
| C3b | Crea `validacion-3-4-dup` con `POST /v1/admin/places` y vuelve a entrar al Panel en frío. **Paso guiado 3:** en el Panel, «Lugares» → «Nuevo lugar»: nombre `VALIDACIÓN-3-4-DUP` (mayúsculas y tilde), cualquier categoría, tocar el mapa; **sin** pulsar «Guardar»; Enter. Comprueba el Nombre y el pie, **toca «Guardar»**, espera hasta 20 s al mensaje y lee `GET /v1/admin/places?q=validacion-3-4` | El Nombre es el mismo que `validacion-3-4-dup` sin mayúsculas ni tildes (si no, falla sin guardar); el formulario sigue a la vista con «Ya existe un lugar con ese nombre (sin distinguir mayúsculas ni tildes).» bajo el nombre (el `409 NOMBRE_DUPLICADO`; no vuelve a 7.6), y el backend sigue con un solo `validacion-3-4-dup` |

## 3. Comprobaciones manuales

Ninguna: todos los criterios son automáticos (los pasos guiados los hace la persona, pero lo comprueba el script, que es
quien pulsa «Guardar»).

## 4. Datos de prueba y limpieza

- **Lugares `validacion-3-4-lugar`** (lo crea la persona desde la app en C1b) y **`validacion-3-4-dup`** (lo crea el
  script con `POST /v1/admin/places` en C3b: categoría `bloque`, en 6.2006, −75.5783, con una `descripcion` que lo
  identifica). Al empezar, el script borra los restos de una ejecución anterior: los de `GET /v1/admin/places?q=
  validacion-3-4` cuyo nombre normalizado (sin tildes ni mayúsculas, la regla del backend) es **exactamente** uno de esos
  dos (`DELETE /v1/admin/places/{id}`); al terminar, también si algo falló, hace lo mismo. Nunca borra otros lugares (uno
  que solo *contiene* el prefijo, p. ej. «validacion-3-4-lugar viejo», se queda). No tienen fotos (`total_fotos` 0).
- Si la persona escribió otro nombre y pulsó «Guardar» por su cuenta, ese lugar **no** se borra (el script no lo
  reconoce): borrarlo en 7.6 (⋮ → «Eliminar»).
- En el teléfono no borra nada ni usa `pm clear`; la limpieza termina con `am force-stop` (el teléfono queda sin sesión,
  `ARCHITECTURE.md` §5.3). Cada login deja su fila en `auditoria` y cada crear o borrar, las suyas (`lugar.crear`,
  `lugar.eliminar`; registro, se conservan).
- Con `--sin-limpieza` quedan los dos lugares (la siguiente ejecución los borra como restos).

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate34.py --entorno dev
```

Sin argumentos propios. Los tres pasos guiados leen la entrada estándar: hay que correrlo en una terminal interactiva
(sin redirigir la entrada, p. ej. `< /dev/null`, ni lanzarlo desde un script sin terminal) o, como hizo el maestro en
FE-2.2, con la entrada en una FIFO para mandar cada Enter.

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
v2 en WSL (si se usa el secreto) y, en Windows, el JBR 21 y el Android SDK. Duración aproximada en `dev`: 10–15 min
(Gradle 1–3 min; `installDebug` 1–2 min; dos logins por la interfaz, ~1 min; los tres pasos guiados, 5–8 min). No
necesita `embedding` (sin hora límite). Crea y borra lugares en `dev`: no correrlo a la vez que otro validador que cree,
borre o cuente lugares (p. ej. `validate22.py`, cuyo C1b compara `total_lugares`). El informe queda en
`project/.validacion/FE-3.4-<AAAAMMDD-HHMMSS>.json` (hora UTC) o en `--informe RUTA`.

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
   read -r -p 'Correo del admin de dev: ' VALIDACION_ADMIN_CORREO
   read -r -s -p 'Contraseña del admin de dev: ' VALIDACION_ADMIN_PASSWORD; echo
   export VALIDACION_ADMIN_CORREO VALIDACION_ADMIN_PASSWORD
   ```
   Esperado: solo las dos preguntas (la contraseña no se ve al escribirla).
2. Pruebas y estilo de los validadores:
   ```bash
   uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen pytest -q
   ```
   Esperado: `All checks passed!`, `20 files already formatted` y `241 passed`.
3. Compilación y pruebas unitarias de la app:
   ```bash
   cmd.exe /c '.\gradlew.bat' --console=plain testDebugUnitTest assembleDebug
   ```
   Esperado: `BUILD SUCCESSFUL` (272 casos, sin fallos). Si dice `Unable to delete directory '…\app\build\…'`, borrar
   `app/build` (`rm -rf app/build`) y repetir (ARCHITECTURE §4.1, «Trampas»).
4. Copia de trabajo limpia (si no, el informe sale con `-dirty`; ARCHITECTURE §5.11, «Trampas»):
   ```bash
   git -c core.autocrlf=input status --short -- .
   ```
   Esperado: sin salida.
5. Teléfono: conectado por USB a Windows, con la depuración USB autorizada, **desbloqueado, con la pantalla encendida**
   («Pantalla activa» en Opciones de desarrollador mientras carga), con Wi-Fi o datos, **TalkBack desactivado** (con
   TalkBack activo `input swipe` puede no desplazar Destino; sin comprobar) y el reconocimiento de voz disponible (C1c
   abre Destino con la voz «dos»):
   ```bash
   $VALIDACION_ADB devices
   ```
   Esperado: una línea `<serial>	device` (no `unauthorized` ni `offline`).
6. Solo en Xiaomi (MIUI/HyperOS): «Instalar vía USB» y «Depuración USB (Configuración de seguridad)» activadas
   (`validation-1-2` §5, paso 5). MIUI apaga «Instalar vía USB» por su cuenta entre sesiones (pasó al validar FE-3.1 y
   FE-2.2): mirarlo antes. Esta orden solo comprueba la segunda:
   ```bash
   $VALIDACION_ADB shell input keyevent 0
   ```
   Esperado: sin salida. Si sale una `java.lang.SecurityException` que menciona `INJECT_EVENTS`, falta «Depuración USB
   (Configuración de seguridad)».
7. Que `dev` responde y que BE-3.1 está cerrado:
   ```bash
   curl -s "$(terraform -chdir=../../INFRASTRUCTURA_TERRAFORM/project/envs/dev output -raw api_base_url)/v1/health"; echo
   grep '^| BE-3.1 |' ../../BACKEND_FASTAPI/docs/PLAN.md | tail -1
   ```
   Esperado: `{"estado":"ok","version":"…","commit":"<SHA corto>"}` y una fila `| BE-3.1 | 3 | Hecho | …` (si no, el
   script dará código 2 en P6).

**Ejecución.** En una terminal interactiva, con el teléfono a mano. El validador instala la app, entra al Panel con el
admin y se detiene en cada **paso guiado** (líneas `· PASO GUIADO — …` por stderr). En el teléfono:

1. **Paso guiado 1 (C1b)**, desde el Panel: **«Lugares»** → **«Nuevo lugar»** → Nombre **`validacion-3-4-lugar`**, Alias
   **`validacion`**, categoría **Bloque** → tocar el mapa en un punto **libre** (lejos de los puntos violeta de otros
   lugares) y comprobar que el pie dice «Punto: <números>». **No pulsar «Guardar»** (lo pulsa el script). Cerrar el
   teclado si tapa el pie y pulsar **Enter**. El script guarda y la app vuelve a la lista de lugares.
2. **Paso guiado 2 (C1c)**: Atrás hasta el Panel → **«Volver al modo público»** → en Inicio, decir **«dos»**: se abre
   Selección de destino. No tocar nada, **no contestar** la pregunta hablada de Destino («¿A dónde quieres ir?»: si se
   dice un lugar, la app sale de Destino y C1c falla; pasó el 2026-10-27) y pulsar **Enter** (el script escribe en el
   buscador).
3. **Paso guiado 3 (C3b)**: el script vuelve a abrir la app y entra al Panel. **«Lugares»** → **«Nuevo lugar»** →
   Nombre **`VALIDACIÓN-3-4-DUP`** (con mayúsculas y tilde), cualquier categoría, tocar el mapa en cualquier punto. **No
   pulsar «Guardar»**; cerrar el teclado si tapa el pie y pulsar **Enter**. El script guarda y espera el mensaje del
   `409` bajo el nombre.

Cuidados (ARCHITECTURE §4.8 y §5.11): si se pulsa «Guardar» antes del Enter, C1b falla («no se ve el formulario de
lugar») y la limpieza borra el lugar; en el mapa, **tocar** pone el alfiler (arrastrar el mapa con un dedo puede desplazar
la página: sin comprobar en el teléfono).

```bash
uv run --group ops python src/ops/validate34.py --entorno dev
```

Esperado (código 0; por stderr salen además líneas `· …` de progreso —los restos borrados, el punto leído del
formulario, el lugar duplicado creado, los pasos guiados, la limpieza— y la ruta del informe):

```
[PASA] P1 Gradle 8.7, JVM 21.0.11 (JetBrains s.r.o. 21.0.11+1-b1163.116)
[PASA] P2 23028RA60L (Android 14, SDK 34, serial <serial>)
[PASA] P3 ApiConfig = terraform output api_base_url; GET /v1/health -> 200
[PASA] P4 200: <correo del admin>, rol admin
[PASA] P5 FE-1.2 Hecho
[PASA] P6 BE-3.1 Hecho; GET /v1/admin/places -> 200 (<n>); GET /v1/places -> 200 (<n>)
[PASA] C1a RemoteLugaresAdminRepositoryTest 11/11 (mínimos 8)
[PASA] C2a FormularioLugarTest 10/10 (mínimos 8)
[PASA] C3a ErroresLugarTest 5/5 (mínimos 4)
[PASA] C1b «validacion-3-4-lugar» creado en 7.7 aparece una vez en GET /v1/places (categoria bloque, alias [validacion], <lat>, <lng>); 7.6 a la vista tras «Guardar»
[PASA] C2b GET /v1/places?lat=<lat>&lng=<lng> (el punto del formulario) da primero «validacion-3-4-lugar» con distancia_m = 0.0 (< 1); guardado en <lat>, <lng>
[PASA] C1c Selección de destino, con «validacion-3-4» en el buscador, muestra la fila «validacion-3-4-lugar, Bloque»
[PASA] C3b «VALIDACIÓN-3-4-DUP» → 409: el formulario muestra «Ya existe un lugar con ese nombre (sin distinguir mayúsculas ni tildes).» y no se cierra; GET /v1/admin/places sigue con un solo «validacion-3-4-dup»
Resultado: pasa (código 0)
```

Al terminar, en stderr: `· limpieza: cerrar la app (am force-stop)` y `· limpieza: borrar los lugares de prueba
(validacion-3-4-lugar, validacion-3-4-dup)` (orden inverso al de registro).

Casos previstos:
- `[FALLA] P6 BE-3.1 no está «Hecho» …` (código 2) → BE-3.1 no está cerrado: esperar.
- `[FALLA] C1b no se ve el formulario de lugar (7.7) para C1b; en pantalla: …` → se pulsó Enter con otra pantalla (o
  «Guardar» antes de tiempo): repetir.
- `[FALLA] C1b el formulario dice «Punto: sin elegir (toca el mapa)»: falta tocar el mapa` → repetir tocando el mapa.
- `[FALLA] C1b el nombre del formulario es «…», no «validacion-3-4-lugar» (no se guardó nada)` → repetir con ese
  nombre exacto (en el teléfono queda el borrador: «Cancelar»).
- `[FALLA] C1b el formulario no guardó: «…»` → la app mostró ese error (sin red, `422`, «Ya existe…» si quedó un lugar
  con ese nombre que el script no borró): avisar con el detalle; mirar las líneas `I/Api` de `files/logs/app.log`.
- `[FALLA] C1b GET /v1/places tiene … lugares «validacion-3-4-lugar» …`, `… tiene categoria = …` o `… tiene alias …` →
  la app no envió lo que se eligió: avisar con el detalle.
- `[FALLA] C2b GET /v1/places?lat=…&lng=… da primero «…» (a … m), no «validacion-3-4-lugar» …` o `[FALLA] C2b
  «validacion-3-4-lugar» está a … m de «Punto: …» (máximo 1.0)` → la posición guardada no es la del pie (criterio C2):
  avisar con el detalle.
- `[FALLA] C1c en 20 s no apareció Selección de destino …` → la voz «dos» no abrió Destino (¿micrófono, reconocimiento
  de voz?): repetir. `[FALLA] C1c Selección de destino no muestra «validacion-3-4-lugar, Bloque» …` → la lista no trae
  el lugar nuevo: avisar con las filas que se vieron.
- `[FALLA] C3b el formulario se cerró como si hubiera guardado «…» (se esperaba el 409)` → la app no mostró el `409`
  (criterio C3): avisar. `[FALLA] C3b en 20 s tras «Guardar» no se vio «Ya existe un lugar con ese nombre…» …` → otro
  error en pantalla (el detalle dice cuál).
- `[ERROR] C1b el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)` (código 3) → correr el
  validador en una terminal interactiva (o con una FIFO). La limpieza corre igual.
- `[ERROR] C1b … installDebug: INSTALL_FAILED_USER_RESTRICTED …` o `… el teléfono no deja a adb … (SecurityException)`
  (código 3) → paso 6.
- `[FALLA] P4 las credenciales del admin no sirven (401 CREDENCIALES_INVALIDAS) …` (código 3) → revisar
  `VALIDACION_ADMIN_*` (paso 1) o el secreto.

En `local` (sin teléfono, API ni AWS): `uv run --group ops python src/ops/validate34.py --entorno local` da código 0 con
`[PASA]` en P1, C1a, C2a y C3a y `[OMITIDA]` en C1b, C2b, C1c y C3b (comprobado el 2026-10-26 en el worktree de FE-3.4,
sobre `e56e211` con los cambios sin commit: C1a 11/11, C2a 12/12, C3a 5/5; entonces `FormularioLugarTest` tenía 12 casos,
2 de ellos de la hoja de 7.4 que se quitó el 2026-10-27, ARCHITECTURE §4.8; tras quitarla no se repitió y hoy se espera
C2a 10/10). Con `--solo C1a,C2a,C3a` en `dev`, P2–P6
quedan «no evaluada» y no se usa el teléfono ni el backend. Con `--solo C1b,C2b` se repite solo lo del formulario.

Con el validador en `dev` con código 0 sobre un commit de `main` sin `-dirty`, la fila FE-3.4 de PLAN §3 pasa a «Hecho»
y se quitan de ARCHITECTURE §4.8, §5.5, §5.9 y §5.11 los «sin comprobar» que la ejecución confirme.
