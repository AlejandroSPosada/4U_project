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

## [0.7.2] — 2026-10-26
- Lote que la motivó: FE-2.1 (validación en `dev`).
- Qué cambió: `validate21.py` P4 tomaba la **primera** fila que empieza por `| FE-2.3 |` del PLAN, que es la de §2.1
  (nombre y dependencias), no la de estado de §3, y bloqueaba con código 2 aunque FE-2.3 estuviera «Hecho». Ahora
  busca la fila cuya segunda celda es la fase (un número). Las pruebas usan un PLAN con las dos filas, como el real.
  Trampa para otros validadores: para leer el estado de un lote, usar `comun.lote_hecho` o filtrar por la fase.
- Contratos tocados (§5): ninguno.
- Cómo se verificó: `pytest` (129 casos) y `ruff`; `validate21.py --entorno dev` sobre el commit siguiente.
- Pendiente: —

## [0.7.1] — 2026-10-26
- Lote que la motivó: FE-2.1 (validación) y FE-2.3 (C3), por decisión del usuario del 2026-10-26: validar en casa,
  no en el campus.
- Qué cambió: `validate21.py` acepta `--minimo-fotos N` (por defecto 50, `MINIMO_FOTOS`) para correr C1 con el
  recorrido de prueba de 10 fotos `validacion-21-casa`, que se borra del backend al terminar (`limpiar-validacion`,
  prefijo `validacion-`). El recorrido real del campus sigue con 50. §5.11 (detalles de `validate21`) al día.
- Contratos tocados (§5): ninguno (solo el validador).
- Cómo se verificó: `pytest` (129 casos, uno nuevo: `test_dev_minimo_fotos_rebaja_el_umbral_de_c1`), `ruff`.
- Pendiente: la calibración real de 7.3b en un tramo medido, con el teléfono que se use para grabar el dataset (FE-2.3
  C3 se validó en casa solo en lo que se pudo comprobar: el detector cuenta los pasos).

## [0.7.0] — 2026-10-25

