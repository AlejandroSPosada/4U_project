# CHANGELOG — App Android (`FRONTEND_KOTLIN`)

Una entrada por versión de [`ARCHITECTURE.md`](./ARCHITECTURE.md), la más reciente primero.

**Cómo se numera la versión del documento**
- **Mayor:** cambio incompatible en un contrato de §5 (firma de una pieza reutilizable, función de un puente WebView,
  formato del almacenamiento local, ruta de navegación). Mientras la versión sea `0.x`, un cambio incompatible sube la
  **menor**.
- **Menor:** vista, pieza o contrato nuevos; decisión nueva (ADR); reorganización del documento.
- **Parche:** aclaraciones, correcciones de redacción o entradas que pasan de ⚠ a verificadas sin cambiar el contrato.

Las historias de usuario del catálogo de `PLAN.md` §5 también se versionan aquí cuando cambian.

**Plantilla de entrada**
```
## [x.y.z] — AAAA-MM-DD
- Lote que la motivó:
- Qué cambió:
- Contratos tocados (§5):
- Cómo se verificó:
- Pendiente:
```

---

## [0.5.0] — 2026-10-25

- **Lote que la motivó:** FE-1.2 (login contra el backend).
- **Qué cambió:**
  - Código: `RemoteAuthRepository` (`POST /v1/auth/login`, `LoginPeticionDto`, `CampusApi.login`,
    `MapeoDatosApi.sesion`) y `LoginViewModel.Factory` lo usa en lugar de `AuthRepositoryStub`; `Sesion` gana
    `expiraEnMs` (y `vencida(ahoraMs)`); `SessionManager(almacen, reloj)` con `AlmacenSesion`/`AlmacenSesionCifrado`
    (clave nueva `expira_en_ms`; `obtener()` da `null` y borra una sesión vencida, sin llamar al backend) y el
    constructor `SessionManager(context)` de siempre; `VigilanteSesion`, `MotivoSinSesion` y `EventosSesion`
    (`session/VigilanteSesion.kt`); `SesionInterceptor` y `SinSesionException` en `ClienteApi.kt`, que sustituye a
    `AutenticacionInterceptor` cuando hay vigilante; `ClienteApi.vigilante` reemplaza a `ClienteApi.proveedorToken`;
    `MapeoErroresApi.codigoError` y `SIN_SESION_LOCAL`; `llamar` convierte `SinSesionException` en
    `ApiException(SesionVencida("SIN_SESION_LOCAL"), 401, null)`; `MyApp` asigna el vigilante (tag `Sesion`); `AppNav`
    vuelve a Login desde rutas `admin/…` al recibir `EventosSesion.sinSesion`.
  - Pruebas: `SesionVencidaTest` (9) y `RemoteAuthRepositoryTest` (6).
  - Validadores: `src/ops/validate12.py`; en `comun.py`, ayudas de AWS por la CLI `aws` (`aws_json`, `cuenta_aws`,
    `terraform_outputs`, `leer_secreto`, `credenciales_admin`, `tarea_cli`, `crear_usuario_validacion`,
    `desactivar_usuario_validacion`), `http_post_json`, `lote_hecho`, `reloj`/`dormir` y el manejo de la interfaz del
    teléfono (`volcar_pantalla`, `tocar`, `escapar_input_text`, `escribir_texto`, `abrir_login`,
    `enviar_credenciales`, `exigir_adb_permitido`…); `adb()` sin PTY. Pruebas: `test_validate12.py` (16) y
    `test_comun_login.py` (28); total 73.
  - Documento: nuevo §4.2 (lo construido en FE-1.2); §5.3 reescrito (caducidad, `AlmacenSesion`, `VigilanteSesion`,
    `EventosSesion` y el flujo completo «401 / sesión vencida → Login»); §5.5 (Login con el backend real y la
    decisión de no dar mensaje propio a `503 SERVICIO_OCUPADO`; guarda del Panel con sesión vencida); §5.6
    (`RemoteAuthRepository`, `Sesion` con `expiraEnMs`); §5.8 (vuelta a Login desde `AppNav`); §5.10 (piezas nuevas,
    orden de interceptores, fila del `401` de sesión, cómo probar una ruta protegida); §5.11 (CLI `aws`, variables
    `VALIDACION_ADMIN_*`, tabla de las ayudas nuevas, detalles de `validate12.py` y trampas de MIUI, uiautomator,
    `input text` y el teclado); §3.2 (paquete `session/`, pruebas, tag `Sesion`); §4.1 (pruebas y una trampa de
    `assertThrows` con `llamar`); §7.1 y §7.2; ADR-FE-14 (sesión perdida en el cliente HTTP con evento global) y
    ADR-FE-15 (validadores con la CLI `aws`).
  - `validation-1-2`: precondiciones reordenadas como en `validation-1-1` (primero las de la máquina, código 3; después
    las de otros lotes, código 2); P1 de antes decía que `ApiConfig.kt` «contiene `VALIDACION_API_URL`» (no es así: se
    compara `ApiConfig.BASE_URL` con la URL vigente); las credenciales del admin salen del secreto si no hay variables;
    C1 y C2 detallan cómo se maneja el teléfono y qué falla en MIUI; §5 con variables, preparación (incluida
    «Depuración USB (Configuración de seguridad)») y salida esperada.
  - `PLAN.md`: FE-1.2 pasa a «En curso»; los entregables de §2.2 nombran también `/v1/collect/…` (como C3).
