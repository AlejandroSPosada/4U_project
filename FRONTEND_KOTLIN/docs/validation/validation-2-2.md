# Validación 2-2 — FE-2.2 Panel con datos reales

| Campo | Valor |
|---|---|
| Lote | `FE-2.2` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate22.py` |
| Entornos | `dev` (cierra el lote): dispositivo físico conectado por `adb` y la API de `dev`; no usa `embedding`. `local` (sin teléfono ni backend: C1a y C2a) |
| Criterios | Automáticos: C1 (C1a y C1b), C2 (C2a y C2b, con un paso guiado) · Manuales: ninguno |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta
(dónde corren, variables, `comun.py`, detalles de `validate22.py`, trampas): `ARCHITECTURE.md` §5.11. Piezas que se
comprueban: `ARCHITECTURE.md` §4.7 (lo construido en FE-2.2), §5.5 (Panel: `PanelAdminViewModel`, `PanelAdminScreen`,
`TextosResumen` y el `content-desc` de cada dato), §5.6 (`ResumenAdmin`) y §5.10 («Panel» y «Subida de un recorrido»).
Contrato del backend que se consume: `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5.5, subsección «`GET /v1/admin/stats`
(BE-2.3)» (desde backend 0.13.0): qué cuenta cada total, qué video es el último y cuándo es `null`, y el formato de
`creado_en`. El validador no recalcula nada de eso: compara el Panel con lo que responde la API.

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla (las siguientes quedan «no evaluada»). Las de la máquina y
las credenciales dan **3**; las de otros lotes, **2** (lote `Bloqueado`). En `local` solo se evalúa P1; en `dev`, P2–P6
solo si C1b o C2b están incluidas.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Gradle y un JDK que lo ejecute | `<VALIDACION_GRADLE> --version` termina con 0 (detalle: versión de Gradle y JVM). Si no → 3 |
| P2 | Dispositivo físico | `adb devices` con uno en estado `device` (el de `ANDROID_SERIAL` si hay varios) y `ro.kernel.qemu` distinto de `1`; anota modelo, Android y SDK. Si no → 3 |
| P3 | `FE-2.1` en «Hecho»: cola local de subida | La fila de `FE-2.1` en `PLAN.md` §3 dice `Hecho`. Si no → 2 |
| P4 | La app apunta a la API vigente y responde | URL vigente = `terraform output -raw api_base_url` + `/v1` (sin Terraform, `VALIDACION_API_URL`; sin ninguna → 3), igual a `ApiConfig.BASE_URL` del código, y `GET <URL>/health` → 200 `"estado": "ok"` (si no → 2) |
| P5 | Login de admin contra `dev` | `POST <URL>/auth/login` con `VALIDACION_ADMIN_CORREO`/`VALIDACION_ADMIN_PASSWORD` o el secreto `campus-locator/dev/admin-inicial` → 200 con `token` y `usuario.rol = "admin"` (`401` o rol distinto → 3; otro código → 2). Guarda el token (nunca se imprime) y el nombre (para el saludo del Panel) |
| P6 | `BE-2.3` en «Hecho»: resumen del panel | La fila de `BE-2.3` en `BACKEND_FASTAPI/docs/PLAN.md` §3 dice `Hecho` y `GET <URL>/admin/stats` con el token → 200 que cumple el contrato (backend §5.5, «`GET /v1/admin/stats` (BE-2.3)»): `total_fotos`, `total_lugares` y `alertas_activas` enteros ≥ 0 y `ultimo_video` presente, `null` o `{numero, creado_en}` con `creado_en` en UTC con `Z`. Si no → 2 |

## 2. Comprobaciones automáticas

