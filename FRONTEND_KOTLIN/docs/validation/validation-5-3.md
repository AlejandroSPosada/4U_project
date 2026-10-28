# Validación 5-3 — FE-5.3 Guía por voz con pasos y fotos

| Campo | Valor |
|---|---|
| Lote | `FE-5.3` — criterios en [`PLAN.md`](../PLAN.md) §2.2 (C1–C3 propuestos el 2026-10-28, a confirmar por el usuario; C4 es el de la meta 3) |
| Script | `project/src/ops/validate53.py` |
| Entornos | `dev`: la API de `dev` (`POST /v1/localize/frame` desde la app, con `embedding` encendido) y un dispositivo físico **en casa** (la posición, el destino y los pasos los pone el modo de simulación del APK de depuración). `local` (sin teléfono ni red: C1a, C2a y C3a) |
| Criterios | Automáticos: C1 (C1a, C1b), C2 (C2a, C2b), C3 (C3a) · Manuales: C3c (capturas) y C4c (día de campo, criterio de la meta 3) |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta
(dónde corren, variables, `comun.py`, detalles de `validate53.py`, trampas): `ARCHITECTURE.md` §5.11. Lo construido:
`ARCHITECTURE.md` §4.13 (piezas en §5.5, §5.6, §5.7 «Guía por voz», §5.8 «Guía de prueba» y §5.10 «Corrección visual
de la guía»). Contratos que consume: `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5.3 (`POST /v1/localize/frame`) y la caché
de alertas de FE-3.6 (§4.12). La caminata en casa usa la ruta de prueba de FE-5.1 (grafo v209: desde 6.201434, −75.578707
hasta `bloque35`, 28,7 m, tres instrucciones). Decisión del usuario del 2026-10-28: el teléfono se lleva en la mano,
frente al pecho, con la cámara hacia adelante (la guía lo dice al empezar y C3a lo comprueba).

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla (las siguientes quedan «no evaluada»). Las de la máquina dan
**3**; las de otros lotes, **2** (lote `Bloqueado`). En `local` solo se evalúa P1; en `dev`, P2–P4 solo si C1b o C2b
están incluidas.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Gradle y un JDK que lo ejecute | `<VALIDACION_GRADLE> --version` termina con 0 (detalle: versión de Gradle y JVM). Si no → 3 |
| P2 | Dispositivo físico | `adb devices` con uno en estado `device` (el de `ANDROID_SERIAL` si hay varios) y `ro.kernel.qemu` distinto de `1`; anota modelo y Android. Si no → 3 |
| P3 | La app apunta a la API vigente y responde | URL vigente = `terraform output -raw api_base_url` + `/v1` (o `VALIDACION_API_URL`), igual a `ApiConfig.BASE_URL`, y `GET <URL>/health` → 200 `"estado": "ok"` (si no → 2) |
| P4 | `FE-5.1` y `BE-5.1` en «Hecho»: la ruta y `POST /v1/localize/frame` | Las filas de `PLAN.md` §3 y de `BACKEND_FASTAPI/docs/PLAN.md` §3 dicen `Hecho`. Si no → 2 |

## 2. Comprobaciones automáticas

C1a, C2a y C3a corren en una sola ejecución de Gradle (las clases de las incluidas). Si C1a o C3a fallan, C1b y C2b
quedan `omitida` («no se hace: falló …»). En `local`, C1b y C2b quedan `omitida`. C1b y C2b comparten **una** caminata
(un solo paso guiado). Orden: C1a, C2a, C3a, C1b, C2b.

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | `<VALIDACION_GRADLE> testDebugUnitTest --tests '*.TrazadoRutaTest' …` (junto con C2a y C3a) y lee los XML | 0 fallos, errores u omitidos y ≥ 4, 5, 6 y 2 casos (hoy 5, 5, 6 y 2) de `TrazadoRutaTest`, `AnunciadorTest`, `GuiaNavegacionTest` y `AlertasEnRutaTest`: avance en la escala de `desdeM` (dentro y fuera del camino), aviso previo a 10 m, maniobra a 3 m, saltos, llegada a 3 m, «Repetir», desvío de 4 lecturas → recálculo avisado, la ruta de prueba caminada en simulación (avisos, fotos a los 10,5 y 21 m, llegada), mezcla de fotos, sin red, y alertas cercanas a la ruta (C1) |
| C2a | Las clases `ReglaMezclaTest`, `RemoteFrameRepositoryTest` y `ComandoGuiaTest` | 0 fallos, errores u omitidos y ≥ 6, 4 y 2 casos (hoy 6, 4 y 2): límite de coherencia (8 + 0,5 × m) y radio (40–100), un salto de 40 m tras 5 m se descarta, la corrección como desplazamiento, niveles, el disparador de fotos, el multipart de `POST /v1/localize/frame` (una parte `foto`, `metadatos` con `rumbo` siempre) con MockWebServer, `503`/`400`/sin red/respuesta rota, «guíame» y la clasificación de fallos (C2) |
| C3a | Estática (`comprobar_estatica`): `PruebaGuia.fijar(` solo en `MainActivity.kt` dentro de `if (rutaPrueba == "navegacion")`, `rutaDePrueba` con `FLAG_DEBUGGABLE`, `"navegacion"` en `RUTAS_DE_PRUEBA`, rutas `navegacion` y `llegada`, «Guiarme» en la 6.3, `@POST("localize/frame")` y `COMO_LLEVAR_EL_TELEFONO` = la decisión del usuario. Después `ColaVozTest` | Lo estático se cumple y `ColaVozTest` tiene 0 fallos y ≥ 2 casos (C3) |
| C1b | Registra la limpieza `am force-stop`, instala el APK (`installDebug`, sin `pm clear`), `pm grant … CAMERA`. **Paso guiado:** sostener el teléfono con la cámara hacia una zona iluminada; Enter. Después `am force-stop`, la hora del teléfono y `am start -W -n com.example.myapplication/.MainActivity --es ruta navegacion --es destino_prueba bloque35 --es posicion_prueba 6.201434,-75.578707 --es simular_pasos 0.7,500`; espera hasta 30 s «Repetir instrucción» (6.5) y hasta 120 s «Ir a otro lugar» (6.6); lee `files/logs/app.log` (`run-as`) desde esa hora | Desde la última «Guía iniciada: …simulación…», la guía dijo en orden: «Lleva el teléfono en la mano, frente al pecho, con la cámara hacia adelante. Vamos a <destino>, a 29 metros por el camino. Camina 14 metros por el camino.», «En N metros, gira a la izquierda.», «Gira a la izquierda y sigue recto 14 metros.», «En N metros, llegas a <destino>.» y «Has llegado a <destino>.» (los avisos de red no cuentan), hay «Llegada mostrada (6.6)» y ninguna línea `CRASH` (C1) |
| C2b | Las mismas líneas de `app.log` | Al menos un `POST /v1/localize/frame -> 200` (tag `Api`) y cada «Foto: ok …» o «Foto: sin_coincidencias …» con su «Foto aceptada|descartada (…)»; la guía llegó (C1b) sin caerse (C2). En casa lo esperado es `sin_coincidencias` |

## 3. Comprobaciones manuales

| ID | Qué hace la persona | Evidencia en el PR |
|---|---|---|
| C3c | Durante la caminata de C1b: una captura de la 6.5 (instrucción en grande, «Faltan N m», estado de las fotos) y otra de la 6.6, con `adb exec-out screencap -p > c3c-guia.png` y `> c3c-llegada.png`, en `validation/evidencia/fe-5-3/` | Las capturas, **sin datos privados**: la vista previa de la cámara de la 6.5 muestra la casa: recortarla o taparla antes de versionar |
| C4c | Día de campo (criterio de la meta 3): en el campus, con `embedding` encendido, al menos 5 recorridos de 50 a 150 m dentro del grafo desde «Ubicarme» → 6.3 → «Guiarme», con el teléfono en la mano, frente al pecho, cámara hacia adelante | Un registro (`evidencia/fe-5-3/campo.md`): por recorrido, origen, destino, si llegó a ≤ 5 m de la entrada, si cada giro se anunció antes del cruce, si un desvío se notó y recalculó, cuánto se alejó la posición de la real (≤ ~10 m), dónde llegó tarde un aviso y dónde falló la foto; con eso se ajusta `ParametrosGuia` |

## 4. Datos de prueba y limpieza

No crea datos en el backend: cada foto que la app manda y responde `200` deja una fila anónima `origen = frame` en
`eventos_localizacion` (sin la posición previa; caduca a los 180 días, backend §5.7). Las fotos de la guía se borran en
el teléfono al enviarlas (`files/camera/guia/`). En el teléfono no borra nada (nunca `pm clear`): quedan las líneas de
`app.log`. Limpieza al terminar: `am force-stop`.

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate53.py --entorno dev
```

Sin argumentos propios. El paso guiado de C1b lee la entrada estándar: hay que correrlo en una terminal interactiva o con
la entrada en una FIFO, como el cierre de FE-2.2 ([`validation-2-2`](./validation-2-2.md) §5).

**Variables** (detalle en `ARCHITECTURE.md` §5.11): las mismas de [`validation-5-1`](./validation-5-1.md) §5
(`VALIDACION_GRADLE`, `JAVA_HOME`, `WSLENV`, `VALIDACION_ADB`, `AWS_PROFILE` para `terraform output`,
`UV_PROJECT_ENVIRONMENT`; `ANDROID_SERIAL` si hay varios dispositivos). No hacen falta las credenciales del admin.
**Necesita `embedding` encendido** (si no, C2b falla con `503`; se apaga solo a las 22:00 de Bogotá). Duración
aproximada: 4–7 min (Gradle 1–3 min; `installDebug` 1–2 min; la caminata ~25 s). El informe queda en
`project/.validacion/FE-5.3-<AAAAMMDD-HHMMSS>.json` (hora UTC) o en `--informe RUTA`.

**Preparación.**

1. Variables del entorno (en la misma terminal de WSL):
   ```bash
   cd /mnt/c/Users/frank/Documents/baul/uni/2026-2/P2/4U_project/FRONTEND_KOTLIN/project
   export AWS_PROFILE=campus-admin
   export JAVA_HOME='C:\Users\frank\.jdks\jbr-21.0.11'
   export WSLENV=JAVA_HOME:ANDROID_SERIAL
   export VALIDACION_GRADLE='cmd.exe /c .\gradlew.bat'
   export VALIDACION_ADB=/mnt/c/Users/frank/AppData/Local/Android/Sdk/platform-tools/adb.exe
   export UV_PROJECT_ENVIRONMENT=/root/.cache/uv-envs/fe-ops
   ```
   Esperado: sin salida.
2. Pruebas y estilo de los validadores:
   ```bash
   uv run --frozen ruff check . && uv run --frozen ruff format --check . && uv run --frozen pytest -q
   ```
   Esperado: `All checks passed!`, `31 files already formatted` y `342 passed, 1 skipped`.
3. Compilación y pruebas unitarias de la app:
   ```bash
   cmd.exe /c '.\gradlew.bat' --console=plain testDebugUnitTest assembleDebug
   ```
   Esperado: `BUILD SUCCESSFUL` (430 casos, sin fallos).
4. Copia de trabajo limpia (si no, el informe sale con `-dirty`):
   ```bash
   git -c core.autocrlf=input status --short -- .
   ```
   Esperado: sin salida.
5. Teléfono: conectado por USB, depuración autorizada, **desbloqueado con la pantalla encendida**, con internet de verdad
   (sin portal cautivo, ARCHITECTURE §4.12), el volumen alto y TalkBack desactivado:
   ```bash
   $VALIDACION_ADB devices
   ```
   Esperado: una línea `<serial>` seguida de `device`.
6. Solo en Xiaomi: «Instalar vía USB» y «Depuración USB (Configuración de seguridad)» activadas (como en
   `validation-5-1` §5, paso 6).
7. `embedding` listo:
   ```bash
   curl -s "$(terraform -chdir=../../INFRASTRUCTURA_TERRAFORM/project/envs/dev output -raw api_base_url)/v1/health/ready"
   ```
   Esperado: un JSON con `embedding` disponible (si no, esperar o pedir que se encienda; el validador no lo enciende).

**Ejecución.** En una terminal interactiva (o con una FIFO), con el teléfono a mano. El validador instala la app y se
detiene en el **paso guiado** (líneas `· PASO GUIADO — …` por stderr):

1. **Paso guiado (C1b):** sostener el teléfono desbloqueado con la cámara trasera hacia una zona iluminada de la casa (no
   tapada ni boca abajo: una foto oscura o borrosa no se envía) durante unos 40 s y pulsar **Enter**. La guía se abre en
   modo de simulación, dice los avisos (se oyen) y termina en la Llegada. Para C3c, tomar las dos capturas mientras tanto.

Por `adb` (FIFO): no hace falta tocar nada; basta con mandar el Enter y dejar el teléfono apoyado mirando a una zona con
luz (no boca abajo sobre la mesa).

Esperado (código 0; por stderr salen además líneas `· …` de progreso y la ruta del informe):

```
[PASA] P1 Gradle 8.7, JVM 21.0.11 (…)
[PASA] P2 23028RA60L (Android 14, serial <serial>)
[PASA] P3 ApiConfig = terraform output api_base_url; GET /v1/health -> 200
[PASA] P4 FE-5.1 y BE-5.1 Hecho
[PASA] C1a TrazadoRutaTest 5/5, AnunciadorTest 5/5, GuiaNavegacionTest 6/6, AlertasEnRutaTest 2/2 (mínimos 4, 5, 6, 2)
[PASA] C2a ReglaMezclaTest 6/6, RemoteFrameRepositoryTest 4/4, ComandoGuiaTest 2/2 (mínimos 6, 4, 2)
[PASA] C3a PruebaGuia solo en MainActivity (APK depurable, ruta navegacion); rutas navegacion y llegada; «Guiarme» en 6.3; @POST("localize/frame"); cómo llevar el teléfono = decisión del usuario; ColaVozTest 2/2 (mínimos 2)
[PASA] C1b ruta 29 m, 3 instrucciones; dijo: Lleva el teléfono en la mano, frente al pecho, con la cámara hacia adelante. Vamos a <destino>, a 29 metros por el camino. Camina 14 metros por el camino. | En 10 metros, gira a la izquierda. | Gira a la izquierda y sigue recto 14 metros. | En 9 metros, llegas a <destino>. | Has llegado a <destino>.
[PASA] C2b 2 fotos enviadas, POST /v1/localize/frame -> 200, 200; respuestas: sin_coincidencias en_radio=… (… ms); sin_coincidencias en_radio=… (… ms); decisiones: descartada (sin_coincidencias), descartada (sin_coincidencias)
[MANUAL] C3c Capturas de 6.5 durante la simulación …
[MANUAL] C4c Día de campo (criterio de la meta 3, …
Resultado: pasa (código 0)
```

(Los N de los avisos previos pueden variar en un metro. Si una foto de la casa se pareciera al dataset, C2b puede decir
«Foto: ok …» con «aceptada» o «descartada (incoherente)»: también pasa.) Para repetir la caminata: `--solo C1b,C2b`.

Casos previstos:
- `[FALLA] C2b ninguna foto se envió: 2 descartadas por calidad (oscura, oscura) …` → la cámara estaba tapada, boca abajo
  o a oscuras: repetir con `--solo C1b,C2b` apuntando a una zona iluminada.
- `[FALLA] C2b ninguna respuesta 200 de POST /v1/localize/frame (códigos ['503', '503'] …)` → `embedding` apagado o
  arrancando (paso 7); con `['falla …']` o sin códigos y `sin_conexion`, el teléfono no tiene internet (portal cautivo).
- `[FALLA] C1b la guía dijo [...]; se esperaba …` → la ruta o los textos cambiaron sin actualizar `GuiaNavegacionTest` y
  las constantes del validador (o el APK instalado es de otro commit).
- `[FALLA] C1b en 30 s no apareció la vista 6.5 («Repetir instrucción») …` → el teléfono estaba bloqueado (paso 5) o la
  guía no arrancó: `adb exec-out run-as com.example.myapplication tail -n 30 files/logs/app.log` (línea «Guía no
  iniciada: …»).
- `[FALLA] C1b en 120 s no apareció la vista 6.6 …` → la simulación se pausó (la app pasó a segundo plano o se apagó la
  pantalla) o la guía no llegó: revisar las líneas `Guia` de `app.log`.
- `[ERROR] C1b el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)` (código 3) → terminal
  interactiva o FIFO.
- `[ERROR] … installDebug: INSTALL_FAILED_USER_RESTRICTED …` (código 3) → paso 6.
- `[FALLA] P4 FE-5.1 no está «Hecho» …` (código 2) → no debería pasar (FE-5.1 «Hecho» desde el 2026-10-28).

En `local` (sin teléfono ni API): `uv run --group ops python src/ops/validate53.py --entorno local` da código 0 con
`[PASA]` en P1, C1a, C2a y C3a, `[OMITIDA]` en C1b y C2b y las manuales C3c y C4c (comprobado el 2026-10-28 en el
worktree de FE-5.3 rebasado sobre `c6b650a`, con la fase 2 sin commit: C1a 5/5, 5/5, 6/6 y 2/2; C2a 6/6, 4/4 y 2/2; C3a
estática + 2/2).

Con el validador en `dev` con código 0 sobre un commit de `main` sin `-dirty` y las capturas C3c, FE-5.3 queda validado
en casa; el lote pasa a «Hecho» cuando el día de campo (C4c) cumpla el criterio de la meta 3 (o el usuario decida otra
cosa). Entonces se quitan de ARCHITECTURE §4.13 los «sin comprobar» que se confirmen.