- **Contratos tocados (§5):** §5.3 (`SessionManager` con constructor nuevo y caducidad; `AlmacenSesion`; formato del
  almacén: clave `expira_en_ms`; `VigilanteSesion`, `EventosSesion`); §5.6 (`Sesion(token, usuario, expiraEnMs)`:
  incompatible para quien la construya —solo `AuthRepositoryStub` y el almacén—); §5.10 (`ClienteApi.proveedorToken`
  desaparece y llega `ClienteApi.vigilante`; `crear`/`okHttp` con `vigilante`; `SesionInterceptor`,
  `SinSesionException`, `CampusApi.login`, `LoginPeticionDto`, `MapeoDatosApi.sesion`, `MapeoErroresApi.codigoError` y
  `SIN_SESION_LOCAL`); §5.8 (`AppNav` navega a `login` por `EventosSesion`); §5.11 (ayudas de `comun.py`). Piezas
  nuevas y cambios incompatibles: en `0.x`, sube la menor.
- **Cómo se verificó:** en Windows, `.\gradlew.bat --console=plain testDebugUnitTest assembleDebug` con JBR 21 →
  `BUILD SUCCESSFUL`, 50 casos sin fallos (`SesionVencidaTest` 9/9, `RemoteAuthRepositoryTest` 6/6, más los 35 de
  FE-1.1). En WSL, `uv run --frozen ruff check .` («All checks passed!»), `ruff format --check .` («7 files already
  formatted») y `pytest -q` (73 passed); `validate12.py --entorno local` → código 0 (P1, C3 9/9, C4 6/6; C1 y C2
  omitidas) y `validate11.py --entorno local` sigue en 0. Lecturas de AWS (2026-10-25): las consultas JMESPath de
  `tarea_cli` contra una tarea parada real, los outputs `ecs_cluster`, `familias_tarea.migrate`, `subredes_tareas` y
  `sg_migrate`, y que los logs de `migrate` (`migrate/app/<id>`) son líneas JSON con `evento` (`usuario_guardado`,
  `usuario_desactivado`).
- **Pendiente:** `validate12.py --entorno dev` con el teléfono (C1 y C2; lo corre el maestro, `validation-1-2` §5);
  comprobar en el Xiaomi el nombre del campo de `dumpsys input_method` y la activación de «Depuración USB
  (Configuración de seguridad)»; `toString()` de `Sesion` y `Usuario` sin token ni correo sigue en FE-4.3.

---

## [0.4.0] — 2026-10-25

