# Validación 3-3 — FE-3.3 Alertas de administración sincronizadas (7.8–7.10)

| Campo | Valor |
|---|---|
| Lote | `FE-3.3` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate33.py` |
| Entornos | `local` (C1a, C2a y C3a, pruebas en la JVM; sin teléfono ni backend) y `dev` (además C1b, C2b y C3b, con dispositivo físico y la API de `dev`) |
| Criterios | Automáticos: C1 (C1a, C1b), C2 (C2a, C2b), C3 (C3a, C3b) · Manual: C3c (evidencia) |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.11 (`validate33.py`, constantes, piezas y trampas). Lo construido: `ARCHITECTURE.md` §4.9.
Contratos que consume: `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §4.11 («Para la app»), §5.3 (`GET /v1/alerts`) y §5.5
(«Alertas: `/v1/admin/alerts` (BE-3.3)»).

## 1. Precondiciones

Se evalúan en este orden y el script se detiene en la primera que falla (las siguientes quedan «no evaluada»). En
`local` solo P1. En `dev`, P2–P6 solo si alguna de C1b, C2b o C3b está incluida.

| ID | Qué debe cumplirse | Cómo lo comprueba el script | Código si falla |
|---|---|---|---|
| P1 | Gradle | `./gradlew --version` con salida 0 | 3 |
| P2 | Dispositivo físico | `adb devices` con uno en estado `device` (el de `ANDROID_SERIAL` si hay varios) y `ro.kernel.qemu` distinto de `1` | 3 |
| P3 | API de `dev` (FE-1.1, INF-1.4, BE-1.1) | URL de `terraform output api_base_url` (o `VALIDACION_API_URL`) igual a `ApiConfig.BASE_URL`; `GET /v1/health` → `200` con `estado: ok` | 2 (3 sin URL) |
| P4 | Login de admin | `POST /v1/auth/login` con las credenciales de admin → `200` con rol `admin` | 3 con `401` o rol distinto; 2 si no |
| P5 | `FE-1.2` en «Hecho» | Fila de `FE-1.2` en `PLAN.md` §3 = `Hecho` | 2 |
| P6 | `BE-3.3` en «Hecho» | Fila en `BACKEND_FASTAPI/docs/PLAN.md` §3 = `Hecho`; `GET /v1/admin/alerts` con token → `200` con `items`; y una **sonda sin rastro**: `POST /v1/admin/alerts/sincronizar` con `{"cambios": [{"op": "eliminar", "id": "<UUID nuevo>"}]}` → `200` con `estado: ok` (un id desconocido no deja *tombstone* ni auditoría, backend §4.11; con `{"cambios": []}` el backend da `422`) | 2 |

## 2. Comprobaciones automáticas

