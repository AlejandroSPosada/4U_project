# Validación 1-2 — FE-1.2 Login contra el backend

| Campo | Valor |
|---|---|
| Lote | `FE-1.2` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate12.py` |
| Entornos | `dev` con dispositivo físico (cierra el lote); `local` (sin teléfono: C3 y C4, pruebas en la JVM) |
| Criterios | Automáticos: C1, C2, C3, C4 · Manuales: ninguno |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta
(dónde corren, variables, `comun.py`, trampas de MIUI y de uiautomator): `ARCHITECTURE.md` §5.11. Piezas que se
comprueban: `ARCHITECTURE.md` §5.3 (sesión) y §5.10 (cliente HTTP).

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla. P1, P2 y P3 son de la máquina (código 3); P4 y P5, de
otros lotes (código 2, lote `Bloqueado`), salvo las credenciales del admin (código 3). En `local` solo se evalúa P1.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Gradle y un JDK que lo ejecute | `<VALIDACION_GRADLE> --version` termina con 0 (detalle: versión de Gradle y JVM). Si no → 3 |
| P2 | Dispositivo físico conectado (solo `dev`) | `adb devices` muestra uno en estado `device` (el de `ANDROID_SERIAL` si hay varios) y `adb shell getprop ro.kernel.qemu` no es `1`; lee modelo, versión de Android y SDK. Si no → 3 |
| P3 | Acceso a AWS para crear la cuenta `user` de prueba (solo `dev` y si C2 está incluida; con `--solo` sin C2 queda «no evaluada») | `aws sts get-caller-identity` (perfil de `AWS_PROFILE`) da la cuenta `648617469176` (si no, o sin credenciales → 3) y `terraform output -json` de `INFRASTRUCTURA_TERRAFORM/project/envs/dev` trae `ecs_cluster`, `familias_tarea.migrate`, `subredes_tareas` y `sg_migrate` (sin Terraform, `init` o credenciales → 3; falta un output → 2) |
| P4 | `FE-1.1` en «Hecho»: la app usa la API de `dev` (solo `dev`) | La fila de `FE-1.1` en `PLAN.md` §3 dice `Hecho`; `ApiConfig.BASE_URL` (leído de `ApiConfig.kt`) es igual a la URL vigente = `terraform output -raw api_base_url` + `/v1` (sin Terraform, `VALIDACION_API_URL`; sin ninguna de las dos → 3); `GET <URL>/health` responde 200 con `"estado": "ok"`. Si no → 2 |
| P5 | `BE-1.3` en «Hecho»: login con JWT (solo `dev`) | Credenciales del admin: `VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` si están las dos; si no, las claves `correo` y `password` del secreto `campus-locator/dev/admin-inicial` (como `credenciales_admin` del backend, backend §5.11; sin permiso → 3, secreto inexistente → 2). `POST <URL>/auth/login` responde 200 con `token`, `expira_en`, `usuario` y `usuario.rol = "admin"`; guarda `usuario.nombre` para C1. `401` o rol distinto de `admin` → 3 (credenciales que no sirven); `404`, `5xx` o sin respuesta → 2. Un `429` de API Gateway se reintenta tras 1, 2 y 4 s |

## 2. Comprobaciones automáticas

En este orden. En `local`, C1 y C2 quedan `omitida` («solo en dev»).

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1 | La primera vez (C1 o C2): `<VALIDACION_GRADLE> installDebug` (instala el APK de depuración y **conserva los datos**) y `adb shell pm grant com.example.myapplication` de `CAMERA`, `RECORD_AUDIO` y, con SDK ≥ 29, `ACTIVITY_RECOGNITION` (`Permisos.INICIALES`: así Inicio no muestra el diálogo de permisos). Luego `am force-stop` y `am start -W -n com.example.myapplication/.MainActivity`; espera hasta 30 s a «Acceso administrador» en Inicio y lo toca (`input tap`); espera Login (dos campos e «Iniciar sesión»); toca el primer campo y escribe el correo del admin con `adb shell input text`, toca el segundo y escribe la contraseña (escapados: espacio → `%s` y los caracteres que interpreta el `sh` del teléfono con `\`; nunca se imprimen); toca «Iniciar sesión» (si el teclado lo tapa, pulsa Atrás solo si el teclado está abierto). Lee la pantalla con `adb exec-out uiautomator dump` cada ~1 s (el XML se borra del teléfono en la misma orden) | En ≤ 15 s desde el toque aparecen «Hola, <primer nombre de `usuario.nombre` de P5>» y «Cerrar sesión» del Panel (7.2; para ver «Cerrar sesión» baja el Panel hasta 4 veces con `input swipe`). Si aparece «Credenciales inválidas», «Sin conexión», «Algo salió mal» o «Sin permisos», falla en el acto con ese texto. Si el teléfono rechaza `pm grant` o `input` con `SecurityException` (MIUI/HyperOS sin «Depuración USB (Configuración de seguridad)»), o `installDebug` da `INSTALL_FAILED_USER_RESTRICTED` («Instalar vía USB»), el estado es `error` (código 3) con la solución en el detalle |
| C2 | Crea o reactiva la cuenta `validacion+user@campus.edu.co` (§4; su desactivación queda registrada **antes** de lanzar la tarea). Repite lo de C1 desde `am force-stop` con esa cuenta y su contraseña | En ≤ 15 s aparece el banner «Sin permisos» (7.1) y no aparece «Cerrar sesión». Si aparecen «Cerrar sesión» o «Hola,», falla («la cuenta user abrió el Panel»); con «Credenciales inválidas», «Sin conexión» o «Algo salió mal», falla con ese texto. Si `crear-usuario` no termina con 0, falla con su código y los eventos del log (`usuario_rechazado`, `comando_fallido`…) |
| C3 | Borra el XML anterior y ejecuta `<VALIDACION_GRADLE> testDebugUnitTest --tests '*.SesionVencidaTest'` (en la misma ejecución que C4 si las dos están incluidas); lee `app/build/test-results/testDebugUnitTest/TEST-*.SesionVencidaTest.xml`. La prueba usa MockWebServer: `401 TOKEN_EXPIRADO`, `TOKEN_INVALIDO` y `NO_AUTENTICADO` en `/v1/admin/stats`, `/v1/collect/videos` y `/v1/admin/videos/{id}`, y una sesión con `expira_en` pasado | ≥ 4 casos y 0 fallos ni errores (hoy 9). Que cada caso comprueba `SessionManager.cerrarSesion()` (la sesión borrada y una llamada a `borrar()` del almacén), el evento `onSinSesion` y lo que recibió el servidor —y que la sesión vencida no llama al servidor (`requestCount == 0`)— lo confirma la revisión del PR |
| C4 | Igual con `--tests '*.RemoteAuthRepositoryTest'` | ≥ 3 casos y 0 fallos ni errores (hoy 6). Que cubren 200, 401 y error de red (`SocketPolicy.DISCONNECT_AT_START`) lo confirma la revisión del PR |

## 3. Comprobaciones manuales

Ninguna: todos los criterios son automáticos.

## 4. Datos de prueba y limpieza

Crea o reactiva la cuenta `validacion+user@campus.edu.co` (rol `user`, nombre `validacion-user`) con una tarea suelta
de la última revisión de `campus-locator-dev-migrate` (Fargate, `subredes_tareas` + `sg_migrate` con IP pública) y el
comando `python -m app.cli crear-usuario --correo validacion+user@campus.edu.co --nombre validacion-user --rol user`;
la contraseña es aleatoria (`validacion-pw-<uuid>`), va en `CREAR_USUARIO_PASSWORD` por un archivo temporal (no en la
línea de comandos) y nunca se imprime (queda visible en `describe-tasks` para quien tenga acceso a la cuenta: es solo
de prueba). Al terminar, también si algo falló, la desactiva con `desactivar-usuario --correo
validacion+user@campus.edu.co` en otra tarea suelta (si no llegó a crearla, «no existe» no es un fallo). Si una
ejecución anterior la dejó, `crear-usuario` la reactiva con una contraseña nueva (backend §5.9 y §5.11). Con
`--sin-limpieza` la cuenta queda activa hasta la siguiente ejecución completa.

En el teléfono: `installDebug` conserva los datos de la app (recorridos, calibración, `app.log`) y no se usa
`pm clear`; los permisos concedidos con `pm grant` son los mismos que pide Inicio y se quedan. Hace `am force-stop`
entre C1 y C2 y al final: `MyApp` borra la sesión en cada arranque en frío (ARCHITECTURE §5.3), así que no queda
ninguna abierta. El volcado de pantalla (`/data/local/tmp/validacion-ui.xml`) se borra en la misma orden que lo crea.
En el backend, cada inicio de sesión deja su fila en `auditoria` (es registro y se conserva).

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate12.py --entorno dev
```

