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

## [0.14.1] — 2026-10-27
- Lote que la motivó: FE-4.1 (cierre: `validate41.py --entorno dev` sobre `7578938`).
- Qué cambió (solo documentos y la evidencia): encabezado (FE-4.1 validado en `dev`); §4.10 con las tres ejecuciones
  en `dev`, lo visto en el teléfono y tres hallazgos sin arreglar (fecha de 7.14 en UTC frente a la de 7.13, distancia de
  7.14 calculada frente a la del servidor en 7.13, título de 7.13 bajo la barra de estado), que pasan a FE-4.4; §5.11,
  trampas de FE-4.1: `focused="true"` del buscador comprobado y la trampa nueva del teléfono bloqueado (`mWakefulness`,
  y que `isKeyguardShowing` no sirve en MIUI); `validation-4-1` §3 con la captura de C2c
  (`evidencia/fe-4-1/c2c-lista-tras-borrar.png`); PLAN: FE-4.1 «Hecho» y los hallazgos en FE-4.4.
- Contratos tocados (§5): ninguno (parche).
- Cómo se verificó: `validate41.py --entorno dev` sobre `7578938` sin `-dirty` (2026-10-27, Xiaomi 23028RA60L). La
  segunda ejecución dio código 1 con el teléfono bloqueado; la tercera, **código 0** (22:42–22:48 de Bogotá, informe
  `FE-4.1-20261028-034252.json`): P1–P6, C1a 11/11, C2a 5/5, C3a 15/15, C1b, C3b y C2b en verde, y la manual C2c con la
  captura de 7.13 (la Galería sin `validacion-4-1-b` la comprobó C2b por la pantalla y la API). Los pasos guiados los
  hizo el maestro por `adb` con la entrada en una FIFO. La limpieza borró los dos videos de prueba (la purga de S3
  espera al `worker`, que solo corre con `embedding` encendido).
- Pendiente: nada de FE-4.1; lo que quedó fuera y los hallazgos, en FE-4.4.

## [0.14.0] — 2026-10-27

- **Lote que la motivó:** FE-4.1 (Videos e imágenes contra el backend, 7.11–7.14), sobre `main` en `97791a0` (0.13.1).
- **Contratos que consume:** backend §4.12, «Para la app (FE-4.1)» (`DELETE` de un video → `202` y fuera de las listas;
  `DELETE` repetido de una imagen → `404`, que la app toma como hecho; `reasignar` con `lugar_id` explícito; URLs GET de
  1 h; `url_miniatura` solo en las `procesada`), §5.5 (`/v1/admin/videos`, `/v1/admin/videos/{id}`, `/v1/admin/images`,
  `POST /v1/admin/images/lote`, `VideoResumen`, `ImagenAdmin`, `GET /v1/admin/places`) y §5.6 (backend 0.15.1, BE-4.1
  «Hecho»); el validador usa además la recolección de §5.4. No hizo falta nada fuera del §5 del backend.
- **Decisiones del usuario del 2026-10-27** (al maestro: «haz lo que más creas conveniente»; se eligieron las
  recomendadas): (1) 7.13 muestra los videos del servidor **más** los recorridos del teléfono sin subir; uno que ya tiene
  video en el servidor sale una sola vez, con los datos del servidor; `assets/videos/` ya no sale; (2) FE-4.1 hace «lo
  esencial»: lo demás (7.12, modo Mapa de la Galería, filtro por fecha, «Subir imágenes», minimapa y comparar cobertura,
  acciones por fila, pulsación larga, base común de mapas) pasa al lote nuevo **FE-4.4**; (3) las capas «Cobertura de
  fotos» y «Rutas» de 7.8, también a FE-4.4.
- **Decisiones del lote (ADR nuevas):** ADR-FE-35 — la Lista junta servidor y teléfono; un recorrido local sale solo si
  es `finalizado` sin `remote_video_id` (se casa por `remote_video_id`, no por `ref_cliente`, que otro teléfono puede
  repetir); los recorridos sin subir se renombran y eliminan en su manifest/carpeta, nunca mientras se suben y nunca
  como efecto de otra acción. ADR-FE-36 — las miniaturas de los recorridos locales llegan al `WebView` por
  `shouldInterceptRequest` (`https://miniaturas.local/…`, copias de 240 px en `cacheDir/miniaturas/`), sin
  `allowFileAccess` (que es `false` desde la API 30: la causa de las miniaturas vacías del hallazgo de FE-2.1).
  ADR-FE-37 — 7.14 espera el `202` antes de salir (aviso «Eliminando…», error con «Reintentar», sin cerrar la app),
  recarga el video 5 min antes de que venzan las URLs y carga «Mostrar otros videos» solo al activarlo, con un tope de
  500 fotos.
- **Qué cambió:**
  - Código (`project/`): nuevos `domain/model/ResumenVideo.kt`, `domain/usecase/Fechas.kt`,
    `data/remote/RemoteVideoRepository.kt`, `data/local/MiniaturasLocales.kt` y `ui/admin/videos/TextosVideos.kt`;
    `data/repository/VideoRepository.kt` reescrito (`VideoRepository`, `ImagenesRepository`, `VideosServidor`,
    `ListaVideos`, `PaginaVideos`, `CambiosVideos`, `RecorridoNoEditableException`, `VideoRepositoryCompuesto`,
    `MezclaVideos`; fuera `EdicionesLocales`, `AssetsVideoRepository`, `FuenteVideos`, `FuenteRecorridos`);
    `Foto.kt` (`Foto` con `lugarId`, `orden`, `titulo`; `Video` con `local`, `editable`, `nota`, `urlsVencenEnMs`,
    `finalizadoEn`); `CampusApi` (6 rutas: listar, `PATCH` y `DELETE` de videos; listar, `DELETE` y lote de imágenes),
    `DtosApi` y `MapeoDatosApi`; `ManifestRecorrido` sin `video(recorrido, carpeta)`; `MapaWebView` con `recursos`;
    7.13 (`VideosScreen`, `VideosViewModel`), 7.14 (`VideoDetalleScreen`, `VideoDetalleViewModel`, `video_detalle.js`,
    `video_detalle.html`) y 7.11 (`GaleriaScreen`, `GaleriaViewModel`) reescritos sobre el backend; 7.6 y 7.7 con
    `onVerFotos`; `UbicacionManualViewModel` (locales primero, servidor como mucho 8 s); `MainActivity` (rutas).
    Borrados los 13 archivos de `assets/videos/vid_0001/` (~9,4 MB). Sin dependencias nuevas de Gradle.
  - Pruebas JVM: nuevas `RemoteVideoRepositoryTest` (15, `MockWebServer`), `TextosVideosTest` (5),
    `MiniaturasLocalesTest` (3) y `HistorialRecoleccionTest` (3); `VideoRepositoryCompuestoTest` reescrita (11: la mezcla
    servidor + teléfono, sin duplicados). Total 337 (41 clases): las 300 de las demás clases siguen pasando sin cambios y
    los 3 casos viejos de `VideoRepositoryCompuestoTest` (sobre `EdicionesLocales` y los assets) quedan reescritos en sus 11.
  - Validadores: `src/ops/validate41.py` (local: C1a, C2a y C3a; `dev`: además C1b, C3b y C2b con dos pasos guiados;
    manual C2c); `comun.py` gana `http_put_bytes` (PUT a S3 sin imprimir la URL) y `jpeg_sintetico` (JPEG en gris hecho a
    mano, sin Pillow); `tests/ops/test_validate41.py` (20) y `tests/ops/test_comun_fe41.py` (5; una se omite sin Pillow).
    Total 277 + 1 omitida.
  - Documento: encabezado; §3.2; §4.1 (337 casos, 41 clases); §4.4 y §4.8 (notas: el hallazgo de las miniaturas y «Ver
    fotos» resueltos); **§4.10 nuevo** (con trampas y «Para los lotes siguientes»: FE-4.4 y FE-4.3); §5.1 (variantes);
    §5.5 (filas de Galería, 7.13, 7.14, `VideoBridge`, `TextosVideos`, `UbicacionManual`, Lugares); §5.6 («`VideoRepository`
    en detalle», modelos, `MiniaturasLocales`, `Fechas`); §5.8 (rutas); §5.9 (`MapaWebView.recursos`, `VideoBridge`);
    §5.10 (`CampusApi`, DTOs, mapeo y nueva «Videos e imágenes de administración (FE-4.1)»); §5.11 (ayudas nuevas de
    `comun.py`, `validate41.py`, 277 casos, trampa de FE-4.1); §7.4 (nota); §7.6, §7.7, §7.11, §7.13 y §7.14
    (implementación actual); ADR-FE-35, ADR-FE-36 y ADR-FE-37; R9 resuelto.
  - `validation-4-1` reescrita en el formato de `validation-3-3`/`3-4`: entornos `local` y `dev`; P1–P6 en el orden del
    contrato común (P6 con una sonda `POST /v1/collect/videos {}` → `422` sin rastro); C1 → C1a, C1b; C2 → C2a, C2b y la
    manual C2c; C3 → C3a, C3b; §4 con los videos de prueba creados por la API de recolección y la limpieza solo de los
    que tienen `nombre` y `ref_cliente` con el prefijo `validacion-4-1`; §5 con variables, preparación, ejecución
    (también por `adb` con una FIFO), salida esperada y casos previstos. No necesita `embedding`.
  - `PLAN.md`: «Alineado con» v0.14.0; §2.1 y §3 con la fila nueva FE-4.4 («Pendiente»); §2.2 FE-4.1 reescrito (alcance,
    entregables, «Hecho en el código» y por qué C1–C3 no cambian; C1 aclara que los recorridos sin subir cuentan como
    datos reales); §2.2 FE-4.4 nuevo; FE-4.3 (quitar `ManifestRecorrido.video(…)` de assets); §3 FE-4.1 «En curso»
    (falta `dev`); §4: HU-17 y HU-18 también en FE-4.4.
  - **Arreglo tras la primera ejecución en `dev`** (2026-10-27, el maestro, sobre `01adb2e`, ya en `main`): código 1 por
    el validador, no por la app. P1–P6, C1a–C3a y C1b pasaron; C3b y C2b fallaron antes del paso guiado con «no se volvió
    al Panel con Atrás», con la pantalla de inicio del teléfono, cuyos nombres de apps acabaron en el log y en el
    informe. Causa más probable (sin comprobar en el teléfono; con un teléfono simulado así, el código anterior da
    exactamente esa salida): `dumpsys input_method` sigue diciendo que el teclado está abierto después de cerrarlo, y
    el Atrás «para cerrar el teclado» de `volver_al_panel` cerró la app en el Panel, que es la raíz. También quedan
    cubiertas las otras dos hipótesis del maestro: el Panel desplazado con el saludo fuera de la pantalla, y el Panel
    recargando. Cambios, solo en los validadores:
    - `comun.py`: `Nodo` gana `paquete` y `enfocado` (con valor por defecto); nuevas `de_la_app`, `app_en_primer_plano`
      y `desplazar_hacia_arriba`; `textos_visibles` ya no imprime textos de otras apps (sí los de los diálogos del
      sistema de `PAQUETES_SISTEMA`), lo que vale para todos los validadores.
    - `validate41.py`:
      - `es_panel` reconoce el Panel por el saludo o por `MARCAS_PANEL`.
      - `pantalla_de_la_app` falla con «la app salió del primer plano» y no toca nada fuera de la app; la siguiente
        comprobación vuelve a abrirla.
      - `cerrar_teclado` solo actúa con un campo enfocado y nunca en el Panel.
      - `volver_al_panel` nunca pulsa Atrás en el Panel ni fuera de la app, espera a que la pantalla cambie entre un Atrás
        y otro, y sube al saludo.
      - `esperar` falla si la app pasa más de 3 s fuera.
    - Pruebas: `test_validate41.py` pasa a 28 casos; el teléfono simulado tiene ahora `package`, la pantalla de inicio, un
      Panel que se desplaza y un teclado «que no se suelta». `test_comun_fe41.py` pasa a 9. Total 289 + 1 omitida.
    - Docs: §4.10 (resultado del intento), §5.11 (ayudas, `validate41.py` y la trampa nueva) y `validation-4-1` §5 (289
      casos y casos previstos nuevos).
    - Versión: se queda en **0.14.0**. Un parche, según las reglas, no puede cambiar un contrato, y esto añade piezas a
      §5.11. FE-4.1 sigue «En curso» y la 0.14.0 es la entrada que describe sus entregables, incluido `validate41.py`. La
      app no cambia.
