# Validación 3-6 — FE-3.6 Alertas públicas

| Campo | Valor |
|---|---|
| Lote | `FE-3.6` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate36.py` |
| Entornos | `dev` (cierra el lote): la API de `dev` (`GET /v1/alerts`, pública, y `/v1/admin/alerts` para las alertas de prueba) y un dispositivo físico **en casa** (la posición llega por el `Intent`: ubicación de prueba de «Ubicarme», ADR-FE-42); **no necesita `embedding`**. `local` (sin teléfono ni red: C1a, C3a y C4a) |
| Criterios | Automáticos: C1 (C1a, C1b, C1c), C2 (C2b, con dos pasos guiados: modo avión), C3 (C3a), C4 (C4a, C4b), C5 (C5a) · Manual: C5 (TalkBack) |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta
(dónde corren, variables, `comun.py`, detalles de `validate36.py`, trampas): `ARCHITECTURE.md` §5.11. Lo construido:
`ARCHITECTURE.md` §4.12 (piezas en §5.6, «Caché de alertas públicas»; §5.7, «Alertas cercanas» y «Reglas de
`DescribirUbicacion`»; §5.8, «Ubicación de prueba de «Ubicarme»»; §5.9, `onNativeRastreoIniciado` e «Inicio desde
«Ubicarme» y alertas en el mapa»; §5.10, «Alertas sin conexión»). Contratos que consume:
`BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5.3 (`GET /v1/alerts`) y §5.5 (`/v1/admin/alerts`: `sincronizar` y `DELETE`,
solo el validador).

Lote fuera del núcleo (decisión del usuario del 2026-10-25: «No necesitamos las alertas por el momento»). C5 viene de
FE-3.1 (decisión del usuario del 2026-10-26 al cerrarlo: «Si, por favor. Cambialo y demos por hecho lo que llevamos.»):
la prueba con TalkBack de «Ver mapa» y el punto de inicio del mapa sin tocarlo. **FE-3.2 no es precondición:** la 6.3 y
el mapa se prueban con la ubicación de prueba de «Ubicarme» del APK de depuración, sin cámara ni `POST /v1/localize`
(ADR-FE-42).

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla (las siguientes quedan «no evaluada»). Las de la máquina dan
**3**; las de otros lotes, **2** (lote `Bloqueado`). En `local` solo se evalúa P1; en `dev`, P2–P5 solo si alguna
comprobación con teléfono (C1b, C1c, C2b, C4b, C5a) está incluida.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Gradle y un JDK que lo ejecute | `<VALIDACION_GRADLE> --version` termina con 0 (detalle: versión de Gradle y JVM). Si no → 3 |
| P2 | Dispositivo físico | `adb devices` con uno en estado `device` (el de `ANDROID_SERIAL` si hay varios) y `ro.kernel.qemu` distinto de `1`; anota modelo, Android y SDK. Si no → 3 |
| P3 | La app apunta a la API vigente y responde | URL vigente = `terraform output -raw api_base_url` + `/v1` (sin Terraform, `VALIDACION_API_URL`; sin ninguna → 3), igual a `ApiConfig.BASE_URL` del código, y `GET <URL>/health` → 200 `"estado": "ok"` (si no → 2) |
| P4 | Credenciales del admin (para las alertas de prueba) | `POST /v1/auth/login` con `credenciales_admin` (variables o el secreto `campus-locator/dev/admin-inicial`) → 200 con rol `admin` (`401` o otro rol → 3; otro error → 2). El token no se imprime |
| P5 | `FE-3.1` y `BE-3.3` en «Hecho»: entrada al mapa y alertas del backend | Las filas `FE-3.1` de `PLAN.md` §3 y `BE-3.3` de `BACKEND_FASTAPI/docs/PLAN.md` §3 dicen `Hecho`, y `GET /v1/alerts` (sin token) → 200 con `generado_en`, `completo = true` y `alertas`. Si no → 2 |

