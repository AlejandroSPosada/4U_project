# Validación 3-2 — FE-3.2 Ubicación real y Resultado (6.3)

| Campo | Valor |
|---|---|
| Lote | `FE-3.2` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate32.py` |
| Entornos | `dev` con dispositivo físico (cierra el lote, junto con la evidencia de C1c y C4c); `local` (sin teléfono ni backend: C1a, C2, C3a y C4a) |
| Criterios | Automáticos: C1 (C1b; apoyo C1a), C2, C3 (C3a y C3b), C4 (C4b; apoyo C4a) · Manuales: C1 (C1c), C4 (C4c) |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta
(dónde corren, variables, `comun.py`, detalles de `validate32.py`, trampas): `ARCHITECTURE.md` §5.11. Piezas que se
comprueban: `ARCHITECTURE.md` §4.6 (lo construido en FE-3.2), §5.2 («Flujo de captura del escaneo», con el formato de
las líneas de `app.log`), §5.5 («Resultado de ubicación»), §5.6 (`LocalizacionRepository`, `SesionDeNavegacion`), §5.7
(`ConversionRumbo`, `DescribirUbicacion`), §5.8 y §5.10 («Ubicarse»). Contrato del backend que se consume:
`BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5.3 (`POST /v1/localize`, `GET /v1/places`) y §5.5 (`GET /v1/admin/videos`, solo
para comprobar el dataset).

Desde el 2026-10-25 el Resultado (6.3) de este lote no muestra alertas cercanas: pasaron a FE-3.6
([`validation-3-6`](./validation-3-6.md), C4). Por decisión del usuario del 2026-10-26 la 6.3 no tiene mapa ni comandos
de voz y, con un destino, dice su distancia y dirección (la navegación guiada es de FE-5.1; ARCHITECTURE ADR-FE-27).

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla (las siguientes quedan «no evaluada»). Las de la máquina, las
credenciales y la hora dan **3**; las de otros lotes, **2** (lote `Bloqueado`). En `local` solo se evalúa P1. En `dev`,
P2 solo hace falta si va C1b, C3b o C4b; P3–P6, si va C1b o C4b; P7, si va C1b (con `--solo` quedan «no evaluada»).

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Gradle y un JDK que lo ejecute | `<VALIDACION_GRADLE> --version` termina con 0 (detalle: versión de Gradle y JVM). Si no → 3 |
| P2 | Dispositivo físico conectado (solo `dev`) | `adb devices` muestra uno en estado `device` (el de `ANDROID_SERIAL` si hay varios) y `adb shell getprop ro.kernel.qemu` no es `1`; lee modelo, versión de Android y SDK. Si no → 3 |
| P3 | `FE-3.1` en «Hecho»: lugares reales en la app (solo `dev`) | La fila de `FE-3.1` en `PLAN.md` §3 dice `Hecho`. Si no → 2 |
| P4 | La app usa la API de `dev` (solo `dev`) | `ApiConfig.BASE_URL` (leído de `ApiConfig.kt`) es igual a la URL vigente = `terraform output -raw api_base_url` + `/v1` (sin Terraform, `VALIDACION_API_URL`; sin ninguna de las dos → 3); `GET <URL>/health` responde 200 con `"estado": "ok"`. Si no → 2 |
| P5 | Credenciales de admin (solo `dev`; para comprobar el dataset en P6) | `VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` si están las dos; si no, el secreto `campus-locator/dev/admin-inicial` (`AWS_PROFILE`). `POST <URL>/auth/login` → 200 con `token` y `usuario.rol = "admin"`. `401` o rol distinto → 3; otro código o sin respuesta → 2 (BE-1.3). El token nunca se imprime |
| P6 | `BE-3.2` en «Hecho»: localización con dataset del campus (solo `dev`) | La fila de `BE-3.2` en `BACKEND_FASTAPI/docs/PLAN.md` §3 dice `Hecho`; `POST <URL>/localize` solo con la parte `metadatos` (`{"rumbos": [], "origen": "escaneo", …}`) y sin fotos responde `400 FOTOS_INVALIDAS` (existe y no procesa nada, backend §5.3); y `GET <URL>/admin/videos?por_pagina=100&pagina=N` (con el token; BE-2.1) suma ≥ 1 en `conteo.procesada`, sin los videos cuyo nombre empieza por `validacion`. Si no → 2 |
| P7 | `embedding` encendido para C1 (solo `dev` y solo si va C1b) | Cuenta de AWS (`aws sts get-caller-identity`, 648617469176) y `terraform output` con `ecs_cluster` y `ecs_servicios` (falta uno → 2). Si `GET <URL>/health/ready` ya dice `"embedding": "ok"`, publica un latido. Si no: pasadas las **20:45** de Bogotá → 3 (hasta 10 min de encendido + 60 de C1 antes del apagado de las 22:00); si no, comprueba INF-2.1, registra el apagado en la limpieza **antes** de encender y lo enciende como `embedding.py encender` (infra §5.10 y §5.11) |