- **Lote que la motivó:** FE-2.1 (subida de recorridos y Resumen de video, 7.5).
- **Qué cambió:**
  - Código: vista 7.5 (`ui/admin/recoleccion/ResumenVideoScreen.kt`, `ResumenVideoState.kt`,
    `ResumenVideoViewModel.kt`) y ruta `admin/recoleccion/resumen?video={video}` (antes un *placeholder* en blanco;
    «Finalizar» de 7.4 navega con `?video=rec_NNNN`). Cola de subida en `data/local/` (paquete nuevo):
    `ManifestRecorrido` (parser **compartido** del `manifest.json`, con Gson), `RecorridoLocal`/`FotoLocal`/
    `FotoPreparada`/`EstadoSubida`, `AlmacenRecorridos` y `CerrojoRecoleccion`, `Recodificacion.kt`
    (`LimitesSubida`, `PlanRecodificacion`, `MotorImagen`, `Recodificador`, `PreparadorFoto`,
    `FotoIlegibleException`), `MotorImagenAndroid`, `SubidorS3` (`PUT` con un `OkHttpClient` sin interceptores),
    `SubidaRecorrido` (crear video, lotes de 50, `PUT`, `403` → URLs nuevas, `complete`, `actualizarEstados`),
    `ColaSubida` (reintentos con espera, «esperar sesión», retomar) y `Subidas` (una instancia por proceso; la inicia
    `MyApp`). Rutas nuevas en `CampusApi` (`crearVideo`, `registrarImagenes`, `completarSubida`, `video`) y DTOs de la
    recolección; `VideoResumenDto.conteo`. `EstadoFoto.PENDIENTE` (con su caso en `MapeoDatosApi.estadoFoto`, la
    Galería y la Lista). `VideoRepositoryCompuesto`, `FuenteVideos` y `FuenteRecorridos` (Galería, Lista, Detalle de
    video y 7.3 ven los recorridos `finalizado`); `AssetsVideoRepository` usa el parser compartido. Panel: retoma la
    cola y muestra la tarjeta de subidas (`AvisoSubidas`, `onAbrirSubida`). `RecoleccionMapaControl.encuadrar()` y
    `listo`, y la función JS `encuadrar()` de `recoleccion_mapa.js`. `RecoleccionRepositoryLocal`: cerrojo compartido y
    `contarPendientes()` con la regla de §5.10.
  - Pruebas JVM nuevas: `AlmacenRecorridosTest` (13), `RecodificacionFotoTest` (12), `SubidaRecorridoTest` (13),
    `ColaSubidaTest` (8), `VideoRepositoryCompuestoTest` (3); `MapeoDatosApiTest` espera `PENDIENTE`. Total 151.
  - Validadores: `src/ops/validate21.py` y en `comun.py` `token` en `http_get`/`http_post_json`, argumentos propios del
    `Validador` (`argumentos`, `args`), `PLAN_BACKEND`, `EmbeddingDev` (encendido de infra §5.10 con la CLI),
    `hora_bogota`, `dimensiones_jpeg`, `leer_objeto_s3`/`ObjetoS3`; pruebas `test_validate21.py` (20) y
    `test_comun_fe21.py` (15). Total 128.
  - Documento: §4.4 nuevo; §2.4; §3.2 (`data/local/`, pruebas, tag `Subida`); §4.1 (151 casos, tres trampas de las
    pruebas); §5.5 (7.5, Panel, Galería, Lista, `RecoleccionMapaControl`, fábricas de los ViewModels de videos); §5.6
    (repositorio compuesto, parser compartido, claves del manifest, regla del estado, `EstadoFoto.PENDIENTE`,
    cerrojo); §5.8 (ruta de 7.5 con argumento, `onAbrirSubida`, Login → Panel retoma); §5.9 (`encuadrar()`); §5.10
    (subida implementada: claves, piezas, pasos, errores, cola, sesión; DTOs y rutas; `SubidorS3`); §5.11 (ayudas
    nuevas, `validate21.py`, trampas); §7.5, §7.11, §7.14; §9.1 (R6, R10 nuevo); ADR-FE-19 (cola en el proceso con el
    estado en el manifest), ADR-FE-20 (re-codificar con EXIF aplicado a los píxeles, en `subida/`) y ADR-FE-21 (C3 en
    S3 y sin Pillow).
  - `validation-2-1` reescrita: entornos `local` y `dev`; precondiciones en el orden del contrato común (máquina → 3,
    otros lotes → 2) y P8 de `embedding` (no hace falta si el video ya está procesado; hora límite 21:30); C1 sobre
    las fotos registradas; C2 con apoyo automático (C2a pruebas JVM, C2b sin duplicados en el backend) y la manual C2c;
    C3a (JVM) y C3b (objetos de S3); C4 estático con «Finalizar» → 7.5; §5 con variables, preparación y salida esperada.
  - `PLAN.md`: FE-2.1 pasa a «En curso».
- **Contratos tocados (§5):** §5.6 (formato del almacenamiento: claves nuevas `remote_video_id`, `subida_estado`,
  `photos[].upload`, `photos[].estado`, `photos[].error` y carpeta `subida/`, compatibles; `EstadoFoto` con un valor
  nuevo al principio, incompatible para un `when` exhaustivo; `VideoRepositoryCompuesto`); §5.8 (la ruta de 7.5 pasa a
  `admin/recoleccion/resumen?video={video}`; navegar sin argumento sigue valiendo); §5.9 (función nueva `encuadrar()`);
  §5.5 (`PanelAdminScreen(onAbrirSubida)`, `PanelAcciones.onAbrirSubida`, `PanelAdminViewModel(…, almacen, cola)`,
  todos con valor por defecto); §5.10 (rutas, DTOs y piezas de `data/local/`); §5.11 (ayudas nuevas, compatibles).
  Piezas, vista, ruta y ADR nuevos y un cambio incompatible en 0.x: sube la menor.
- **Cómo se verificó:** en Windows, `.\gradlew.bat --console=plain testDebugUnitTest assembleDebug` con JBR 21 →
  `BUILD SUCCESSFUL`, 151 casos sin fallos. En WSL, `uv run --frozen ruff check .` («All checks passed!»),
  `ruff format --check .` («12 files already formatted»), `pytest -q` (128 passed) y `validate21.py --entorno local` →
  código 0 (P1; C2a 13/13, 8/8, 13/13; C3a 12/12; C4; C1, C2b y C3b omitidas; la manual C2c). Sin teléfono, sin `adb`
  y sin tocar AWS (lo coordina el maestro).