- **Contradicciones corregidas:**
  - La `validation-4-1` anterior creaba las fotos de prueba con Pillow (no está en el grupo `ops`), usaba `ref_cliente =
    nombre` (un segundo intento da `409 VIDEO_ELIMINADO`) y limpiaba por `q` sin mirar `ref_cliente` (podía borrar un video
    real que se llamara así); sus precondiciones no seguían el orden del contrato común (sin Gradle, dispositivo, API
    ni login) y C2 era solo manual.
  - §5.5 dejaba como ⚠ que el rumbo negativo salía «undefined» en la tarjeta de 7.14: el JS lo normaliza.
  - §4.8 y §7.6 decían que «Ver fotos» de 7.6 esperaba a FE-4.1 (deshabilitado): ya abre la Galería.
  - §5.5 y §5.6 daban las fotos de un recorrido local como `file://<ruta>` sin decir que el `WebView` de 7.14 no las
    carga (`allowFileAccess = false` desde la API 30: la causa de las miniaturas vacías del hallazgo de FE-2.1); ahora
    llegan por `https://miniaturas.local/…` (ADR-FE-36).
  - El aviso de §5.10 de que `VideoResumenDto` aún no traía `iniciado_en`, `finalizado_en`, `duracion_s`, `distancia_m`
    ni `pasos` («el lote que los necesite (FE-4.1) los añade») queda cumplido: añadidos y comprobados por `GET` en `dev`.
- **Contratos tocados (§5):** §5.6 `VideoRepository` **incompatible** (interfaz nueva; `EdicionesLocales`,
  `AssetsVideoRepository` y `FuenteRecorridos` ya no existen; `ManifestRecorrido.video(recorrido, carpeta)` quitada);
  `Foto` y `Video` ampliados con valores por defecto; modelos nuevos de `ResumenVideo.kt`. §5.5 `VideosScreen` (con
  `onNuevoVideo`), `VideoDetalleScreen` (sin `onAbrirImagen`), `GaleriaScreen` (`lugarId`, `videoId`) y `GaleriaAcciones`
  (acciones nuevas), `LugaresScreen`/`LugarFormScreen` con `onVerFotos`. §5.8 ruta `admin/imagenes?lugar={lugar}&video={video}`
  (los dos opcionales: `admin/imagenes` sigue sirviendo). §5.9 `MapaWebView(…, recursos = null)` (compatible) y
  `VideoBridge` (`pedirOtros`; `eliminarVideo` ya no sale solo; formatos de `videoJson`/`otrosJson`). §5.10 rutas, DTOs y
  mapeo nuevos. Por ser `0.x`, el cambio incompatible sube la menor.
- **Cómo se verificó (2026-10-27, worktree de FE-4.1 sobre `97791a0`, sin commit):** en Windows `testDebugUnitTest
  assembleDebug` → `BUILD SUCCESSFUL`, 337 casos, 0 fallos (41 clases); en WSL `ruff check` («All checks passed!»),
  `ruff format --check` («25 files already formatted») y `pytest` (277 passed, 1 skipped); `validate41.py --entorno
  local` → código 0 (P1; C1a 11/11; C2a 5/5; C3a 15/15; C1b, C3b y C2b omitidas; C2c manual); `jpeg_sintetico`
  decodificado con Pillow del entorno del backend (`JPEG (640, 480) L`). En `dev`, solo lecturas `GET` con el admin
  (formas de `/v1/admin/videos`, `/v1/admin/videos/{id}` y `/v1/admin/images`, que coinciden con los DTOs; sin restos
  `validacion-4-1`). `git diff --stat` igual a `--stat --ignore-cr-at-eol`.
  - **Tras el arreglo** (worktree sobre `01adb2e`, sin commit):
    - `ruff check` limpio, `ruff format --check` («25 files already formatted»), `pytest` (289 passed, 1 skipped) y
      `validate41.py --entorno local` con código 0.
    - El caso nuevo «`dumpsys` no suelta el teclado», corrido contra el `validate41.py` de `01adb2e`, da lo mismo que
      `dev`: C1b pasa y C3b y C2b fallan con «no se volvió al Panel con Atrás».
- **Pendiente:** `validate41.py --entorno dev` con el teléfono (C1b, C3b, C2b; dos pasos guiados; lo coordina el
  maestro; repetir tras el arreglo del validador) y la evidencia de C2c; sin probar en el teléfono todo lo de §4.10
  («Sin probar en el teléfono») y, del arreglo, que `uiautomator` marque `focused` en el buscador de Compose; FE-4.4
  (planificar); de FE-4.3, quitar `ManifestRecorrido.video(…)` de assets y mover `GaleriaColores` y los campos de la
  Galería a `ui/components/`.

## [0.13.1] — 2026-10-27
- Lote que la motivó: FE-3.3 (cierre: `validate33.py --entorno dev` sobre `7b275b6`).
- Qué cambió (solo documentos y la evidencia): encabezado (FE-3.3 validado en `dev`); §5.11, `validate33.py`: lo que
  quedaba «sin comprobar en `dev`» (filas de 7.10, la hoja abierta, Atrás, `input text`) comprobado, el envoltorio de
  `VALIDACION_GRADLE` de FE-3.4 sirvió tal cual y dónde se pone el nombre del recorrido en el paso guiado 1;
  `validation-3-3` §3 con la captura de C3c (`evidencia/fe-3-3/c3c-lista-y-formulario.png`); PLAN: FE-3.3 «Hecho».
- Contratos tocados (§5): ninguno (parche).
- Cómo se verificó: `validate33.py --entorno dev` con código 0 a la primera sobre `7b275b6` sin `-dirty` (2026-10-27,
  22:56–23:06 UTC, informe `FE-3.3-20261027-225637.json`, Xiaomi 23028RA60L con datos móviles): P1–P6, C1a (11/11 y 3/3),
  C2a 8/8, C3a 9/9, C1b (c1 creada en 7.4 durante `rec_0014`, 25 fotos, a 2,2 m de la primera foto; 1 enviada, 1
  aplicada), C2b (c2 creada y borrada antes de sincronizar: 1 enviada = 1 aplicada, no está en el backend) y C3b (7.10
  con c1 y c3; c3 abre «Editar alerta» y se cierra sin guardar, versión 1) en verde; la manual C3c, con la captura. Los
  pasos guiados los hizo el maestro por `adb` con la entrada en una FIFO. La limpieza borró las 3 alertas y el recorrido
  de prueba del teléfono. CI de `main` (`frontend.yml`) en verde sobre `7b275b6`.
- Pendiente: nada de FE-3.3.

## [0.13.0] — 2026-10-27

- **Lote que la motivó:** FE-3.3 (Alertas de administración sincronizadas, 7.8–7.10, y las alertas de 7.4). Se
  construyó el 2026-10-26 sobre una rama vieja de FE-3.4 (`c9c1d24`, con la hoja de 7.4 que FE-3.4 quitó antes de
  integrarse) con el número 0.12.0 provisional, y el 2026-10-27 se rebasó sobre `main` (`3b3b30c`: FE-3.4 «Hecho»,
  0.12.1); por eso es la 0.13.0.
- **Contratos que consume:** backend §4.11, «Para la app (FE-3.3 y FE-3.6)» (una sola operación por id, la última; un
  `eliminar` de un id desconocido no deja rastro; `estado = error` no se arregla reintentando), §5.3 `GET /v1/alerts` y
  §5.5, «Alertas: `/v1/admin/alerts` (BE-3.3)» (backend 0.14.1, BE-3.3 «Hecho»). Los docs de la app los enlazan (§4.9,
  §5.10, `validation-3-3`).
