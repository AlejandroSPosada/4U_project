# Validación 3-6 — FE-3.6 Alertas públicas

| Campo | Valor |
|---|---|
| Lote | `FE-3.6` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate36.py` (sin escribir todavía) |
| Entornos | `dev` con dispositivo físico |
| Criterios | Automáticos: C1a, C1b, C3 · Manuales: C2, C4, C5 |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.11. Piezas que se comprueban: `ARCHITECTURE.md` §2.5 (alertas en el flujo público), §5.10
(«Alertas sin conexión»), §6.3 (alertas cercanas en el Resultado) y, para C5, §4.5 (entrada al mapa y hallazgos con
TalkBack 17), §5.2 («Segundo plano», ADR-FE-22) y §5.5 (Inicio y `MapaPublicoScreen`).

Lote fuera del núcleo (decisión del usuario del 2026-10-25: «No necesitamos las alertas por el momento»). Sus
comprobaciones vienen de `validation-3-1` (antes C2, C3 y C4 de FE-3.1) y la C4 es nueva, por las alertas cercanas de
6.3 que antes eran de FE-3.2. **C5 viene de FE-3.1** (decisión del usuario del 2026-10-26 al cerrarlo: «Si, por favor.
Cambialo y demos por hecho lo que llevamos.»): la parte con TalkBack de su C2c y el punto de inicio del mapa sin
tocarlo (PLAN §2.2, FE-3.6).

## 1. Precondiciones

Se evalúan en este orden y el script no sigue si una falla. P1, P2 y P3 son de la máquina (código 3); P4, P5 y P6, de
otros lotes (código 2, lote `Bloqueado`).

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Dispositivo físico y Gradle | `adb devices` con uno en estado `device` (el de `ANDROID_SERIAL` si hay varios), `ro.kernel.qemu` distinto de `1` y `./gradlew --version` con salida 0. Si no → 3 |
| P2 | Credenciales de admin para crear las alertas de prueba | `POST /v1/auth/login` con las credenciales de admin responde 200 (con `401`: código 3) |
| P3 | Acceso a AWS para encender `embedding` en C4 (solo si C4 está incluida) | `aws sts get-caller-identity` da la cuenta `648617469176` (perfil de `AWS_PROFILE`). Si no → 3 |
| P4 | `FE-3.1` en «Hecho»: lugares reales y entrada al mapa desde Inicio | Fila de `FE-3.1` en `PLAN.md` §3 = `Hecho` |
| P5 | `FE-3.2` en «Hecho»: Resultado (6.3) con el backend real | Fila de `FE-3.2` en `PLAN.md` §3 = `Hecho` |
| P6 | `BE-3.3` en «Hecho»: alertas del backend | Fila en `BACKEND_FASTAPI/docs/PLAN.md` §3 = `Hecho`; `GET /v1/alerts` responde 200 con `generado_en` y `completo = true`, y `GET /v1/admin/alerts` con token responde 200 |

## 2. Comprobaciones automáticas

Instala el APK con `./gradlew installDebug` (conserva los datos de la app). La «siguiente sincronización» se provoca
reiniciando la app (`am force-stop` y `am start -n com.example.myapplication/.MainActivity`) y esperando 20 s. La caché
se lee copiando la base de Room con `adb exec-out run-as com.example.myapplication cat databases/campus_locator.db`
(tabla `alertas`, §5.10) y abriéndola con `sqlite3` de Python.

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | Crea la alerta `validacion-3-6-c1` con `PUT /v1/admin/alerts/{uuid}`, provoca una sincronización y lee la caché | La caché tiene una fila con ese `id`, `mensaje` y `radio = 15` |
| C1b | Borra la alerta con `DELETE /v1/admin/alerts/{id}`, provoca otra sincronización y vuelve a leer la caché | `GET /v1/alerts?desde=<generado_en anterior>` trae el `id` en `eliminadas` y la caché ya no tiene ese `id` |
| C3 | `./gradlew testDebugUnitTest --tests '*.DetectarAlertasCercanasTest'` | Sale con 0 y los XML de `app/build/test-results/testDebugUnitTest/` suman ≥ 4 casos y 0 fallos (la revisión del PR confirma que cubren radio, incertidumbre, una vez por aproximación y vigencia) |

## 3. Comprobaciones manuales

Antes de limpiar, el script espera Enter para que la persona haga C2 y C4 con las alertas de §4 (C5 no necesita
alertas: se puede hacer antes o después). Para C4 enciende
`embedding` si está apagado (como `embedding.py encender`, infra §3.4 y §5.10) y, al terminar, lo apaga solo si lo
encendió él; hora límite para empezar: 21:00 de Bogotá (a las 22:00 se apaga solo).

| ID | Qué hace la persona | Evidencia en el PR |
|---|---|---|
| C2 | Con red, abre la app y espera 20 s (sincroniza). Activa el modo avión, ve a ≥ 50 m del lugar que imprime el script, abre el mapa público desde Inicio (comando de voz «mapa» o acción de TalkBack «Ver mapa»: ruta `mapa`, `MapaPublicoScreen`, posición por PDR), fija ahí el inicio y camina hasta el lugar | Video con audio: modo avión visible y la app leyendo «validacion-3-6-c2» al entrar en el radio, una sola vez mientras sigue dentro |
| C4 | Con red y `embedding` encendido, va al lugar que imprime el script (con dataset), espera 20 s con la app abierta (sincroniza), hace Inicio → Ubicarme y escucha el Resultado (6.3) | Video con audio: tras la ubicación, el Resultado muestra y lee «validacion-3-6-c4» |
| C5 | Con TalkBack activo abre el mapa público desde Inicio con la acción «Ver mapa»; el seguimiento empieza en la posición de «Ubicarme» sin tocar el mapa (y, mientras exista, también fijando un punto y pulsando ▶); vuelve a Inicio con Atrás y comprueba que el mapa ya no lee sensores (procedimiento abajo) | `c5-video.mp4` (con audio de TalkBack, si se puede: `adb shell screenrecord` no graba audio), `c5-sensores-inicio.txt` (`dumpsys sensorservice` de vuelta en Inicio) y `c5-app-log.txt` (líneas `Pdr`) en `evidencia/fe-3-6/` |

**C5 — procedimiento** (viene de `validation-3-1` C2c; `ARCHITECTURE.md` §4.5, §5.2 «Segundo plano» y §5.5 «Inicio»).
El lote define cómo llega la posición de «Ubicarme» al mapa (PLAN §2.2, FE-3.6) y ajusta los pasos 3 y 4.
1. Activar **TalkBack** antes de abrir la app. Con TalkBack 17.0.1 en el Xiaomi (2026-10-26) sale primero su tutorial:
   terminarlo o salir de él.
2. Abrir la app desde el lanzador (Inicio) y empezar a grabar la pantalla. Con el foco en el botón principal, abrir sus
   **acciones** y elegir **«Ver mapa»**: se abre el mapa público. **Sin comprobar** cómo se abren las acciones en
   TalkBack 17: el toque con tres dedos abrió «Search screen» (no el menú de TalkBack) y el doble toque ejecuta la
   acción principal del botón (Ubicarme, abre el escaneo), no «Ver mapa». Probar el menú de TalkBack con el gesto que
   indique su tutorial o sus ajustes («Acciones» en el menú) y anotar en `ARCHITECTURE.md` §4.5 el que funcione.
3. Comprobar que el seguimiento empieza en la posición de «Ubicarme» sin tocar el mapa (lo que construya FE-3.6).
4. Mientras exista el inicio por toque: desactivar TalkBack si estorba, tocar un punto del mapa y pulsar **▶**: la
   posición empieza en el punto tocado.
5. Pulsar **Atrás**: vuelve a Inicio. Parar la grabación y guardarla como `$EVID/c5-video.mp4`
   (`EVID=../docs/validation/evidencia/fe-3-6`).
6. Con la app en Inicio (sin volver al mapa), esperar 5 s y
   `adb shell dumpsys sensorservice > $EVID/c5-sensores-inicio.txt` y
   `adb exec-out run-as com.example.myapplication cat files/logs/app.log | grep "I/Pdr" | tail -n 10 > $EVID/c5-app-log.txt`.
7. Pasa si el video muestra la entrada por TalkBack, el inicio del seguimiento y la vuelta a Inicio, si en
   `c5-sensores-inicio.txt` no hay ninguna conexión **activa** de `com.example.myapplication` al acelerómetro ni al
   vector de rotación (el historial de registros anteriores también la nombra y no cuenta; formato de `dumpsys` **sin
   comprobar** en el Xiaomi, como en `validation-2-3` C5) y si `c5-app-log.txt` muestra `sensores registrados (iniciar;
   …)` al empezar el seguimiento seguido de `sensores quitados (segundo plano)` o `(detener)` al volver.

## 4. Datos de prueba y limpieza

Crea con la API la alerta de C1a y las alertas `validacion-3-6-c2` y `validacion-3-6-c4` (prioridad `alta`, radio
15 m, en la coordenada del primer lugar de `GET /v1/places` por nombre, que el script imprime; para C4 conviene un
lugar con fotos en el dataset). Al terminar, también si algo falló, borra con `DELETE /v1/admin/alerts/{id}` todo lo
que empiece por `validacion-3-6`; al empezar, hace lo mismo con los restos de una ejecución anterior
(`GET /v1/admin/alerts?q=validacion-3-6`). La caché del teléfono se vacía sola en la siguiente sincronización; el
script no usa `pm clear`. `POST /v1/localize` no guarda las fotos (BE-3.2).

## 5. Cómo ejecutarlo

```bash
cd FRONTEND_KOTLIN/project
uv run --group ops python src/ops/validate36.py --entorno dev
```

Variables: `VALIDACION_API_URL`, `VALIDACION_ADMIN_CORREO`, `VALIDACION_ADMIN_PASSWORD`, `AWS_PROFILE` (para
`embedding`; `ARCHITECTURE.md` §5.11) y `ANDROID_SERIAL` si hay varios dispositivos. Duración aproximada: 8 minutos de
script, más 15 de C2, 10 de C4 (con `embedding` encendido, ~0,10 USD/h) y 10 de C5. El detalle de §5 (variables de WSL,
preparación numerada y salida esperada, como `validation-1-2` §5) lo escribe el lote al implementar el validador.