**Variables** (detalle en `ARCHITECTURE.md` §5.11). En la máquina del equipo el validador corre en WSL y usa el
Gradle y el `adb` de Windows (ARCHITECTURE §4.1) y la CLI `aws` de WSL:

| Variable | Valor en WSL | Obligatoria |
|---|---|---|
| `VALIDACION_GRADLE` | `cmd.exe /c .\gradlew.bat` | Sí en WSL (WSL no tiene JDK ni SDK) |
| `JAVA_HOME` | `C:\Users\frank\.jdks\jbr-21.0.11` (el JBR 21; el de Android Studio es Java 25 y Gradle 8.7 no lo admite) | Sí en WSL |
| `WSLENV` | `JAVA_HOME:ANDROID_SERIAL` (pasa esas dos a los procesos de Windows) | Sí en WSL |
| `VALIDACION_ADB` | `/mnt/c/Users/frank/AppData/Local/Android/Sdk/platform-tools/adb.exe` | Sí en WSL, en `dev` |
| `AWS_PROFILE` | `campus-admin` (`terraform output`, `aws sts`, el secreto del admin y las tareas sueltas de `migrate`) | Sí en `dev` |
| `VALIDACION_ADMIN_CORREO`, `VALIDACION_ADMIN_PASSWORD` | No hacen falta: sin ellas se usa el secreto `campus-locator/dev/admin-inicial` | No |
| `VALIDACION_API_URL` | No hace falta: solo se usa si `terraform output` falla | No |
| `ANDROID_SERIAL` | Solo si hay varios dispositivos | No |
| `UV_PROJECT_ENVIRONMENT` | `/root/.cache/uv-envs/fe-ops` (el `.venv` fuera de `/mnt/c`, más rápido) | No |

