# Validación 1-1 — FE-1.1 Cliente HTTP, conexión real y CI

| Campo | Valor |
|---|---|
| Lote | `FE-1.1` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate11.py` |
| Entornos | `dev` con dispositivo físico (cierra el lote); `local` (sin teléfono: C2 y C4a) |
| Criterios | Automáticos: C1 (C1a), C2, C4 (C4a, C4b) · Manuales: C1 (C1b), C3 |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta
(dónde corren, variables, `comun.py`): `ARCHITECTURE.md` §5.11. Piezas que se comprueban: `ARCHITECTURE.md` §5.10.

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla. P1 y P2 son de la máquina (código 3); P3 y P4, de otros
lotes (código 2, lote `Bloqueado`). En `local` solo se evalúa P1.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Gradle y un JDK que lo ejecute | `<VALIDACION_GRADLE> --version` termina con 0 (detalle: versión de Gradle y JVM). Si no → 3 |
| P2 | Dispositivo físico conectado (solo `dev`) | `adb devices` muestra uno en estado `device` (el de `ANDROID_SERIAL` si hay varios) y `adb shell getprop ro.kernel.qemu` no es `1`. Si no → 3 |
| P3 | `INF-1.4` en «Hecho»: el borde HTTPS responde (solo `dev`) | URL = `terraform output -raw api_base_url` + `/v1` (sin Terraform, `VALIDACION_API_URL`; sin ninguna de las dos → 3; que no sea `https://…/v1` → 3). `GET <URL>/health` da alguna respuesta HTTP (no error de DNS, TLS, conexión ni tiempo agotado). Si no → 2 |
| P4 | `BE-1.1` en «Hecho»: salud del backend desplegada (solo `dev`) | `GET <URL>/health` responde 200 con `"estado": "ok"`. Si no → 2 |

## 2. Comprobaciones automáticas

En este orden. En `local`, C1a y C4b quedan `omitida` («solo en dev»).

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | `<VALIDACION_GRADLE> installDebug` (instala el APK de depuración y **conserva los datos**); lee la hora del teléfono (`adb shell date`); `am force-stop` y `am start -W -n com.example.myapplication/.MainActivity`; durante 60 s, cada 3 s, lee `files/logs/app.log` con `run-as` y busca la línea `I/Api … GET /v1/health -> <código> (<n> ms) rid=<uuid>` (formato de `RequestIdInterceptor`, ARCHITECTURE §5.10) con hora ≥ la del arranque | Aparece una con `-> 200`: el teléfono llegó a `dev` por la URL de `ApiConfig.kt` y el `X-Request-Id` quedó en `AppLog` (HU-22). El detalle trae el `rid` |
| C2 | Borra los XML anteriores de las dos clases y ejecuta `<VALIDACION_GRADLE> testDebugUnitTest --tests *.MapeoErroresApiTest --tests *.MapeoDatosApiTest`; lee `app/build/test-results/testDebugUnitTest/TEST-*.<clase>.xml` | Gradle sale con 0 y cada clase ejecutó ≥ 1 caso sin fallos ni errores (hoy 14 y 13). Que cubren las dos tablas de §5.10 fila por fila lo confirma la revisión del PR (cada prueba lleva el número de fila en un comentario) |
| C4a | Lee `ApiConfig.BASE_URL` del código (`const val API_BASE_URL = "…"` y `const val BASE_URL = "$API_BASE_URL/v1"`) y la compara con `terraform output -raw api_base_url` + `/v1` (infra §5.2; sin Terraform, con `VALIDACION_API_URL`) | Las dos coinciden sin barra final y son `https://…/v1` |
| C4b | `GET <ApiConfig.BASE_URL>/health` desde la máquina | Responde 200 |

## 3. Comprobaciones manuales