- **Decisiones (aceptadas por el maestro el 2026-10-26):** ADR-FE-33 — el almacén local de las alertas del editor es un
  archivo JSON con escritura atómica (`files/alertas/editor.json`) detrás de `AlmacenAlertas`, **sin Room** (mismo
  patrón que los manifests, probado en la JVM, sin dependencias nuevas; Room queda como alternativa reversible).
  ADR-FE-34 — pendientes con una operación por id (crear y borrar → un `eliminar`, que siempre se envía; un `ok` solo
  saca el pendiente si no cambió durante el envío), un repositorio único por proceso para 7.4, 7.8 y 7.10, 7.4 guarda en
  local y solo lee la ruta pública `GET /v1/alerts` (sin riesgo de `401` que saque 7.4 de la pila: guía de §4.8), y
  `CambiosAlertas` para que el Panel recargue «Alertas activas».
- **Qué cambió:**
  - Código (`project/`): `domain/model/Alerta.kt` (vigencia, `version`, `actualizadoEnMs`; `OperacionAlerta`);
    `domain/model/PosicionAdmin.kt`; `data/repository/AlertasRepository.kt` (`AlertasRepository`, `EstadoAlertas`,
    `ResultadoSincronizacion`, `ReglasAlertas`, `CambiosAlertas`); `data/local/AlmacenAlertas.kt`;
    `data/remote/RemoteAlertasRepository.kt` (y `object Alertas`); `CampusApi` (`alertasPublicas`, `alertasAdmin`,
    `sincronizarAlertas`), `DtosApi` (6 DTOs), `MapeoDatosApi` (`alerta` ampliado, `entradaAlerta`, `cambioAlerta`,
    `milisAIso`); `ui/admin/mapa/` (`EditorMapaViewModel` y `EditorMapaScreen` reescritos sobre el repositorio, sin datos
    de ejemplo, con lugares reales, «Mi posición», «Ver lista», `Toast` de la sincronización y ajuste en el mapa;
    `AlertaFormSheet` con dictado, «Escuchar cómo sonará», vigencia y «Ajustar en el mapa»; nuevos `FormularioAlerta.kt`,
    `PiezasMapaAlertas.kt`, `AlertasViewModel.kt` y `AlertasScreen.kt` —vista 7.10—); `assets/editor_mapa.js` (modo
    `ajustar`, `ajustarBorrador`, `verAlerta`, `nuevaAlerta`, puente `ajusteTerminado`); `MainActivity` (`posicionAdmin`
    real, `onVerLista`, ruta `admin/mapa/alertas`); `RecoleccionViewModel`, `RecoleccionState` y `RecoleccionScreen` (7.4:
    alertas en el repositorio, las existentes por `GET /v1/alerts`, `PosicionAdmin`, `errorVigenciaAlerta`; sin
    `validarMensajeAlerta`); `PanelAdminViewModel` (`cambiosAlertas`); `VoiceController.listen(…, soloMejor = false)`.
    Sin dependencias nuevas de Gradle.
  - Pruebas JVM nuevas: `ReglasAlertasTest` (8), `RemoteAlertasRepositoryTest` (11), `AlmacenAlertasTest` (3),
    `FormularioAlertaTest` (9). Total 303; las 272 de `main` no cambiaron (305 sobre la rama vieja de FE-3.4).
  - Validadores: `src/ops/validate33.py` (C1a, C2a y C3a en la JVM; en `dev`, C1b —alerta creada en 7.4 que llega al
    backend a ≤ 30 m de la primera foto—, C2b —crear y borrar sin rastro: ni en la lista, ni en las diferencias de
    `GET /v1/alerts?desde=`, y `app.log` sin errores— y C3b —7.10 lista la alerta creada por la API y abre su edición—,
    con tres pasos guiados; manual C3c); `tests/ops/test_validate33.py` (12). Total 253. Sin ayudas nuevas en `comun.py`.
  - Documento: encabezado; §3.2 (paquetes, `data/local`, tag `Alertas` y líneas de `RecoleccionVM`); §4.1 (303 casos);
    §4.8 (guía para FE-3.3 marcada como hecha); **§4.9 nuevo** (con la trampa «7.4 y la sesión» y «Para los lotes
    siguientes»: FE-3.6 y FE-4.3); §5.1 (variantes); §5.2 (`VoiceController`, recolección: alertas, retomar); §5.5 (filas
    de `AlertaFormSheet`, `AlertasScreen` y `EditorMapaScreen`; `AlertaFormSheet` en detalle; `FormularioAlerta`,
    `FiltrosAlertas`, `TextosAlertas`; piezas de los mapas; `EditorMapaViewModel`; `EditorMapaScreen` y `EditorBridge`;
    «Lista de alertas (7.10)»; Panel; `RecoleccionScreen`); §5.6 (`AlertasRepository`, modelos, `Alerta` en detalle,
    `OperacionAlerta`/`EstadoAlertas`/`ReglasAlertas`, `AlmacenAlertas`, `PosicionAdmin`); §5.8 (`admin/mapa`,
    `admin/mapa/alertas`, restauración); §5.9 (`EditorBridge`); §5.10 (encabezado, `CampusApi`, piezas, DTOs, mapeo, nueva
    «Alertas de administración», «Alertas sin conexión», «Editor de alertas»); §5.11 (`validate33.py`, 253 casos,
    trampas, también las de MIUI de FE-3.4); §7.4, §7.8, §7.9 y §7.10 (implementación actual); ADR-FE-17 y ADR-FE-32
    (notas); ADR-FE-33 y ADR-FE-34 nuevas; R9.
  - `validation-3-3` reescrita como `validation-3-4`: entornos `local` y `dev`; precondiciones en el orden del contrato
    común (P1 Gradle, P2 dispositivo, P3 API, P4 login, P5 FE-1.2, P6 BE-3.3 con una sonda sin rastro); C1 → C1a, C1b; C2
    → C2a, C2b; C3 → C3a, C3b (automática) y C3c manual (capturas); §4 con el borrado por mensaje exacto y del recorrido;
    §5 con variables, preparación, ejecución (también por `adb` con una FIFO, como `validation-2-2` §5), salida esperada
    y casos previstos.
  - `PLAN.md`: «Alineado con» v0.13.0; FE-3.3 «En curso» (§3: falta `dev`; el paso guiado por `adb` con una FIFO);
    §2.2 FE-3.3 («Hecho en el código», sin Room) y FE-3.6 (la caché pública decide su almacenamiento; piezas ya
    disponibles).
  - **Rebase sobre `main` (2026-10-27):** el código se aplicó sin conflictos (FE-3.3 no usa nada de la hoja de 7.4 que
    FE-3.4 retiró; `RecoleccionScreen` solo gana `errorVigencia`); los conflictos fueron solo de documentos (encabezado,
    §3.2, §4.1, §4.8, §5.1, §5.6, §5.11, §7.4, esta entrada y PLAN §3). Donde chocaban, el texto de `main` sobre FE-3.4
    manda y encima van las adiciones de FE-3.3; se reescribieron las frases de FE-3.3 que suponían que la hoja existía:
    la trampa «7.4 y la sesión» (de §4.8 pasa a §4.9 y dice lo que hace 7.4 desde FE-3.3: alertas en disco y solo la
    ruta pública `GET /v1/alerts`), las listas de §5.1 (`estado`, `Factory`, recolección del estado, `…Acciones`), las
    tablas de §5.6, §7.4 («Implementación actual» y «Pendiente»), la nota que FE-3.3 había puesto en ADR-FE-31 (quitada:
    la ADR está retirada) y la referencia de ADR-FE-34 a ella. La firma de `RecoleccionScreen` de §5.5 queda la de
    `main`. Versión: 0.12.0 → 0.13.0.
- **Contradicciones corregidas:**
  - `validation-3-3` P2 pedía `POST /v1/admin/alerts/sincronizar` con `{"cambios": []}` → 200, pero el backend exige de 1
    a 100 cambios (vacío → `422`, backend §5.5): ahora la sonda es un `eliminar` de un UUID desconocido (`ok`, sin rastro).
  - `validation-3-3` §4 creaba c3 con `PUT /v1/admin/alerts/{uuid}` (no hay ayuda para `PUT` en `comun.py`): ahora con
    `sincronizar` (`upsert`). Además solo preveía `dev` y C1/C2 sin dividir.
  - PLAN §2.2 y ARCHITECTURE §3.2/§5.10 daban Room por hecho para FE-3.3 (y §5.10 una base `campus_locator.db`):
    ADR-FE-33 lo cambia; la caché pública queda para FE-3.6.
  - §7.8 decía que `Alerta.kt` tiene «Modelos `Alerta` y `Lugar`»: `Lugar` desapareció en FE-3.4.
  - ADR-FE-17 y §5.2 («Retomar») decían que las alertas de 7.4 se pierden al matar el proceso, y R9 las contaba entre lo
    que se pierde: ya no.
  - §5.5 daba `EditorMapaScreen(vm = viewModel())`, la posición de la hoja con `%.5f` (con el idioma del teléfono) y que
    `sincronizando` y `error` no llegan al mapa ni se ven: ahora `Factory`, 6 decimales con punto y un `Toast`.
  - Al rebasar (2026-10-27): PLAN «Alineado con» seguía en la versión de antes de FE-3.3 (ahora v0.13.0); la fila de
    `AlertasRepository` de §5.6 decía que 7.4 lo recibe «por su `Factory`», pero `RecoleccionViewModel` no tiene
    `Factory` (lo toma en su constructor con `Alertas.de(app)`, como dice §5.2); y la trampa «7.4 y la sesión» de §4.8,
    ADR-FE-34 y la nota de ADR-FE-31 daban por hecho que 7.4 hacía llamadas protegidas por la hoja de FE-3.4, que nunca
    llegó a `main`.
- **Contratos tocados (§5):** §5.2 (`VoiceController.listen(…, soloMejor = false)`); §5.5 (`AlertaFormSheet` con
  `errorVigencia` y `onAjustarEnMapa`, con valores por defecto; `EditorMapaContent` con cuatro parámetros nuevos con
  valor por defecto; `AlertasScreen` nueva; `PanelAdminViewModel` con `cambiosAlertas`; la firma de `RecoleccionScreen`
  no cambia); §5.6 (`AlertasRepository`, `Alerta` ampliada con valores por defecto, `OperacionAlerta`, `EstadoAlertas`,
  `AlmacenAlertas` y el archivo nuevo `files/alertas/editor.json`, `PosicionAdmin`); §5.8 (ruta nueva
  `admin/mapa/alertas`); §5.9 (`EditorBridge`: `ajustarBorrador`, `verAlerta`, `nuevaAlerta`, `ajusteTerminado`); §5.10
  (rutas, DTOs y mapeo de alertas). Todo compatible con lo anterior (menor).
