# Validación 4-1 — FE-4.1 Videos e imágenes contra el backend (7.11–7.14)

| Campo | Valor |
|---|---|
| Lote | `FE-4.1` — criterios en [`PLAN.md`](../PLAN.md) §2.2 (alcance «lo esencial», decisión del usuario del 2026-10-27) |
| Script | `project/src/ops/validate41.py` |
| Entornos | `dev` (cierra el lote): dispositivo físico conectado por `adb` y la API de `dev`; **no necesita `embedding`** (las fotos de prueba pueden quedarse en `subida`). `local` (sin teléfono ni backend: C1a, C2a y C3a) |
| Criterios | Automáticos: C1 (C1a, C1b), C2 (C2a, C2b), C3 (C3a, C3b), con dos pasos guiados · Manual: C2c (capturas) |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta
(dónde corren, variables, `comun.py` —con `http_put_bytes` y `jpeg_sintetico`, nuevas en FE-4.1—, detalles de
`validate41.py`, trampas): `ARCHITECTURE.md` §5.11. Lo construido: `ARCHITECTURE.md` §4.10 (piezas en §5.5, «`VideosScreen`
y `VideosViewModel`», «`VideoDetalleScreen` y `VideoBridge`», «`GaleriaViewModel`», «`GaleriaScreen`»; §5.6, «`VideoRepository`
en detalle»; §5.9; §5.10, «Videos e imágenes de administración»). Contratos que consume: `BACKEND_FASTAPI/docs/ARCHITECTURE.md`
§4.12 («Para la app (FE-4.1)»), §5.4 (recolección: solo el script, para crear los videos de prueba), §5.5
(`/v1/admin/videos`, `/v1/admin/images`, `VideoResumen`, `ImagenAdmin`) y §5.6. El validador no recalcula nada: compara lo
que muestra la app con lo que responde la API (y con los manifests del teléfono).

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla (las siguientes quedan «no evaluada»). Las de la máquina y
las credenciales dan **3**; las de otros lotes, **2** (lote `Bloqueado`). En `local` solo se evalúa P1; en `dev`, P2–P6
solo si alguna de C1b, C3b o C2b está incluida.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Gradle y un JDK que lo ejecute | `<VALIDACION_GRADLE> --version` termina con 0 (detalle: versión de Gradle y JVM). Si no → 3 |
| P2 | Dispositivo físico | `adb devices` con uno en estado `device` (el de `ANDROID_SERIAL` si hay varios) y `ro.kernel.qemu` distinto de `1`; anota modelo, Android y SDK. Si no → 3 |
| P3 | La app apunta a la API vigente y responde | URL vigente = `terraform output -raw api_base_url` + `/v1` (sin Terraform, `VALIDACION_API_URL`; sin ninguna → 3), igual a `ApiConfig.BASE_URL` del código, y `GET <URL>/health` → 200 `"estado": "ok"` (si no → 2) |
| P4 | Login de admin contra `dev` | `POST <URL>/auth/login` con `VALIDACION_ADMIN_CORREO`/`VALIDACION_ADMIN_PASSWORD` o el secreto `campus-locator/dev/admin-inicial` → 200 con `token` y `usuario.rol = "admin"` (`401` o rol distinto → 3; otro código → 2). Guarda el token (nunca se imprime) y el nombre (para el saludo del Panel) |
| P5 | `FE-2.1` en «Hecho»: subida de recorridos (la cola y los manifests que 7.13 junta con el servidor) | La fila de `FE-2.1` en `PLAN.md` §3 dice `Hecho`. Si no → 2 |
| P6 | `BE-2.1` y `BE-4.1` en «Hecho»: recolección y administración de videos e imágenes | Las dos filas en `BACKEND_FASTAPI/docs/PLAN.md` §3 dicen `Hecho`; con el token, `GET <URL>/admin/videos?por_pagina=1` y `GET <URL>/admin/images?por_pagina=1` → 200 con `items` y `total`; y `POST <URL>/collect/videos` con `{}` → `422 VALIDACION` (la recolección responde, sin crear nada). Si no → 2 |

## 2. Comprobaciones automáticas

