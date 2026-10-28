# Validación 5-1 — FE-5.1 Grafo y rutas

| Campo | Valor |
|---|---|
| Lote | `FE-5.1` — criterios en [`PLAN.md`](../PLAN.md) §2.2 (propuestos el 2026-10-28, a confirmar por el usuario) |
| Script | `project/src/ops/validate51.py` |
| Entornos | `dev` (cierra el lote): la API de `dev` (solo `GET /v1/places`, pública) y un dispositivo físico **en casa** (la posición de prueba llega por el `Intent`); **no necesita `embedding`** ni escribe nada en el backend. `local` (sin teléfono ni red: C1a, C1b, C2a, C3a y C4a) |
| Criterios | Automáticos: C1 (C1a, C1b), C2 (C2a), C3 (C3a, C3b), C4 (C4a, C4b, con un paso guiado) · Manual: C4c (captura) |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta
(dónde corren, variables, `comun.py`, detalles de `validate51.py`, trampas): `ARCHITECTURE.md` §5.11. Lo construido:
`ARCHITECTURE.md` §4.11 (piezas en §5.6, «`assets/grafo.json` y `GrafoDeLaApp`»; §5.7, «Grafo y rutas»; §5.8, «Destino y
posición de prueba del mapa»; §5.9, `AndroidBridge` y «Aviso de ruta del mapa»). Contrato que consume:
`BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5.3 (`GET /v1/places`, solo lectura). El validador no recalcula rutas en Python:
compara el aviso del mapa con lo que fija `PlanificadorTest` en la JVM para la misma posición y el mismo destino.

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla (las siguientes quedan «no evaluada»). Las de la máquina dan
**3**; las de otros lotes, **2** (lote `Bloqueado`). En `local` solo se evalúa P1; en `dev`, P2 solo si C4b está incluida
y P3–P4 solo si C3b está incluida.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Gradle y un JDK que lo ejecute | `<VALIDACION_GRADLE> --version` termina con 0 (detalle: versión de Gradle y JVM). Si no → 3 |
| P2 | Dispositivo físico | `adb devices` con uno en estado `device` (el de `ANDROID_SERIAL` si hay varios) y `ro.kernel.qemu` distinto de `1`; anota modelo, Android y SDK. Si no → 3 |
| P3 | La app apunta a la API vigente y responde | URL vigente = `terraform output -raw api_base_url` + `/v1` (sin Terraform, `VALIDACION_API_URL`; sin ninguna → 3), igual a `ApiConfig.BASE_URL` del código, y `GET <URL>/health` → 200 `"estado": "ok"` (si no → 2) |
| P4 | `FE-3.1` y `BE-3.1` en «Hecho»: los lugares públicos | La fila `FE-3.1` de `PLAN.md` §3 y la `BE-3.1` de `BACKEND_FASTAPI/docs/PLAN.md` §3 dicen `Hecho`. Si no → 2 |

## 2. Comprobaciones automáticas

C1a, C2a, C3a y C4a corren en una sola ejecución de Gradle (las clases de las incluidas). Si C1b o C4a fallan, C4b queda
`omitida` («no se hace: falló …»). En `local`, C3b y C4b quedan `omitida`. Orden: C1a, C1b, C2a, C3a, C4a, C3b, C4b.

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | `<VALIDACION_GRADLE> testDebugUnitTest --tests '*.LectorGrafoTest'` (junto con C2a, C3a y C4a) y lee su XML | 0 fallos, errores u omitidos y ≥ 6 casos (hoy 7): el grafo real de `assets/` es válido (26 nodos, 31 aristas, 8 entradas, un componente, versión 180) y los inválidos (JSON roto, formato distinto, ids repetidos, aristas a nodos inexistentes, componentes aislados, entradas sin lugar, nodos sin coordenadas) dan `Invalido` sin lanzar |
| C1b | Estática sobre `app/src/main/assets/grafo.json` con las reglas de `LectorGrafo` (`revisar_grafo`): formato 1, `version` entera, ids únicos, aristas a nodos que existen y no a sí mismas, `metros` > 0, toda `entrada` con `lugar`, al menos una entrada y un solo componente | El archivo cumple todo; el detalle da versión, nodos, aristas (bloqueadas), entradas, lugares, metros totales |
| C2a | Las clases `ProyeccionRutaTest` e `InstruccionesTest` | 0 fallos, errores u omitidos y ≥ 7 y ≥ 6 casos (hoy 9 y 8): proyección sobre la arista (no el nodo más cercano), Dijkstra a la entrada más cercana sin aristas bloqueadas, y los textos de las instrucciones por umbrales (C2) |
| C3a | La clase `EmparejamientoTest` | 0 fallos, errores u omitidos y ≥ 3 casos (hoy 3): normalización, nombre o alias, exactos, y los lugares de `dev` de hoy |
| C4a | Estática: `PruebaMapa.fijar(` solo en `MainActivity.kt`, una vez, dentro de `if (rutaPrueba == "mapa")`, y `rutaDePrueba` con `FLAG_DEBUGGABLE` (ADR-FE-38); `assets/app.js` con `window.onNativeRuta`, `window.onNativeInicio` y `bridgeCall('listo')`. Después las clases `PlanificadorTest` y `RutaEnMapaTest` | Lo estático se cumple y las clases tienen 0 fallos, errores u omitidos y ≥ 5 y ≥ 3 casos (hoy 7 y 3): la ruta de la validación en casa (59,7 m, «Camina 45 metros por el camino.»), la primera según el rumbo, dos entradas, alias, destino fuera del grafo, el JSON del mapa, la 6.3 con y sin ruta, y los avisos del mapa |
| C3b | `GET <URL>/places` (pública, sin token) y empareja cada `lugar` del grafo con los lugares (nombre exacto o nombre/alias normalizado, como la app) | Todos los lugares del grafo casan (C3). El detalle separa los exactos de los normalizados. **El 2026-10-28 falla:** `dev` solo tiene «Bloque 35» |
| C4b | Registra la limpieza `am force-stop`, instala el APK (`installDebug`, sin `pm clear`) y abre el mapa de prueba: `am force-stop` y `am start -W -n com.example.myapplication/.MainActivity --es ruta mapa --es destino_prueba bloque35 --es posicion_prueba 6.201434,-75.578427`. Espera hasta 30 s el aviso de Compose sobre el mapa (`uiautomator dump`). **Paso guiado:** tocar otro punto del mapa; Enter. Espera hasta 15 s un aviso distinto | El aviso dice «Ruta a Bloque 35: 60 m por el camino» y debajo «Camina 45 metros por el camino.» (los de `PlanificadorTest`); tras tocar, otro «Ruta a Bloque 35: N m por el camino» con su primera instrucción (C4: ruta, distancia por el camino, primera instrucción y recálculo) |

## 3. Comprobaciones manuales

| ID | Qué hace la persona | Evidencia en el PR |
|---|---|---|
| C4c | Captura del mapa con la ruta verde y el aviso, en el paso guiado de C4b **antes** de pulsar Enter: `adb exec-out screencap -p > c4c-mapa-ruta.png`, en `validation/evidencia/fe-5-1/` | La captura, sin datos privados: muestra el campus y la posición de prueba, no la de la persona (el teléfono está en casa, pero el mapa está en el campus) |

## 4. Datos de prueba y limpieza

- **Nada en el backend:** solo lee `GET /v1/places` (pública). No crea lugares: si C3b falla, crear los lugares que faltan
  es una decisión del usuario (7.7), no del validador.
- **En el teléfono:** instala el APK de depuración de este commit (conserva los datos: recorridos sin subir, calibración,
  alertas) y abre la ruta de prueba `mapa` con el destino y la posición de prueba (ADR-FE-38). Nunca usa `pm clear` ni
  concede permisos (el mapa no los pide). Los datos de prueba del mapa (`PruebaMapa`) viven en memoria y se borran al
  salir del mapa o al cerrar la app.
- **Limpieza** (también si algo falla): `am force-stop` de la app. Con `--sin-limpieza` la app queda abierta en el mapa.

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate51.py --entorno dev
```

Sin argumentos propios. El paso guiado de C4b lee la entrada estándar: hay que correrlo en una terminal interactiva (sin
redirigir la entrada, p. ej. `< /dev/null`) o con la entrada en una FIFO y el toque hecho por `adb`, como el cierre de
FE-2.2 ([`validation-2-2`](./validation-2-2.md) §5).

**Variables** (detalle en `ARCHITECTURE.md` §5.11). En la máquina del equipo el validador corre en WSL y usa el Gradle y
el `adb` de Windows (ARCHITECTURE §4.1):

| Variable | Valor en WSL | Obligatoria |
|---|---|---|
| `VALIDACION_GRADLE` | `cmd.exe /c .\gradlew.bat` (o el envoltorio del maestro que cambia `installDebug` por `adb install -r`, trampas de FE-3.4 en ARCHITECTURE §5.11) | Sí en WSL |
| `JAVA_HOME` | `C:\Users\frank\.jdks\jbr-21.0.11` | Sí en WSL |
| `WSLENV` | `JAVA_HOME:ANDROID_SERIAL` | Sí en WSL |
| `VALIDACION_ADB` | `/mnt/c/Users/frank/AppData/Local/Android/Sdk/platform-tools/adb.exe` | Sí en WSL, en `dev` con C4b |
| `AWS_PROFILE` | `campus-admin` (solo para `terraform output`) | Sí en `dev` con C3b, salvo que esté `VALIDACION_API_URL` |
| `VALIDACION_API_URL` | No hace falta: solo se usa si `terraform output` falla | No |
| `ANDROID_SERIAL` | Solo si hay varios dispositivos | No |
| `UV_PROJECT_ENVIRONMENT` | `/root/.cache/uv-envs/fe-ops` | No |

No hacen falta las credenciales del admin (no llama a rutas protegidas). Herramientas: `uv`, `terraform` con `terraform
init` hecho en `INFRASTRUCTURA_TERRAFORM/project/envs/dev` (para la URL) y, en Windows, el JBR 21 y el Android SDK.
Duración aproximada en `dev`: 4–7 min (Gradle 1–3 min; `installDebug` 1–2 min; abrir el mapa y cargar Leaflet ~10 s; el
paso guiado, 1 min). **No necesita `embedding`** (sin hora límite). El informe queda en
`project/.validacion/FE-5.1-<AAAAMMDD-HHMMSS>.json` (hora UTC) o en `--informe RUTA`.

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
   Esperado: `All checks passed!`, `27 files already formatted` y `312 passed, 1 skipped` (la omitida es la
   decodificación con Pillow de `jpeg_sintetico`, que no está en el grupo `ops`).
3. Compilación y pruebas unitarias de la app:
   ```bash
   cmd.exe /c '.\gradlew.bat' --console=plain testDebugUnitTest assembleDebug
   ```
   Esperado: `BUILD SUCCESSFUL` (374 casos, sin fallos). Si dice `Unable to delete directory '…\app\build\…'`, borrar
   `app/build` y repetir (ARCHITECTURE §4.1, «Trampas»).
4. Copia de trabajo limpia (si no, el informe sale con `-dirty`):
   ```bash
   git -c core.autocrlf=input status --short -- .
   ```
   Esperado: sin salida.
5. Teléfono: conectado por USB, depuración autorizada, desbloqueado con la pantalla encendida (`adb shell dumpsys power |
   grep mWakefulness=` → `Awake`), con internet de verdad (datos móviles o un Wi-Fi con salida: el mapa carga Leaflet de
   `unpkg.com` y las teselas de OSM) y TalkBack desactivado:
   ```bash
   $VALIDACION_ADB devices
   ```
   Esperado: una línea `<serial>` seguida de `device` (no `unauthorized` ni `offline`).
6. Solo en Xiaomi: «Instalar vía USB» y «Depuración USB (Configuración de seguridad)» activadas (MIUI apaga la primera
   entre sesiones):
   ```bash
   $VALIDACION_ADB shell input keyevent 0
   ```
   Esperado: sin salida (una `SecurityException` con `INJECT_EVENTS` = falta la segunda).
7. Que `dev` responde y qué lugares tiene (para saber de antemano si C3b pasará):
   ```bash
   curl -s "$(terraform -chdir=../../INFRASTRUCTURA_TERRAFORM/project/envs/dev output -raw api_base_url)/v1/places" | python3 -c 'import json,sys; print([i["nombre"] for i in json.load(sys.stdin)["items"]])'
   ```
   Esperado: la lista de nombres. El 2026-10-28 era `['Bloque 35']`: con eso C3b falla (faltan seis lugares del grafo).

**Ejecución.** En una terminal interactiva (o con una FIFO), con el teléfono a mano. El validador instala la app, abre
el mapa de prueba, comprueba el aviso y se detiene en el **paso guiado** (líneas `· PASO GUIADO — …` por stderr). Cuando
se detiene, el teléfono muestra el mapa en el campus con la ruta verde hasta Bloque 35 y arriba el aviso:

1. **Paso guiado (C4b):** tomar la captura de C4c (`$VALIDACION_ADB exec-out screencap -p > c4c-mapa-ruta.png`). Tocar
   **otro punto del mapa**, a uno o dos dedos del punto azul, **sin** pulsar ▶; esperar a que el aviso de arriba cambie de
   distancia. Pulsar **Enter**.

Por `adb` (FIFO): el aviso son dos `TextView` de Compose arriba de la pantalla; el mapa (`WebView`) ocupa el resto.
`$VALIDACION_ADB shell input tap <x> <y>` con `x` en el centro de la pantalla e `y` unos 200 px por debajo del centro sirve
(el punto azul queda en el centro del mapa al fijar la posición).

```bash
uv run --group ops python src/ops/validate51.py --entorno dev
```

Esperado **hoy** (código 1 por C3b, mientras `dev` tenga solo «Bloque 35»; por stderr salen además líneas `· …` de
progreso —paso guiado, limpieza— y la ruta del informe):

```
[PASA] P1 Gradle 8.7, JVM 21.0.11 (…)
[PASA] P2 23028RA60L (Android 14, SDK 34, serial <serial>)
[PASA] P3 ApiConfig = terraform output api_base_url; GET /v1/health -> 200
[PASA] P4 FE-3.1 y BE-3.1 Hecho
[PASA] C1a LectorGrafoTest 7/7 (mínimos 6)
[PASA] C1b assets/grafo.json v180: 26 nodos, 31 aristas (0 bloqueadas), 8 entradas con lugar (7 lugares), 650 m, un solo componente
[PASA] C2a ProyeccionRutaTest 9/9, InstruccionesTest 8/8 (mínimos 7, 6)
[PASA] C3a EmparejamientoTest 3/3 (mínimos 3)
[PASA] C4a PruebaMapa solo en MainActivity (APK depurable, ruta mapa); app.js con onNativeRuta, onNativeInicio y listo; PlanificadorTest 7/7, RutaEnMapaTest 3/3 (mínimos 5, 3)
[FALLA] C3b 6 de 7 lugares del grafo no existen en GET /v1/places: bloque 33, biblioteca, bloque 38, cocnverso, bloque 34, cafeteria (GET /v1/places -> 1 lugares; exactos: Bloque 35)
[PASA] C4b con bloque35 y 6.201434,-75.578427: «Ruta a Bloque 35: 60 m por el camino» / «Camina 45 metros por el camino.»; tras tocar otro punto: «Ruta a Bloque 35: N m por el camino» / «…»
[MANUAL] C4c Captura del mapa con la ruta y el aviso, …
Resultado: falla (código 1)
```

Con los seis lugares creados en `dev` (con esos nombres o con un alias que case, ARCHITECTURE §5.7), C3b pasa con «los 7
lugares del grafo existen en el backend (…)» y el resultado es `pasa (código 0)`. Para repetir solo C4b (sin API):
`--solo C4b` (P3 y P4 quedan «no evaluada»); para repetir solo C3b tras crear los lugares: `--solo C3b` (P2 «no
evaluada», sin teléfono).

Casos previstos:
- `[FALLA] C4b el mapa muestra «Destino: Bloque 35. Toca el mapa para fijar tu posición y ver la ruta.» en vez de la ruta
  (¿sin internet para Leaflet? ¿grafo inválido?)` → la página no llegó a `listo()`: sin internet (Leaflet viene de
  `unpkg.com`) o la página falló al arrancar. Revisar la red del teléfono (paso 5) y `adb exec-out run-as
  com.example.myapplication tail -n 30 files/logs/app.log` (líneas `MapaPublico` con errores de JS y `Grafo`).
- `[FALLA] C4b el mapa muestra «Rutas desactivadas: el grafo de caminos no es válido.» …` → `assets/grafo.json` no pasó
  `LectorGrafo` en el teléfono (la línea `Grafo` de `app.log` dice por qué); C1b debería haber fallado antes.
- `[FALLA] C4b en 30 s no apareció el aviso «Ruta a …» en el mapa; en pantalla: …` → no se abrió el mapa (otra pantalla,
  teléfono bloqueado: paso 5) o el APK instalado no es el de este commit.
- `[FALLA] C4b el aviso dice «…» / «…»; se esperaba «Ruta a Bloque 35: 60 m por el camino» / «Camina 45 metros por el
  camino.»` → el grafo o el cálculo cambiaron sin actualizar `PlanificadorTest` y las constantes del validador.
- `[FALLA] C4b en 15 s no apareció un aviso de ruta distinto tras tocar el mapa …` → el toque no llegó al mapa (se tocó el
  aviso o el mismo punto) o la ruta no se recalcula: repetir con `--solo C4b` tocando más lejos.
- `[FALLA] C3b N de 7 lugares del grafo no existen en GET /v1/places: …` → faltan lugares en `dev` (hoy, seis): decisión
  del usuario (crearlos en 7.7 o corregir el grafo); no es un fallo de la app.
- `[ERROR] C4b el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)` (código 3) → correr el
  validador en una terminal interactiva (o con una FIFO). La limpieza corre igual.
- `[ERROR] C4b installDebug: INSTALL_FAILED_USER_RESTRICTED …` (código 3) → paso 6.
- `[FALLA] P4 BE-3.1 no está «Hecho» …` (código 2) → no debería pasar (BE-3.1 está «Hecho» desde el 2026-10-25).

En `local` (sin teléfono ni API): `uv run --group ops python src/ops/validate51.py --entorno local` da código 0 con
`[PASA]` en P1, C1a, C1b, C2a, C3a y C4a, `[OMITIDA]` en C3b («solo en dev (GET /v1/places)») y C4b («solo en dev
(teléfono en casa)») y la manual C4c (comprobado el 2026-10-28 en el worktree de FE-5.1, sobre `bef5853` con los cambios
sin commit: C1a 7/7, C2a 9/9 y 8/8, C3a 3/3, C4a 7/7 y 3/3).

Con el validador en `dev` con código 0 sobre un commit de `main` sin `-dirty`, la fila FE-5.1 de PLAN §3 pasa a «Hecho» y
se quitan de ARCHITECTURE §4.11, §5.9 y §5.11 los «sin comprobar» que la ejecución confirme.