| ID | Qué hace la persona | Evidencia en el PR |
|---|---|---|
| C1b | Con la app que C1a dejó abierta en Inicio y el teléfono con Wi-Fi o datos: mira la barra inferior (punto verde y «Conectado»). Activa el modo avión y espera 20 s (el sondeo es cada 15 s y cada intento dura como mucho 5 s; ARCHITECTURE §5.5, «Inicio»). Desactívalo y espera otros 20 s | Video corto o tres capturas de la barra inferior de Inicio: «Conectado», «Sin conexión» con el modo avión visible y de nuevo «Conectado» |
| C3 | En el PR que trae FE-1.1 (debe tocar `FRONTEND_KOTLIN/project/**` o `.github/workflows/frontend.yml`, si no `frontend.yml` no corre), los dos checks de `frontend.yml`, **`compilar y pruebas unitarias`** y **`validadores`**, en verde sobre el último commit del PR | Enlace a la ejecución de `frontend.yml` en la descripción del PR (pasos en §5, «C3») |

## 4. Datos de prueba y limpieza

No crea nada en el backend: solo `GET /v1/health`. En el teléfono, `installDebug` conserva los datos de la app
(recorridos, calibración, `app.log`) y no se usa `pm clear`; `am force-stop` cierra la app si estaba abierta (una
recolección en curso queda guardada en disco, ADR-FE-07, y se puede descartar o retomar después). Lee `app.log` sin
modificarlo. No deja restos: no hay nada que limpiar de ejecuciones anteriores.

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate11.py --entorno dev
```

**Variables** (detalle en `ARCHITECTURE.md` §5.11). En la máquina del equipo el validador corre en WSL y usa el
Gradle y el `adb` de Windows (ARCHITECTURE §4.1):

| Variable | Valor en WSL | Obligatoria |
|---|---|---|
| `VALIDACION_GRADLE` | `cmd.exe /c .\gradlew.bat` | Sí en WSL (WSL no tiene JDK ni SDK) |
| `JAVA_HOME` | `C:\Users\frank\.jdks\jbr-21.0.11` (el JBR 21; el de Android Studio es Java 25 y Gradle 8.7 no lo admite) | Sí en WSL |
| `WSLENV` | `JAVA_HOME:ANDROID_SERIAL` (pasa esas dos a los procesos de Windows) | Sí en WSL |
| `VALIDACION_ADB` | `/mnt/c/Users/frank/AppData/Local/Android/Sdk/platform-tools/adb.exe` | Sí en WSL, en `dev` |
| `AWS_PROFILE` | `campus-admin` (solo para `terraform output`, que lee el estado) | Sí, salvo que se use `VALIDACION_API_URL` |
| `VALIDACION_API_URL` | No hace falta: solo se usa si `terraform output` falla | No |
| `ANDROID_SERIAL` | Solo si hay varios dispositivos | No |
| `UV_PROJECT_ENVIRONMENT` | `/root/.cache/uv-envs/fe-ops` (el `.venv` fuera de `/mnt/c`, más rápido) | No |

Herramientas: `uv`, `terraform` con `terraform init` hecho en `INFRASTRUCTURA_TERRAFORM/project/envs/dev`, y en
Windows el JBR 21 y el Android SDK. Duración aproximada en `dev`: 3–6 min (Gradle) más 2 de la comprobación manual. El
informe queda en `project/.validacion/FE-1.1-<AAAAMMDD-HHMMSS>.json` (hora UTC) o en `--informe RUTA`.

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
   Esperado: `All checks passed!`, `4 files already formatted` y `29 passed`.
3. Compilación y pruebas unitarias de la app:
   ```bash
   cmd.exe /c '.\gradlew.bat' --console=plain testDebugUnitTest assembleDebug
   ```
   Esperado: `BUILD SUCCESSFUL`. Si dice `Unable to delete directory '…\app\build\…'`, borrar `app/build`
   (`rm -rf app/build`) y repetir (ARCHITECTURE §4.1, «Trampas»).
4. Teléfono: conectado por USB a Windows, con la depuración USB autorizada, desbloqueado y con Wi-Fi o datos:
   ```bash
   $VALIDACION_ADB devices
   ```
   Esperado: una línea `<serial>	device` (no `unauthorized` ni `offline`). Si es la primera vez que se instala la
   app en ese teléfono, aceptar el diálogo de permisos de Inicio cuando C1a la abra (si no, Inicio no arranca su
   sondeo y C1a falla a los 60 s).
5. Que `dev` responde:
   ```bash
   curl -s "$(terraform -chdir=../../INFRASTRUCTURA_TERRAFORM/project/envs/dev output -raw api_base_url)/v1/health"
   ```
   Esperado: `{"estado":"ok","version":"0.1.0","commit":"<SHA corto>"}`.

**Ejecución.**

```bash
uv run --group ops python src/ops/validate11.py --entorno dev
```

Esperado (código 0):

```
[PASA] P1 Gradle 8.7, JVM 21.0.11 (JetBrains s.r.o. 21.0.11+1-b1163.116)
[PASA] P2 <modelo> (Android <versión>, serial <serial>)
[PASA] P3 terraform output api_base_url: HTTPS responde (HTTP 200)
[PASA] P4 200 estado=ok, backend 0.1.0 commit <SHA corto>
[PASA] C1a el teléfono llegó a GET /v1/health -> 200 (rid=<uuid>)
[PASA] C2 MapeoErroresApiTest 14/14, MapeoDatosApiTest 13/13
[PASA] C4a ApiConfig.BASE_URL = https://fuzq99kddb.execute-api.us-east-1.amazonaws.com/v1 (= terraform output api_base_url)
[PASA] C4b GET <ApiConfig>/health -> 200 en <n> ms
[MANUAL] C1b Con la app abierta en Inicio (la dejó así C1a), mira la barra inferior: …
[MANUAL] C3 En el PR que trae FE-1.1, el check «frontend / compilar y pruebas unitarias» …
Resultado: pasa (código 0)
```

Luego, la comprobación manual **C1b** (§3) con la app que quedó abierta en el teléfono.

En `local` (sin teléfono): `uv run --group ops python src/ops/validate11.py --entorno local` da código 0 con `[PASA]`
en P1, C2 y C4a y `[OMITIDA]` en C1a y C4b (comprobado el 2026-10-25). Sin teléfono en `dev`, P2 falla y el código es
3 (`adb devices no muestra ningún dispositivo`).

**C3 (lo coordina quien abre el PR).**

1. El PR debe tocar `FRONTEND_KOTLIN/project/**` o `.github/workflows/frontend.yml` (los de FE-1.1 tocan los dos).
2. Tras subir la rama, buscar la ejecución del PR:
   ```bash
   gh run list --workflow frontend.yml --branch <rama del PR> --limit 1 --json conclusion,headSha,url
   ```
   Esperado: `"conclusion": "success"`, `"headSha"` igual a `git rev-parse <rama del PR>` y la URL de la ejecución.
   Mientras corre, `conclusion` sale vacío; `gh run watch <id>` espera a que termine.
3. En la ejecución, los jobs `compilar y pruebas unitarias` y `validadores` en verde; el resumen del primero trae la
   tabla de casos por clase (`MapeoErroresApiTest` 14, `MapeoDatosApiTest` 13, `ClienteApiTest` 7, `ExampleUnitTest` 1).
4. Pegar la URL en la descripción del PR.

Si `compilar y pruebas unitarias` falla en el runner y en local pasa, lo más probable es el SDK del runner (plataforma
`android-35` o build-tools ausentes) o la JVM: el log del paso `./gradlew …` lo dice (`--stacktrace`). Con eso, y con
el validador en `dev` con código 0 sobre un commit de `main` sin `-dirty`, la fila FE-1.1 de PLAN §3 pasa a «Hecho».