C1a y C2a corren en una sola ejecución de Gradle; si alguna falla, C1b y C2b quedan `omitida` («no se hace: falló …»).
En `local`, C1b y C2b quedan `omitida`. Orden en `dev`: C1a, C2a, C1b, C2b.

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | Borra los XML anteriores y ejecuta `<VALIDACION_GRADLE> testDebugUnitTest --tests '*.RemoteAdminRepositoryTest' --tests '*.TextosResumenTest'` (junto con C2a); lee `app/build/test-results/testDebugUnitTest/TEST-*.<clase>.xml` | Gradle sale con 0 y cada clase tiene su XML, 0 fallos, 0 errores, 0 omitidos y al menos 8 y 4 casos (hoy 11 y 6). Cubren `GET /v1/admin/stats` con la sesión, el mapeo de los cuatro datos con la fecha ISO en milisegundos, `ultimo_video = null`, respuestas fuera de contrato, sesión perdida, sin red y los textos del Panel («2.842», «Hoy / Ayer / d MMM, HH:mm» en la zona del teléfono) (`ARCHITECTURE.md` §4.7 y §5.10) |
| C1b | Borra el lugar `validacion-2-2-lugar` que haya dejado una ejecución anterior y lo crea (§4); lee `GET /v1/admin/stats` (antes); instala el APK de depuración (`installDebug`, conserva los datos), concede los permisos de Inicio y **entra al Panel iniciando sesión por la interfaz** como `validation-1-2` C1 (`am force-stop`, `am start`, «Acceso administrador», correo y contraseña con `input text`); baja el Panel hasta ver el «Resumen rápido» cargado y lee el `content-desc` de cada dato con `adb exec-out uiautomator dump` («2.842 fotos en el dataset», «12 último video recolectado. Hoy, 09:24», `ARCHITECTURE.md` §5.5); lee la hora del teléfono (`adb shell date +%Y-%m-%dT%H:%M:%S%z`) y otra vez `GET /v1/admin/stats` (después) | Las dos respuestas son iguales, `total_lugares` ≥ 1 y los cuatro datos del backend del Panel coinciden con ellas: fotos, lugares y alertas (quitado el separador de miles), y el último video: su número y la fecha de `ultimo_video.creado_en` en la zona del teléfono («Hoy, HH:mm», «Ayer, HH:mm» o «d <mes>, HH:mm»; el mes no se compara porque su abreviatura depende del idioma); con `ultimo_video = null`, «—» y sin fecha |
| C2a | Como C1a, con `--tests '*.PendientesPanelTest'` | XML con 0 fallos, errores ni omitidos y ≥ 4 casos (hoy 5): la regla del Panel es la de la cola (`fotosPendientesDe` = `AlmacenRecorridos.contarFotosPendientes()`: fotos sin `sync = subida` de los recorridos `finalizado`, sin los `en_curso` ni los manifests ilegibles), el resumen solo cambia «Fotos pendientes», una subida que avanza baja la cuenta y una sesión perdida no muestra error |
| C2b | Con el Panel abierto (por C1b, o entra como en C1b): lee los manifests de `files/recoleccion/` (`adb exec-out run-as com.example.myapplication ls -1` y `cat`); borra los restos `validacion-2-2` de una ejecución anterior que no llegaron al backend (§4). **Paso guiado:** pide grabar un recorrido corto `validacion-2-2` («Cada 3 s», ≥ 3 fotos), «Finalizar video» y, en 7.5, **«Guardar y subir después»** (vuelve al Panel), y espera Enter. Después busca el recorrido nuevo, espera hasta 10 s a ver el Panel y, hasta 30 s, lee el dato «fotos pendientes de subir» entre dos lecturas de los manifests | Hay un recorrido nuevo llamado `validacion-2-2`, `finalizado` y con ≥ 1 foto sin subir; y «Fotos pendientes de subir» del Panel = las fotos sin `sync = subida` de los recorridos `finalizado` del teléfono (la regla de la app, `ARCHITECTURE.md` §5.10), igual antes y después de leer el Panel. Como el Panel vuelve de 7.5 a la misma pantalla, esto comprueba además que relee la cola al volver (ADR-FE-28) |

## 3. Comprobaciones manuales

Ninguna: todos los criterios son automáticos (el paso guiado de C2b lo hace la persona, pero lo comprueba el script).