- **Pendiente:** C1 y C2 en el campus con el teléfono y `validate21.py --entorno dev` (`validation-2-1` §3 y §5; para
  validar hace falta FE-2.3 «Hecho»). Sin comprobar en el teléfono: el aspecto de 7.5 y de la tarjeta del Panel, la
  re-codificación con `Bitmap` y el EXIF de CameraX, y `EmbeddingDev` de la app contra AWS. Decisiones provisionales
  del maestro, a confirmar por el usuario: los recorridos `en_curso` no salen en Galería/Lista; renombrar y eliminar
  un recorrido local desde 7.13/7.14 sigue en memoria; 7.3 cuenta los recorridos grabados para la última posición y el
  nombre; «corregir la trayectoria» de 7.5 queda fuera; los originales se quedan en el teléfono tras subir. FE-2.2 debe
  conectar «Fotos pendientes» a `AlmacenRecorridos.contarFotosPendientes()`.

---

## [0.6.1] — 2026-10-25

- **Lote que la motivó:** ninguno; decisión del usuario del 2026-10-25, «No necesitamos las alertas por el momento»
  (resuelve la decisión 1 de §6 de `PRIORITY.md`). En el backend, BE-3.1 queda solo con lugares y las alertas pasan al
  lote nuevo BE-3.3.
- **Qué cambió:**
  - `PLAN.md`: lote nuevo **FE-3.6 — Alertas públicas** (fuera del núcleo; para construir FE-3.1 y FE-3.2, para
    validar FE-3.1, FE-3.2 y BE-3.3) con lo de alertas que tenían FE-3.1 (caché en Room con sincronización por
    diferencias, `DetectarAlertasCercanas`, anuncio en la ruta `mapa`: sus C2–C4 pasan a C1–C3) y FE-3.2 (alertas
    cercanas en `ResultadoUbicacionScreen`, con un criterio nuevo C4). FE-3.1 pasa a «Lugares públicos y entrada al
    mapa» (C1 lugares; C2 nuevo: abrir el mapa desde Inicio por voz y con TalkBack); FE-3.2 queda sin alertas (sus C1–C4
    no cambian); FE-3.3 valida contra BE-3.3. §2.1, §2.2, §3 (fila FE-3.6 y nota de FE-3.3) y §4 (HU-05: FE-3.6 y
    BE-3.3; HU-16: BE-3.3).
  - Validaciones: `validation-3-6` nueva (C1a, C1b y C3 automáticas, C2 y C4 manuales; `validate36.py` sin escribir);
    `validation-3-1` reescrita sin alertas (precondiciones en el orden del contrato común: máquina → 3, otros lotes →
    2); `validation-3-2` (P1 sin alertas; P3 de la máquina, código 3); `validation-3-3` (P2 con BE-3.3).
  - Documento: §2.5, §5.10 («Alertas sin conexión»: se anuncian desde FE-3.6; `POST /v1/localize` no trae alertas,
    las de 6.3 salen de la caché) y §6.3 citan FE-3.6 en lugar de FE-3.1 y FE-3.2.
- **Contratos tocados (§5):** ninguno; solo cambian los lotes que entregan cada pieza. Sube el parche.
- **Cómo se verificó:** búsqueda de «FE-3.1», «FE-3.2», «BE-3.1», «alerta» y «DetectarAlertas» en `docs/`; contrato de
  `POST /v1/localize` en backend §5.3 (no trae alertas). El PLAN del backend todavía no tiene BE-3.3 (lo escribe otro
  lote): las referencias a BE-3.3 siguen la decisión del maestro.
- **Pendiente:** cuando el backend publique BE-3.3, comprobar que sus rutas (`GET /v1/alerts`, `/v1/admin/alerts`,
  `sincronizar`) siguen siendo las que citan §5.10, `validation-3-3` y `validation-3-6`. El `README.md` raíz (orden
  entre carpetas, fase 3) todavía dice que FE-3.3 espera BE-3.1 y no nombra FE-3.6.