Herramientas: `uv`, `terraform` con `terraform init` hecho en `INFRASTRUCTURA_TERRAFORM/project/envs/dev`, la CLI
`aws` v2 en WSL y, en Windows, el JBR 21 y el Android SDK. Duración aproximada en `dev`: 8–10 min (Gradle 2–4 min; cada
tarea suelta de `migrate`, `crear-usuario` y `desactivar-usuario`, 1–2 min; cada login en el teléfono, menos de un
minuto). No necesita `embedding` (sin hora límite). El informe queda en `project/.validacion/FE-1.2-<AAAAMMDD-HHMMSS>.json`
(hora UTC) o en `--informe RUTA`.

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
   Esperado: `All checks passed!`, `7 files already formatted` y `73 passed`.
3. Compilación y pruebas unitarias de la app:
   ```bash
   cmd.exe /c '.\gradlew.bat' --console=plain testDebugUnitTest assembleDebug
   ```
   Esperado: `BUILD SUCCESSFUL`. Si dice `Unable to delete directory '…\app\build\…'`, borrar `app/build`
   (`rm -rf app/build`) y repetir (ARCHITECTURE §4.1, «Trampas»).
4. Teléfono: conectado por USB a Windows, con la depuración USB autorizada, **desbloqueado, con la pantalla encendida**
   (uiautomator no lee una pantalla apagada o bloqueada: conviene activar «Pantalla activa» en Opciones de
   desarrollador mientras carga) y con Wi-Fi o datos:
   ```bash
   $VALIDACION_ADB devices
   ```
   Esperado: una línea `<serial>	device` (no `unauthorized` ni `offline`).