## 4. Datos de prueba y limpieza

- **Lugar `validacion-2-2-lugar`** (C1b, para que `total_lugares` no sea solo lo que ya haya): al empezar, el script
  borra los lugares que se llamen exactamente así (`GET /v1/admin/places?q=validacion-2-2` y `DELETE`, sin distinguir
  mayúsculas); después lo crea con `POST /v1/admin/places` (categoría `bloque`, 0,0005° al norte del primer lugar de
  `GET /v1/places`, o en una posición fija del campus si no hay ninguno) y registra su `DELETE /v1/admin/places/{id}`
  en la limpieza, que corre también si algo falla.
- **Sin alertas:** las rutas de alertas son de BE-3.3, sin implementar (backend §5.5, `404`); `alertas_activas` se
  compara tal cual (0 mientras no exista BE-3.3).
- **Recorrido `validacion-2-2`** (C2b, local en el teléfono, nunca se sube): al terminar el script cierra la app y lo
  borra del teléfono (`run-as … rm -rf files/recoleccion/<rec_NNNN>`, lo mismo que «Descartar video» de 7.5). Solo
  borra lo que se creó en el paso guiado con ese nombre y que el backend no conoce (sin `remote_video_id` y con
  `subida_estado = sin_subir`); al empezar borra igual los restos `validacion-2-2` de una ejecución anterior. Nunca toca
  otros recorridos (los del dataset sin subir se quedan y entran en la cuenta) ni usa `pm clear`.
- Si la persona tocó «Subir y procesar» por error, el recorrido llegó al backend como video `validacion-2-2` (dataset
  de `dev`): el script **no** lo borra (avisa por stderr); lo borra del backend el maestro como en FE-2.1
  (`limpiar-validacion` no sirve: su `ref_cliente` es `rec_NNNN`), y después se descarta en el teléfono.