---

## [0.6.0] — 2026-10-25

- **Lote que la motivó:** FE-2.3 (pruebas en dispositivo y robustez de la recolección), más los huecos de
  documentación que dejó FE-1.2 (verificados por el maestro en `dev` el 2026-10-25).
- **Qué cambió:**
  - Código: pruebas JVM nuevas `CalibracionPasoTest` (13; el documento la citaba pero **no existía**),
    `StepDetectorTest` (11; tampoco existía), `DisparadorCapturaTest` (10), `DerivaTest` (6), `RetomarRecoleccionTest`
    (6) e `InterruptorSensoresTest` (6); no hizo falta extraer lógica de clases Android para las cuatro de C1.
    `sensors/InterruptorSensores.kt` (lógica pura: sensores registrados ⇔ rastreo pedido y primer plano) y
    `PdrTracker` con parámetro nuevo `cicloDeVida: Lifecycle? = ProcessLifecycleOwner.get().lifecycle`: quita los
    sensores en `ON_STOP` del proceso y los vuelve a poner en `ON_START` si el rastreo seguía pedido; registra con el tag
    `Pdr`; dependencia `androidx.lifecycle:lifecycle-process:2.8.7` (catálogo `lifecycleProcess`). Retomar una
    grabación: `domain/model/ProgresoRecoleccion.kt` (`ProgresoRecoleccion`, `VideoEnCurso`, `PuntoRecorrido`),
    `domain/usecase/RetomarRecoleccion.kt`, `RecoleccionRepository.leerEnCurso` y `guardarProgreso` (clave `progress`
    del manifest), `RecoleccionViewModel` guarda el progreso y, sin `InicioRecoleccion`, retoma el video `en_curso` en
    pausa (antes, `SIN_INICIO`); 7.3 muestra «Retomar …» (`FilaRetomar`, `GrabacionPendiente`, `onRetomar`). Ruta
    `mapa` para `MapaPublicoScreen`, que se abre con el extra `ruta` del `Intent` solo en el APK de depuración
    (`MainActivity.EXTRA_RUTA`, `RUTAS_DE_PRUEBA`). C2 no necesitó cambios: `recoleccion_mapa.js` y
    `calibracion_mapa.js` ya usaban `MapaBase.crearMapa`.
  - Validadores: `src/ops/validate23.py` y `comun.listar_archivos_app`; pruebas `tests/ops/test_validate23.py` (20);
    total 93.
  - Documento: §4.3 nuevo (lo construido en FE-2.3); §5.2 (`PdrTracker` con ciclo de vida, `InterruptorSensores`,
    `StepDetectorTest`, reglas exactas de `DisparadorCaptura` y `Deriva`, progreso y retomar en «Flujo de captura de la
    recolección»); §5.5 (`MapaPublicoScreen` con ruta, 7.3 con «Retomar …», 7.4 y 7.3b); §5.6 (`progress` del manifest
    con ejemplo, `leerEnCurso`, `guardarProgreso`, modelos nuevos, tipos de `campus_calibracion`); §5.7 (qué cubre cada
    prueba, `RetomarRecoleccion`); §5.8 (ruta `mapa`, extra `ruta`, `onRetomar`); §5.9 (C2 comprobado); §5.11
    (`listar_archivos_app`, detalles de `validate23.py`, trampas de las manuales); §3.2 (pruebas, tags `Pdr`,
    `RecoleccionVM`, `RecoleccionRepo`); §4.1 (102 casos); §7.3, §7.3b, §7.4; §9; ADR-FE-16 (PDR con el ciclo de vida
    del proceso), ADR-FE-17 (retomar desde el manifest) y ADR-FE-18 (ruta de prueba por el `Intent`). Los ⚠ que solo
    dependían de lo automático se quitaron (C2 de `recoleccion_mapa.js`, «Kotlin sin compilar» de 7.3, «no ejecutado en
    Gradle», sensores en segundo plano, `MapaPublicoScreen` sin ruta, `buscarEnCurso` sin usar); los que dependen de la
    prueba de campo quedan como «a verificar en dispositivo (FE-2.3 C3/C4/C5)».
  - Huecos de FE-1.2 integrados aquí (sin una 0.5.1 aparte): §4.2 (resultado en `dev` sobre `4d578c5`: C1 6,6 s, C2
    2,9 s); §5.10 «Subida y sesión» (la cola de FE-2.1 espera sesión ante `SIN_SESION_LOCAL`) y `PUT` a S3 con un
    `OkHttpClient` propio sin interceptores; §5.8 (tras volver a Login, el login lleva a `admin/panel` y la 7.5 se pierde
    de la pila); §5.11 (cómo entrar como admin desde otro validador copiando de `validate12.py`; `tarea_cli` solo para
    `migrate`; el orbe de Inicio no provoca «could not get idle state»; MIUI comprobado con el ajuste activo; trampa
    nueva de `-dirty` por archivos del IDE). `validation-1-2` §5 paso 5 deja como «sin comprobar» solo el texto exacto
    de la excepción y si MIUI pide cuenta Mi y SIM. De los «Pendiente» de 0.5.0 ya están verificados en `dev`
    `validate12.py` con el teléfono (C1 y C2) y que «Depuración USB (Configuración de seguridad)» activa deja usar
    `pm grant` e `input`; siguen sin comprobar el nombre del campo de `dumpsys input_method` en el Xiaomi y el
    `toString()` de `Sesion` y `Usuario` (FE-4.3).
  - `validation-2-3`: P1 pasa a ser `--version` (código 3, como `validate12`; la compilación la prueba C1) y P2, de la
    máquina (código 3; antes decía que cualquier precondición daba 2, contra el contrato común); C1 con mínimos de casos
    y sin omitidos; C2 sin contar comentarios; manuales con procedimiento paso a paso, plantilla del «Registro de
    pruebas en dispositivo» y evidencia en `evidencia/fe-2-3/`; §5 con variables, preparación y salida esperada.
  - `PLAN.md`: FE-2.3 pasa a «En curso»; FE-3.1 aclara que la ruta `mapa` ya existe y solo falta su entrada desde
    Inicio.