## 2. Comprobaciones automáticas

C1a, C3a y C4a corren en una sola ejecución de Gradle (las clases de las incluidas); si alguna falla, las del teléfono
quedan `omitida` («no se hace: falló …»). En `local`, C1b, C1c, C2b, C4b y C5a quedan `omitida`. Orden: C1a, C3a, C4a,
C1b, C1c, C2b, C4b, C5a (si C1b falla, las siguientes quedan `omitida`). Antes de la primera del teléfono, el script
instala el APK (`installDebug`, sin `pm clear`), borra los restos `validacion-3-6-c1|c2` del backend y crea **c1**
(`validacion-3-6-c1`, prioridad normal) y **c2** (`validacion-3-6-c2`, prioridad alta), las dos con radio 15 m en
6.201484, −75.578427 (~6 m al norte de la ubicación de prueba, en el campus). «Sincronizar el teléfono» = `am
force-stop` + `am start -W -n com.example.myapplication/.MainActivity --es ruta mapa` (arranque en frío: el proceso nuevo
sincroniza al pasar a primer plano) y esperar hasta 45 s una línea nueva «Alertas públicas sincronizadas (…)» en
`files/logs/app.log`.

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | `<VALIDACION_GRADLE> testDebugUnitTest --tests '*.CacheAlertasPublicasTest'` (junto con C3a y C4a) y lee su XML | 0 fallos, errores u omitidos y ≥ 5 casos (hoy 7): primera vez completa y después por diferencias con `desde`, borrada → desaparece, una cada 5 min, sin red la caché queda, `422` con `desde` → completa, el archivo sobrevive a un proceso nuevo (C1 y C2 en la JVM) |
| C1b | Sincroniza el teléfono y lee `files/alertas/publicas.json` con `run-as … cat` | La caché tiene c1 y c2 (mensaje y radio 15) y guarda `generado_en` (C1: llega en la siguiente sincronización) |
| C1c | Borra c1 con `DELETE /v1/admin/alerts/{id}`, sincroniza el teléfono y vuelve a leer la caché | La sincronización fue **por diferencias** con ≥ 1 eliminada, c1 ya no está y c2 sí, y `GET /v1/alerts?desde=<generado_en anterior>` trae c1 en `eliminadas` (C1: al borrarla desaparece) |
| C2b | **Paso guiado 1:** activar el modo avión; Enter. Exige `adb shell settings get global airplane_mode_on` = `1`. Abre el mapa con la ubicación de prueba: `am force-stop` y `am start -W -n … --es ruta mapa --es ubicacion_prueba 6.201434,-75.578427`. Espera hasta 30 s. **Paso guiado 2:** desactivar el modo avión; Enter | En `app.log`: «Alerta anunciada (mapa): <c2> …», «Inicio desde Ubicarme …» (el mapa empezó desde la ubicación de prueba sin tocarlo), **ninguna** sincronización correcta (sin red) y c1 no anunciada; en pantalla, el aviso «Alerta: validacion-3-6-c2.» (C2: en modo avión, tras una sincronización previa, se anuncia al entrar en su radio) |
| C3a | La clase `DetectarAlertasCercanasTest` | 0 fallos, errores u omitidos y ≥ 5 casos (hoy 7): radio, incertidumbre, vigencia (inactivas, futuras, vencidas), orden alta primero, una vez por aproximación con histéresis y espera, alertas que salen de la lista (C3) |
| C4a | Estática: `PruebaUbicacion.resultado(` solo en `MainActivity.kt`, una vez, dentro de `if (rutaPrueba != null)`; `rutaDePrueba` con `FLAG_DEBUGGABLE`; `RUTAS_DE_PRUEBA` con `"resultado"`; la ruta `resultado` con `onVerMapa = { nav.navigate("mapa")`; `MapaPublicoScreen.kt` con `SesionDeNavegacion.ubicacionVigente()` y `onNativeRastreoIniciado(`; `assets/app.js` con `window.onNativeRastreoIniciado`. Después la clase `AlertasEnResultadoTest` | Lo estático se cumple y la clase tiene 0 fallos, errores u omitidos y ≥ 3 casos (hoy 4): en 6.3 las alertas se dicen al final, después de la ruta, alta primero; la incertidumbre es el radio de la posición; sin posición no hay alertas; la ubicación de prueba (C4 en la JVM) |
| C4b | Abre la 6.3 con la ubicación de prueba: `am start -W -n … --es ruta resultado --es ubicacion_prueba 6.201434,-75.578427`; espera «No hay lugares conocidos cerca» (20 s) y la tarjeta (5 s, después hasta 3 desplazamientos) | La 6.3 muestra «Alertas cercanas» con «validacion-3-6-c2.» **debajo** del título de la ubicación (si los tres se ven en el mismo volcado) y `app.log` tiene «Alerta anunciada (resultado): <c2> …» y «Resultado: alta» (C4: se muestra y se lee después de la ubicación) |
| C5a | En la 6.3 (la de C4b), busca «Caminar con el mapa» (hasta 3 desplazamientos) y lo toca | En `app.log`, tras el toque: «Inicio desde Ubicarme …», «sensores registrados (iniciar\|primer plano …» (`Pdr`) y «Alerta anunciada (mapa): <c2> …»; en pantalla, el aviso «Alerta: …» (C5: el seguimiento empieza en la posición de «Ubicarme» sin tocar el mapa) |

## 3. Comprobaciones manuales

| ID | Qué hace la persona | Evidencia en el PR |
|---|---|---|
| C5 | Con **TalkBack** activo: desde Inicio, abrir el mapa con la acción «Ver mapa» del botón principal; hacer Ubicarme (o la ruta de prueba `resultado` con `ubicacion_prueba`) y, en el Resultado, «Caminar con el mapa» con doble toque; comprobar que el seguimiento empieza sin tocar el mapa (se oye «Sigo tus pasos desde tu última ubicación.») y, mientras exista, también fijando un punto y pulsando ▶; Atrás vuelve a Inicio y el mapa ya no lee sensores (procedimiento abajo) | `c5-video.mp4` (sin audio: `adb shell screenrecord` no lo graba), `c5-sensores-inicio.txt` (`dumpsys sensorservice` de vuelta en Inicio) y `c5-app-log.txt` (líneas `Pdr` y `MapaPublico`) en `evidencia/fe-3-6/`, y el gesto de TalkBack 17 que abrió las acciones anotado en `ARCHITECTURE.md` §4.5 |

**C5 — procedimiento** (`ARCHITECTURE.md` §4.5, «Hallazgos con TalkBack 17»; §4.12; §5.2, «Segundo plano»). Si no cabe
el día de la validación, queda pendiente sin bloquear el código (encargo del maestro del 2026-10-28).
1. Activar **TalkBack** antes de abrir la app. Con TalkBack 17.0.1 en el Xiaomi (2026-10-26) sale primero su tutorial:
   terminarlo o salir de él. Empezar a grabar: `adb shell screenrecord /sdcard/c5.mp4` (se para con Ctrl+C).
2. Abrir la app desde el lanzador (Inicio). Con el foco en el botón principal, abrir sus **acciones** y elegir **«Ver
   mapa»**. **Sin comprobar** cómo se abren en TalkBack 17: el toque con tres dedos abrió «Search screen» y el doble
   toque ejecuta la acción principal (Ubicarme). Probar el menú de TalkBack con el gesto que indique su ayuda
   («Acciones») y anotar en §4.5 el que funcione. Atrás vuelve a Inicio.
3. Ubicarse (en el campus) o, en casa, `adb shell am force-stop com.example.myapplication` y `adb shell am start -n
   com.example.myapplication/.MainActivity --es ruta resultado --es ubicacion_prueba 6.201434,-75.578427`. En el
   Resultado, mover el foco a **«Caminar con el mapa»** y tocar dos veces: se abre el mapa, se oye «Sigo tus pasos desde tu
   última ubicación.» y, si hay una alerta cerca, su mensaje.
4. Mientras exista el inicio por toque: desactivar TalkBack si estorba, pausar con ⏸, tocar un punto del mapa y pulsar
   **▶**: la posición empieza en el punto tocado.
5. Pulsar **Atrás**: vuelve a Inicio. Parar la grabación y bajarla: `adb pull /sdcard/c5.mp4 $EVID/c5-video.mp4`
   (`EVID=../docs/validation/evidencia/fe-3-6`).
6. Con la app en Inicio, esperar 5 s y `adb shell dumpsys sensorservice > $EVID/c5-sensores-inicio.txt` y `adb exec-out
   run-as com.example.myapplication cat files/logs/app.log | grep -E "I/(Pdr|MapaPublico)" | tail -n 15 >
   $EVID/c5-app-log.txt`.
7. Pasa si el video muestra la entrada por TalkBack, el inicio del seguimiento y la vuelta a Inicio, si en
   `c5-sensores-inicio.txt` no hay ninguna conexión **activa** de `com.example.myapplication` al acelerómetro ni al
   vector de rotación (el historial también la nombra y no cuenta; formato **sin comprobar** en el Xiaomi) y si
   `c5-app-log.txt` muestra «Inicio desde Ubicarme …» y `sensores registrados (…)` seguidos de `sensores quitados
   (segundo plano)` o `(detener)` al volver. El video no debe mostrar datos privados (en casa, el mapa está en el campus).

## 4. Datos de prueba y limpieza

- **En el backend:** crea con `POST /v1/admin/alerts/sincronizar` (un `upsert` con un UUID nuevo, como `validate33.py`)
  `validacion-3-6-c1` (normal) y `validacion-3-6-c2` (alta), radio 15 m, en 6.201484, −75.578427. Al empezar borra los
  restos de una ejecución anterior (`GET /v1/admin/alerts?q=validacion-3-6` y `DELETE` de las que se llaman
  **exactamente** así, sin distinguir mayúsculas ni tildes; una alerta que solo contiene el prefijo se queda). C1c borra
  c1. Al terminar, también si algo falló, `DELETE` de c2 y c1 (registrados en cuanto se piden). Cada `DELETE` deja un
  *tombstone* de 90 días (backend §4.11), como en `validate33.py`.
- **En el teléfono:** instala el APK de depuración de este commit (conserva los datos: recorridos sin subir,
  calibración, alertas del editor) y abre las rutas de prueba `mapa` y `resultado` con `ubicacion_prueba` (solo APK de
  depuración y arranque nuevo, ADR-FE-42; la ubicación de prueba vive en memoria y caduca a los 2 min). Al terminar,
  tras borrar las alertas, vuelve a sincronizar (arranque en frío) para que la caché del teléfono quede sin ellas (si no
  hay red, se ponen al día en la próxima sincronización). Nunca usa `pm clear` ni concede permisos.
- **Limpieza** (también si algo falla, orden inverso): `DELETE` de las alertas de prueba, sincronizar la caché del
  teléfono y `am force-stop`. Con `--sin-limpieza` las alertas quedan en `dev` (la siguiente ejecución las borra como
  restos). Si la ejecución se corta en C2b, **desactivar el modo avión** a mano.

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate36.py --entorno dev
```

Sin argumentos propios. Los dos pasos guiados de C2b leen la entrada estándar: hay que correrlo en una terminal
interactiva (sin redirigir la entrada, p. ej. `< /dev/null`) o con la entrada en una FIFO y el modo avión puesto y
quitado por la persona o por `adb`, como el cierre de FE-2.2 ([`validation-2-2`](./validation-2-2.md) §5).

**Variables** (detalle en `ARCHITECTURE.md` §5.11). En la máquina del equipo el validador corre en WSL y usa el Gradle y
el `adb` de Windows (ARCHITECTURE §4.1):

| Variable | Valor en WSL | Obligatoria |
|---|---|---|
| `VALIDACION_GRADLE` | `cmd.exe /c .\gradlew.bat` (o el envoltorio del maestro que cambia `installDebug` por `adb install -r`, trampas de FE-3.4 en ARCHITECTURE §5.11) | Sí en WSL |
| `JAVA_HOME` | `C:\Users\frank\.jdks\jbr-21.0.11` | Sí en WSL |
| `WSLENV` | `JAVA_HOME:ANDROID_SERIAL` | Sí en WSL |
| `VALIDACION_ADB` | `/mnt/c/Users/frank/AppData/Local/Android/Sdk/platform-tools/adb.exe` | Sí en WSL, en `dev` |
| `AWS_PROFILE` | `campus-admin` (`terraform output` y el secreto del admin) | Sí en `dev`, salvo que estén `VALIDACION_API_URL` y las credenciales |
| `VALIDACION_ADMIN_CORREO`, `VALIDACION_ADMIN_PASSWORD` | No hacen falta: sin ellas se leen del secreto `campus-locator/dev/admin-inicial` (nunca se imprimen) | No |
| `VALIDACION_API_URL` | No hace falta: solo se usa si `terraform output` falla | No |
| `ANDROID_SERIAL` | Solo si hay varios dispositivos | No |
| `UV_PROJECT_ENVIRONMENT` | `/root/.cache/uv-envs/fe-ops` | No |

Herramientas: `uv`, `terraform` con `terraform init` hecho en `INFRASTRUCTURA_TERRAFORM/project/envs/dev` (para la URL),
la CLI `aws` (secreto del admin) y, en Windows, el JBR 21 y el Android SDK. Duración aproximada en `dev`: 6–10 min
(Gradle 1–3 min; `installDebug` 1–2 min; cada sincronización ~5–15 s; los dos pasos guiados, 1–2 min). **No necesita
`embedding`** (sin hora límite). El informe queda en `project/.validacion/FE-3.6-<AAAAMMDD-HHMMSS>.json` (hora UTC) o en
`--informe RUTA`.

**Preparación.**

1. Variables del entorno (en la misma terminal de WSL donde se ejecutará el validador):
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
   Esperado: `All checks passed!`, `29 files already formatted` y `327 passed, 1 skipped` (la omitida es la
   decodificación con Pillow de `jpeg_sintetico`, que no está en el grupo `ops`).
3. Compilación y pruebas unitarias de la app:
   ```bash
   cmd.exe /c '.\gradlew.bat' --console=plain testDebugUnitTest assembleDebug
   ```
   Esperado: `BUILD SUCCESSFUL` (392 casos, sin fallos). Si dice `Unable to delete directory '…\app\build\…'`, borrar
   `app/build` y repetir (ARCHITECTURE §4.1, «Trampas»).
4. Copia de trabajo limpia (si no, el informe sale con `-dirty`):
   ```bash
   git -c core.autocrlf=input status --short -- .
   ```
   Esperado: sin salida.
5. Teléfono: conectado por USB, depuración autorizada, desbloqueado con la pantalla encendida (`adb shell dumpsys power |
   grep mWakefulness=` → `Awake`), **sin** modo avión, con internet de verdad (datos móviles o un Wi-Fi con salida: C1b y
   C1c sincronizan) y TalkBack desactivado:
   ```bash
   $VALIDACION_ADB devices && $VALIDACION_ADB shell settings get global airplane_mode_on
   ```
   Esperado: una línea `<serial>` seguida de `device` y después `0`.
6. Solo en Xiaomi: «Instalar vía USB» y «Depuración USB (Configuración de seguridad)» activadas (MIUI apaga la primera
   entre sesiones):
   ```bash
   $VALIDACION_ADB shell input keyevent 0
   ```
   Esperado: sin salida (una `SecurityException` con `INJECT_EVENTS` = falta la segunda).
7. Que `dev` responde y cuántas alertas públicas hay (solo lectura):
   ```bash
   curl -s "$(terraform -chdir=../../INFRASTRUCTURA_TERRAFORM/project/envs/dev output -raw api_base_url)/v1/alerts" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["completo"], len(d["alertas"]))'
   ```
   Esperado: `True N` (N = las alertas activas de `dev`; puede ser 0).

**Ejecución.** En una terminal interactiva (o con una FIFO), con el teléfono a mano. El validador instala la app, crea
las alertas, sincroniza el teléfono dos veces (C1b y C1c: la app se abre sola en el mapa) y se detiene en el **paso
guiado 1** (líneas `· PASO GUIADO — …` por stderr):

1. **Paso guiado 1 (C2b):** activar el **modo avión** (con el cable USB puesto; comprobar que el Wi-Fi también quedó
   apagado). No abrir la app. Pulsar **Enter**. El script abre el mapa con la ubicación de prueba: se oye «Sigo tus pasos
   desde tu última ubicación.» y, enseguida, «validacion-3-6-c2.» (alta), el teléfono vibra y arriba aparece «Alerta:
   validacion-3-6-c2.» (sin internet el mapa puede quedar en negro: no importa).
2. **Paso guiado 2 (C2b):** desactivar el modo avión y esperar a que vuelva la conexión. Pulsar **Enter**. El script
   abre la 6.3 con la ubicación de prueba (C4b: «No hay lugares conocidos cerca», la confianza y la tarjeta «Alertas
   cercanas» con «validacion-3-6-c2.», que también se oye al final) y toca «Caminar con el mapa» (C5a: el mapa empieza
   solo y vuelve a anunciar la alerta).

Por `adb` (FIFO): `$VALIDACION_ADB shell cmd connectivity airplane-mode enable` y `… disable` (**sin comprobar** en
MIUI; si no funciona, la persona lo hace a mano) y `echo > fifo` para cada Enter.

```bash
uv run --group ops python src/ops/validate36.py --entorno dev
```

Esperado (por stderr salen además líneas `· …` de progreso —restos borrados, pasos guiados, limpieza— y la ruta del
informe):

```
[PASA] P1 Gradle 8.7, JVM 21.0.11 (…)
[PASA] P2 23028RA60L (Android 14, SDK 34, serial <serial>)
[PASA] P3 ApiConfig = terraform output api_base_url; GET /v1/health -> 200
[PASA] P4 200: <correo del admin>, rol admin
[PASA] P5 FE-3.1 y BE-3.3 Hecho; GET /v1/alerts -> 200 (N activas)
[PASA] C1a CacheAlertasPublicasTest 7/7 (mínimos 5)
[PASA] C3a DetectarAlertasCercanasTest 7/7 (mínimos 5)
[PASA] C4a ubicación de prueba solo en MainActivity (APK depurable, rutas resultado y mapa); 6.3 → mapa; el mapa empieza desde Ubicarme (onNativeRastreoIniciado); AlertasEnResultadoTest 4/4 (mínimos 3)
[PASA] C1b validacion-3-6-c1 y validacion-3-6-c2 en la caché del teléfono tras la sincronización (completa|diferencias desde …, …)
[PASA] C1c borrada en el backend (validacion-3-6-c1 en «eliminadas» de GET /v1/alerts?desde=), la sincronización siguiente (diferencias desde …, R recibidas, 1 eliminadas, N en caché) la quitó de la caché; validacion-3-6-c2 sigue
[PASA] C2b en modo avión, el mapa empezó desde la ubicación de prueba y anunció validacion-3-6-c2 desde la caché (a 6 m, radio 15 m, incertidumbre 5 m, alta); sin sincronizar (N intentos fallidos)
[PASA] C4b 6.3 con la ubicación de prueba: «No hay lugares conocidos cerca» y, debajo de la ubicación, «Alertas cercanas» con «validacion-3-6-c2.» (a 6 m, incertidumbre 5 m)
[PASA] C5a «Caminar con el mapa» abrió el mapa con el seguimiento empezado en la ubicación de prueba sin tocarlo (Pdr: sensores registrados) y anunció validacion-3-6-c2 (a 6 m)
[MANUAL] C5 Con TalkBack activo …
Resultado: pasa (código 0)
```

Para repetir solo una parte: `--solo C1` (sin pasos guiados), `--solo C2b`, `--solo C4b,C5a` (C1b no corre: si c2 no
está en la caché, el script sincroniza antes).

Casos previstos:
- `[FALLA] C1b en 45 s no apareció «Alertas públicas sincronizadas (…)» … en app.log; en app.log: «Alertas públicas: no
  se pudo sincronizar (primer plano): SinConexionException»` → el teléfono no tiene internet de verdad (paso 5) o sigue
  en modo avión.
- `[FALLA] C1b tras la sincronización (…) la caché del teléfono no tiene …` → el APK instalado no es el de este commit, o
  la caché no se guardó (`adb exec-out run-as com.example.myapplication cat files/alertas/publicas.json`).
- `[FALLA] C1c la sincronización tras borrar no fue por diferencias con eliminadas (completa, …)` → el backend no aceptó
  `desde` (en `app.log`, «el backend no aceptó desde=…») o la caché se perdió entre las dos sincronizaciones.
- `[FALLA] C2b el modo avión no está activado (…)` → en el paso guiado 1 no se activó (o MIUI no lo refleja en
  `settings`): repetir con `--solo C2b`.
- `[FALLA] C2b hubo una sincronización correcta en modo avión (…): ¿hay red?` → el Wi-Fi quedó encendido con el modo
  avión: apagarlo y repetir con `--solo C2b`.
- `[FALLA] C2b en 30 s no apareció «Alerta anunciada (mapa): <validacion-3-6-c2>» en app.log` → el mapa no empezó desde
  la ubicación de prueba (¿APK de otro commit?) o c2 no estaba en la caché (C1b).
- `[FALLA] C4b la 6.3 no muestra «Alertas cercanas» con «validacion-3-6-c2.» …` → la 6.3 no leyó la caché (línea
  `AlertasPublicas` en `app.log`) o la tarjeta quedó fuera de la pantalla.
- `[FALLA] C5a la 6.3 no ofrece «Caminar con el mapa» …` → la ubicación de prueba ya no es vigente (pasaron más de 2 min
  desde que se abrió la 6.3): repetir con `--solo C4b,C5a`.
- `[ERROR] C2b el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)` (código 3) → correr el
  validador en una terminal interactiva (o con una FIFO). La limpieza corre igual (desactivar el modo avión a mano).
- `[ERROR] C1b installDebug: INSTALL_FAILED_USER_RESTRICTED …` (código 3) → paso 6.
- `[FALLA] P5 BE-3.3 no está «Hecho» …` (código 2) → no debería pasar (BE-3.3 está «Hecho» desde el 2026-10-27).

En `local` (sin teléfono ni API): `uv run --group ops python src/ops/validate36.py --entorno local` da código 0 con
`[PASA]` en P1, C1a, C3a y C4a, `[OMITIDA]` en C1b, C1c, C2b, C4b y C5a («solo en dev (teléfono en casa)») y la manual
C5 (comprobado el 2026-10-28 en el worktree de FE-3.6, sobre `56e685a` con los cambios sin commit: C1a 7/7, C3a 7/7,
C4a estática + 4/4).

Con el validador en `dev` con código 0 sobre un commit de `main` sin `-dirty` y la manual C5 con evidencia (o dejada
pendiente por decisión del usuario), la fila FE-3.6 de PLAN §3 pasa a «Hecho» y se quitan de ARCHITECTURE §4.12 y §5.11
los «sin comprobar» que la ejecución confirme.