- **Cómo se verificó (2026-10-26, worktree de FE-3.3 sobre `c9c1d24`, sin commit):** `testDebugUnitTest assembleDebug`
  en Windows (también con `--rerun-tasks`) → `BUILD SUCCESSFUL`, 305 casos, 0 fallos, sin avisos nuevos del compilador;
  en WSL `ruff check` («All checks passed!»), `ruff format --check` («22 files already formatted») y `pytest` (253) en
  verde; `validate33.py --entorno local` → código 0 (P1; C1a 11/11 y 3/3; C2a 8/8; C3a 9/9; C1b, C2b y C3b omitidas;
  C3c manual). `editor_mapa.js` en el modo demo de un Chromium de escritorio (servido en `127.0.0.1`): las funciones
  nuevas existen y el ajuste, «ver» y «nueva» funcionan sin errores de consola. `git diff --stat` igual a
  `--stat --ignore-cr-at-eol`. **Tras el rebase (2026-10-27, sobre `3b3b30c`, sin commit):** `testDebugUnitTest
  assembleDebug` en Windows → `BUILD SUCCESSFUL`, 303 casos, 0 fallos (XML de `app/build/test-results/testDebugUnitTest`:
  37 clases; `FormularioLugarTest` 10); en WSL `ruff check` («All checks passed!»), `ruff format --check` («22 files
  already formatted») y `pytest` (253 passed); `validate33.py --entorno local` → código 0 (P1; C1a 11/11 y 3/3; C2a 8/8;
  C3a 9/9; C1b, C2b y C3b omitidas; C3c manual). `git grep` de la hoja retirada en `FRONTEND_KOTLIN` deja lo mismo que
  en `main`.
- **Pendiente:** validar en `dev` con el teléfono (C1b, C2b, C3b y C3c; lo coordina el maestro); sin probar en el
  teléfono el dictado, la voz y el `DatePicker` de la hoja, el modo ajustar en el `WebView`, TalkBack en 7.10 y que
  uiautomator vuelque sus filas y la hoja.

## [0.12.1] — 2026-10-27
- Lote que la motivó: FE-3.4 (cierre: `validate34.py --entorno dev` sobre `8317f56`).
- Qué cambió (solo documentos): encabezado y §4.8 con lo validado en `dev` y lo que sigue sin comprobar (la recarga del
  Panel); §5.10 (`crear` y el `409` comprobados contra el backend real); §5.11, trampas de `validate34.py` vistas en el
  teléfono: no contestar la pregunta hablada de Destino en C1c, MIUI rechazando `installDebug` sin diálogo (y el
  envoltorio de `VALIDACION_GRADLE` que usó el maestro) y el Wi-Fi de visitantes sin salida; `validation-3-4` §5, paso
  guiado 2; PLAN: FE-3.4 «Hecho».
- Contratos tocados (§5): ninguno (parche).
- Cómo se verificó: en `dev`, con el Xiaomi 23028RA60L y datos móviles, sobre `8317f56` sin `-dirty`: corrida completa
  (informe `FE-3.4-20261027-221328.json`, código 1) con P1–P6, C1a 11/11, C2a 10/10, C3a 5/5, C1b, C2b y C3b en verde y
  C1c en falla porque la persona contestó por voz en Destino; `--solo C1b,C2b,C1c` (informe
  `FE-3.4-20261027-223100.json`) con código 0. Antes, dos intentos con código 3 (Wi-Fi sin salida;
  `INSTALL_FAILED_USER_RESTRICTED`). Los pasos guiados los hizo el maestro por `adb` salvo la voz «dos» y el nombre de
  C3b, que escribió la persona (quedó «VALIDACION-3-4-DUP», sin tilde).
- Pendiente: probar en el teléfono la recarga del Panel al volver de 7.6/7.7.

## [0.12.0] — 2026-10-27

- **Lote que la motivó:** FE-3.4 (Lugares de administración, 7.6 y 7.7). Además, el entregable que pidió el maestro al
  cerrar FE-2.2: «Lugares registrados» del Panel al día al volver de 7.6/7.7.
- **Contratos que consume:** backend §5.5, «Lugares: `/v1/admin/places` (BE-3.1)» (backend 0.11.0: `LugarEntrada`,
  `LugarAdmin`, `409 NOMBRE_DUPLICADO` con `detalle: null`, `PUT` que reemplaza todo, `DELETE` idempotente) y §5.3,
  `GET /v1/places` (para la validación). Los docs de la app los enlazan sin copiarlos (§4.8, §5.10, `validation-3-4`).
- **Decisiones (aceptadas por el maestro el 2026-10-26; ADR-FE-30 y 32):** un solo modelo de lugar (`Lugar`
  desaparece; `LugarDestino` no cambia y lo envuelve `LugarAdmin` en la administración; renombrarlo a `Lugar` y mover a
  `ui/components/` lo de Destino que usa 7.6 pasan a FE-4.3); la coordenada se redondea a 6 decimales y el pie «Punto:
  …» muestra exactamente lo que se guarda; la unicidad del nombre la decide el backend (`409` bajo el nombre); un
  contador de cambios de lugares (`CambiosLugares`) recarga 7.6 y, en `ON_RESUME`, el «Resumen rápido» del Panel solo si
  cambiaron los lugares (enmienda ADR-FE-28). Decisión del usuario del 2026-10-27: **«Marcar punto de interés» (7.4) no
  se implementa** (ADR-FE-31, que lo ponía en una hoja de 7.4, queda retirada; abajo, «Retirado antes de integrar»).
- **Qué cambió:**
  - Código (`project/`): `domain/model/LugarAdmin.kt` (`LugarAdmin`, `DatosLugar`); `Alerta.kt` sin `Lugar`;
    `LugarDestino.kt` (solo KDoc); `EditorMapaViewModel` con `List<LugarDestino>`; `data/repository/LugaresAdminRepository.kt`
    (interfaz, `ContadorCambios`, `CambiosLugares`); `data/remote/RemoteLugaresAdminRepository.kt`; `CampusApi`
    (`lugaresAdmin`, `crearLugar`, `reemplazarLugar`, `borrarLugar`), `DtosApi` (`LugarAdminDto`,
    `ListaLugaresAdminDto`, `LugarEntradaDto`), `MapeoDatosApi` (`lugarAdmin`, `entradaLugar`); `ui/admin/lugares/`
    (7.6: `LugaresScreen`, `LugaresState`, `LugaresViewModel`; 7.7: `LugarFormScreen`, `LugarFormState`,
    `LugarFormViewModel`; `FormularioLugar`, `ErroresLugarMapeo`; `componentes/MapaLugares.kt`);
    `assets/lugar_mapa.html` y `lugar_mapa.js` (puente `LugarBridge`); `MainActivity` (ruta `admin/lugares` real y
    `admin/lugares/form?id={id}`); `PanelAdminViewModel` (`cambiosLugares`, `debeRecargarResumen`). 7.4
    (`RecoleccionScreen.kt`) no cambia: es igual al de `main`.
  - Pruebas JVM nuevas: `RemoteLugaresAdminRepositoryTest` (11), `FormularioLugarTest` (10), `ErroresLugarTest` (5),
    `RecargaResumenTest` (3). Total 272; las 243 de antes no cambiaron.
  - Validadores: `src/ops/validate34.py` (C1a, C2a y C3a en la JVM; en `dev`, C1b —crear en 7.7 y verlo en
    `GET /v1/places`—, C2b —la posición del pie es la guardada—, C1c —la fila en Selección de destino— y C3b —el `409`
    en el formulario—, con tres pasos guiados y el script tocando «Guardar»); `tests/ops/test_validate34.py` (19). Total
    241. Sin ayudas nuevas en `comun.py`.
  - Documento: encabezado; §3.2 (paquete, pruebas, tag `Lugares`, `lugar_mapa`); §4 (componentes de Destino
    reutilizados); §4.1 (272 casos); §4.7 (trampa del Panel enmendada); **§4.8 nuevo** (con «Para los lotes
    siguientes»: qué tocar en FE-3.3, FE-4.1 y FE-4.3, con las listas de archivos de `grep`); §5.1 (variantes); §5.5 (filas
    nuevas, Panel —constructor, `cargarResumen`, recarga por lugares, «Qué se recarga y cuándo», `ChipTiempoReal`,
    `onLugares`—, la sección «Lugares de administración» y una nota en «`RecoleccionScreen`»: el botón descartado sigue
    deshabilitado); §5.6 (`LugaresAdminRepository`, `LugarAdmin`, `DatosLugar`, `CambiosLugares`, «Un solo modelo de
    lugar» en lugar del ⚠);
    §5.7 (`filtrar` en 7.6); §5.8 (rutas, argumento `id`, *placeholders*, sin guarda); §5.9 (`LugarBridge`); §5.10
    (encabezado, `CampusApi`, piezas, «Lugares de administración», DTOs, fila 409/422, mapeo, obligatorios); §5.11
    (`validate34.py`, 241 casos, trampas); §7.4 (el botón del diseño, descartado por el usuario); §7.6 y §7.7
    (implementación actual); ADR-FE-28 enmendada; ADR-FE-30 y 32 nuevas; ADR-FE-31 nueva y retirada.
  - `validation-3-4` reescrita como `validation-2-2`: entornos `local` y `dev`; precondiciones en el orden del contrato
    común (P1 Gradle, P2 dispositivo, P3 API, P4 login, P5 FE-1.2, P6 BE-3.1); C1 → C1a, C1b, C1c; C2 → C2a, C2b; C3 →
    C3a, C3b (automática, con paso guiado); §4 con el borrado por nombre exacto; §5 con variables, preparación,
    ejecución, salida esperada y casos previstos.
  - `PLAN.md`: FE-3.4 en «En curso» (§3; falta `dev`); §2.2 FE-3.4 («Hecho en el código» y «Marcar punto de interés»
    retirado de los entregables); FE-3.3 (lugares reales en el editor); FE-4.1 («Ver fotos» de 7.6 y el enlace a la
    galería de 7.7); FE-4.3 (renombrar `LugarDestino`, mover los componentes de Destino, pasar 7.3 a lugares reales y
    quitar de 7.4 el botón deshabilitado «Marcar punto de interés»).
  - **Retirado antes de integrar (decisión del usuario, 2026-10-27: no se implementa «Marcar punto de interés»):** la
    hoja de 7.4 que el lote había construido y que nunca llegó a `main`: `ui/admin/lugares/PuntoInteresSheet.kt` y
    `PuntoInteresViewModel.kt` (con `PuntoInteresUiState`, `PuntoInteresAcciones` y `lugaresPorCercania`),
    `FormularioLugar.moverA`, las pruebas `moverA_conservaTodoMenosLaCoordenada_redondeada` y
    `lugaresPorCercania_ordenaPorDistanciaAlPunto` de `FormularioLugarTest` (12 → 10; total 274 → 272), el parámetro
    `puntoInteres` de `RecoleccionScreen` y su `Toast` (el botón vuelve a dibujarse deshabilitado con «Próximamente»,
    como antes), las menciones en los KDoc y, en estos docs, sus filas de §5.5, sus trampas de §4.8 y el criterio
    pendiente de PLAN (`validation-3-4` espera ahora 272 casos y C2a 10/10). ADR-FE-31 queda como retirada. Así FE-3.4
    ya no toca 7.4.