## 2. Comprobaciones automáticas

En este orden. En `local`, C1b, C4b y C3b quedan `omitida` («solo en dev»). Si alguna de C1a, C2, C3a o C4a falla, en
`dev` C1b, C4b y C3b quedan `omitida` («no se hace: falló …»).

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | Borra los XML anteriores y ejecuta **una vez** `<VALIDACION_GRADLE> testDebugUnitTest --tests '*.<clase>'` con las clases de C1a, C2, C3a y C4a que estén incluidas; lee `app/build/test-results/testDebugUnitTest/TEST-*.<clase>.xml` de `RemoteLocalizacionRepositoryTest`, `DescribirUbicacionTest` y `SesionDeNavegacionTest` | Gradle sale con 0 y cada clase tiene su XML, 0 fallos, errores ni omitidos y ≥ 8, 8 y 4 casos (hoy 11, 11 y 5): el `multipart` de `POST /v1/localize` y su respuesta y errores, los textos de la 6.3 (direcciones relativas con la corrección de rumbo, confianza baja, sin coincidencias, destino) y la vigencia de la ubicación (ARCHITECTURE §5.6, §5.7 y §5.10) |
| C1b | (`dev`) `installDebug` (**conserva los datos**) y `pm grant` de los permisos de Inicio. Imprime por stderr los lugares de `GET /v1/places` y el estado de `embedding`. Anota la hora del teléfono, abre la app en Inicio y espera «Acceso administrador». **Paso guiado** (C1c, §3): la persona hace los 10 puntos y pulsa Enter. Lee `files/logs/app.log` desde esa hora y cuenta las líneas `I/EscaneoVM … Resultado: ok …` o `… Resultado: sin_coincidencias …` (una por cada `200` de `POST /v1/localize`); las imprime por stderr (hora, resultado, nivel, confianza, si hubo lugar cercano y cuántas referencias) para la tabla de C1c. Si encendió `embedding` en P7, lo apaga ya (para poder seguir con C4) | ≥ 10 resultados. El detalle dice cuántos de cada nivel y los errores (`Escaneo en ERROR: …`) que hubo. Que la app dijera el lugar **correcto** lo comprueba la persona (C1c) |
| C2 | Como C1a, con `ConversionRumboTest` | XML con 0 fallos, errores ni omitidos y ≥ 5 casos (hoy 7): acimut magnético (−180, 180] → rumbo verdadero [0, 360) con −180, 180 y 0, declinación **positiva y negativa** cruzando el norte, barrido de todo el rango y redondeo a 0,1° sin dar 360 (ARCHITECTURE §5.7); lo confirma la revisión del PR |
| C3a | Lee `ui/ubicacion/EscaneoViewModel.kt` y, como C1a, `FotosEscaneoTest` | Una sola declaración `const val CONSERVAR_FOTOS = false` (con o sin `private` o `internal`) y el XML con ≥ 4 casos (hoy 6): la carpeta del escaneo se borra entera, también las fotos que llegan tarde |
| C4a | Como C1a, con `ErrorEscaneoTest` | XML con ≥ 5 casos (hoy 7): `503 EMBEDDING_NO_DISPONIBLE` (y cualquier `503`) → «El servicio de ubicación no está disponible en este momento»; sin red, `429`, fotos inválidas, tiempo agotado y el resto |
| C4b | (`dev`) Si `embedding` lo apagó el validador (tras C1b), espera hasta 300 s a que `GET <URL>/health/ready` deje de decir `"embedding": "ok"`; si está encendido y no lo encendió él → `error` (3; casos previstos en §5). Prepara el teléfono (si C1b no lo hizo), anota la hora, abre Inicio. **Paso guiado** (C4c, §3): la persona da una vuelta y pulsa Enter. Lee `app.log` desde esa hora | Hay alguna línea `I/Api … POST /v1/localize -> <código>` y ninguna con `200`; hay `W/EscaneoVM … Escaneo en ERROR: SERVICIO_NO_DISPONIBLE`; no hay ninguna línea `CRASH` y la app sigue viva (`adb shell pidof com.example.myapplication`) |
| C3b | (`dev`) Lee `lastUpdateTime` de `adb shell dumpsys package com.example.myapplication`, `files/logs/app.log` y las carpetas de `files/camera/photos/` (`adb exec-out run-as com.example.myapplication ls -1 …`) | `app.log` tiene ≥ 1 sesión `[scan-…]` de `EscaneoVM` desde la instalación y ninguna carpeta `<yyyy-MM-dd_HH-mm-ss>` posterior a la instalación contiene `.jpg`. Informa cuántas líneas «Fotos del escaneo borradas» hubo |