5. Solo en Xiaomi (MIUI/HyperOS): en Ajustes → Opciones de desarrollador, activar **«Instalar vía USB»** (ya hecho en
   FE-1.1; si al instalar aparece un diálogo en el teléfono, aceptarlo) y **«Depuración USB (Configuración de
   seguridad)»** (sin ella `pm grant` e `input` fallan; con ella funcionan, comprobado en `dev` el 2026-10-25). **Sin
   comprobar:** si MIUI pide una cuenta Mi y SIM para activarla. Para comprobarlo:
   ```bash
   $VALIDACION_ADB shell input keyevent 0
   ```
   Esperado: sin salida (la tecla 0 no hace nada). Si sale una `java.lang.SecurityException` que menciona
   `INJECT_EVENTS`, falta «Depuración USB (Configuración de seguridad)» (el texto exacto de la excepción en el Xiaomi,
   sin comprobar).
6. Acceso a AWS:
   ```bash
   aws sts get-caller-identity --query Account --output text
   ```
   Esperado: `648617469176`.
7. Que `dev` responde:
   ```bash
   curl -s "$(terraform -chdir=../../INFRASTRUCTURA_TERRAFORM/project/envs/dev output -raw api_base_url)/v1/health"
   ```
   Esperado: `{"estado":"ok","version":"0.1.0","commit":"<SHA corto>"}`.

**Ejecución.** Durante la ejecución no tocar el teléfono: el validador abre la app, escribe y toca por su cuenta.

```bash
uv run --group ops python src/ops/validate12.py --entorno dev
```

Esperado (código 0; por stderr salen además líneas `· …` de progreso: las tareas sueltas, la limpieza y la ruta del
informe):

```
[PASA] P1 Gradle 8.7, JVM 21.0.11 (JetBrains s.r.o. 21.0.11+1-b1163.116)
[PASA] P2 23028RA60L (Android 14, SDK 34, serial <serial>)
[PASA] P3 cuenta 648617469176 (root); outputs para la tarea suelta de migrate
[PASA] P4 FE-1.1 Hecho; ApiConfig = terraform output api_base_url; GET /v1/health -> 200
[PASA] P5 200: admin@campus.edu.co, rol admin, expira_en <AAAA-MM-DDTHH:MM:SSZ>
[PASA] C1 Panel con «Hola, <primer nombre>» y «Cerrar sesión» a los <n> s del toque
[PASA] C2 «Sin permisos» a los <n> s, sin «Cerrar sesión»
[PASA] C3 SesionVencidaTest 9/9 (mínimo 4)
[PASA] C4 RemoteAuthRepositoryTest 6/6 (mínimo 3)
Resultado: pasa (código 0)
```

Al terminar, en stderr: `· limpieza: desactivar validacion+user@campus.edu.co` y `· limpieza: cerrar la app (am
force-stop)`; la app queda cerrada en el teléfono.

Si algo falla, el detalle dice qué se veía en la pantalla (sin campos de texto). Casos previstos:
- `[ERROR] C1 el teléfono no deja a adb conceder CAMERA (pm grant) (SecurityException): …` → paso 5 («Depuración USB
  (Configuración de seguridad)»). Código 3.
- `[ERROR] C1 installDebug: INSTALL_FAILED_USER_RESTRICTED …` → paso 5 («Instalar vía USB» y el diálogo). Código 3.
- `[FALLA] C1 en 30 s no apareció «Acceso administrador»; en pantalla: …` → pantalla bloqueada o apagada, o un diálogo
  del sistema encima de Inicio.
- `[FALLA] C1 la app mostró «Credenciales inválidas» en vez del Panel` → la contraseña no se escribió bien (algún
  carácter que `input text` no reproduce) o el secreto no corresponde al admin.
- `[FALLA] C1 no se ve «Iniciar sesión»; …` → el teclado tapa el botón y no se detectó (`dumpsys input_method`).

En `local` (sin teléfono): `uv run --group ops python src/ops/validate12.py --entorno local` da código 0 con `[PASA]`
en P1, C3 y C4 y `[OMITIDA]` en C1 y C2 (comprobado el 2026-10-25). Sin teléfono en `dev`, P2 falla y el código es 3
(`adb devices no muestra ningún dispositivo`).

Con el validador en `dev` con código 0 sobre un commit de `main` sin `-dirty`, la fila FE-1.2 de PLAN §3 pasa a
«Hecho».