- **Contradicciones corregidas:**
  - `validation-3-4` C3 decía que el `409` muestra `detalle.campos`: el backend lo da con `detalle: null` (backend §5.5 y
    §5.6); la app reconoce el campo por el `codigo`. También tenía las precondiciones fuera del orden del contrato
    común (y sin P3), solo `dev`, C1b con la acción de TalkBack «Ir a un lugar» (con TalkBack 17 no se consiguió, §4.5:
    ahora la voz «dos») y C3 manual; no tenía preparación ni salida esperada.
  - §5.10, «Errores → modelos de la app»: «`409` / `422` → mensaje del campo afectado (`detalle.campos`)» no vale para
    el `409`; ahora lo dice.
  - §5.8 y §5.5 (Panel) contaban `admin/lugares` como *placeholder*; §5.6 tenía el ⚠ de `Lugar` y `LugarDestino` y la
    fila de `LugaresRepository` decía «futuras 7.6/7.7» (la administración usa otro repositorio).
  - ADR-FE-28, §4.7 y §5.5 (`ChipTiempoReal`) decían que el Panel solo pide el backend al abrirse: desde ahora también al
    volver si cambiaron los lugares.
  - §5.6 decía que `LugaresRepositoryStub` no se usa en la app desde FE-3.1, pero la `Factory` de 7.3
    (`UbicacionManualViewModel`) lo crea (lo decía bien §5.5, «UbicacionManual»; comprobado con `grep`): 7.3 dibuja
    los 6 lugares de ejemplo como referencia. Corregido en §5.6 y anotado en §4.8 y PLAN FE-4.3 (sin cambio de código).
- **Contratos tocados (§5):** §5.5 (piezas nuevas; `PanelAdminViewModel` con `cambiosLugares`; la firma de
  `RecoleccionScreen` no cambia); §5.6 (`LugaresAdminRepository`, `LugarAdmin`, `DatosLugar`,
  `CambiosLugares`; `Lugar` eliminado); §5.8 (rutas nuevas); §5.9 (`LugarBridge`); §5.10 (rutas, DTOs y mapeo).
- **Cómo se verificó:** el 2026-10-26 (worktree de FE-3.4 sobre `e56e211`, sin commit, todavía con la hoja de 7.4):
  `testDebugUnitTest assembleDebug` en Windows (`--rerun-tasks`) → `BUILD SUCCESSFUL`, 274 casos, 0 fallos; en WSL
  `ruff check`, `ruff format --check` («20 files already formatted») y `pytest` (241) en verde; `validate34.py --entorno
  local` → código 0 (C1a 11/11, C2a 12/12, C3a 5/5). El 2026-10-27, tras retirar la hoja (el maestro, en el worktree
  rebasado sobre `main`, sin commit): `testDebugUnitTest assembleDebug` en Windows → `BUILD SUCCESSFUL`, 272 casos,
  0 fallos (`FormularioLugarTest` 10); `pytest` sigue en 241. `validate34.py --entorno local` **no se repitió** tras
  retirar la hoja (C2a exige como mínimo 8 casos de `FormularioLugarTest`; lo cubre la ejecución en `dev`).
- **Pendiente:** `validate34.py --entorno dev` con el Xiaomi (lo coordina el maestro); probar en el teléfono las vistas,
  la recarga del Panel y `lugar_mapa.js` (no se ejecutó en ninguna parte); «Ver fotos» (FE-4.1); renombrar
  `LugarDestino` y quitar de 7.4 el botón deshabilitado (FE-4.3); lugares reales en el editor de mapa (FE-3.3).

## [0.11.0] — 2026-10-27
- Lote que la motivó: ninguno; pedido del usuario en el día de campo, para comparar la posición que da `POST
  /v1/localize` con el punto real.
- Qué cambió: la vista 6.3 muestra, debajo del título, el punto estimado en letra pequeña («Punto estimado: 6.20131,
  -75.57897», 14 sp, `TextoSecundario`). Campo nuevo `DescripcionUbicacion.coordenadas` (por defecto `null`) y función
  `DescribirUbicacion.coordenadas(lat, lng)` (5 decimales, `Locale.ROOT`). No se dice en voz alta.
- Contratos tocados (§5): §5.7 (`DescripcionUbicacion`, reglas de `DescribirUbicacion`) y la pantalla de la 6.3.
- Cómo se verificó: `DescribirUbicacionTest` (con posición, el texto exacto; sin coincidencias, `null`) y
  `assembleDebug`. En el teléfono, sin comprobar.
- Pendiente: decidir si se queda en la versión final o se esconde detrás de un modo de depuración.

## [0.10.1] — 2026-10-26
- Lote que la motivó: FE-2.2 (cierre).
- Qué cambió (solo documentos; el código validado es el de `cf4fcbb`):
  - `PLAN.md` §3: FE-2.2 pasa a «Hecho» (`cf4fcbb` 2026-10-26, ARCHITECTURE 0.10.1), con el informe, el primer
    intento con código 3 por `INSTALL_FAILED_USER_RESTRICTED`, cómo se hizo el paso guiado (por `adb`, Enter por una
    FIFO), lo que sigue sin comprobar y los 12 recorridos viejos que quedan en el teléfono.
  - ARCHITECTURE: encabezado; §4.7 con lo validado en `dev` (BE-2.3 ya «Hecho»; qué quedó comprobado en el teléfono y
    qué no; que la relectura al volver de 7.5 queda deducida de 69 → 79); §5.5 («`RecoleccionScreen`»: dónde se cambia
    el intervalo, que «Ajustes» abre un *placeholder* y deja la grabación en pausa, el aviso «No se pudo tomar la foto.»
    y su origen en `onFotoFallida()`, y el «Cada» repetido —«Cada Cada 3 s» en la fila del intervalo, en las opciones del
    selector y en la tarjeta—, comprobado en pantalla con el volcado de uiautomator del maestro, con los tres sitios del
    código); §5.8 (`onAjustes` de 7.4); §5.10 «Panel» (comprobado contra el backend real con `ultimo_video = null`);
    §5.11 (trampas de `validate22.py`: lo comprobado en `dev`, el paso guiado por `adb` con una FIFO).
  - `validation-2-2` §5: consejos para el paso guiado en 7.4, casos previstos al día y el resultado de la validación.
  - `PLAN.md` §2.2 FE-4.3: tarea nueva, quitar el «Cada» repetido de 7.4 (una línea en cada uno de los tres sitios).
- Contratos tocados (§5): ninguno (parche: aclaraciones y entradas que pasan de «sin comprobar» a comprobadas).
- Cómo se verificó: `validate22.py --entorno dev` con código 0 sobre `cf4fcbb` (sin `-dirty`; `main` = FE-2.2 `2ecbb52`
  + INF-3.1 + cierre de BE-2.3), informe `.validacion/FE-2.2-20261026-184835.json` (18:48–18:54 UTC), Xiaomi
  23028RA60L (Android 14), hecho por el maestro: P1–P6, C1a 11/11 y 6/6, C2a 5/5, C1b (0 fotos, 1 lugar, 0 alertas, sin
  video) y C2b (79 = 69 + 10 de `rec_0014` «validacion-2-2»); limpieza completa.
- Pendiente: el texto de la fecha del último video en el teléfono (`dev` no tenía videos; lo cubre `TextosResumenTest`
  en la JVM); la recarga de «Lugares registrados» al volver de 7.6/7.7 (entregable de FE-3.4); el «Cada Cada 3 s» de 7.4
  (FE-4.3) y la causa del «No se pudo tomar la foto.» al empezar (sin mirar `app.log`).

## [0.10.0] — 2026-10-26

- **Lote que la motivó:** FE-2.2 (Panel con datos reales). Además, solo en documentos, la decisión abierta 18 que el
  usuario resolvió hoy (abajo).
- **Contrato que consume:** backend §5.5, subsección «`GET /v1/admin/stats` (BE-2.3)» (backend 0.13.0), que fija qué
  video es el último, qué cuenta cada total, el formato de `creado_en` y los errores. Los docs de la app lo enlazan
  (§4.7, §5.6, §5.10 «Panel», ADR-FE-28, `validation-2-2`) sin copiarlo; `isoAMilis` acepta exactamente su formato de
  fecha (UTC con `Z`, sin fracciones).
- **Decisión del usuario del 2026-10-26** (decisión abierta 18, Inicio, para FE-3.5). Pregunta del maestro: «Decisión
  abierta 18 (Inicio) para FE-3.5: ¿cómo debe ser la pantalla de Inicio?», opciones «Dos botones (Recomendado)» / «Orbe
  único» / «Decidir después». Respuesta literal: «Orbe único» (como hoy: un orbe que lleva a Ubicarme; «Ir a un lugar»
  y «mapa» por voz o por acciones de TalkBack). También decidió que FE-3.5 se hace después del día de campo (desde el
  2026-10-28). Queda en ADR-FE-29 y §8.2 (18 resuelta); FE-3.5 debe resolver cómo llega TalkBack a «Ir a un lugar» y
  «Ver mapa» (hallazgo de FE-3.1, §4.5), sin decidirlo aquí.