- **Lote que la motivó:** FE-1.1 (cliente HTTP, conexión real y CI).
- **Qué cambió:**
  - Código: `ApiConfig.kt` apunta a `api_base_url` de `dev` + `/v1` (antes, una IP por `http://` del prototipo);
    nuevo paquete `data/remote/` (`CampusApi`, `ClienteApi` con `RequestIdInterceptor` y `AutenticacionInterceptor`,
    `llamar`/`llamarSinCuerpo`, `FalloApi`, `ApiException`, `SinConexionException`, `RespuestaInesperadaException`,
    `MapeoErroresApi`, DTOs, `MapeoDatosApi`, `RemoteBackendHealth`); `BackendHealth` se muda a
    `data/repository/BackendHealth.kt` y `BackendHealthStub` desaparece; `InicioViewModel` sondea `GET /v1/health`
    real; Manifest con `usesCleartextTraffic="false"`; dependencias Retrofit 2.11.0, `converter-gson` y
    `mockwebserver` 4.12.0 (pruebas). Se quitaron de `app/build.gradle.kts` dos líneas
    `lifecycle-*-compose:<tu versión>` (plantillas sin versión, duplicadas de las del catálogo; Gradle las ignoraba por
    resolución de conflictos).
  - Pruebas: `MapeoErroresApiTest` (14), `MapeoDatosApiTest` (13) y `ClienteApiTest` (7).
  - CI: `.github/workflows/frontend.yml` (jobs `compilar y pruebas unitarias` y `validadores`).
  - Validadores: `project/pyproject.toml` + `uv.lock`, `src/ops/comun.py`, `src/ops/validate11.py` y
    `tests/ops/` (29 casos); `.validacion/` y los cachés de Python en `.gitignore`.
    `commit_actual()` usa `git -c core.autocrlf=input` porque el Git de WSL ve como modificados los ~100 archivos con
    CRLF que sacó el Git de Windows (§5.11, «Trampas»).
  - Documento: nuevo §4.1 (dónde y cómo se compila, `frontend.yml`, trampas); §5.10 con la tabla de piezas de
    `data/remote/`, el orden exacto de las reglas de errores, las funciones del mapeo de datos, cómo añadir una ruta y
    las trampas del cliente; §5.11 con dónde corren los validadores (WSL + Gradle y `adb` de Windows), sus variables, la
    tabla de `comun.py` y sus trampas; §3.2 (estructura con `tests/ops`, `uv.lock`, `.validacion/` y el tag `Api`);
    §5.2 y §5.5/§5.6 (`BackendHealth` real, tag `Api`); ADR-FE-12 (Retrofit + OkHttp + Gson) y ADR-FE-13 (solo HTTPS).
    Tras la revisión «solo docs»: «Detalles internos del cliente» (§5.10: campos de cada DTO, orden de interceptores,
    convertidor Gson, `requestId` por excepción, pruebas con MockWebServer) y «Detalles internos de los validadores»
    (§5.11: entorno de `ejecutar`, estados del informe, constantes de `validate11.py`, configuración de `pyproject.toml`).
  - `validation-1-1`: C3 pasa a manual (la coordina el maestro con el PR); C1 se parte en C1a (automática: el teléfono
    registra `GET /v1/health -> 200` en `app.log`) y C1b (manual: modo avión); C4 en C4a (URL) y C4b (salud por esa
    URL); precondiciones reordenadas (primero herramientas, código 3; luego otros lotes, código 2); `local` admitido
    para C2 y C4a; §5 con variables, preparación y salida esperada.
- **Contratos tocados (§5):** §5.10 (piezas nuevas de `data/remote/`, formato de la línea `Api` de `AppLog`, forma de
  `ApiConfig.kt` que lee el validador); §5.5 y §5.6 (`BackendHealth` cambia de archivo y de implementación; misma
  firma, pero pasa del paquete `ui.inicio` a `data.repository`: incompatible para quien lo importe, y solo lo usaba
  `InicioViewModel`); §5.11 (ayudas de `comun.py`). Piezas nuevas y un cambio incompatible menor: en `0.x`, sube la menor.
- **Cómo se verificó:** en Windows, `.\gradlew.bat testDebugUnitTest assembleDebug` con JBR 21 → `BUILD SUCCESSFUL`,
  35 casos sin fallos (34 nuevos + `ExampleUnitTest`). En WSL, `uv run --frozen ruff check .`, `ruff format --check .` y
  `pytest` (29 casos) en verde; `validate11.py --entorno local` → código 0 (C2 14/14 y 13/13; C4a igual al output
  `api_base_url` + `/v1`); `validate11.py --entorno dev` sin teléfono → código 3 en P2, como se espera. `GET /v1/health`
  de `dev` responde `200 {"estado":"ok",…}` con `x-request-id` (curl, 2026-10-25).