C1a, C2a y C3a corren juntas en una sola ejecución de Gradle (`testDebugUnitTest --tests …`); si una falla, C1b, C2b y
C3b quedan `omitida` («no se hace: falló …»). Antes de C1b el script instala el APK (`installDebug`, sin `pm clear`),
concede los permisos de Inicio, borra los restos de una ejecución anterior (§4) y entra al Panel con el admin por la
interfaz. C1b, C2b y C3b tienen un **paso guiado** cada una: el script escribe la instrucción y espera Enter.

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | `RemoteAlertasRepositoryTest` y `AlmacenAlertasTest` en la JVM | Al menos 8 y 3 casos, sin fallos ni omitidos (hoy 11 y 3) |
| C1b | Anota los recorridos de `files/recoleccion` y la hora del teléfono. **Paso guiado:** grabar en 7.4 el recorrido `validacion-3-3` («Cada 3 s», quieto), «Agregar alerta aquí» con mensaje `validacion-3-3-c1`, «Finalizar video» → «Guardar y subir después»; en 7.8 ver el marcador y pulsar «Guardar / Sincronizar». Lee el recorrido nuevo, `files/logs/app.log` y `GET /v1/admin/alerts?q=validacion-3-3-c1` | Hay un recorrido nuevo `validacion-3-3` con fotos, `app.log` tiene desde esa hora una línea `I/Alertas Alertas sincronizadas: …` y en el backend hay exactamente 1 alerta `validacion-3-3-c1`, activa y a ≤ 30 m de la primera foto del recorrido |
| C2a | `ReglasAlertasTest` en la JVM | Al menos 6 casos, sin fallos ni omitidos (hoy 8) |
| C2b | Toma `generado_en` de `GET /v1/alerts` y la hora del teléfono. **Paso guiado:** en 7.8 «Nueva alerta» con mensaje `validacion-3-3-c2`, eliminarla y pulsar «Guardar / Sincronizar». Lee `app.log`, `GET /v1/admin/alerts?q=validacion-3-3-c2` y `GET /v1/alerts?desde=<generado_en>` | `app.log` no tiene desde esa hora líneas de nivel `E` ni tag `CRASH`; la última sincronización dice `E enviadas, E aplicadas, 0 rechazadas`; `validacion-3-3-c2` no está en la lista de administración ni entre las `alertas` de las diferencias, y las `eliminadas` no traen ids que no borró el propio validador (un *tombstone* querría decir que la app envió `upsert` + `eliminar`) |
| C3a | `FormularioAlertaTest` en la JVM | Al menos 7 casos, sin fallos ni omitidos (hoy 9) |
| C3b | Crea `validacion-3-3-c3` por la API (`sincronizar` con un `upsert`). **Paso guiado:** en 7.8 «Ver lista». El script toca el buscador de 7.10, escribe `validacion-3-3`, espera las filas, toca la de c3, espera «Editar alerta» y pulsa Atrás | Se ven las filas de `validacion-3-3-c3` (y de `validacion-3-3-c1` si C1b la creó) con el `content-desc` de `descripcionFilaAlerta`; tocar c3 abre «Editar alerta» con ese mensaje en el campo; tras cerrar sin guardar, c3 sigue en `version` 1 en el backend |

## 3. Comprobaciones manuales

| ID | Qué hace la persona | Evidencia en el PR |
|---|---|---|
| C3c | Durante C3b, capturas (por `adb exec-out screencap -p`) de 7.10 con «validacion-3-3» en el buscador y del formulario 7.9 abierto con `validacion-3-3-c3` | Capturas de 7.10 con `validacion-3-3-c1` y `validacion-3-3-c3` (creada solo en el backend) y del formulario 7.9 abierto con el mensaje de `validacion-3-3-c3`, sin datos privados |

## 4. Datos de prueba y limpieza