- **Qué cambió:**
  - Código: `RemoteAdminRepository` (`data/remote/`, nuevo): `GET /v1/admin/stats` con `MapeoDatosApi.resumenAdmin` y,
    después de validar la respuesta, las fotos pendientes de la cola local (`fotosPendientes: suspend () -> Int`).
    `CampusApi.estadisticas()` (`@GET("admin/stats")`). `MapeoDatosApi.resumenAdmin`: con `ultimo_video` presente,
    `numero` obligatorio. `fotosPendientesDe(recorridos)` (función de nivel superior de `AlmacenRecorridos.kt`; la usa
    `contarFotosPendientes()`). Panel: la `Factory` usa `RemoteAdminRepository(fotosPendientes = {
    Subidas.almacen.contarFotosPendientes() })` (antes `AdminRepositoryStub`); `alReanudar()` (lo llama la pantalla en
    cada `ON_RESUME`) y el recolector de la cola recalculan tarjeta y «Fotos pendientes» (`resumenConPendientes`) sin
    llamar al backend; `cargarResumen()` relanza `CancellationException` y no muestra su error con una sesión perdida
    (`errorVisibleDelResumen`). `TextosResumen` (`ui/admin/panel/`, nuevo): `numero()` y `fecha()` salen de la pantalla
    (antes privadas con `DateUtils`) para probarlos en la JVM. `AdminRepositoryStub` queda sin uso.
  - Pruebas JVM nuevas: `RemoteAdminRepositoryTest` (11), `TextosResumenTest` (6), `PendientesPanelTest` (5). Total 243.
  - Validadores: `src/ops/validate22.py` (C1a y C2a en la JVM; en `dev`, C1b —Panel leído con uiautomator = `GET
    /v1/admin/stats` antes y después, con el lugar de prueba `validacion-2-2-lugar`— y C2b —paso guiado: grabar
    `validacion-2-2` y «Guardar y subir después»; «Fotos pendientes» = manifests del teléfono; borra del teléfono el
    recorrido de prueba al terminar—); `tests/ops/test_validate22.py` (32). Total 222. Sin ayudas nuevas en `comun.py`.
  - Documento: §4.7 nuevo; encabezado; §3.2 (pruebas); §4.1 (243 casos y la firma de la ayuda de pruebas
    `ManifestPrueba`, que solo se nombraba desde FE-2.1); §5.5 (`PanelAdminViewModel`: `Factory`, `alReanudar`,
    `resumenConPendientes`, `cargarResumen`, qué se recarga y cuándo, con su consecuencia para FE-3.4; `PanelAdminScreen`: `ON_RESUME`,
    `TextosResumen`, `content-desc` de `TileDato`; «Inicio»: decisión 18); §5.6 (`AdminRepository` real, `ResumenAdmin`
    sin el ⚠ de orígenes); §5.8 (`admin/panel` relee al volver); §5.10 (encabezado, `CampusApi`, `RemoteAdminRepository`,
    «Panel» nuevo, mapeo y obligatorios de `stats`, regla de «Fotos pendientes», `fotosPendientesDe`, qué salta
    `listar()`); §5.11 (`validate22.py`, trampas, 222 casos); §6.1 (nota de la decisión 18); §7.2; ADR-FE-18 (referencia
    a la 18); ADR-FE-28 y ADR-FE-29 nuevas; §8.2 (18 resuelta).
  - `validation-2-2` reescrita: entornos `local` y `dev`; precondiciones en el orden del contrato común (P1 Gradle, P2
    dispositivo, P3 FE-2.1, P4 API, P5 login, P6 BE-2.3); C1 → C1a (JVM) y C1b (teléfono); C2 → C2a (JVM) y C2b (paso
    guiado); §4 sin alertas; §5 con variables, preparación y salida esperada.
  - `PLAN.md`: FE-2.2 pasa a «En curso» (§3); FE-3.5 con la decisión 18 resuelta (§2.2 y §3); FE-3.4 (§2.2) con un
    entregable nuevo por decisión del maestro: «Lugares registrados» del Panel al día al volver de 7.6/7.7 (hoy el Panel
    no recarga el backend al volver, ADR-FE-28).
- **Contradicciones corregidas:**
  - `validation-2-2` §4 creaba una alerta con `PUT /v1/admin/alerts/{id}`: esa ruta es de BE-3.3, sin implementar
    (responde `404`, backend §5.5). Ahora solo crea el lugar de prueba; `alertas_activas` se compara tal cual (0 mientras
    no exista BE-3.3).
  - `validation-2-2` evaluaba primero los otros lotes (P1 FE-2.1, P2 BE-2.3) y después la máquina (P3), al revés que el
    contrato común; con credenciales malas en P2 daba 3 dentro de una precondición de otro lote; contaba solo
    `"sync": "pendiente"` (la app cuenta lo que no es `sync = subida`); dejaba el video de prueba para que la persona lo
    descartara a mano; y no tenía entorno `local`, preparación ni salida esperada.
  - §5.10 decía que «Fotos pendientes» = `photos[].sync = pendiente`; el código (`RecorridoLocal.fotosPendientes`)
    cuenta las fotos sin `sync = subida` (iguales en los manifests de la app; ahora se dice así).
  - §5.5 (`PanelAdminScreen`) contaba `onRecolector` entre las rutas *placeholder*: abre 7.3 (`admin/ubicacion-manual`).
  - §5.6 decía que FE-2.2 podía usar `contarPendientes()` o `contarFotosPendientes()`; usa el segundo.
- **Contratos tocados (§5):** §5.5 (`PanelAdminViewModel.alReanudar()` nuevo; `cargarResumen()` ya no marca error con
  una sesión perdida; `TextosResumen` nuevo, `internal`); §5.6 (`AdminRepository` real, sin cambiar la interfaz); §5.10
  (ruta `estadisticas()`, `RemoteAdminRepository`, `fotosPendientesDe`; `resumenAdmin` rechaza `ultimo_video` sin
  `numero`, compatible con el contrato del backend); §5.11 (validador nuevo). Pieza, ruta y ADR nuevos: sube la menor.
- **Cómo se verificó:** en Windows, `.\gradlew.bat --console=plain testDebugUnitTest assembleDebug` con el JBR 21
  (`C:\Users\frank\.jdks\jbr-21.0.11`) → `BUILD SUCCESSFUL`, 243 casos sin fallos. En WSL, `uv run --frozen ruff check .`
  («All checks passed!»), `ruff format --check .` («18 files already formatted»), `pytest -q` (222 passed) y
  `validate22.py --entorno local` → código 0 (P1; C1a 11/11 y 6/6; C2a 5/5; C1b y C2b omitidas). Sin teléfono y sin
  tocar `dev` (BE-2.3 se construye en paralelo y no está desplegado; lo coordina el maestro).
- **Pendiente:** `validate22.py --entorno dev` con el Xiaomi cuando BE-2.3 esté «Hecho» (C1b y C2b; `validation-2-2`
  §5). Sin comprobar en el teléfono: el `content-desc` de los `TileDato` con uiautomator, el formato «d MMM» del
  Android del teléfono, `adb shell date +%z` y `run-as … rm -rf` en MIUI, y que `ON_RESUME` relea la cola al volver de
  7.5. Esta entrada es autocontenida: si al integrarla hace falta otro número (p. ej. por un parche de FE-3.2 en
  `main`), se renumera sin cambiar su contenido.

## [0.9.2] — 2026-10-26
- Lote que la motivó: FE-3.2 (sigue «En curso»), prueba de humo en el teléfono pedida por el usuario.
- Qué cambió: §4.6 y la fila FE-3.2 de PLAN §3 anotan la prueba de Ubicarme en casa (Xiaomi 23028RA60L, APK de
  `076c853`, `embedding` encendido, dataset de `dev` vacío): `POST /v1/localize` → 200 en 1911 ms con
  `sin_coincidencias`, la 6.3 «No reconocí este lugar», declinación −7,9° y las 10 copias del escaneo borradas. Pasan a
  comprobadas en el teléfono el `multipart` contra el backend real, la declinación y el borrado; la lista de lo que
  sigue sin comprobar queda al día. Evidencia nueva en `validation/evidencia/fe-3-2/` (captura de la 6.3 y las líneas
  `[scan-8365]` de `app.log`; sin video, porque la vuelta muestra la cámara).
- Contratos tocados (§5): ninguno.
- Cómo se verificó: `app.log` del teléfono (`run-as … cat files/logs/app.log`), `ls -R files/camera/photos` vacío tras
  la respuesta y captura de pantalla por `adb`. No es un criterio de `validation-3-2` (C1–C4 siguen pendientes).
- Pendiente: lo de 0.9.0 (C1 en el campus, C4 de noche, C3b y `validate32.py --entorno dev` con BE-3.2 «Hecho»).

## [0.9.1] — 2026-10-26
- Lote que la motivó: FE-3.2 (cierre de la documentación, a la pregunta del maestro «¿se podrían hacer FE-3.5, FE-3.6 y
  la validación de FE-3.2 en `dev` leyendo solo docs?»), y su primera ejecución en `dev`.
- Qué cambió (solo documentos; el código es el de `e3f3d12`): §5.5, el formato exacto de la línea `ResultadoVM`
  (`Resultado: <nivel|sin_coincidencias|sin ubicación>, destino <sí|no>`) y la trampa de que empieza por `Resultado:`
  como la de `EscaneoVM` (hay que filtrar por tag); §5.6, los valores de `RESULTADO_DE_PRUEBA` (los usa la vista previa
  de la 6.3); §5.11, que el doble de `esperar_enter` de `test_validate32.py` reconoce los pasos guiados por «puntos
  conocidos» y «embedding apagado»; §4.6 y PLAN §3, el resultado en `dev`.
- Contratos tocados (§5): ninguno (aclaraciones).
- Cómo se verificó: `validate32.py --entorno dev` sobre `e3f3d12` (el maestro): P1–P5 pasan, P6 falla (BE-3.2 no está
  «Hecho»), P7 no evaluada, código 2 (`Bloqueado`), informe `.validacion/FE-3.2-20261026-153456.json`; lo esperado.