- **Pendiente:** ejecución en `dev` con el teléfono (C1a, C4b, C1b manual) y PR con `frontend.yml` en verde (C3, la
  primera vez que corre en un runner Linux). El viejo `project/ARCHITECTURE_front.md` (copia anterior a 0.2.0, con
  datos desactualizados) sigue en el repositorio.

---

## [0.3.2] — 2026-10-24

- **Lote que la motivó:** ninguno; `embedding` deja de usar GPU y pasa a Fargate con 2 vCPU, con el mismo encendido
  bajo demanda (`INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` 0.9.0, ADR-INF-14).
- **Qué cambió:** las menciones a «la GPU de embeddings» pasan a «embeddings» en §1.2, §3, §5.10 y R8 (§9.1); el
  encendido tarda 2–3 min (antes 5–10). `validation-3-2` (C1 y C4) y `validation-3-5` (C3) usan `embedding.py` en lugar
  de `gpu.py`.
- **Contratos tocados (§5):** ninguno; la app no ve el modelo ni la dimensión de los vectores. Solo redacción: sube el
  parche.
- **Cómo se verificó:** búsqueda de «GPU» y «gpu.py» en `docs/`; revisión cruzada con infra 0.9.0 y backend 0.5.0.
- **Pendiente:** nada.

---

## [0.3.1] — 2026-10-24

- **Lote que la motivó:** ninguno; la infraestructura cambia el horario fijo de `embedding` por una GPU apagada por
  defecto que se enciende a mano (`INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` 0.7.0, ADR-INF-13).
- **Qué cambió:** referencias al «horario de `dev`» en §1.2 (regla de contratos), §3 («El backend visto desde la app»), el
  mensaje de `503 EMBEDDING_NO_DISPONIBLE` de §5.10 y R8 (§9.1); `validation-2-1` P4 (el script enciende `embedding` si hace falta),
  `validation-3-2` (C1 con la GPU encendida y C4 con ella apagada, en lugar de dentro y fuera del horario) y
  `validation-3-5` C3.
- **Contratos tocados (§5):** ninguno; la app ya trataba `503 EMBEDDING_NO_DISPONIBLE`. Solo redacción: sube el parche.
- **Cómo se verificó:** búsqueda de «horario», «06:00» y «22:00» en `docs/` y revisión cruzada con infra 0.7.0 y
  backend 0.4.0.
- **Pendiente:** nada.

---

## [0.3.0] — 2026-10-23

- **Lote que la motivó:** ninguno; cambio de organización del monorepo pedido por el equipo.
- **Qué cambió:**
  - El código de la carpeta irá en `project/` y la documentación en `docs/`, con una carpeta nueva
    `docs/validation/` (un documento por lote) y un validador por lote en `project/src/ops/validate<fase><n>.py`.
  - Los lotes se renumeran como `<PREFIJO>-<fase>.<n>` para que el nombre de su validación coincida con el lote
    (`validation-2-2.md` ↔ `validate22.py` ↔ lote x-2.2).
  - El PLAN separa las dependencias «para construir» de las «para validar», numera los criterios de cierre (C1, C2…)
    y añade a §3 las columnas «Validación» y «Última validación».
  - El proyecto Gradle pasa a `FRONTEND_KOTLIN/project/`; la ruta base del código Kotlin es
    `project/app/src/main/java/com/example/myapplication/` (§3.2 describe la carpeta completa).
  - La fase «P» del prototipo pasa a ser la fase 0; sus lotes, FE-0.1 a FE-0.12, quedan cerrados sin validación
    automática.
  - Nuevo §5.11: cómo validan los scripts de la app (Gradle, `adb` con dispositivo físico, comprobaciones estáticas y la
    API de `dev`).
  - FE-4.2 (Ajustes) tiene ahora criterios de cierre.
  - Tras escribir los documentos de validación: §5.10 define la cola de subida (el propio `manifest.json`, con
    `remote_video_id` y `subida_estado`), la base Room `campus_locator.db`, cuándo se sincronizan las alertas y dónde
    se anuncian; §5.11 aclara que no hay backend local (solo HTTPS) y que `connectedDebugAndroidTest` borra los datos
    de la app.
  - `MapaPublicoScreen` no tiene ruta hoy (⚠ verificar en `AppNav`); FE-3.1 le da la ruta pública `mapa`.
  - `CONSERVAR_FOTOS = false` pasa de FE-4.3 a FE-3.2 (FE-4.3 queda con C1–C5); FE-1.2 C3 se comprueba con
    `SesionVencidaTest`; FE-3.4 C2 deja de depender de `/v1/localize` (y de BE-3.2); las pruebas de los criterios
    tienen nombre de clase; FE-2.1 no borra el recorrido que valida: es dataset real.