- **Contratos tocados (§5):** §5.2 (`PdrTracker`: parámetro nuevo con valor por defecto, comportamiento en segundo
  plano y `activo` = rastreo pedido); §5.6 (formato del almacenamiento: clave nueva `progress`, compatible; métodos
  nuevos de `RecoleccionRepository`, incompatible solo para quien lo implemente —hoy solo `RecoleccionRepositoryLocal`—;
  modelos nuevos); §5.5 (`UbicacionManualScreen(onRetomar)`, `UbicacionManualContent(grabacionPendiente)`,
  `UbicacionManualAcciones.onRetomar`, todos con valor por defecto); §5.8 (ruta `mapa`, extra `ruta`, `onRetomar`);
  §5.7 (`RetomarRecoleccion`); §5.11 (`listar_archivos_app`). Piezas, ruta y ADR nuevos: sube la menor.
- **Cómo se verificó:** en Windows, `.\gradlew.bat --console=plain testDebugUnitTest assembleDebug` con JBR 21 →
  `BUILD SUCCESSFUL`, 102 casos sin fallos (las seis clases nuevas, 52 casos, más los 50 de FE-1.1 y FE-1.2). Los casos
  de `StepDetectorTest` se calcularon antes con una réplica en Python del detector. En WSL, `uv run --frozen ruff
  check .` («All checks passed!»), `ruff format --check .` («9 files already formatted») y `pytest -q` (93 passed);
  `validate23.py --entorno local` → código 0 (P1; C1 13/13, 11/11, 10/10 y 6/6; C2; tres manuales). Sin teléfono ni
  `adb` (lo coordina el maestro).
- **Pendiente:** `validate23.py --entorno dev` con el teléfono y las manuales C3 (campo), C4 y C5 con su evidencia en
  `evidencia/fe-2-3/` (`validation-2-3` §3 y §5); después, quitar los «a verificar en dispositivo (FE-2.3 …)» que
  confirme la evidencia y pasar FE-2.3 a «Hecho». `RecoleccionRepositoryLocal` sigue sin pruebas automáticas (usa
  `org.json`). Las alertas creadas durante una grabación se pierden al retomar (FE-3.3).

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