Si C3b falla por no haber escaneos (p. ej. con `--solo C3` antes de hacer C1 o C4), se repite después de las vueltas con
`--solo C3`: sin C1b ni C4b no instala, así que la hora de instalación no cambia.

## 3. Comprobaciones manuales

La evidencia se guarda en `evidencia/fe-3-2/` y se cita en el PR. En los comandos, `adb` es `$VALIDACION_ADB` en WSL
(§5). El script las imprime como `[MANUAL] C1c` y `[MANUAL] C4c`; sus pasos guiados son C1b y C4b.

| ID | Qué hace la persona | Evidencia en el PR |
|---|---|---|
| C1c | Durante el paso guiado de C1b, con `embedding` encendido: elige 10 puntos conocidos del campus con dataset (junto a lugares de la lista que imprime el script) y en cada uno hace Inicio → «uno» (o el botón principal), da la vuelta y escucha el Resultado (6.3) | `c1-tabla.md`: los 10 puntos (punto, lugar esperado, lo que dijo la app, nivel de confianza, si pidió volver a ubicarse), apoyada en las líneas que imprime C1b; y un video con audio de al menos dos puntos (si muestra algo privado, no se versiona y se cita en el PR). Pasa si en cada punto la app dice el lugar correcto o, con confianza baja, lo dice y ofrece «Volver a ubicarme» |
| C4c | Durante el paso guiado de C4b, con `embedding` apagado: Inicio → «uno» → vuelta completa | `c4-video.mp4` con audio: tras «Analizando…», la app dice «El servicio de ubicación no está disponible en este momento» (§5.10) y no se cierra (si muestra algo privado, se cita en el PR) |

**C1c — procedimiento** (en el campus; `embedding` lo enciende P7 si hace falta y lo apaga C1b al terminar):
1. Con el teléfono en Inicio (lo abre el script) y **TalkBack desactivado** (la 6.3 con TalkBack es de FE-3.5), empezar a
   grabar la pantalla con audio en el primer punto.