C1a, C2a y C3a corren en una sola ejecución de Gradle; si alguna falla, C1b, C3b y C2b quedan `omitida` («no se hace:
falló …»). En `local`, C1b, C3b y C2b quedan `omitida`. Orden en `dev`: C1a, C2a, C3a, C1b, C3b, C2b. Antes de C1b el
script crea los videos de prueba (§4), instala el APK (`installDebug`, sin `pm clear`), concede los permisos de Inicio y
entra al Panel con el admin **por la interfaz** (como `validation-3-4`).

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | Estática sobre `app/src/main/java/…` (sin comentarios ni cadenas): busca `EdicionesLocales`, `AssetsVideoRepository` y `FuenteRecorridos`; mira que no exista `app/src/main/assets/videos/` y que las `Factory` de `GaleriaViewModel.kt`, `VideosViewModel.kt` y `VideoDetalleViewModel.kt` y `deLaApp` de `VideoRepository.kt` creen `RemoteVideoRepository()` / `VideoRepositoryCompuesto.deLaApp()`. Después `<VALIDACION_GRADLE> testDebugUnitTest --tests '*.VideoRepositoryCompuestoTest'` (junto con C2a y C3a) y lee su XML | No queda ninguno de los tres nombres, no hay `assets/videos/`, las `Factory` usan el backend, Gradle sale con 0 y la clase tiene 0 fallos, errores u omitidos y ≥ 8 casos (hoy 11): la mezcla servidor + teléfono (un recorrido sale una sola vez, los locales salen sin red, renombrar/eliminar uno local persiste en disco y no se permite mientras se sube) |
| C2a | Estática sobre `assets/video_detalle.js`: el cuerpo de `function eliminarVideo()` llama a `call('eliminarVideo')` y **no** tiene `setTimeout` ni `salir` (la app vuelve a la lista cuando el servidor confirma, no a los 900 ms). Y la clase `TextosVideosTest` | El JS cumple y la clase tiene 0 fallos, errores u omitidos y ≥ 4 casos (hoy 5): los errores de borrar se convierten en un mensaje (nunca lanzan; con la sesión perdida, ninguno) |
| C3a | La clase `RemoteVideoRepositoryTest` | 0 fallos, errores u omitidos y ≥ 10 casos (hoy 15): `PATCH /v1/admin/videos/{id}` con `{"nombre"}` y su aviso, `DELETE` `202`, el lote con `"lugar_id": null`, las páginas, el detalle con sus URLs |
| C1b | Lee los manifests de `files/recoleccion` (`run-as`; si no puede, no compara «M sin subir» y lo dice). En el Panel toca «Videos» y espera 7.13 (hasta 30 s) con «N videos»; escribe `validacion-4-1` en su buscador y espera las filas de los dos videos de prueba; vuelve al Panel, toca «Imágenes» y lee «N imágenes» de la Galería. Lee `GET /v1/admin/videos` y `GET /v1/admin/images` (`total`) antes y después de cada pantalla | «N videos» = `total` de `GET /v1/admin/videos` (antes o después); «M sin subir en este teléfono» (0 si no está) = recorridos `finalizado` sin `remote_video_id` en los manifests; con `validacion-4-1`, las filas «Video validacion-4-1-a, …» y «Video validacion-4-1-b, …» y «N videos» = `total` con `q`; la Galería, «N imágenes» = `total` de `GET /v1/admin/images` |
| C3b | Deja 7.13 abierta con `validacion-4-1` en el buscador. **Paso guiado 1:** abrir `validacion-4-1-a`, «Renombrar», escribir `validacion-4-1-renombrado`, «Guardar» y esperar el nombre nuevo; Enter. Consulta `GET /v1/admin/videos/{id}` cada ~1 s hasta 20 s (y mira que la app no muestre «No se pudo renombrar…») | El backend da `nombre = "validacion-4-1-renombrado"` (C3) |
| C2b | Deja 7.13 abierta con la búsqueda. **Paso guiado 2:** abrir `validacion-4-1-b`, «Eliminar video», escribir su nombre y confirmar; **esperar sin tocar** a que la app vuelva sola a la lista; Enter. Espera hasta 30 s a 7.13 (si se ve «No se pudo eliminar el video», falla con su mensaje); `GET /v1/admin/videos/{id}` de B; en 7.13, con la búsqueda, las filas y «N videos»; vuelve al Panel, toca «Imágenes», escribe `validacion-4-1` en el buscador de la Galería y lee «N imágenes» y las tarjetas; `GET /v1/admin/images?q=validacion-4-1` y `?video_id=<B>` | La app volvió sola a 7.13; el backend da `404` para B; 7.13 ya no tiene la fila de B y sí la de A (renombrado) con «N videos» = `total` con `q`; la Galería muestra «N imágenes» = `total` de `GET /v1/admin/images?q=validacion-4-1` y ninguna tarjeta «…, video validacion-4-1-b», y `?video_id=<B>` da 0 fotos — todo sin reiniciar la app (C2) |