La persona crea `validacion-3-3-c1` (en 7.4) y `validacion-3-3-c2` (en 7.8, y la borra antes de sincronizar); el script
crea `validacion-3-3-c3` con `POST /v1/admin/alerts/sincronizar` (un `upsert`; `comun.py` no tiene ayuda para `PUT`).
Al empezar (una vez) y al terminar (también si algo falló), el script borra con `DELETE /v1/admin/alerts/{id}` las
alertas de `GET /v1/admin/alerts?q=validacion-3-3` cuyo mensaje normalizado es **exactamente** uno de los tres (una que
solo contiene el prefijo se queda) y borra del teléfono (`am force-stop` + `run-as … rm -rf files/recoleccion/<carpeta>`)
los recorridos `validacion-3-3` que el backend no conoce (sin `remote_video_id` y `sin_subir`). Cada `DELETE` deja un
*tombstone* que el backend purga a los 90 días. Al final cierra la app (`am force-stop`). Nunca usa `pm clear`.

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate33.py --entorno dev
```

Sin argumentos propios. Los tres pasos guiados leen la entrada estándar: hay que correrlo en una terminal interactiva
(sin redirigir la entrada, p. ej. `< /dev/null`) o con la entrada en una FIFO y los pasos hechos por `adb` (`input
tap/text`, `uiautomator`), como el cierre de FE-2.2 ([`validation-2-2`](./validation-2-2.md) §5).

**Variables** (detalle en `ARCHITECTURE.md` §5.11). En la máquina del equipo el validador corre en WSL y usa el Gradle y
el `adb` de Windows (ARCHITECTURE §4.1):

| Variable | Valor en WSL | Obligatoria |
|---|---|---|
| `VALIDACION_GRADLE` | `cmd.exe /c .\gradlew.bat` | Sí en WSL |
| `JAVA_HOME` | `C:\Users\frank\.jdks\jbr-21.0.11` | Sí en WSL |
| `WSLENV` | `JAVA_HOME:ANDROID_SERIAL` | Sí en WSL |
| `VALIDACION_ADB` | `/mnt/c/Users/frank/AppData/Local/Android/Sdk/platform-tools/adb.exe` | Sí en WSL, en `dev` |
| `AWS_PROFILE` | `campus-admin` (`terraform output` y, sin `VALIDACION_ADMIN_*`, el secreto del admin) | Sí en `dev`, salvo que estén `VALIDACION_API_URL` y las dos `VALIDACION_ADMIN_*` |
| `VALIDACION_ADMIN_CORREO`, `VALIDACION_ADMIN_PASSWORD` | Las del admin de `dev`, leídas sin eco; sin ellas, el secreto `campus-locator/dev/admin-inicial` | No |
| `ANDROID_SERIAL` | Solo si hay varios dispositivos | No |
| `UV_PROJECT_ENVIRONMENT` | `/root/.cache/uv-envs/fe-ops` | No |

Duración aproximada en `dev`: 12–18 min (Gradle 1–3 min; `installDebug` 1–2 min; login ~1 min; los tres pasos guiados,
8–12 min, con la grabación corta de C1b). No necesita `embedding`. Crea y borra alertas en `dev`: no correrlo a la vez que
otro admin que borre alertas (C2b vería sus *tombstones*) ni que `validate22.py` (cuenta `alertas_activas`). El informe
queda en `project/.validacion/FE-3.3-<AAAAMMDD-HHMMSS>.json` (hora UTC) o en `--informe RUTA`.

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
   Esperado: `All checks passed!`, `22 files already formatted` y `253 passed`.
3. Compilación y pruebas unitarias de la app:
   ```bash
   cmd.exe /c '.\gradlew.bat' --console=plain testDebugUnitTest assembleDebug
   ```
   Esperado: `BUILD SUCCESSFUL` (303 casos, sin fallos).
4. Copia de trabajo limpia (si no, el informe sale con `-dirty`):
   ```bash
   git -c core.autocrlf=input status --short -- .
   ```
   Esperado: sin salida.
5. Teléfono: conectado por USB, depuración autorizada, desbloqueado con la pantalla encendida, con Wi-Fi o datos,
   TalkBack desactivado, la cámara utilizable (C1b graba) y el reconocimiento de voz disponible si se quiere probar el
   dictado (no lo exige el script):
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
7. Que `dev` responde y que BE-3.3 está cerrado:
   ```bash
   curl -s "$(terraform -chdir=../../INFRASTRUCTURA_TERRAFORM/project/envs/dev output -raw api_base_url)/v1/health"; echo
   grep '^| BE-3.3 |' ../../BACKEND_FASTAPI/docs/PLAN.md | tail -1
   ```
   Esperado: `{"estado":"ok",…}` y una fila `| BE-3.3 | 3 | Hecho | …` (si no, código 2 en P6).

**Ejecución.** En una terminal interactiva (o con una FIFO), con el teléfono a mano. El validador instala la app, entra
al Panel con el admin y se detiene en cada **paso guiado** (líneas `· PASO GUIADO — …` por stderr):

1. **Paso guiado 1 (C1b)**, desde el Panel: «Recolector de imágenes» (7.3) → punto de inicio y rumbo → nombre
   **`validacion-3-3`** → «Confirmar y comenzar». En 7.4: intervalo «Cada 3 s», quieto, al menos 2 fotos → «Agregar
   alerta aquí» → mensaje **`validacion-3-3-c1`** → «Guardar» → «Finalizar video» → en 7.5 **«Guardar y subir después»**
   (no «Subir y procesar»). En el Panel, «Mapa y alertas» (7.8): ver el marcador → **«Guardar / Sincronizar»** (sale
   «Sincronizado: …»). Pulsar **Enter**.
2. **Paso guiado 2 (C2b)**, en 7.8: «Nueva alerta» → tocar el mapa → mensaje **`validacion-3-3-c2`** → «Guardar» → tocar
   su marcador → «Eliminar» (confirmar) → **«Guardar / Sincronizar»** (sale «Sincronizado: …»). Pulsar **Enter**.
3. **Paso guiado 3 (C3b)**, en 7.8: **«Ver lista»** (se abre 7.10). No tocar nada más y pulsar **Enter** (el script
   escribe en el buscador, abre `validacion-3-3-c3` y la cierra). Para C3c, tomar las capturas mientras se ven la lista y
   el formulario (o repetir a mano la búsqueda antes de que termine: c3 se borra en la limpieza).

```bash
uv run --group ops python src/ops/validate33.py --entorno dev
```

Esperado (código 0; por stderr salen además líneas `· …` de progreso y la ruta del informe):

```
[PASA] P1 Gradle 8.7, JVM 21.0.11 (…)
[PASA] P2 23028RA60L (Android 14, SDK 34, serial <serial>)
[PASA] P3 ApiConfig = terraform output api_base_url; GET /v1/health -> 200
[PASA] P4 200: <correo>, rol admin
[PASA] P5 FE-1.2 Hecho
[PASA] P6 BE-3.3 Hecho; GET /v1/admin/alerts -> 200 (N); POST /v1/admin/alerts/sincronizar (sonda eliminar de un id desconocido) -> 200 ok
[PASA] C1a RemoteAlertasRepositoryTest 11/11, AlmacenAlertasTest 3/3 (mínimos 8, 3)
[PASA] C2a ReglasAlertasTest 8/8 (mínimos 6)
[PASA] C3a FormularioAlertaTest 9/9 (mínimos 7)
[PASA] C1b «validacion-3-3-c1» creada en 7.4 durante rec_NNNN (F fotos) está en GET /v1/admin/alerts, activa, a D m de la primera foto (máximo 30); app.log: E enviadas, E aplicadas, 0 rechazadas
[PASA] C2b crear y borrar «validacion-3-3-c2» antes de sincronizar: app.log sin errores (1 enviadas = 1 aplicadas, 0 rechazadas); no está en GET /v1/admin/alerts ni en GET /v1/alerts?desde=<generado_en>, sin borradas ajenas
[PASA] C3b 7.10 con «validacion-3-3» en el buscador muestra validacion-3-3-c1, validacion-3-3-c3; tocar «validacion-3-3-c3» (creada solo en el backend) abre «Editar alerta» con su mensaje; cerrada sin guardar, sigue en la versión 1
[MANUAL] C3c Evidencia para el PR (validation-3-3 §3): …
Resultado: pasa (código 0)
```

En `local` (`--entorno local`): P1, C1a, C2a y C3a `[PASA]`, C1b, C2b y C3b `[OMITIDA] solo en dev …`, la manual C3c y
`Resultado: pasa (código 0)` (comprobado el 2026-10-26 en el worktree de FE-3.3 y de nuevo el 2026-10-27, rebasado
sobre `main` `3b3b30c`: C1a 11/11 y 3/3, C2a 8/8, C3a 9/9).

Casos previstos: `--solo C1a,C2a,C3a` en `dev` no usa teléfono ni backend (P2–P6 «no evaluada»); una prueba de la JVM
que falla omite las del teléfono (código 1); fin de la entrada (EOF) en un paso guiado da código 3 y la limpieza corre
igual; C2b falla si la app envía `upsert` + `eliminar` (*tombstone*), si `app.log` tiene un error o si no sincronizó;
C1b falla si la alerta está a más de 30 m de la primera foto o si no hay línea de sincronización; C3b falla si 7.10 no
trae la alerta del backend.