2. En cada punto: decir **«uno»** (o tocar el botón principal); escuchar las instrucciones y girar despacio con el
   teléfono vertical hasta oír «Listo, analizando»; escuchar el Resultado. Anotar lo dicho. Tocar **«Volver al
   inicio»** (o Atrás).
3. Con confianza baja o «No reconocí este lugar», la app ofrece «Volver a ubicarme» como primer botón: anotarlo (vale si
   la app dice que la ubicación no es segura).
4. Tras los 10 puntos, parar la grabación y pulsar Enter en la terminal. Copiar las líneas de resultado que imprime C1b
   (por stderr) en `$EVID/c1-tabla.md` y completarlas con el punto, el lugar esperado y lo dicho en cada uno.

**C4c — procedimiento** (de noche o cuando `embedding` esté apagado; con `--solo C4,C3` no hace falta encenderlo):
1. Comprobar que `GET <URL>/health/ready` dice `"embedding": "no_disponible"` (paso 8 de §5).
2. Con el teléfono en Inicio (lo abre el script), empezar a grabar la pantalla con audio, decir «uno», dar la vuelta
   completa y esperar el mensaje («El servicio de ubicación no está disponible en este momento. Toca repetir para
   intentar otra vez.»). Parar la grabación, guardarla como `$EVID/c4-video.mp4` y pulsar Enter en la terminal.

## 4. Datos de prueba y limpieza

No crea nada en el backend: `POST /v1/localize` no guarda las fotos (backend ADR-BE-06) y la sonda de P6 se rechaza
antes de procesar (sí cuenta como llamada a `POST /v1/localize`, recurso compartido: no correr el validador mientras otro
lote lo usa). Cada `200` de las vueltas de C1 deja una fila anónima en `eventos_localizacion` del backend (es registro y
se conserva). Si P7 encendió `embedding`, lo apaga C1b al terminar y, en todo caso, la limpieza (también si algo falló;
con `--sin-limpieza` queda encendido hasta su apagado automático: 45 min sin uso o las 22:00). En el teléfono:
`installDebug` conserva los datos de la app y no se usa `pm clear`; las fotos de cada escaneo las borra la propia app
(C3). Al terminar, `am force-stop`.

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate32.py --entorno dev
```

Sin argumentos propios. Lo habitual es correrlo en **dos sesiones**: en el campus `--solo C1,C2,C3a,C4a` (o completo, si
justo después se hará C4) y de noche `--solo C4,C3`. Los pasos guiados leen la entrada estándar: hay que correrlo en una
terminal interactiva (sin redirigir la entrada, p. ej. `< /dev/null`, ni lanzarlo desde un script sin terminal).

**Hoy (2026-10-26) en `dev` da código 2** (P6: BE-3.2 está «En curso», sin dataset ni calibración): es lo esperado
hasta que BE-3.2 se cierre.

**Variables** (detalle en `ARCHITECTURE.md` §5.11). En la máquina del equipo el validador corre en WSL y usa el Gradle y
el `adb` de Windows (ARCHITECTURE §4.1):

| Variable | Valor en WSL | Obligatoria |
|---|---|---|
| `VALIDACION_GRADLE` | `cmd.exe /c .\gradlew.bat` | Sí en WSL (WSL no tiene JDK ni SDK) |
| `JAVA_HOME` | `C:\Users\frank\.jdks\jbr-21.0.11` (el JBR 21; el de Android Studio es Java 25 y Gradle 8.7 no lo admite) | Sí en WSL |
| `WSLENV` | `JAVA_HOME:ANDROID_SERIAL` (pasa esas dos a los procesos de Windows) | Sí en WSL |
| `VALIDACION_ADB` | `/mnt/c/Users/frank/AppData/Local/Android/Sdk/platform-tools/adb.exe` | Sí en WSL, en `dev` |
| `AWS_PROFILE` | `campus-admin` (`terraform output`, cuyo estado está en S3; el secreto del admin si no se dan `VALIDACION_ADMIN_*`; y en P7 la cuenta, los outputs de ECS y el encendido de `embedding`) | Sí en `dev` |
| `VALIDACION_ADMIN_CORREO`, `VALIDACION_ADMIN_PASSWORD` | Las del admin de `dev`, leídas sin eco (paso 1); sin ellas, el secreto `campus-locator/dev/admin-inicial` | No |
| `VALIDACION_API_URL` | No hace falta: solo se usa si `terraform output` falla | No |
| `ANDROID_SERIAL` | Solo si hay varios dispositivos | No |
| `UV_PROJECT_ENVIRONMENT` | `/root/.cache/uv-envs/fe-ops` (el `.venv` fuera de `/mnt/c`, más rápido) | No |

Herramientas: `uv`, `terraform` con `terraform init` hecho en `INFRASTRUCTURA_TERRAFORM/project/envs/dev`, la CLI `aws`
v2 en WSL y, en Windows, el JBR 21 y el Android SDK. Duración aproximada en `dev`: 5–8 min de script (Gradle 1–3 min;
`installDebug` 1–2 min; encender `embedding` 3–6 min si está apagado), más ~60 min de C1 en el campus y ~10 min de C4.
**Hora límite para empezar C1: 20:45 de Bogotá** (`embedding` se apaga solo a las 22:00). El informe queda en
`project/.validacion/FE-3.2-<AAAAMMDD-HHMMSS>.json` (hora UTC) o en `--informe RUTA`.

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
   export EVID=../docs/validation/evidencia/fe-3-2
   read -r -p 'Correo del admin de dev: ' VALIDACION_ADMIN_CORREO
   read -r -s -p 'Contraseña del admin de dev: ' VALIDACION_ADMIN_PASSWORD; echo
   export VALIDACION_ADMIN_CORREO VALIDACION_ADMIN_PASSWORD
   ```
   Esperado: solo las dos preguntas (la contraseña no se ve al escribirla).