## 3. Comprobaciones manuales

| ID | Qué hace la persona | Evidencia en el PR |
|---|---|---|
| C2c | Dos capturas por `adb exec-out screencap -p` después del borrado: 7.13 con `validacion-4-1` en el buscador (solo `validacion-4-1-renombrado`), tomada en el paso guiado 2 **antes de pulsar Enter** (la app ya volvió sola a 7.13 y conserva la búsqueda); y la Galería con la misma búsqueda (sus 3 fotos). El script pasa por la Galería unos segundos y al terminar borra los videos, así que para la segunda: correr con `--sin-limpieza`, al terminar (la app queda en el Panel) abrir «Imágenes», escribir `validacion-4-1`, capturar, y limpiar con `--solo C1b` (§4) | Las dos capturas, sin datos privados (solo nombres de prueba; nada de la cámara). Opcional: el informe ya trae C2b comprobado por la pantalla y la API |

## 4. Datos de prueba y limpieza

- **Videos `validacion-4-1-a` y `validacion-4-1-b`** (`nombre`), creados por el script con la API de recolección
  (backend §5.4), sin la app: `POST /v1/collect/videos` con `ref_cliente = <nombre>-<AAAAMMDD-HHMMSS>` (único en cada
  ejecución: volver a usar uno borrado da `409 VIDEO_ELIMINADO`), `iniciado_en`/`finalizado_en` el 2026-01-01 (así 7.3
  nunca los toma como «el último»), `inicio` y fotos en (1,0, −100,0) —fuera del campus, como los validadores del
  backend—, `total_fotos` 3 y `dispositivo` `validate41.py`; `POST …/images` con 3 fotos (JPEG sintéticos en gris de
  640×480 hechos sin Pillow, `comun.jpeg_sintetico`); `PUT` de cada una a su URL prefirmada con **exactamente** los
  encabezados recibidos (`comun.http_put_bytes`; las URLs nunca se imprimen); `POST …/complete`. La persona renombra A
  (`validacion-4-1-renombrado`) y elimina B desde la app.
- **Limpieza** (al empezar, antes de crear, y al terminar, también si algo falla): `DELETE /v1/admin/videos/{id}` (`202`
  o `404`) **solo** de los videos de `GET /v1/admin/videos?q=validacion-4-1` cuyo `nombre` **y** `ref_cliente` empiezan
  por `validacion-4-1` (incluido el renombrado), y de los que creó esta ejecución si su `ref_cliente` es del prefijo
  (por si la persona los renombró a otra cosa). **Nunca** otros videos —el backend tiene el dataset real del usuario: uno
  que solo se *llama* `validacion-4-1…` pero cuyo `ref_cliente` no lo es se queda— ni imágenes sueltas. El borrado retira
  los vectores al instante; los objetos de S3 los purga el `worker` cuando corre (con `embedding` encendido).
- En el teléfono no borra nada ni usa `pm clear` (tiene recorridos reales sin subir: solo los lee); la limpieza termina con
  `am force-stop` (el teléfono queda sin sesión, `ARCHITECTURE.md` §5.3). Cada login y cada escritura dejan su fila en
  `auditoria` del backend (`video.renombrar`, `video.eliminar`; registro, se conservan).