- Con `--sin-limpieza` quedan el lugar y el recorrido (descartarlo en 7.5; la siguiente ejecución los borra como restos).
- La limpieza termina con `am force-stop`: el teléfono queda sin sesión (`ARCHITECTURE.md` §5.3). El login deja su
  fila en `auditoria` (registro, se conserva).

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate22.py --entorno dev
```

Sin argumentos propios. El paso guiado de C2b lee la entrada estándar: hay que correrlo en una terminal interactiva
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
v2 en WSL (si se usa el secreto) y, en Windows, el JBR 21 y el Android SDK. Duración aproximada en `dev`: 6–10 min
(Gradle 1–3 min; `installDebug` 1–2 min; login y lectura del Panel, ~1 min; el paso guiado, 2–3 min). No necesita
`embedding` (sin hora límite). No correrlo a la vez que otro validador que cree o borre lugares, videos o fotos en
`dev` (p. ej. el de BE-2.3): C1b compara totales globales. El informe queda en
`project/.validacion/FE-2.2-<AAAAMMDD-HHMMSS>.json` (hora UTC) o en `--informe RUTA`.

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
   Esperado: `All checks passed!`, `18 files already formatted` y `222 passed`.
3. Compilación y pruebas unitarias de la app:
   ```bash
   cmd.exe /c '.\gradlew.bat' --console=plain testDebugUnitTest assembleDebug
   ```
   Esperado: `BUILD SUCCESSFUL` (243 casos, sin fallos). Si dice `Unable to delete directory '…\app\build\…'`, borrar
   `app/build` (`rm -rf app/build`) y repetir (ARCHITECTURE §4.1, «Trampas»).
4. Copia de trabajo limpia (si no, el informe sale con `-dirty`; ARCHITECTURE §5.11, «Trampas»):
   ```bash
   git -c core.autocrlf=input status --short -- .
   ```
   Esperado: sin salida.
5. Teléfono: conectado por USB a Windows, con la depuración USB autorizada, **desbloqueado, con la pantalla encendida**
   («Pantalla activa» en Opciones de desarrollador mientras carga), con Wi-Fi o datos y **TalkBack desactivado** (con
   TalkBack activo `input swipe` puede no desplazar el Panel; sin comprobar):
   ```bash
   $VALIDACION_ADB devices
   ```
   Esperado: una línea `<serial>	device` (no `unauthorized` ni `offline`).
6. Solo en Xiaomi (MIUI/HyperOS): «Instalar vía USB» y «Depuración USB (Configuración de seguridad)» activadas
   (`validation-1-2` §5, paso 5). MIUI puede apagar «Instalar vía USB» por su cuenta entre sesiones (`validation-3-1`
   §5, paso 6): mirarlo antes. Esta orden solo comprueba la segunda:
   ```bash
   $VALIDACION_ADB shell input keyevent 0
   ```
   Esperado: sin salida. Si sale una `java.lang.SecurityException` que menciona `INJECT_EVENTS`, falta «Depuración USB
   (Configuración de seguridad)».
7. Que `dev` responde y que BE-2.3 está cerrado:
   ```bash
   curl -s "$(terraform -chdir=../../INFRASTRUCTURA_TERRAFORM/project/envs/dev output -raw api_base_url)/v1/health"; echo
   grep '^| BE-2.3 |' ../../BACKEND_FASTAPI/docs/PLAN.md | tail -1
   ```
   Esperado: `{"estado":"ok","version":"…","commit":"<SHA corto>"}` y una fila `| BE-2.3 | 2 | Hecho | …` (si dice
   `Pendiente` o `En curso`, el script dará código 2 en P6).
8. Para el paso guiado: cualquier sitio sirve (las fotos del recorrido de prueba no se suben y se borran al terminar).
   Si 7.3 muestra una fila «Retomar …» (hay una grabación sin terminar), **no** usarla: el recorrido de la prueba debe
   ser nuevo.

**Ejecución.** En una terminal interactiva, con el teléfono a mano. El validador instala la app, entra al Panel con el
admin, lee el «Resumen rápido» (C1b) y se detiene en el **paso guiado** de C2b (líneas `· PASO GUIADO — …` por stderr).
Entonces, en el teléfono, desde el Panel: **«Recolector de imágenes»** → marcar un punto de inicio y el rumbo →
nombre **`validacion-2-2`** → «Confirmar y comenzar» → en la recolección, **«Cada 3 s»** y dejar que tome al menos 3
fotos → «Finalizar video» → en el Resumen de video, **«Guardar y subir después»** (no «Subir y procesar»): la app vuelve
al Panel. Con el Panel a la vista, pulsar **Enter** en la terminal y no tocar más el teléfono.

```bash
uv run --group ops python src/ops/validate22.py --entorno dev
```

Esperado (código 0; por stderr salen además líneas `· …` de progreso —el lugar creado, los recorridos antes del paso
guiado, el paso guiado, la limpieza— y la ruta del informe):

```
[PASA] P1 Gradle 8.7, JVM 21.0.11 (JetBrains s.r.o. 21.0.11+1-b1163.116)
[PASA] P2 23028RA60L (Android 14, SDK 34, serial <serial>)
[PASA] P3 FE-2.1 Hecho
[PASA] P4 ApiConfig = terraform output api_base_url; GET /v1/health -> 200
[PASA] P5 200: <correo del admin>, rol admin
[PASA] P6 BE-2.3 Hecho; GET /v1/admin/stats -> 200 (<f> fotos, <l> lugares, <a> alertas, video <n> (<creado_en>))
[PASA] C1a RemoteAdminRepositoryTest 11/11, TextosResumenTest 6/6 (mínimos 8, 4)
[PASA] C2a PendientesPanelTest 5/5 (mínimos 4)
[PASA] C1b Panel = GET /v1/admin/stats (igual antes y después): <f> fotos, <l+1> lugares (incluye validacion-2-2-lugar), <a> alertas, último video <n> · «Hoy, HH:mm»
[PASA] C2b «Fotos pendientes de subir» = <p> = fotos sin subir de los recorridos finalizados del teléfono (incluye rec_NNNN «validacion-2-2», <k> fotos; antes de grabar: <p0>)
Resultado: pasa (código 0)
```

Con `ultimo_video = null` (sin videos en `dev`), P6 dice «sin video» y C1b «sin video («—»)». Al terminar, en stderr:
`· limpieza: borrar del teléfono rec_NNNN «validacion-2-2»`, `· limpieza: cerrar la app (am force-stop)` y
`· limpieza: borrar el lugar validacion-2-2-lugar` (orden inverso al de registro).

Casos previstos:
- `[FALLA] P6 BE-2.3 no está «Hecho» …` o `[FALLA] P6 BE-2.3: GET /v1/admin/stats respondió 404 …` (código 2) → BE-2.3
  aún no está cerrado o desplegado: esperar.
- `[FALLA] P6 BE-2.3: GET /v1/admin/stats no cumple el contrato (backend §5.5): …` (código 2) → avisar al maestro con
  el motivo (contrato del backend).
- `[FALLA] C1b el Panel no coincide con GET /v1/admin/stats: fotos en el dataset: Panel «…», API …` → la app no muestra
  lo que da la API: avisar con el detalle (`fecha del último video: …` dice qué esperaba y la hora del teléfono).
- `[FALLA] C1b GET /v1/admin/stats cambió mientras se leía el Panel …` → alguien subía videos o cambiaba lugares en
  `dev` (otro validador): repetir cuando termine.
- `[FALLA] C1b el Panel dice «No se pudo cargar el resumen.» …` → el teléfono no llega a `GET /v1/admin/stats`: mirar
  las líneas `I/Api` de `files/logs/app.log`.
- `[FALLA] C1b en 30 s no se vio el «Resumen rápido» cargado (datos visibles: …)` → uiautomator no vuelca los datos
  (**sin comprobar** en el Xiaomi) o el Panel no bajó (¿TalkBack activo?): avisar con el detalle.
- `[FALLA] C2b no hay un recorrido nuevo «validacion-2-2» en el teléfono (nuevos: …)` → se grabó con otro nombre (no se
  borra: descartarlo en 7.5) o no se grabó: repetir.
- `[FALLA] C2b rec_NNNN «validacion-2-2» está en_curso …` → faltó «Finalizar video» (o no tomó ninguna foto): repetir
  (la limpieza lo borra).
- `[FALLA] C2b en 10 s no apareció el Panel …` → se pulsó Enter con otra pantalla (p. ej. 7.5): repetir terminando en
  el Panel.
- `[FALLA] C2b «Fotos pendientes de subir» del Panel = «…», pero los manifests del teléfono dan … y …` → el Panel no
  relee la cola al volver (o una subida en marcha no terminó en 30 s): avisar con el detalle.
- `[ERROR] C2b el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)` (código 3) → correr el
  validador en una terminal interactiva. La limpieza corre igual.
- `[ERROR] C1b el teléfono no deja a adb … (SecurityException)` o `installDebug: INSTALL_FAILED_USER_RESTRICTED …`
  (código 3) → paso 6.
- `[FALLA] P5 las credenciales del admin no sirven (401 CREDENCIALES_INVALIDAS) …` (código 3) → revisar
  `VALIDACION_ADMIN_*` (paso 1) o el secreto.

En `local` (sin teléfono, API ni AWS): `uv run --group ops python src/ops/validate22.py --entorno local` da código 0 con
`[PASA]` en P1, C1a y C2a y `[OMITIDA]` en C1b y C2b (comprobado el 2026-10-26 en el worktree de FE-2.2, sobre
`e037904` con los cambios sin commit). Con `--solo C1a,C2a` en `dev`, P2–P6 quedan «no evaluada» y no se usa el teléfono
ni el backend.

Con el validador en `dev` con código 0 sobre un commit de `main` sin `-dirty`, la fila FE-2.2 de PLAN §3 pasa a «Hecho»
y se quitan de ARCHITECTURE §4.7 y §5.11 los «sin comprobar» que la ejecución confirme.