2. Pruebas y estilo de los validadores:
   ```bash
   uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen pytest -q
   ```
   Esperado: `All checks passed!`, `16 files already formatted` y `190 passed`.
3. Compilación y pruebas unitarias de la app:
   ```bash
   cmd.exe /c '.\gradlew.bat' --console=plain testDebugUnitTest assembleDebug
   ```
   Esperado: `BUILD SUCCESSFUL` (221 casos, sin fallos). Si dice `Unable to delete directory '…\app\build\…'`, borrar
   `app/build` (`rm -rf app/build`) y repetir (ARCHITECTURE §4.1, «Trampas»).
4. El validador en `local` (no toca el teléfono ni `dev`; así no se enciende `embedding` en vano si algo de la JVM falla):
   ```bash
   uv run --group ops python src/ops/validate32.py --entorno local
   ```
   Esperado: `Resultado: pasa (código 0)` (abajo, «En `local`»).
5. Copia de trabajo limpia (si no, el informe sale con `-dirty`; ARCHITECTURE §5.11, «Trampas»):
   ```bash
   git -c core.autocrlf=input status --short -- .
   ```
   Esperado: sin salida.
6. Teléfono: conectado por USB a Windows, con la depuración USB autorizada, **desbloqueado, con la pantalla encendida**
   («Pantalla activa» en Opciones de desarrollador mientras carga), con datos móviles o Wi-Fi y **TalkBack desactivado**:
   ```bash
   $VALIDACION_ADB devices
   ```
   Esperado: una línea `<serial>	device` (no `unauthorized` ni `offline`).