- Con `--sin-limpieza` quedan los videos de prueba, la app abierta y la sesión (la siguiente ejecución en `dev` con
  alguna de C1b, C3b o C2b los borra como restos al empezar; la más corta es `--solo C1b`, sin pasos guiados: crea un
  par nuevo y lo borra al terminar).

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate41.py --entorno dev
```

Sin argumentos propios. Los dos pasos guiados leen la entrada estándar: hay que correrlo en una terminal interactiva (sin
redirigir la entrada, p. ej. `< /dev/null`) o con la entrada en una FIFO y los pasos hechos por `adb` (`input tap/text`,
`uiautomator`), como el cierre de FE-2.2 ([`validation-2-2`](./validation-2-2.md) §5).

**Variables** (detalle en `ARCHITECTURE.md` §5.11). En la máquina del equipo el validador corre en WSL y usa el Gradle y
el `adb` de Windows (ARCHITECTURE §4.1):

| Variable | Valor en WSL | Obligatoria |
|---|---|---|
| `VALIDACION_GRADLE` | `cmd.exe /c .\gradlew.bat` (o el envoltorio del maestro que cambia `installDebug` por `adb install -r`, trampas de FE-3.4 en ARCHITECTURE §5.11) | Sí en WSL |
| `JAVA_HOME` | `C:\Users\frank\.jdks\jbr-21.0.11` | Sí en WSL |
| `WSLENV` | `JAVA_HOME:ANDROID_SERIAL` | Sí en WSL |
| `VALIDACION_ADB` | `/mnt/c/Users/frank/AppData/Local/Android/Sdk/platform-tools/adb.exe` | Sí en WSL, en `dev` |
| `AWS_PROFILE` | `campus-admin` (`terraform output` y, sin `VALIDACION_ADMIN_*`, el secreto del admin) | Sí en `dev`, salvo que estén `VALIDACION_API_URL` y las dos `VALIDACION_ADMIN_*` |
| `VALIDACION_ADMIN_CORREO`, `VALIDACION_ADMIN_PASSWORD` | Las del admin de `dev`, leídas sin eco; sin ellas, el secreto `campus-locator/dev/admin-inicial` | No |
| `VALIDACION_API_URL` | No hace falta: solo se usa si `terraform output` falla | No |
| `ANDROID_SERIAL` | Solo si hay varios dispositivos | No |
| `UV_PROJECT_ENVIRONMENT` | `/root/.cache/uv-envs/fe-ops` | No |

Herramientas: `uv`, `terraform` con `terraform init` hecho en `INFRASTRUCTURA_TERRAFORM/project/envs/dev`, la CLI `aws`
v2 en WSL (si se usa el secreto) y, en Windows, el JBR 21 y el Android SDK. Duración aproximada en `dev`: 10–15 min
(Gradle 1–3 min; crear los dos videos ~10 s; `installDebug` 1–2 min; login por la interfaz ~1 min; C1b ~1 min; los dos
pasos guiados, 3–5 min). **No necesita `embedding`** (sin hora límite). Crea y borra videos en `dev`: no correrlo a la vez
que otro validador que cuente videos o fotos (`validate22.py` compara `total_fotos`) ni que el de BE-4.1 (borra todos los
videos `validacion-`), ni mientras el teléfono sube recorridos (los totales cambiarían a mitad de C1b). El informe queda
en `project/.validacion/FE-4.1-<AAAAMMDD-HHMMSS>.json` (hora UTC) o en `--informe RUTA`.

**Preparación.**

1. Variables del entorno (en la misma terminal de WSL donde se ejecutará el validador; si se prefiere el secreto, saltar
   las dos líneas `read` y el `export` de `VALIDACION_ADMIN_*`):
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
   Esperado: `All checks passed!`, `25 files already formatted` y `289 passed, 1 skipped` (la omitida es la
   decodificación con Pillow de `jpeg_sintetico`, que no está en el grupo `ops`).
3. Compilación y pruebas unitarias de la app:
   ```bash
   cmd.exe /c '.\gradlew.bat' --console=plain testDebugUnitTest assembleDebug
   ```
   Esperado: `BUILD SUCCESSFUL` (337 casos, sin fallos). Si dice `Unable to delete directory '…\app\build\…'`, borrar
   `app/build` y repetir (ARCHITECTURE §4.1, «Trampas»).
4. Copia de trabajo limpia (si no, el informe sale con `-dirty`):
   ```bash
   git -c core.autocrlf=input status --short -- .
   ```
   Esperado: sin salida.
5. Teléfono: conectado por USB, depuración autorizada, desbloqueado con la pantalla encendida, con datos móviles o un
   Wi-Fi con salida a internet (en «EAFIT_VISITANTES» la API no respondía, trampas de FE-3.4), TalkBack desactivado y
   **sin una subida en marcha** (no tocar «Subir y procesar» durante la validación):
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
7. Que `dev` responde y que BE-4.1 está cerrado:
   ```bash
   curl -s "$(terraform -chdir=../../INFRASTRUCTURA_TERRAFORM/project/envs/dev output -raw api_base_url)/v1/health"; echo
   grep '^| BE-4.1 |' ../../BACKEND_FASTAPI/docs/PLAN.md | tail -1
   ```
   Esperado: `{"estado":"ok",…}` y una fila `| BE-4.1 | 4 | Hecho | …` (si no, código 2 en P6).

**Ejecución.** En una terminal interactiva (o con una FIFO), con el teléfono a mano. El validador crea los videos de
prueba, instala la app, entra al Panel con el admin, recorre 7.13 y la Galería solo (C1b) y se detiene en cada **paso
guiado** (líneas `· PASO GUIADO — …` por stderr). Cuando se detiene, la app ya está en 7.13 con `validacion-4-1` en el
buscador:

1. **Paso guiado 1 (C3b):** tocar la fila **`validacion-4-1-a`** → en su detalle (7.14), **«Renombrar»** → escribir
   **`validacion-4-1-renombrado`** → **«Guardar»** → esperar a que la cabecera muestre el nombre nuevo (la app tapa el
   mapa con «Guardando el nombre…» mientras responde el servidor). Pulsar **Enter**.
2. **Paso guiado 2 (C2b):** el script vuelve a dejar 7.13 con la búsqueda. Tocar la fila **`validacion-4-1-b`** →
   **«Eliminar video»** → escribir **`validacion-4-1-b`** → confirmar. **No tocar nada más**: la app muestra «Eliminando el
   video…» y vuelve **sola** a la lista cuando el servidor confirma (con un aviso ««validacion-4-1-b» eliminado (3 fotos
   retiradas).»). Para C2c, tomar aquí la captura de 7.13 (solo `validacion-4-1-renombrado`). Pulsar **Enter**. El
   script comprueba la lista y pasa por la Galería (la captura de la Galería, como dice §3).

Por `adb` (FIFO): las filas de 7.13 se encuentran con `uiautomator dump` por su `content-desc` («Video
validacion-4-1-a, …»); en 7.14 los botones son del `WebView` («Renombrar», «Eliminar video»; el campo del diálogo es un
`EditText` del `WebView`): tocar por coordenadas tras una captura.

```bash
uv run --group ops python src/ops/validate41.py --entorno dev
```

Esperado (código 0; por stderr salen además líneas `· …` de progreso —restos borrados, videos creados, pasos guiados,
limpieza— y la ruta del informe):

```
[PASA] P1 Gradle 8.7, JVM 21.0.11 (…)
[PASA] P2 23028RA60L (Android 14, SDK 34, serial <serial>)
[PASA] P3 ApiConfig = terraform output api_base_url; GET /v1/health -> 200
[PASA] P4 200: <correo>, rol admin
[PASA] P5 FE-2.1 Hecho
[PASA] P6 BE-2.1 y BE-4.1 Hecho; GET /v1/admin/videos -> 200 (total N); GET /v1/admin/images -> 200 (total M); POST /v1/collect/videos {} -> 422 VALIDACION
[PASA] C1a sin EdicionesLocales, AssetsVideoRepository, FuenteRecorridos ni assets/videos; las Factory de 7.11–7.14 usan el backend; VideoRepositoryCompuestoTest 11/11 (mínimos 8)
[PASA] C2a video_detalle.js: eliminarVideo() llama al puente y no sale sola; TextosVideosTest 5/5 (mínimos 4)
[PASA] C3a RemoteVideoRepositoryTest 15/15 (mínimos 10)
[PASA] C1b 7.13 «N+2 videos» = GET /v1/admin/videos (total); «K sin subir en este teléfono» = manifests; con «validacion-4-1»: validacion-4-1-a y validacion-4-1-b (2 = total con q); 7.11 «M+6 imágenes» = GET /v1/admin/images
[PASA] C3b «validacion-4-1-a» renombrado en 7.14: GET /v1/admin/videos/{id} da nombre «validacion-4-1-renombrado»
[PASA] C2b «validacion-4-1-b» eliminado en 7.14: la app volvió sola a 7.13, que ya no lo lista (sí «validacion-4-1-renombrado»; 1 = total con q); GET /v1/admin/videos/{id} -> 404; la Galería con «validacion-4-1» muestra 3 imágenes (= GET /v1/admin/images?q=) y ninguna de «validacion-4-1-b», sin reiniciar la app
[MANUAL] C2c Evidencia para el PR (validation-4-1 §3): …
Resultado: pasa (código 0)
```

(«2 = total con q» y «3 imágenes» suponen que en `dev` no hay otros videos cuyo nombre contenga `validacion-4-1`; si los
hay, los números son mayores y el script los compara igual con la API.) Al terminar, en stderr: `· limpieza: cerrar la
app (am force-stop)` y `· limpieza: borrar los videos de prueba (validacion-4-1-*)` (orden inverso al de registro).

El validador nunca pulsa Atrás en el Panel (es la raíz: cerraría la app) ni con otra app en primer plano: reconoce el
Panel por el saludo o, si está desplazado, por los textos de sus tarjetas, y antes de cada Atrás, toque o texto mira el
`package` del volcado. Los mensajes nunca listan textos de otras apps (p. ej. la pantalla de inicio): dicen «(la app no
está en primer plano: …; sus textos no se muestran)».

Casos previstos:
- `[FALLA] C1b|C3b|C2b la app salió del primer plano (se ve otra app o la pantalla de inicio): no se pulsa nada fuera de
  ella` (o `… mientras se esperaba <qué>`) → la app se cerró o alguien la dejó (Inicio, una notificación). Si fue al
  eliminar en C2b, es una falla de la app (C2: «sin cerrar la app»); si no, repetir con el teléfono quieto. La siguiente
  comprobación vuelve a abrirla e iniciar sesión sola. (En la primera ejecución en `dev`, sobre `01adb2e`, C3b y C2b
  fallaron con «no se volvió al Panel con Atrás» por el validador: ARCHITECTURE §5.11, trampas de FE-4.1.)
- `[FALLA] … se ve el Panel pero no «Hola, <nombre>» tras subir 5 veces` → el saludo cambió (o el nombre del admin):
  revisar `saludo_esperado`.
- `[FALLA] P6 BE-4.1 no está «Hecho» …` (código 2) → BE-4.1 no está cerrado: esperar.
- `[FALLA] C1b 7.13 dice «X videos», pero GET /v1/admin/videos da total Y` → la Lista no muestra el `total` del servidor
  (o cambió mientras se leía: repetir sin subidas en marcha).
- `[FALLA] C1b 7.13 dice «X sin subir en este teléfono», pero hay Y recorridos finalizados sin remote_video_id …` → la
  mezcla servidor + teléfono no cuenta bien los locales: avisar con el detalle.
- `[FALLA] C1b en 15 s no se vio «validacion-4-1-a», «validacion-4-1-b» y «2 videos» …` → la búsqueda no filtra o falta un
  video de prueba: avisar con lo que se veía.
- `[FALLA] C1b la Galería dice «X imágenes», pero GET /v1/admin/images da total Y` → la Galería no muestra el `total`.
- `[FALLA] C3b en 20 s GET /v1/admin/videos/{id} sigue con nombre «validacion-4-1-a», …` → no se guardó el nombre (o se
  escribió otro): repetir con `--solo C3b`. `[FALLA] C3b la app mostró «No se pudo renombrar…»` → error del servidor o sin
  red: el detalle lo dice.
- `[FALLA] C2b la app mostró «No se pudo eliminar el video»: «…»` → el borrado falló (el mensaje dice por qué); la app no
  se cerró, que también es parte de C2. `[FALLA] C2b en 30 s no se vio la lista de videos (7.13) tras eliminar …` → la app
  no volvió sola (o la persona no confirmó). `[FALLA] C2b GET /v1/admin/videos/{id} de «validacion-4-1-b» sigue
  respondiendo 200 …` → la app no llamó al `DELETE`.
- `[FALLA] C2b en 15 s no se vio la Galería con «validacion-4-1»: …` → la Galería sigue mostrando fotos del video borrado.
- `[ERROR] C3b el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)` (código 3) → correr el
  validador en una terminal interactiva (o con una FIFO). La limpieza corre igual.
- `[ERROR] C1b … installDebug: INSTALL_FAILED_USER_RESTRICTED …` o `… el teléfono no deja a adb … (SecurityException)`
  (código 3) → paso 6.
- `[FALLA] P4 las credenciales del admin no sirven (401 CREDENCIALES_INVALIDAS) …` (código 3) → revisar
  `VALIDACION_ADMIN_*` (paso 1) o el secreto.

En `local` (sin teléfono, API ni AWS): `uv run --group ops python src/ops/validate41.py --entorno local` da código 0 con
`[PASA]` en P1, C1a, C2a y C3a, `[OMITIDA] solo en dev …` en C1b, C3b y C2b y la manual C2c (comprobado el 2026-10-27 en
el worktree de FE-4.1, sobre `97791a0` con los cambios sin commit: C1a 11/11, C2a 5/5, C3a 15/15). Con `--solo
C1a,C2a,C3a` en `dev`, P2–P6 quedan «no evaluada» y no se usa el teléfono ni el backend. Con `--solo C3b` o `--solo C2b`
se repite solo ese paso (crea los dos videos igual y los borra al final).

Con el validador en `dev` con código 0 sobre un commit de `main` sin `-dirty`, la fila FE-4.1 de PLAN §3 pasa a «Hecho» y
se quitan de ARCHITECTURE §4.10, §5.5 y §5.11 los «sin comprobar» que la ejecución confirme.