- **Contratos tocados (§5):** §5.10 (cola de subida, caché de alertas), §5.11 (nuevo). Ninguna pieza de la app cambia
  de firma.
- **Equivalencia de identificadores** (las entradas anteriores usan los viejos): FE-01 → FE-0.1 · FE-02 → FE-0.2 · FE-03
  → FE-0.3 · FE-04 → FE-0.4 · FE-05 → FE-0.5 · FE-06 → FE-0.6 · FE-07 → FE-0.7 · FE-08 → FE-0.8 · FE-09 → FE-0.9 · FE-10
  → FE-0.10 · FE-11 → FE-0.11 · FE-12 → FE-0.12 · FE-13 → FE-1.1 · FE-14 → FE-1.2 · FE-15 → FE-2.1 · FE-16 → FE-2.2 ·
  FE-23 → FE-2.3 · FE-17 → FE-3.1 · FE-18 → FE-3.2 · FE-19 → FE-3.3 · FE-20 → FE-3.4 · FE-25 → FE-3.5 · FE-21 → FE-4.1 ·
  FE-22 → FE-4.2 · FE-24 → FE-4.3 · FE-26 → FE-5.1 · FE-27 → FE-5.2 · FE-28 → FE-6.1.
- **Cómo se verificó:** comprobación automática de que los lotes citados existen, de que las referencias cruzadas entre
  secciones resuelven, de que cada documento de validación cubre una vez cada criterio de su lote y de que las tablas
  están bien formadas.
- **Pendiente:** escribir los validadores (cada lote los entrega con su código); mover físicamente el proyecto Gradle a
  `project/`.


---

## [0.2.0] — 2026-10-23

- **Lote que la motivó:** ninguno de la app; reorganización de la documentación del monorepo en tres documentos por
  carpeta (`docs/ARCHITECTURE.md`, `docs/PLAN.md`, `docs/CHANGELOG.md`) y alineación con los contratos nuevos de
  `BACKEND_FASTAPI` v0.1.0, `SERVICE_EMBEDDING` v0.1.0 e `INFRASTRUCTURA_TERRAFORM` v0.1.0.