7. Solo en Xiaomi (MIUI/HyperOS): «Instalar vía USB» y «Depuración USB (Configuración de seguridad)» activadas (MIUI
   puede apagar la primera por su cuenta entre sesiones; `validation-3-1` §5, paso 6). Para comprobar la segunda:
   ```bash
   $VALIDACION_ADB shell input keyevent 0
   ```
   Esperado: sin salida. Si sale una `java.lang.SecurityException` que menciona `INJECT_EVENTS`, falta «Depuración USB
   (Configuración de seguridad)».
8. Que `dev` responde, el estado de `embedding` y la carpeta de evidencia:
   ```bash
   API="$(terraform -chdir=../../INFRASTRUCTURA_TERRAFORM/project/envs/dev output -raw api_base_url)/v1"
   curl -s "$API/health"; echo
   curl -s "$API/health/ready"; echo
   mkdir -p $EVID && ls -d $EVID
   ```
   Esperado: `{"estado":"ok","version":"…","commit":"<SHA corto>"}`, `{"estado":"ok","db":"ok","embedding":"ok"}` (o
   `"no_disponible"`: para C1 lo enciende P7; para C4 debe decir `no_disponible`) y
   `../docs/validation/evidencia/fe-3-2`.

**Ejecución en el campus (C1).** En una terminal interactiva, con el teléfono a mano: el validador instala la app,
enciende `embedding` si hace falta, imprime los lugares, abre Inicio y se detiene en el **paso guiado** (líneas
`· PASO GUIADO — …` por stderr). Hacer los 10 puntos (C1c, §3) y pulsar **Enter**.

```bash
uv run --group ops python src/ops/validate32.py --entorno dev --solo C1,C2,C3a,C4a
```

Esperado (código 0; por stderr salen además líneas `· …` de progreso —lugares, estado de `embedding`, el paso guiado,
una línea por resultado y la limpieza— y la ruta del informe):

```
[PASA] P1 Gradle 8.7, JVM 21.0.11 (JetBrains s.r.o. 21.0.11+1-b1163.116)
[PASA] P2 23028RA60L (Android 14, SDK 34, serial <serial>)
[PASA] P3 FE-3.1 Hecho
[PASA] P4 ApiConfig = terraform output api_base_url; GET /v1/health -> 200
[PASA] P5 200: <correo del admin>, rol admin
[PASA] P6 BE-3.2 Hecho; POST /v1/localize sin fotos -> 400 FOTOS_INVALIDAS; dataset con <n> fotos procesadas
[PASA] P7 cuenta 648617469176 (<usuario>); embedding encendido por el validador en <s> s
[PASA] C1a RemoteLocalizacionRepositoryTest 11/11, DescribirUbicacionTest 11/11, SesionDeNavegacionTest 5/5 (mínimos 8, 8, 4)
[PASA] C2 ConversionRumboTest 7/7 (mínimos 5)
[PASA] C3a CONSERVAR_FOTOS = false; FotosEscaneoTest 6/6 (mínimos 4)
[PASA] C4a ErrorEscaneoTest 7/7 (mínimos 5)
[PASA] C1b 10 resultados (alta <a>, media <m>, baja <b>, sin_coincidencias <s>) desde las <hora del teléfono>
[OMITIDA] C4b excluida con --solo
[OMITIDA] C3b excluida con --solo
[MANUAL] C1c [APK de este commit instalado por el validador] Tabla de los 10 puntos …
[MANUAL] C4c [APK de este commit instalado por el validador] Con embedding apagado, Inicio → «uno» → vuelta completa: …
Resultado: pasa (código 0)
```

Con `embedding` ya encendido, P7 dice `embedding ya estaba encendido (latido publicado)` y no lo apaga.

**Ejecución de noche (C4 y C3).** Con `embedding` apagado (paso 8: `"embedding": "no_disponible"`):

```bash
uv run --group ops python src/ops/validate32.py --entorno dev --solo C4,C3
```