- Pendiente: lo de 0.9.0 (C1, C4 y C3b en `dev` cuando BE-3.2 esté «Hecho»).

## [0.9.0] — 2026-10-26

- **Lote que la motivó:** FE-3.2 (ubicación real y Resultado 6.3; sin alertas, que son de FE-3.6).
- **Decisiones del usuario del 2026-10-26** (respuestas literales a las preguntas del maestro): decisión abierta 15 →
  «En memoria (Recomendado)» (ADR-FE-24); destino sin vista 6.5 → «Decir distancia y dirección (Recomendado)» y vista 6.3
  → «Sin mapa ni voz (Recomendado)» (ADR-FE-27).
- **Qué cambió:**
  - Código: `LocalizacionRepository` (`data/repository/`, nuevo; con `FotoEscaneo`, stub y `RESULTADO_DE_PRUEBA`)
    reemplaza a `ui/ubicacion/EscaneoBackend.kt` (borrado). `RemoteLocalizacionRepository` (`data/remote/`, nuevo):
    `POST /v1/localize` `multipart/form-data` con las fotos re-codificadas a 1024 px y calidad 85 (≤ 1,5 MB) en
    `envio_<i>.jpg` y `metadatos` (`rumbos` normalizados, `origen`, `app_version`). `CampusApi.localizar`, DTOs
    (`MetadatosLocalizacionDto`, `LocalizacionRespuestaDto`, `PosicionDto`, `LugarCercanoDto`, `ReferenciaLugarDto`),
    `MapeoDatosApi.resultadoUbicacion`, `FalloApi.FotosInvalidas(indice, motivo)` para `400 FOTOS_INVALIDAS`.
    `LimitesRecodificacion` (`SUBIDA`, `LOCALIZACION`) y `Recodificador(motor, limites)` (la subida no cambia). Modelos
    `ResultadoUbicacion`, `PosicionEstimada`, `LugarCercano`, `ReferenciaLugar`, `NivelConfianza`, `UbicacionEstimada`
    y el holder `SesionNavegacion`/`SesionDeNavegacion` (`domain/model/`). `ConversionRumbo` y `DescribirUbicacion`
    (`domain/usecase/`), `Declinacion` (`sensors/`), `FotosEscaneo` (`ui/ubicacion/`). Escaneo: `CONSERVAR_FOTOS =
    false` (`internal`), `iniciar(carpeta)`, rumbo verdadero de cada foto, eventos por `Channel`,
    `Completado(resultado, rumboAlTerminar)`, errores `SERVICIO_NO_DISPONIBLE`, `DEMASIADOS_INTENTOS`,
    `FOTOS_INVALIDAS` y `DESCONOCIDO` con `ErrorEscaneo.deExcepcion` (lo inesperado ya no sale como «sin conexión»),
    borrado de la carpeta al recibir la respuesta, «Ajustes» conectado. Vista 6.3 nueva (`ResultadoUbicacionScreen`,
    `…ViewModel`, `…State`). `SeleccionDestinoViewModel` da la posición vigente a `RemoteLugaresRepository`.
    `MainActivity`: ruta `resultado`; `ubicarme` → `resultado`; `destino` → `resultado` o `ubicarme` saliendo de la
    pila; `inicio` «uno» quita el destino.
  - Pruebas JVM nuevas: `RemoteLocalizacionRepositoryTest` (11), `ConversionRumboTest` (7, criterio C2),
    `DescribirUbicacionTest` (11), `SesionDeNavegacionTest` (5), `FotosEscaneoTest` (6), `ErrorEscaneoTest` (7);
    `MapeoErroresApiTest` +1 y `RecodificacionFotoTest` +2. Total 221.
  - Validadores: `src/ops/validate32.py` (C1a, C1b con paso guiado y `embedding` encendido, C2, C3a, C3b, C4a, C4b con
    paso guiado y `embedding` apagado; manuales C1c y C4c) y en `comun.py` `ParteMultipart`, `cuerpo_multipart` y
    `http_post_multipart`; `test_validate32.py` (31). Total 190.
  - Documento: §4.6 nuevo; encabezado; §2.1; §3.2 (paquetes, pruebas, tags `ResultadoVM` y líneas nuevas de
    `EscaneoVM`, sin ubicación en los registros); §4 (componentes de `ui/components/`); §4.1 (221 casos); §5.1
    (variantes); §5.2 (`VoiceController`, `AppLog`, `crearCarpetaEscaneo`, `tomarFoto`, `EscucharOrientacion`, «Flujo de
    captura del escaneo» reescrito con `ErrorEscaneo.deExcepcion` y el formato de las líneas de `app.log`); §5.5 (vista
    6.3, Destino); §5.6 (`LocalizacionRepository`, modelos y `SesionDeNavegacion`); §5.7 (`ConversionRumbo`,
    `DescribirUbicacion` y sus reglas); §5.8 (rutas `inicio`, `ubicarme`, `resultado`, `destino`, holder del flujo
    público); §5.10 («Ubicarse» completo, errores, mapeo, DTOs, `LimitesRecodificacion`, «Rumbo» y «Lugares» al día);
    §5.11 (ayudas de FE-3.2, `validate32.py`, trampas, 190 casos); §6.2–§6.4; ADR-FE-23 (proveedor conectado),
    ADR-FE-06, ADR-FE-24 a ADR-FE-27; decisiones abiertas 12 y 15 resueltas; R4 y R7.
  - `validation-3-2` reescrita: entornos `local` y `dev`; precondiciones en el orden del contrato común (máquina,
    otros lotes, credenciales, `embedding`); C1 → C1a (JVM), C1b (paso guiado) y la manual C1c; C3 → C3a y C3b; C4 →
    C4a, C4b (paso guiado) y la manual C4c; hora límite 20:45; §5 con variables, preparación y salida esperada.
  - `PLAN.md`: FE-3.2 pasa a «En curso» con las decisiones del usuario en §2.2; FE-3.5 ya no lleva «estado viejo de
    Destino al volver del escaneo» (lo resolvió la ruta en FE-3.2).
- **Contradicciones corregidas:**
  - `validation-3-2` P2 pedía `GET /v1/admin/stats` con `total_fotos` > 0: esa ruta es de BE-2.3 (Pendiente), que no
    está en «Para validar» de FE-3.2 (PLAN §2.1). Ahora el dataset se comprueba con `GET /v1/admin/videos` (BE-2.1,
    Hecho), sumando `conteo.procesada` sin los videos `validacion…`.
  - `validation-3-2` evaluaba primero los otros lotes (P1 FE-3.1, P2 BE-3.2) y después la máquina (P3), al revés que el
    contrato común (§5.11: primero herramientas); no tenía precondición de credenciales (la de `stats` las necesitaba),
    ni hora límite para `embedding` (infra §5.11 la exige), ni entorno `local`; su §5 no tenía variables, preparación
    ni salida esperada; y su C1 manual exigía que el script encendiera `embedding` y lo apagara «al terminar C1» sin
    decir que eso obliga a esperar a la persona (ahora es un paso guiado, C1b).
  - `validation-3-2` C2 decía «una declinación negativa»; PLAN C2 pide positiva y negativa: ahora las dos.
  - §4 listaba siete componentes en `ui/components/`; solo existe `BannerEstado.kt` (los demás eran nombres previstos).
  - §5.1 no nombraba al Escaneo entre las vistas con `estado` como nombre del `StateFlow` (sí lo es).
- **Contratos tocados (§5):** §5.2 (`EscaneoViewModel.iniciar(carpeta)`, `eventos` pasa a `Flow` sobre un `Channel`,
  `EscaneoEvento.Completado` pasa de `data object` a `data class` —incompatible para un `when`—, `ErrorEscaneo` con
  cuatro valores nuevos y `deExcepcion`, `EscaneoScreen.onCompletado` con datos, `CONSERVAR_FOTOS` `internal`);
  §5.5 (vista 6.3 nueva); §5.6 (`LocalizacionRepository` reemplaza a `EscaneoBackend` —incompatible—, modelos y holder
  nuevos); §5.7 (dos casos de uso nuevos); §5.8 (ruta `resultado` nueva y cambios de `inicio`, `ubicarme` y `destino`);
  §5.10 (ruta, DTOs, `FalloApi.FotosInvalidas`, `Recodificador` con límites —compatible—); §5.11 (ayudas nuevas,
  compatibles). Piezas, ADR y cambios incompatibles en 0.x: sube la menor.
- **Cómo se verificó:** en Windows, `.\gradlew.bat --console=plain testDebugUnitTest assembleDebug` con JBR 21 →
  `BUILD SUCCESSFUL`, 221 casos sin fallos. En WSL, `uv run --frozen ruff check .` («All checks passed!»),
  `ruff format --check .` («16 files already formatted»), `pytest -q` (190 passed) y `validate32.py --entorno local` →
  código 0 (P1; C1a 11/11, 11/11 y 5/5; C2 7/7; C3a; C4a 7/7; C1b, C4b y C3b omitidas; manuales C1c y C4c). Sin
  teléfono y sin tocar `dev` (lo coordina el maestro; con BE-3.2 «En curso», `validate32.py --entorno dev` da hoy código
  2).
- **Pendiente:** `validate32.py --entorno dev` cuando BE-3.2 esté «Hecho» (dataset real y calibración): C1 en el campus
  (10 puntos, con `embedding` encendido) y C4 de noche (`embedding` apagado), con su evidencia en
  `validation/evidencia/fe-3-2/`; C3b después de esas vueltas. Sin comprobar en el teléfono: la re-codificación a 1024 px
  con `MotorImagenAndroid`, que el backend real acepte el `multipart`, el valor de la declinación (≈ −7° en Medellín),
  el borrado de las fotos, la 6.3 con TalkBack (y si su voz se solapa con TalkBack, FE-3.5) y las distancias reales en
  Destino. El texto de C2c de `validate31.py` sigue pendiente (FE-4.3): corregirlo exige tocar `validation-3-1`, que
  este lote no toca.

## [0.8.1] — 2026-10-26