- **Qué cambió:**
  - El documento se mudó de `FRONTEND_KOTLIN/ARCHITECTURE.md` a `FRONTEND_KOTLIN/docs/ARCHITECTURE.md`. Las imágenes
    de diseño se enlazan ahora como `../assets/…`. **El archivo anterior debe borrarse** para no tener dos versiones.
  - Nuevo §1 (propósito, regla de contratos, guía de numeración). §1 «Visión general» y §2 se unieron en §2.
    §3 + §4 → §3 (3.1 y 3.2). §5 «Mapa de vistas» → §4. **§11 → §5** (todas las referencias «11.N» se cambiaron a
    «5.N»). §6 y §7 conservan su numeración. §8 → §8.2 (decisiones abiertas, misma numeración) y se añade §8.1 (ADR).
    §9 → §9.2 y se añade §9.1 (riesgos).
  - El antiguo §10 «Estado de implementación», las listas «Pendiente» de las vistas 6.4, 7.3, 7.3b, 7.4, 7.8, 7.9,
    7.11 y 7.14, y el antiguo §11.10 se movieron a `PLAN.md` (lotes FE-01 a FE-28 y tabla de estado §3). En su lugar,
    cada vista conserva su descripción («Implementación actual») y una referencia al lote. Las limitaciones de 7.3b
    siguen en el ARCHITECTURE como «Limitaciones conocidas».
  - La tabla «Responsabilidades del backend (resumen de endpoints)» del antiguo §3 se eliminó: el contrato vive en
    `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5. Diferencias con lo que había aquí: prefijo `/v1` en todas las rutas;
    las fotos del dataset ya no se envían a `POST /collect/videos/{id}/images` sino con URLs prefirmadas;
    `POST /v1/collect/videos/{id}/complete` nuevo; alertas de admin con `PUT` idempotente y
    `POST /v1/admin/alerts/sincronizar`; `GET /admin/videos/{id}/images` pasa a `GET /v1/admin/videos/{id}` (incluye
    las fotos); `GET /admin/stats` es el resumen del panel y las estadísticas de uso quedan en
    `GET /v1/admin/stats/uso` (Fase 5).
  - Decisiones abiertas resueltas por el backend: 7 (privacidad), 10 (borrado de videos) y 11 (autenticación); la 2
    (grafo de caminos) queda aplazada a la Fase 5; la 3 fija el radio por defecto en 15 m; la 9 queda resuelta en parte
    (auditoría). Nuevas decisiones abiertas 17 (nombre del producto), 18 (interacción de Inicio) y 19 (nombre por
    defecto de los videos).
  - ADR-FE-01 a ADR-FE-11 registran decisiones que ya estaban aplicadas en el código; ADR-FE-10 es nueva.
  - El catálogo de historias de usuario (HU-01 a HU-23, propuestas) se crea en `PLAN.md` §5 y es el único del
    proyecto.
- **Contratos tocados (§5):** numeración (§11 → §5). **Nuevo §5.10** «Consumo de la API del backend»: URL base,
  mapeo de errores, mapeo de datos, conversión de rumbo a norte verdadero, subida con URLs prefirmadas y caché de
  alertas. Ninguna pieza existente cambió de firma.
- **Cómo se verificó:** comprobación automática de que cada línea del documento anterior aparece en el nuevo (con la
  numeración cambiada) salvo los bloques movidos a `PLAN.md` y `CHANGELOG.md` y las ediciones listadas arriba;
  revisión cruzada de §5.10 con el §5 del backend. Una revisión independiente posterior movió las tablas de
  `AndroidBridge`, `EditorBridge` y `VideoBridge` a §5.9,
  la estructura de los videos locales (`manifest.json`) a §5.6 y sustituyó los fragmentos de navegación de 7.1, 7.2,
  7.8, 7.11 y 7.14 por referencias a §5.8 (eran copias y una ya estaba desactualizada); también actualizó rutas a
  `/v1`, corrigió afirmaciones que contradecían ADR-FE-04 («sin compilar», sensor de hardware de pasos), alineó el
  tiempo de lectura a 30 s, añadió la re-codificación de fotos antes de subir y pasó `EstadoFoto.PENDIENTE` a FE-15.
- **Pendiente:** implementar §5.10 (FE-13 en adelante); borrar el antiguo `FRONTEND_KOTLIN/ARCHITECTURE.md`;
  confirmar que las imágenes de diseño están en `FRONTEND_KOTLIN/assets/`.

---

## [0.1.0] — 2026-10-12 (reconstruida)

Versión del documento tal como estaba antes de la reorganización (sin número de versión en su momento). Esta entrada
reconstruye su historia a partir de las notas que el propio documento llevaba en su antiguo §11.10. **Usa la
numeración de entonces:** §11 = §5 actual y §10 = `PLAN.md` §3.

- **Lote que la motivó:** construcción del prototipo (lotes FE-01 a FE-12).
- **Qué cambió, por tandas de revisión:**
  - **Tanda 4:** `VideosViewModel.kt`, `LoginViewModel.kt`, `InicioViewModel.kt` (con `BackendHealth`),
    `InicioScreen.kt` y `SeleccionDestinoViewModel.kt` documentados y verificados contra el código (11.5; ajustes en
    11.1, 11.2, 11.3, 11.4 y 11.6 a 11.8).
  - **Tanda 5:** `MainActivity.kt` releído (confirma 11.3 y 11.8), `SeleccionDestinoScreen.kt`, `DestinoUiState` y
    `LoginScreen.kt` (11.5).
  - **Tanda 6 (bache 1):** `BuscarLugares.kt` (con `InterpretarRespuesta` y `Respuesta`), `LugarDestino.kt` (con
    `CategoriaLugar`) y `SeleccionDestinoState.kt` completo (11.5, 11.6 y 11.7).
  - **Tanda 7 (bache 2):** `PanelesVoz.kt`, `ListaLugares.kt` y `Comun.kt` de `ui/destino/componentes/` (11.5 y 11.6).
  - **Tanda 8 (bache 3):** `LugaresRepository.kt` (con `LUGARES_DE_PRUEBA`), `AdminRepository.kt`, `ResumenAdmin.kt`
    y `Usuario.kt` (11.5, 11.6 y 11.7).
  - **Tanda 9 (bache 4, 2026-10-10):** el PDR pasa a Kotlin (`PdrEngine.kt`, `StepDetector.kt`, `PdrTracker.kt`,
    `PuentePdr.kt`, `MapaPublicoScreen.kt`); `app.js` e `index.html` solo dibujan; base común de mapas
    (`mapa_base.js`, `MapaWebView`). ⚠ sin probar en dispositivo.
  - **Tanda 10 (2026-10-11):** vista 7.3 (`UbicacionManualScreen.kt`, `UbicacionManualViewModel.kt`,
    `UbicacionManualState.kt`, `InicioRecoleccion.kt`, `ubicacion_manual.html/js`).
  - **Tanda 11 (2026-10-11):** vista 7.4 (`FotoRecolectada.kt`, `SesionRecoleccion.kt`, `DisparadorCaptura.kt`,
    `RecoleccionRepository.kt`, `RecoleccionState.kt`, `RecoleccionViewModel.kt`, `RecoleccionScreen.kt`,
    `PanelesRecoleccion.kt`, `MapaRecoleccion.kt`, `recoleccion_mapa.html/js`) y rutas nuevas en `AppNav`. Documentado
    a partir de lo entregado, sin releerlo contra el código final.
  - **Tanda 12 (2026-10-12):** vista 7.3b (`CalibracionPaso.kt`, `CalibracionPasoRepository.kt`,
    `CalibracionState.kt`, `CalibracionViewModel.kt`, `CalibracionScreen.kt`, `MapaCalibracion.kt`,
    `calibracion_mapa.html/js`, `CalibracionPasoTest.kt`); longitud de paso inyectable en `PdrEngine` y `PdrTracker`;
    fila «Calibrar mi paso» en 7.3. Ese mismo día los pasos pasan a salir siempre del acelerómetro (se descarta
    `TYPE_STEP_DETECTOR`). Tras compilar el proyecto entero, el aviso «Kotlin sin compilar» de las tandas anteriores
    dejó de aplicar a lo que forma parte del build.
  - Antes de la tanda 4 ya estaban documentados y verificados: `VoiceController` y `ComandoParser`, `SessionManager`,
    `VideoRepository` / `AssetsVideoRepository` / `EdicionesLocales` y `Foto.kt`, `AuthRepository` y `Alerta.kt`,
    `OrientationProvider` y `CapturaFoto`, `ui/ubicacion/componentes/`, `MyApp.kt`, `MainActivity.kt`,
    `EscaneoViewModel.kt` y el resto del escaneo, `FeedbackCaptura.kt`, `AppLog.kt`, `AlertaFormSheet.kt`, el editor
    de mapa (`EditorMapaViewModel.kt`, `EditorMapaScreen.kt`, `editor_mapa.html/js`), el panel, la galería, la lista y
    el detalle de videos (`video_detalle.html/js`) y `CampusColors.kt`.
- **Decisiones de esta etapa:** mapa con OSM + Leaflet en lugar de `eafit.mbtiles`; PDR solo en Kotlin; pasos por
  acelerómetro; calibración del paso por dispositivo; `SesionDeRecoleccion` como *holder* de la recolección; control de
  calidad de imagen desactivado temporalmente (ahora ADR-FE-02 a ADR-FE-07 y ADR-FE-11).
- **Contratos tocados:** puentes `AndroidBridge`, `EditorBridge`, `VideoBridge`, `UbicacionBridge`,
  `RecoleccionBridge` y `CalibracionBridge`; almacenamiento `files/recoleccion/` y `SharedPreferences`
  `campus_calibracion`; rutas `admin/ubicacion-manual`, `admin/calibracion`, `admin/recoleccion` y
  `admin/recoleccion/resumen`.
- **Cómo se verificó:** lectura de los archivos citados por tanda; `CalibracionPaso.kt` y `PdrEngine.kt` con kotlinc
  2.0.21 (13 comprobaciones); páginas web con jsdom; el proyecto completo compila y las vistas 7.3 y 7.3b se abren en
  dispositivo (Xiaomi 23028RA60L, Android 14).
- **Pendiente:** heredado por los lotes de `PLAN.md` (FE-13 a FE-28).