Esperado: `[PASA]` en P1–P6, `[NO EVALUADA] P7 C1b excluida con --solo (…)`, `[OMITIDA]` en C1a, C2 y C1b, `[PASA]` en
C3a y C4a, `[PASA] C4b embedding no_disponible; POST /v1/localize -> 503; SERVICIO_NO_DISPONIBLE («El servicio de
ubicación no está disponible en este momento»); la app sigue abierta`, `[PASA] C3b <n> sesiones [scan-…] desde la
instalación (<hora>), <n> borrados registrados; 0 carpetas de escaneo posteriores, ninguna con .jpg`, las dos manuales y
`Resultado: pasa (código 0)`. Al terminar, en stderr: `· limpieza: cerrar la app (am force-stop)`. Después, guardar
`c4-video.mp4` (C4c).

Una ejecución completa (`--entorno dev` sin `--solo`, antes de las 20:45) hace C1b, apaga `embedding`, espera a que
`/health/ready` diga `no_disponible` y sigue con C4b y C3b.

Casos previstos:
- `[FALLA] P6 BE-3.2 no está «Hecho» en BACKEND_FASTAPI/docs/PLAN.md §3` (código 2) → **lo esperado hoy**: BE-3.2 sigue
  «En curso» (sin dataset ni calibración). Lo mismo con `… POST /v1/localize sin fotos respondió <código> …` (BE-3.2 sin
  desplegar) o `… el dataset no tiene ninguna foto procesada …`.
- `[FALLA] P7 son las 20:50 en Bogotá: después de las 20:45 no se enciende embedding para C1 …` (código 3) → repetir
  mañana, o de noche solo `--solo C4,C3`.
- `[ERROR] C4b embedding está encendido (no lo encendió este validador): …` (código 3) → otra sesión lo tiene encendido:
  esperar a que se apague solo (45 min sin uso o a las 22:00) y repetir con `--solo C4,C3`.
- `[FALLA] C1b solo <n> resultados … (mínimo 10)` → no se hicieron los 10 puntos o algunas vueltas fallaron (el detalle
  lista los `Escaneo en ERROR: …`): repetir con `--solo C1`.
- `[FALLA] C4b POST /v1/localize respondió 200 …: embedding no estaba apagado` → repetir con `embedding` apagado.
- `[FALLA] C4b app.log no tiene ninguna línea «POST /v1/localize» …` → la vuelta no llegó a enviar las fotos (se canceló o
  quedó incompleta): repetir.
- `[FALLA] C3b quedan fotos de escaneo en el teléfono: …` → `CONSERVAR_FOTOS` o el borrado no funcionan en el teléfono:
  avisar al maestro.
- `[ERROR] C1b el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)` (código 3) → correr el
  validador en una terminal interactiva. La limpieza apaga `embedding` igual si lo encendió.
- `[ERROR] C1b installDebug: INSTALL_FAILED_USER_RESTRICTED …` o `… pm grant … (SecurityException)` (código 3) → paso 7.
- `[FALLA] P5 las credenciales del admin no sirven (401 CREDENCIALES_INVALIDAS) …` (código 3) → revisar
  `VALIDACION_ADMIN_*` (paso 1) o el secreto.

**En `local`** (sin teléfono, API ni AWS): `uv run --group ops python src/ops/validate32.py --entorno local` da código 0
con `[PASA]` en P1, C1a, C2, C3a y C4a, `[OMITIDA]` en C1b, C4b y C3b y las `[MANUAL]` C1c y C4c (comprobado el
2026-10-26). Sin teléfono en `dev`, P2 falla y el código es 3 (`adb devices no muestra ningún dispositivo`).

Con el validador en `dev` con código 0 sobre un commit de `main` sin `-dirty` (C1 y C4 pueden venir de dos ejecuciones
sobre el mismo commit) y la evidencia de C1c y C4c en `evidencia/fe-3-2/`, la fila FE-3.2 de PLAN §3 pasa a «Hecho» y
se quitan de ARCHITECTURE §4.6 los «sin comprobar» que la evidencia confirme.