- **Lote que la motivó:** FE-3.1 (cierre: validado en `dev`) y la decisión del usuario del 2026-10-26, a la propuesta
  del maestro «cerrar FE-3.1 como Hecho con lo validado (C1b en dev y la entrada al mapa por voz) y pasar la prueba con
  TalkBack del mapa y el hueco del punto de inicio a FE-3.6»: «Si, por favor. Cambialo y demos por hecho lo que
  llevamos.»
- **Qué cambió (solo documentos; el código validado es el de `b553390`):**
  - `PLAN.md`: FE-3.1 C2 queda solo con la voz «mapa» y Atrás → Inicio, con la decisión anotada; fila de §3 en
    «Hecho» (`b553390` 2026-10-26, informe, primer intento con código 3, evidencia, lo que pasó a FE-3.6 y los hallazgos
    con TalkBack 17). FE-3.6: entregables nuevos (punto de inicio del mapa sin tocarlo, desde Ubicarme; probar «Ver
    mapa» con TalkBack) y criterio C5. FE-3.5: nota de los hallazgos con TalkBack 17. FE-4.3: quitar Coil 3 sin uso,
    el error de `lintDebug` y el texto viejo de `validate31.py`.
  - `validation-3-1`: C2c solo por voz, con su resultado y la evidencia (`evidencia/fe-3-1/c2-1-inicio.png`,
    `c2-2-mapa-por-voz.png`, `c2-3-atras-a-inicio.png`); resultado de la ejecución en `dev`; trampa de MIUI («Instalar
    vía USB» se apaga solo); aviso de que el texto que imprime `validate31.py` para C2c aún pide TalkBack.
  - `validation-3-6`: C5 nuevo (abrir el mapa con TalkBack «Ver mapa», inicio sin tocar el mapa —y, mientras exista,
    con toque y ▶—, Atrás y `dumpsys sensorservice` al volver), con procedimiento y hallazgos de TalkBack 17.
  - ARCHITECTURE: encabezado; §4.5 con lo validado en `dev`, lo que pasó a FE-3.6, el mapa que hoy no sirve a una
    persona ciega (inicio por toque) y los hallazgos con TalkBack 17; §4.1, trampa de los dos Coil del build;
    §5.2 (tags de `AppLog` al día, evidencia de FE-3.6 C5); §5.5 (`MapaPublicoScreen` y acciones del orbe con lo
    comprobado y lo que no); §5.11 (texto desactualizado de `instruccion_c2`/`INSTRUCCION_C1B`, lo comprobado de
    `validate31.py` en `dev`, 0 lugares en `dev`); §6.1.
- **Contradicciones corregidas:** la fila de tags de `AppLog` de §5.2 no tenía `Pdr`, `Subida` ni `Lugares` (§3.2 sí).
  §3.2 se mantiene como la lista completa.
- **Contratos tocados (§5):** ninguno (parche: el código no cambia; la acción «Ver mapa» sigue existiendo).
- **Cómo se verificó:** `validate31.py --entorno dev` con código 0 sobre `b553390` (sin `-dirty`; informe
  `.validacion/FE-3.1-20261026-142022.json`, Xiaomi 23028RA60L, Android 14) y C2c por voz con capturas, ambos hechos
  por el maestro con el usuario; `frontend.yml` en verde sobre `b553390`.
- **Pendiente:** FE-3.6 C5 (TalkBack «Ver mapa», inicio desde Ubicarme, sensores del mapa en el teléfono); el texto de
  C2c de `validate31.py` en el próximo cambio de código.

## [0.8.0] — 2026-10-26

- **Lote que la motivó:** FE-3.1 (lugares públicos y entrada al mapa; sin alertas, que son de FE-3.6).
- **Qué cambió:**
  - Código: `RemoteLugaresRepository` (`data/remote/`, nuevo): `GET /v1/places` con la posición por un proveedor (hoy
    `{ null }`), descarta categorías desconocidas e `id` repetidos con una línea `Lugares`; `CampusApi.lugares(lat?,
    lng?, categoria?)` y `ListaLugaresDto`. `SeleccionDestinoViewModel` lo usa en lugar del stub (`LugaresRepositoryStub`
    queda para la vista previa). `FilaLugar`: si la foto (`imagenUrl`) no carga, el ícono de la categoría (antes, un
    cuadro vacío). `Comando.VER_MAPA` en `ComandoParser` (palabra completa «mapa»/«mapas»; palabras separadas también
    por signos); `InicioEvento.VerMapa`, `InicioViewModel.verMapa()` y `BIENVENIDA` con «o mapa para ver el mapa»;
    `InicioScreen`/`InicioContent(onVerMapa = {})` y la acción de TalkBack «Ver mapa» en el orbe; la ruta `inicio`
    navega a `mapa` (`launchSingleTop`). `ObservadorPrimerPlano` (`sensors/`, nuevo, extraído de `PdrTracker`) y
    `MapaPublicoScreen` crea su `PdrTracker` con el ciclo de vida de su entrada de la pila (hallazgo de FE-2.3).
  - Pruebas JVM nuevas: `RemoteLugaresRepositoryTest` (9), `ComandoParserTest` (5), `ObservadorPrimerPlanoTest` (6).
    Total 171.
  - Validadores: `src/ops/validate31.py` (C1a, C1b con paso guiado, C2a, C2b; manual C2c) y en `comun.py`
    `http_delete` y `esperar_enter`; `test_validate31.py` (30). Total 159.
  - Documento: §4.5 nuevo; §3.2 (pruebas, ruta `mapa`, tag `Lugares`, `sensors/`); §4.1 (171 casos; resultado de
    `lintDebug`); §5.2 (`ComandoParser`, `PdrTracker.cicloDeVida`, `ObservadorPrimerPlano`, receta, segundo plano y
    longitud de paso); §5.5 (`MapaPublicoScreen`, `FilaLugar`, Inicio, `SeleccionDestinoViewModel`); §5.6
    (`LugaresRepository` real, `LugarDestino` con el backend); §5.8 (`inicio` → `mapa`, fila `mapa`); §5.10 (ruta, DTO,
    `RemoteLugaresRepository` y «Lugares»); §5.11 (ayudas de FE-3.1, `validate31.py`, trampas); §6.1 y §6.4;
    ADR-FE-22 (el PDR del mapa sigue el ciclo de vida de su pantalla) y ADR-FE-23 (posición por proveedor; hoy sin
    posición).
  - `validation-3-1` reescrita: entornos `local` y `dev`; precondiciones en el orden del contrato común (P5 ya no
    exige ≥ 1 lugar); C1 → C1a (JVM) y C1b (teléfono, paso guiado); C2 → C2a (JVM) y C2b (estático) de apoyo y la
    manual C2c; §5 con variables, preparación y salida esperada.
  - `PLAN.md`: FE-3.1 pasa a «En curso»; FE-3.5 ya no lleva «miniatura sin ícono de respaldo» (lo resolvió FE-3.1).
- **Contradicciones corregidas:**
  - `validation-3-1` P4 exigía `GET /v1/places` con ≥ 1 lugar y C1 creaba el lugar de prueba «junto al primer lugar»:
    en `dev` puede no haber ninguno (el backend quitó ese requisito de BE-3.2 en su 0.12.0 por lo mismo). Ahora solo
    exige `200` y, sin lugares, usa una posición fija del campus.
  - §4.3 y §4.4 seguían diciendo «a verificar en dispositivo» de FE-2.3 C4–C5 y de FE-2.1 C1–C2, ya validados en `dev`
    según PLAN §3: ahora dicen lo verificado y lo que falta. El encabezado decía «la prueba en el campus (FE-2.1 C1 y
    C2) sigue pendiente».
  - §4.1 decía que `frontend.yml` estaba «sin comprobar en un runner hasta el primer PR»: pasó en el PR #8 (FE-1.1 C3).
  - §5.5 (Destino) decía que con el stub todas las distancias son `null`; el stub sí las trae (85–310 m, §5.6).
  - El hallazgo de C5 de FE-2.3 solo estaba en la fila FE-2.3 de PLAN §3: ahora también en §4.3 y §4.5.
- **Contratos tocados (§5):** §5.2 (`Comando` con un valor nuevo antes de `NINGUNO`: un `when` exhaustivo de otro
  archivo dejaría de compilar; `ComandoParser` separa por signos; `ObservadorPrimerPlano` nuevo); §5.5
  (`InicioScreen`/`InicioContent` con `onVerMapa` por defecto `{}`, `InicioEvento.VerMapa` nuevo —incompatible para un
  `when` exhaustivo—, `FilaLugar` con respaldo); §5.6 (`LugaresRepository` real, sin cambiar la interfaz); §5.8 (`inicio`
  entrega `onVerMapa` → `mapa`); §5.10 (ruta y DTO nuevos, `RemoteLugaresRepository`); §5.11 (ayudas nuevas,
  compatibles). Piezas, ADR y cambios incompatibles en 0.x: sube la menor.
- **Cómo se verificó:** en Windows, `.\gradlew.bat --console=plain testDebugUnitTest assembleDebug` con JBR 21 →
  `BUILD SUCCESSFUL`, 171 casos sin fallos; `lintDebug` falla por un error anterior (`MapaWebView.kt:125`) y no da avisos
  en los archivos de FE-3.1. En WSL, `uv run --frozen ruff check .` («All checks passed!»), `ruff format --check .`
  («14 files already formatted»), `pytest -q` (159 passed) y `validate31.py --entorno local` → código 0 (P1; C1a 9/9;
  C2a 5/5 y 6/6; C2b; C1b omitida; la manual C2c). Sin teléfono y sin tocar `dev` (lo coordina el maestro).
- **Pendiente:** `validate31.py --entorno dev` con el teléfono (C1b) y la manual C2c con video (`validation-3-1` §3 y
  §5). Sin comprobar: la miniatura con foto (el backend no tiene fotos de lugares), `uiautomator dump` de Destino
  mientras escucha, que `input swipe` no desplace con TalkBack activo, el nombre de las acciones de TalkBack en el
  Xiaomi y que el mapa abierto desde Inicio no deje conexiones en `dumpsys sensorservice` tras volver. Distancias
  reales cuando FE-3.2 dé una posición; orden por popularidad con BE-5.2.

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
