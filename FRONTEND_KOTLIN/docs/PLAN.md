# PLAN — App Android (`FRONTEND_KOTLIN`)

Qué se construye y en qué orden. **Cómo** funciona cada pieza está en [`ARCHITECTURE.md`](./ARCHITECTURE.md);
**por qué y cuándo** cambió algo, en [`CHANGELOG.md`](./CHANGELOG.md); **cómo se comprueba** cada lote, en
[`validation/`](./validation/).

Alineado con `ARCHITECTURE.md` **v0.9.2**. Este archivo contiene además el **catálogo único de historias de usuario**
del proyecto (§5), que los planes de las otras carpetas referencian.

---

## 1. Cómo usar este plan

- No hay fechas: el orden lo dan las fases y las dependencias.
- **Identificadores:** `FE-<fase>.<n>`. Su validación es `docs/validation/validation-<fase>-<n>.md` y su script,
  `project/src/ops/validate<fase><n>.py` (FE-2.3 → `validation-2-3.md` → `validate23.py`; FE-0.12 → `validate012.py`).
- **§3 es la única tabla de estado de la app.** Al cerrar un lote solo se edita su fila en §3. (Reemplaza al antiguo
  §10 «Estado de implementación» del ARCHITECTURE y a las listas de «Pendiente» de cada vista.)
- **Dos tipos de dependencia** (§2.1): *para construir* (lo que hace falta para escribir el código; muchas veces se
  puede avanzar con *stubs*) y *para validar* (lo que debe estar **Hecho**, aquí o en otras carpetas, para ejecutar la
  validación; si falta, el validador termina con código 2 y el lote queda `Bloqueado`).
- **Cerrar un lote:** cumplir sus criterios (C1, C2…); validador con código 0 (en la app, casi siempre con un
  dispositivo conectado por `adb` y contra `dev`); evidencia de las comprobaciones manuales en el PR (las pruebas con
  TalkBack o caminando no se automatizan); actualizar su fila de §3. Si toca un contrato, antes se actualiza
  `ARCHITECTURE.md` §5 (sube la versión) y se añade la entrada en `CHANGELOG.md`.
- Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11; lo propio de la app,
  `ARCHITECTURE.md` §5.11. Orden global entre carpetas: `README.md` raíz.
- Prefijos de otras carpetas: `INF-`, `BE-`, `EMB-`; su estado está en el §3 del `PLAN.md` de cada una.
- Los lotes **FE-0.1 a FE-0.12** se construyeron antes de este plan (fase 0: el prototipo con datos locales). Se
  cerraron sin validación automática; sus pruebas en dispositivo se hacen en FE-2.3 y su trabajo pendiente se repartió
  entre los lotes nuevos, que lo citan.
- Definición de «hecho» común, además de la validación: compila, `frontend.yml` en verde (desde FE-1.1), probado en un
  **dispositivo físico** (los sensores y la cámara no se prueban en emulador), probado con TalkBack si es una vista
  pública, y §5 del ARCHITECTURE actualizado si cambió alguna pieza reutilizable.

---

## 2. Fases y lotes

Fases comunes a las cuatro carpetas: `INFRASTRUCTURA_TERRAFORM/docs/PLAN.md` §2.1. En la app, la fase 0 es el
prototipo ya construido sobre datos locales y *stubs*.

### 2.1 Lotes por fase

| Lote | Nombre | Para construir | Para validar | Validación |
|---|---|---|---|---|
| FE-0.1 | Inicio y voz (6.1) | — | — | — |
| FE-0.2 | Escaneo 360° (6.2) | — | — | — |
| FE-0.3 | Selección de destino (6.4) | — | — | — |
| FE-0.4 | Login y sesión (7.1) | — | — | — |
| FE-0.5 | Panel de administración (7.2) | FE-0.4 | — | — |
| FE-0.6 | Editor de mapa y formulario de alerta (7.8, 7.9) | — | — | — |
| FE-0.7 | Galería de imágenes (7.11) | — | — | — |
| FE-0.8 | Lista y detalle de videos (7.13, 7.14) | — | — | — |
| FE-0.9 | PDR y mapa público (2.3, 2.6) | — | — | — |
| FE-0.10 | Ubicación manual inicial (7.3) | FE-0.9 | — | — |
| FE-0.11 | Recolección en curso (7.4) | FE-0.10 | — | — |
| FE-0.12 | Calibración de la longitud de paso (7.3b) | FE-0.9 | — | — |
| FE-1.1 | Cliente HTTP, conexión real y CI | — | BE-1.1, INF-1.4 | [`validation-1-1`](./validation/validation-1-1.md) |
| FE-1.2 | Login contra el backend | FE-1.1 | FE-1.1, BE-1.3 | [`validation-1-2`](./validation/validation-1-2.md) |
| FE-2.1 | Subida de recorridos y Resumen de video (7.5) | FE-1.2 | FE-1.2, FE-2.3, BE-2.1, BE-2.2 | [`validation-2-1`](./validation/validation-2-1.md) |
| FE-2.2 | Panel con datos reales | FE-2.1 | FE-2.1, BE-2.3 | [`validation-2-2`](./validation/validation-2-2.md) |
| FE-2.3 | Pruebas en dispositivo y robustez de la recolección | FE-0.11, FE-0.12 | — | [`validation-2-3`](./validation/validation-2-3.md) |
| FE-3.1 | Lugares públicos y entrada al mapa | FE-1.1 | FE-1.1, BE-3.1 | [`validation-3-1`](./validation/validation-3-1.md) |
| FE-3.2 | Ubicación real y Resultado (6.3) | FE-3.1 | FE-3.1, BE-3.2 | [`validation-3-2`](./validation/validation-3-2.md) |
| FE-3.3 | Alertas de administración sincronizadas (7.8–7.10) | FE-1.2 | FE-1.2, BE-3.3 | [`validation-3-3`](./validation/validation-3-3.md) |
| FE-3.4 | Lugares de administración (7.6, 7.7) | FE-1.2 | FE-1.2, BE-3.1 | [`validation-3-4`](./validation/validation-3-4.md) |
| FE-3.5 | Accesibilidad y voz del flujo público | FE-3.2 | FE-3.2 | [`validation-3-5`](./validation/validation-3-5.md) |
| FE-3.6 | Alertas públicas | FE-3.1, FE-3.2 | FE-3.1, FE-3.2, BE-3.3 | [`validation-3-6`](./validation/validation-3-6.md) |
| FE-4.1 | Videos e imágenes contra el backend (7.11–7.14) | FE-2.1 | FE-2.1, BE-4.1 | [`validation-4-1`](./validation/validation-4-1.md) |
| FE-4.2 | Ajustes (6.7) | — | — | [`validation-4-2`](./validation/validation-4-2.md) |
| FE-4.3 | Limpieza y deuda técnica | — | — | [`validation-4-3`](./validation/validation-4-3.md) |
| FE-5.1 | Navegación guiada, llegada y fusión (6.5, 6.6) — diferido | FE-3.2, BE-5.1, BE-5.3 | — | — |
| FE-5.2 | Estadísticas (7.15) — diferido | BE-5.2 | — | — |
| FE-6.1 | Preparación para publicar — diferido | Fases 1–4 cerradas | — | — |

### 2.2 Detalle de los lotes pendientes

Los lotes FE-0.1 a FE-0.12 están descritos en `ARCHITECTURE.md` (vista correspondiente y §5); aquí solo figuran en §3.

#### FE-1.1 — Cliente HTTP, conexión real y CI
- **Entregables:** cliente HTTP (Retrofit + OkHttp o Ktor; la elección se registra como ADR: Retrofit + OkHttp, ADR-FE-12), `data/remote/` con DTOs,
  `ApiConfig.kt` con `api_base_url` + `/v1`, mapeo de errores y encabezados de ARCHITECTURE §5.10, `X-Request-Id` en
  `AppLog`, `BackendHealth` real contra `GET /v1/health` (reemplaza a `BackendHealthStub`; §5.5, «Inicio»),
  `.github/workflows/frontend.yml` (compilar y pruebas unitarias), `project/pyproject.toml` y `src/ops/comun.py` para
  los validadores.
- **Criterios de cierre:**
  - C1. El indicador de Inicio muestra «Conectado» contra `dev` y «Sin conexión» en modo avión.
  - C2. Pasan las pruebas unitarias `MapeoErroresApiTest` y `MapeoDatosApiTest` (`data/remote/`), que cubren las dos
    tablas de §5.10.
  - C3. `frontend.yml` queda en verde en un PR.
  - C4. `ApiConfig.kt` apunta al `api_base_url` vigente más `/v1`.
- **Historias:** HU-09, HU-20, HU-22.

#### FE-1.2 — Login contra el backend
- **Entregables:** `RemoteAuthRepository` (`POST /v1/auth/login`); la sesión guarda `expira_en`; respuesta a
  `401 TOKEN_*` / `NO_AUTENTICADO` en cualquier ruta `/v1/admin/…` o `/v1/collect/…` (cerrar sesión e ir a Login,
  §5.3 y §5.10).
- **Criterios de cierre:**
  - C1. El admin inicial entra al panel.
  - C2. Un usuario `user` ve «Sin permisos».
  - C3. Pasa la prueba unitaria `SesionVencidaTest`: un `401 TOKEN_EXPIRADO`, `TOKEN_INVALIDO` o `NO_AUTENTICADO` en
    cualquier ruta `/v1/admin/*` o `/v1/collect/*` cierra la sesión y emite `onSinSesion` (la ruta vuelve a Login sin
    cerrar la app), y una sesión con `expira_en` pasado se trata como «sin sesión» sin llamar al backend.
  - C4. `RemoteAuthRepositoryTest` cubre 200, 401 y error de red (MockWebServer).
- **Historias:** HU-10.

#### FE-2.1 — Subida de recorridos y Resumen de video (7.5)
- **Entregables:**
  - `ResumenVideoScreen` (vista 7.5): nombre editable, estadísticas, trayectoria, carrusel con descarte, «Subir y
    procesar» con progreso por foto, «Guardar y subir después», «Descartar video».
  - Cola persistente de subida en `data/local/` según §5.10 (re-codificar cada foto, crear video, URLs prefirmadas,
    `PUT`, `complete`, reintentos, retomar); valor `EstadoFoto.PENDIENTE` para mostrar el progreso por foto.
  - Ver lo recolectado en Galería, Lista y Detalle de video: hoy `AssetsVideoRepository` solo lee `assets/`; hace
    falta un `VideoRepository` compuesto (assets + `files/recoleccion/`) y un parser de manifest compartido (§5.6).
  - Pendiente heredado de 7.4: «Finalizar» lleva a un placeholder en blanco (`admin/recoleccion/resumen`).
- **Criterios de cierre:**
  - C1. Un recorrido de ≥ 50 fotos grabado en el campus queda `procesado` en el backend.
  - C2. Cortar la red a mitad de la subida y reabrir la app completa la subida sin duplicar fotos.
  - C3. Ninguna foto subida supera 4 MB ni 1600 px de lado mayor.
  - C4. «Finalizar» en 7.4 abre la vista 7.5.
- **Historias:** HU-14.

#### FE-2.2 — Panel con datos reales
- **Entregables:** `RemoteAdminRepository` (`GET /v1/admin/stats`, fecha ISO → milisegundos); «fotos pendientes»
  desde la cola de FE-2.1; decidir los ⚠ de `ResumenAdmin` (§5.6: origen del último video, conversión de fecha).
- **Criterios de cierre:**
  - C1. Los cuatro datos que vienen del backend coinciden con `GET /v1/admin/stats`.
  - C2. «Fotos pendientes» coincide con la cola local de subida.
- **Historias:** HU-11.

#### FE-2.3 — Pruebas en dispositivo y robustez de la recolección
Se hace **antes** de recolectar el dataset real (Fase 2), porque las coordenadas de las fotos dependen del PDR.
- **Pruebas en dispositivo físico** (quitar los ⚠ correspondientes del ARCHITECTURE):
  - PDR y mapa público (`app.js`, `index.html`, `PuentePdr.kt`, `MapaPublicoScreen.kt`; 2.6 y 5.2).
  - Vista 7.3 completa y los supuestos listados en 5.5 («UbicacionManual»).
  - Calibración (7.3b): pasada completa A→B, guardar y recolectar con la longitud calibrada; comprobar que
    `distanciaMetros ≈ pasos × longitud guardada` y que el disparador de 5 m dispara cada ≈ `5 / longitud` pasos;
    **recalibrar** tras el cambio de detector del 2026-10-12.
  - Recolección (7.4) en un recorrido conocido.
- **Pruebas automáticas:** `CalibracionPasoTest` y `StepDetectorTest` en Gradle; pruebas unitarias nuevas de
  `DisparadorCaptura` y `Deriva`.
- **Robustez:** retomar una grabación tras matar el proceso (`buscarEnCurso()` existe, pero no se usa: hoy se muestra
  `SIN_INICIO`); manejo de `ON_STOP` en `PdrTracker` (hoy lo resuelve el ViewModel de la recolección).
- **Criterios de cierre:**
  - C1. Pasan `CalibracionPasoTest`, `StepDetectorTest`, `DisparadorCapturaTest` y `DerivaTest` (las dos últimas,
    nuevas).
  - C2. `recoleccion_mapa.js` y `calibracion_mapa.js` usan `MapaBase.crearMapa` (no `base.crearMapa`; 5.9).
  - C3. Registro de pruebas en dispositivo (modelo, Android, recorrido, error final medido) para el PDR, 7.3, 7.3b y
    7.4, con la longitud de paso recalibrada.
  - C4. Matar el proceso durante una grabación y volver a abrir la app permite retomarla.
  - C5. Con la app en segundo plano, `PdrTracker` deja de leer sensores.
- **Historias:** HU-12, HU-13.

#### FE-3.1 — Lugares públicos y entrada al mapa
Desde el 2026-10-25 no lleva alertas: el usuario decidió «No necesitamos las alertas por el momento» y lo de alertas
públicas pasó a FE-3.6 (como en el backend, donde BE-3.1 queda con lugares y las alertas pasan a BE-3.3).
- **Entregables:** `RemoteLugaresRepository` (`GET /v1/places`, con distancias reales cuando hay posición; ordenar por
  popularidad queda para cuando exista BE-5.2); fotos de los lugares cuando el backend las tenga (hoy se muestra el
  ícono de la categoría si no hay `imagenUrl`); entrada a la ruta pública `mapa` de `MapaPublicoScreen` (la ruta ya
  existe desde FE-2.3, que solo la abre con un extra del `Intent` en depuración; falta llegar desde Inicio, con el
  comando de voz «mapa» y la acción de TalkBack «Ver mapa»; no depende de las alertas, que se anunciarán ahí en FE-3.6);
  hallazgo de FE-2.3: que el `PdrTracker` del mapa deje de leer sensores cuando el mapa no es la pantalla visible
  (hecho en FE-3.1 con el ciclo de vida de la pantalla, ADR-FE-22). La acción «Ver mapa» está en el código, pero su
  prueba con TalkBack pasó a FE-3.6 (abajo).
- **Criterios de cierre:**
  - C1. Selección de destino muestra los lugares de `GET /v1/places`.
  - C2. Desde Inicio se abre el mapa público con el comando de voz «mapa», y Atrás vuelve a Inicio.
- **Decisión del usuario del 2026-10-26** (al validar en `dev`): C2 decía también «y con la acción de TalkBack «Ver
  mapa»». Con TalkBack 17 en el Xiaomi no se encontró cómo abrir las acciones del botón principal (hallazgos en la fila
  FE-3.1 de §3) y, además, para usar el mapa hay que tocar el punto de inicio, cosa que una persona ciega no puede
  hacer. Propuesta del maestro: «cerrar FE-3.1 como Hecho con lo validado (C1b en dev y la entrada al mapa por voz) y
  pasar la prueba con TalkBack del mapa y el hueco del punto de inicio a FE-3.6»; respuesta del usuario: «Si, por
  favor. Cambialo y demos por hecho lo que llevamos.»
- **Historias:** HU-03.

#### FE-3.2 — Ubicación real y Resultado (6.3)
- **Entregables:**
  - `EscaneoBackend` real (desde ARCHITECTURE 0.9.0 es `LocalizacionRepository` + `RemoteLocalizacionRepository`):
    `POST /v1/localize` con fotos re-codificadas y rumbos en norte verdadero (§5.10); guardar el acimut de cada foto;
    `EscaneoEvento.Completado` con el resultado.
  - Decisión abierta 15 para el flujo público (`SesionDeNavegacion` u otra), y actualizar ARCHITECTURE §5.8.
  - `ResultadoUbicacionScreen` (vista 6.3) con referencias relativas, confianza y acciones. Las alertas cercanas de
    6.3 son de FE-3.6 (desde el 2026-10-25).
  - Destino elegido en 6.4 que llega a 6.5 tras el escaneo (hoy `AppNav` lo descarta, §5.8). Como 6.5 es de FE-5.1,
    por decisión del usuario (abajo) el destino queda en `SesionDeNavegacion` y la 6.3 dice su distancia y dirección.
  - Mensaje hablado para `503 EMBEDDING_NO_DISPONIBLE`.
  - `CONSERVAR_FOTOS = false` (decisión abierta 12): las fotos del escaneo se borran al recibir la respuesta,
    incluidas las que llegan fuera de la fase `ESCANEANDO` (hoy nunca se borran; §5.2).
- **Criterios de cierre:**
  - C1. En 10 puntos conocidos con dataset, la app dice el lugar correcto o pide repetir con confianza baja.
  - C2. Pasa `ConversionRumboTest` (magnético (−180, 180] → verdadero [0, 360), con declinación positiva y negativa).
  - C3. `CONSERVAR_FOTOS` vale `false` y ninguna foto de escaneo queda en el teléfono.
  - C4. Con `embedding` apagado, la app dice que el servicio de ubicación no está disponible.
- **Decisiones del usuario del 2026-10-26** (respuestas literales a las preguntas del maestro; ARCHITECTURE §4.6):
  decisión abierta 15 → «En memoria (Recomendado)» (`SesionDeNavegacion`, ADR-FE-24); el destino sin vista 6.5 (es de
  FE-5.1) → «Decir distancia y dirección (Recomendado)»: la 6.3 dice la distancia y la dirección al destino, sin ruta
  provisional; la vista 6.3 → «Sin mapa ni voz (Recomendado)»: botones legibles por TalkBack, los comandos de voz en 6.3
  pasan a FE-3.5 (ADR-FE-27).
- **Historias:** HU-01, HU-02, HU-23.

#### FE-3.3 — Alertas de administración sincronizadas (7.8–7.10)
- **Entregables:**
  - Repositorio local (Room) y API real (`/v1/admin/alerts`, `sincronizar`); pendientes que guardan la operación
    (§5.5 y §5.10).
  - Pasar la posición real del admin en `posicionAdmin` (hoy `{ null }`).
  - Formulario 7.9 completo: dictado por voz, «Escuchar cómo sonará», vigencia y «Ajustar en el mapa».
  - Lista de alertas (vista 7.10), conectada a `onVerLista`.
  - Pendiente heredado de 7.4: las alertas existentes **no se cargan** en el mapa en vivo y las creadas durante la
    grabación **se pierden al salir** (no hay `AlertasRepository`).
- **Criterios de cierre:**
  - C1. Una alerta creada durante la recolección aparece en el editor y en el backend tras sincronizar.
  - C2. Crear y borrar una alerta antes de sincronizar no produce errores ni deja rastro en el backend.
  - C3. La vista 7.10 lista las alertas del backend y abre su edición.
- **Historias:** HU-16.
- Desde el 2026-10-25 la administración de alertas del backend es BE-3.3 (antes BE-3.1), fuera del núcleo como FE-3.6.

#### FE-3.4 — Lugares de administración (7.6, 7.7)
- **Entregables:** vistas 7.6 y 7.7 contra el backend; unificar `Lugar` y `LugarDestino` (§5.6); habilitar «Marcar
  punto de interés» en 7.4 (hoy deshabilitado, «Próximamente»).
- **Criterios de cierre:**
  - C1. Un lugar creado en la app aparece en `GET /v1/places` y en Selección de destino.
  - C2. La posición elegida en el mapa de 7.7 es la que guarda el backend: `GET /v1/places?lat=<pos>&lng=<pos>` lo
    devuelve primero, con `distancia_m` < 1.
  - C3. Un nombre repetido muestra el error `409` en el formulario.
- **Historias:** HU-15.

#### FE-3.5 — Accesibilidad y voz del flujo público
- **Entregables:**
  - Decidir y aplicar la interacción de Inicio (decisión abierta 18): orbe único o dos botones + micrófono + Ajustes;
    que la explicación hablada de permisos suene **antes** del primer diálogo (hoy la ruta pide los permisos antes de
    mostrar la pantalla; 5.5, «Inicio»).
  - Los ⚠ de `ui/destino/componentes/` (5.5): chip «Más» sin nombre para TalkBack, posible solapamiento de voces
    (tres `liveRegion` + `VoiceController`), «Lugares cercanos» sin distancias (con datos reales se ve desde FE-3.1,
    hasta que FE-3.2 dé una posición) y qué hace `alPresionarMicrofono` al tocar mientras escucha. (La miniatura sin
    ícono de respaldo la resolvió FE-3.1.)
  - Los dos ⚠ de `BuscarLugares` (5.7): coincidencia exacta que gana sin preguntar e hipótesis unidas de `listen`.
  - (El estado viejo de Destino al volver del escaneo lo resolvió FE-3.2 en la ruta: `destino` sale de la pila al
    confirmar; ARCHITECTURE §5.5 y §5.8.)
  - Desde FE-3.2 (decisión del usuario del 2026-10-26, ADR-FE-27): comandos de voz en la vista 6.3 (repetir, volver a
    ubicarse, ir a un lugar, inicio) y comprobar si la voz del Resultado se solapa con TalkBack (ARCHITECTURE §5.5,
    «Resultado de ubicación»).
  - Tener en cuenta lo visto con TalkBack 17 en el Xiaomi al validar FE-3.1 (ARCHITECTURE §4.5, «Hallazgos con
    TalkBack 17»): las acciones personalizadas del orbe («Ir a un lugar», «Ver mapa») no se encontraron con los gestos
    probados, así que hoy por toque con TalkBack solo se llega a Ubicarme.
- **Criterios de cierre:**
  - C1. Las pruebas de accesibilidad automáticas (Espresso con `AccessibilityChecks`) pasan en las vistas públicas.
  - C2. `BuscarLugaresTest` cubre los dos casos ⚠.
  - C3. El recorrido Inicio → Ubicarme → Resultado → Destino se completa solo con voz y solo con TalkBack, sin voces
    superpuestas, probado por al menos una persona usuaria de lector de pantalla.
- **Historias:** HU-08.

#### FE-3.6 — Alertas públicas
Fuera del núcleo: el 2026-10-25 el usuario decidió «No necesitamos las alertas por el momento». Reúne lo de alertas
públicas que antes estaba en FE-3.1 (caché, detección, anuncio en el mapa) y en FE-3.2 (alertas cercanas en 6.3).
- **Entregables:**
  - Caché de alertas en Room con sincronización por diferencias y sus disparadores (§5.10, «Alertas sin conexión»;
    `GET /v1/alerts` de BE-3.3).
  - Caso de uso `DetectarAlertasCercanas` (radio + incertidumbre, una vez por aproximación, prioridad alta interrumpe;
    2.5).
  - Anunciar las alertas en el mapa público (ruta `mapa`, `MapaPublicoScreen`, posición por PDR) mientras se camina.
  - Alertas cercanas en `ResultadoUbicacionScreen` (6.3): se muestran y se leen después de la ubicación. Salen de la
    caché local y de la posición estimada: `POST /v1/localize` no trae alertas (backend §5.3).
  - Desde FE-3.1 (decisión del usuario del 2026-10-26, PLAN §2.2 FE-3.1): **punto de inicio del mapa público sin tocar
    el mapa.** Hoy el seguimiento solo empieza si se toca un punto del mapa (o el botón GPS) y se pulsa ▶, algo que una
    persona ciega no puede hacer. El inicio debe salir de la ubicación de «Ubicarme» (el resultado de FE-3.2, por el
    *holder* de la decisión abierta 15) y el rastreo debe poder empezar sin ▶ (por voz o al abrir el mapa). A decidir
    en el lote: hoy el punto de partida lo fija la página (`AndroidBridge.setPosition`, ARCHITECTURE §5.9), así que
    probablemente haga falta una función nueva Kotlin → web (cambio de contrato de §5.9).
  - Desde FE-3.1: probar con TalkBack la acción «Ver mapa» del botón principal de Inicio (ya está en el código,
    ARCHITECTURE §5.5) y documentar cómo se abren las acciones en TalkBack 17 (hallazgos en ARCHITECTURE §4.5).
- **Criterios de cierre:**
  - C1. Una alerta creada en el backend llega al teléfono en la siguiente sincronización, y al borrarla desaparece.
  - C2. En modo avión, tras una sincronización previa, se anuncia una alerta al entrar en su radio.
  - C3. `DetectarAlertasCercanasTest` cubre radio, incertidumbre, una vez por aproximación y vigencia.
  - C4. En el Resultado (6.3), una alerta activa dentro del radio de la posición estimada se muestra y se lee después
    de la ubicación.
  - C5 (desde FE-3.1, decisión del usuario del 2026-10-26). Con TalkBack activo, desde Inicio se abre el mapa público
    con la acción «Ver mapa»; el seguimiento empieza en la posición de «Ubicarme» sin tocar el mapa (y, mientras
    exista, también fijando un punto y pulsando ▶), y Atrás vuelve a Inicio.
- **Historias:** HU-05.

#### FE-4.1 — Videos e imágenes contra el backend (7.11–7.14)
- **Entregables:** `RemoteVideoRepository` (desaparece `EdicionesLocales`) y lo pendiente de cada vista:
  - **7.8:** cargar las capas de cobertura y rutas (hoy los interruptores existen sin datos).
  - **7.11 Galería:** vista de mapa con las fotos filtradas (con un filtro de video activo, solo las de ese video);
    filtro por fecha (requiere `capturada_en` real); Eliminar y Reasignar contra `/v1/admin/images` (hoy solo en
    memoria) con un selector de lugares reales en vez de texto libre; navegar al detalle (7.12) con `videoId` y
    `fotoId`; botón «Subir imágenes» (opcional).
  - **7.12 Detalle de imagen:** vista nueva.
  - **7.13 Lista de videos:** duración, minimapa, orden y búsqueda, acciones por fila, comparar cobertura, «Nuevo
    video».
  - **7.14 Detalle de video:** duración en el encabezado; confirmación reforzada por pulsación larga; borrado con
    `DELETE /v1/admin/videos/{id}` (`202`: el video sale de la búsqueda al instante) y manejo de error; persistir
    renombrar y eliminar; que la Galería se refresque al eliminar fotos desde aquí; navegar al Detalle de imagen; nombre
    editable en el encabezado; reutilizar la base común de mapas en el modo Mapa de la galería y en el minimapa de 7.12.
- **Criterios de cierre:**
  - C1. Las vistas 7.11 a 7.14 funcionan solo con datos del backend (`EdicionesLocales` ya no existe).
  - C2. Borrar un video desde 7.14 lo quita de la lista y de la Galería sin reiniciar la app.
  - C3. Renombrar un video en la app se refleja en `GET /v1/admin/videos/{id}`.
- **Historias:** HU-17, HU-18.

#### FE-4.2 — Ajustes (6.7)
- **Entregables:** vista 6.7 con persistencia local; relación entre la unidad «metros / pasos» y la longitud de paso
  calibrada (7.3b).
- **Criterios de cierre:**
  - C1. Cada ajuste se aplica de inmediato y se conserva tras reiniciar la app (prueba instrumentada
    `AjustesPersistenciaTest`).
  - C2. La vista pasa las pruebas de accesibilidad de FE-3.5.
- **Historias:** HU-07.

#### FE-4.3 — Limpieza y deuda técnica
- **Código y configuración:**
  - Sacar de `java/com/example/myapplication/` los archivos `archivos_zip.py`, `crear_archivos.py` y `out.zip`.
  - Quitar la dependencia sin uso de Coil 3 (`libs.coil.compose`, `io.coil-kt.coil3`); las vistas usan Coil 2
    (ARCHITECTURE §4.1, «Trampas»; visto en FE-3.1). Arreglar el error de `lintDebug` en `MapaWebView.kt:125` (§4.1).
  - Corregir el texto de `validate31.py` para la manual C2c y el paso guiado (hoy aún pide TalkBack, ▶ y `dumpsys`;
    C2c es solo por voz desde el 2026-10-26, ARCHITECTURE §5.11), si antes no lo hace otro lote que toque el código.
  - Quitar de `project/` (código, scripts y su README) las referencias a `eafit.mbtiles`.
  - Quitar `ACTIVITY_RECOGNITION` de `Permisos.INICIALES`, `Permisos.ACTIVIDAD`, la ruta `admin/calibracion` y el
    Manifest (3.2, «Permisos de Android»).
  - Reactivar el control de calidad de imagen (`CalidadImagen.kt`): foto borrosa y poca luz en 6.2 y 7.4.
  - Proteger `SpeechRecognizer` con `isRecognitionAvailable` (9.2).
  - Empaquetar Leaflet y fuentes en `assets/` (decisión abierta 13).
  - Migrar `MapaPublicoScreen` a `MapaWebView(…, pasarInsets = false)` (5.9); confirmar que solo la usa la ruta
    `mapa` (FE-3.1) y quitar el botón GPS que ya no se usa (decisión abierta 14); CSS de mapas duplicado →
    `mapa_base.css`.
  - Mover `BotonIcono` y `Modifier.tarjeta` a `ui/components/`; `GaleriaColores` y demás paletas privadas a
    `CampusColors`; tema propio en lugar del `MaterialTheme` por defecto (5.4).
  - `toString()` de `Sesion` y `Usuario` sin token ni correo (5.6).
  - Guardas de rol en las rutas `admin/*` (5.8).
  - Enriquecer los *stubs* que queden (errores `IOException`, lugares de `DEPORTES` y `ADMINISTRACION`, `imagenUrl`,
    distancias nulas, fecha y último video nulos; 5.6).
- **Diseño pendiente:** 7.3 — foto de referencia y badge de brújula «N»; 7.4 — brújula «N», mapa que no rota y
  teselas de OSM en vez de satélite; 7.3b — promediar varias pasadas; decidir 0,70 m o 0,72 m como valor genérico.
- **Decisiones a tomar:** nombre del producto (decisión abierta 17) y nombre por defecto de los videos (19).
- **Criterios de cierre:**
  - C1. En `project/app/src/main/java/` no hay archivos `.py` ni `.zip`.
  - C2. No quedan referencias a `eafit.mbtiles` en `project/` (`docs/` puede citarlo como historia).
  - C3. `ACTIVITY_RECOGNITION` no aparece en el Manifest ni en `Permisos`.
  - C4. Ninguna página de `assets/` carga recursos de `unpkg.com` ni de Google Fonts.
  - C5. Las demás tareas de la lista están hechas o abiertas como lote nuevo (lista revisada en el PR).
- **Historias:** HU-08.

#### FE-5.1 — Navegación guiada, llegada y fusión (diferido)
- **Alcance:** vistas 6.5 y 6.6 sobre `PdrTracker`; fusión PDR + visual en `domain/fusion/` (decisiones abiertas 4 y 5);
  corrección visual con BE-5.1; rutas con BE-5.3; funcionamiento sin conexión (decisión abierta 6); deriva de la brújula
  (decisión abierta 16).
- **Historias:** HU-04, HU-05, HU-06.

#### FE-5.2 — Estadísticas (diferido)
- **Alcance:** vista 7.15 con BE-5.2.
- **Historias:** HU-19.

#### FE-6.1 — Preparación para publicar (diferido)
- **Alcance:** proveedor de teselas (decisión abierta 1), SDK mínimo y dispositivos soportados (decisión abierta 8),
  firma y distribución del APK, URL del entorno `prod`.
- **Historias:** HU-20.

---

## 3. Estado de los lotes

> **Única tabla de estado de la app.** Valores: `Pendiente`, `En curso`, `Bloqueado` (una precondición de validación
> no se cumple), `Hecho`, `Diferido`. «Hecho» en la fase 0 significa: pantalla funcional sobre datos locales o *stubs*,
> cerrada sin validación automática. «Última validación» = commit corto y fecha de la última ejecución con código 0.

| Lote | Fase | Estado | Validación | Última validación | Versión de ARCHITECTURE al cerrar | Datos | Nota |
|---|---|---|---|---|---|---|---|
| FE-0.1 | 0 | Hecho | — | — | 0.1.0 | Local | Explicación hablada previa a los permisos nunca suena (FE-3.5) |
| FE-0.2 | 0 | Hecho | — | — | 0.1.0 | *Stub* (`EscaneoBackend`) | Control de calidad sin uso; `CONSERVAR_FOTOS = true` |
| FE-0.3 | 0 | Hecho | — | — | 0.1.0 | *Stub* (`LugaresRepository`) | |
| FE-0.4 | 0 | Hecho | — | — | 0.1.0 | *Stub* (`AuthRepository`) | |
| FE-0.5 | 0 | Hecho | — | — | 0.1.0 | *Stub* (`AdminRepository`) | |
| FE-0.6 | 0 | Hecho | — | — | 0.1.0 | Local; sincronización simulada | |
| FE-0.7 | 0 | Hecho | — | — | 0.1.0 | Local (`assets/`) | Eliminar y Reasignar solo en memoria |
| FE-0.8 | 0 | Hecho | — | — | 0.1.0 | Local (`assets/`) | 7.13 en versión mínima; renombrar y eliminar solo en memoria |
| FE-0.9 | 0 | Hecho | — | — | 0.1.0 | — | ⚠ Sin probar en dispositivo (FE-2.3) |
| FE-0.10 | 0 | Hecho | — | — | 0.1.0 | Local (`assets/`) | Compila y se abre en dispositivo; prueba completa en FE-2.3 |
| FE-0.11 | 0 | Hecho | — | — | 0.1.0 | Local (`files/recoleccion/`) | Sin pruebas automáticas (FE-2.3) |
| FE-0.12 | 0 | Hecho | — | — | 0.1.0 | Local (`SharedPreferences`) | ⚠ Pasada completa sin probar (FE-2.3) |
| FE-1.1 | 1 | Hecho | [1-1](./validation/validation-1-1.md) | `c5917bd` 2026-10-25 | 0.4.0 | `dev` (`GET /v1/health`) | `validate11.py --entorno dev` con código 0 en un Xiaomi 23028RA60L (Android 14): C1a (`GET /v1/health` → 200 desde el teléfono), C2, C4a y C4b (338 ms). C1b manual: [capturas](./validation/evidencia/fe-1-1/) «Conectado» → modo avión «Sin conexión» → «Conectado». C3: `frontend.yml` en verde en el PR #8 (`104673b`). En MIUI/HyperOS hay que activar «Instalar vía USB» en Opciones de desarrollador; sin eso `installDebug` da `INSTALL_FAILED_USER_RESTRICTED` |
| FE-1.2 | 1 | Hecho | [1-2](./validation/validation-1-2.md) | `4d578c5` 2026-10-25 | 0.5.0 | `dev` (`POST /v1/auth/login`; cuenta `validacion+user` por tarea suelta de `migrate`) | `validate12.py --entorno dev` con código 0 en el Xiaomi 23028RA60L (Android 14), informe `.validacion/FE-1.2-20261026-013200.json`: P1–P5; C1 Panel con «Hola, Administrador» y «Cerrar sesión» a los 6,6 s; C2 «Sin permisos» a los 2,9 s sin «Cerrar sesión»; C3 `SesionVencidaTest` 9/9; C4 `RemoteAuthRepositoryTest` 6/6. En MIUI/HyperOS hace falta además «Depuración USB (Configuración de seguridad)» (`pm grant` e `input`). La primera ejecución (sobre `a86649c`) pasó igual, pero salió `-dirty` por `.idea/vcs.xml` (Android Studio añade el mapeo a la raíz del monorepo) y un `.kotlin/sessions/*.salive` versionado por error; desde `4d578c5`, `.kotlin/` está en `.gitignore` y `vcs.xml` lleva ese mapeo |
| FE-2.1 | 2 | Hecho | [2-1](./validation/validation-2-1.md) | `a69a79a` 2026-10-26 | 0.7.2 | `dev` (`/v1/collect/…`, `GET /v1/admin/videos[/{id}]`, S3 `dataset/`); local (`files/recoleccion/`) | Código y pruebas listos (ARCHITECTURE 0.7.0, §4.4): vista 7.5 y su ruta (C4), cola de subida en `data/local/` (re-codificación ≤ 1600 px y ≤ 4 MB, lotes de 50, `PUT` sin interceptores, `403` → URLs nuevas, «esperar sesión», retomar sin duplicar), `EstadoFoto.PENDIENTE`, Galería/Lista/Detalle con los recorridos locales y tarjeta de subidas en el Panel. 151 casos JVM (C2a 13/8/13, C3a 12); `validate21.py --entorno local` con código 0 (2026-10-25; P1, C2a, C3a, C4). **En `dev`, en casa por decisión del usuario (2026-10-26)**, con un Redmi Note 15 Pro y el APK de `4c87f5e`: recorrido de prueba `validacion_21_casa` (`rec_0017`, 56 fotos, «Cada 3 s»). C2c manual: con 13 fotos subidas, modo avión, app cerrada desde Recientes, reabierta, y la subida se retomó hasta «Subido» (capturas de 7.5 subiendo, 24 de 56, y de 7.13 vistas por el maestro; no se versionan: muestran la casa). `validate21.py --entorno dev --video validacion_21_casa` con código 0 (informe `.validacion/FE-2.1-20261026-130806.json`): P1–P8 (`embedding` encendido en 173 s y apagado al final), C1 (56 fotos `procesada` en 244 s), C2a, C2b (56 = `total_fotos`, sin órdenes repetidas), C3a, C3b (máx. 473 591 B y 1600 px) y C4. La primera corrida (sobre `5642cbd`) se bloqueó por un error del validador en P4, corregido en `a69a79a` (0.7.2). Al terminar, el maestro borró del backend los dos recorridos de prueba (`validacion-21-casa`, 11 fotos, y `validacion_21_casa`, 56) con SQL por la tarea de validación y `aws s3 rm` (autorizado por el usuario): `limpiar-validacion` no sirve para recorridos de la app, porque su `ref_cliente` es `rec_NNNN` y no empieza por `validacion-`. Hallazgo: en 7.14 (Detalle de video) las miniaturas de un recorrido local salen vacías, aunque en 7.5 se ven (pendiente, FE-4.1). Decisiones provisionales del maestro, a confirmar por el usuario: CHANGELOG 0.7.0, «Pendiente» |
| FE-2.2 | 2 | Pendiente | [2-2](./validation/validation-2-2.md) | — | — | | |
| FE-2.3 | 2 | Hecho | [2-3](./validation/validation-2-3.md) | `02adcb9` 2026-10-25 | 0.7.1 | Local (`files/recoleccion/`, `campus_calibracion`); no usa el backend | Código y pruebas listos (ARCHITECTURE 0.6.0, §4.3): C1 con las cuatro clases en Gradle (13, 11, 10 y 6 casos; `CalibracionPasoTest` y `StepDetectorTest` no existían), C2 sin cambios de código, retomar tras matar el proceso (C4) y `PdrTracker` que sigue el ciclo de vida del proceso (C5); ruta `mapa` de prueba (`--es ruta mapa`). `validate23.py --entorno local` con código 0 (2026-10-25). **En `dev`** (2026-10-25, Xiaomi 23028RA60L, Android 14): `validate23.py --entorno dev` con código 0 sobre `02adcb9` (informe `.validacion/FE-2.3-20261026-023206.json`; calibración guardada: ninguna, la app usaba 0,72 m). **C4 pasa:** una sola carpeta nueva `rec_0013`, `finalizado`, fotos `0001`–`0021` seguidas (9 antes de `am kill`, 12 después); evidencia `c4-recoleccion.txt` y `c4-manifest.json` (el video `c4-video.mp4` no se sube: puede mostrar la cámara en casa). **C5 pasa:** en segundo plano la app no está en las conexiones activas de `dumpsys sensorservice` (calibración y mapa) y en primer plano sí (acelerómetro y vector de rotación); `app.log` con `sensores quitados (detener)`, `(segundo plano)` y `registrados (primer plano; …)`; evidencia `c5-*.txt`. Hallazgo: abrir la app desde el ícono tras la ruta de prueba `mapa` muestra Inicio, pero el `PdrTracker` del mapa sigue en la pila y vuelve a registrar sensores en primer plano (21:48:35): el PDR sigue al proceso, no a la pantalla visible (tener en cuenta en FE-3.1). **C3, en casa por decisión del usuario (2026-10-26)**, en un Redmi Note 15 Pro con el APK de `4c87f5e`: 7.3b contó bien los pasos reales (10 en un tramo de 7,1 m marcado en el mapa, sin medir en el terreno), así que la longitud guardada (0,71 m) es provisional; el PDR del mapa público y 7.3 en un recorrido conocido de ≥ 100 m no se hicieron. Evidencia: [`registro.md`](./validation/evidencia/fe-2-3/registro.md). **Antes de grabar el dataset hay que recalibrar 7.3b en un tramo recto medido, con el teléfono con el que se grabe** |
| FE-3.1 | 3 | Hecho | [3-1](./validation/validation-3-1.md) | `b553390` 2026-10-26 | 0.8.1 | `dev` (`GET /v1/places`, 0 lugares; lugar de prueba `validacion-3-1-lugar` por `POST`/`DELETE /v1/admin/places`, borrado al terminar) | Código y pruebas (ARCHITECTURE 0.8.0, §4.5): `RemoteLugaresRepository` (`GET /v1/places`; sin posición hasta FE-3.2, ADR-FE-23), foto del lugar o ícono de respaldo, entrada al mapa desde Inicio (voz «mapa» y acción de TalkBack «Ver mapa»; Atrás vuelve) y el PDR del mapa atado al ciclo de vida de su pantalla (hallazgo de FE-2.3, ADR-FE-22); 171 casos JVM; `frontend.yml` en verde sobre `b553390`. `validate31.py --entorno dev` con código 0 sobre `b553390` (sin `-dirty`) en el Xiaomi 23028RA60L (Android 14), informe `.validacion/FE-3.1-20261026-142022.json` (14:20–14:23 UTC): P1–P5 (`GET /v1/places` → 0 lugares en `dev`); C1a 9/9; C1b «1 lugares en Selección de destino = GET /v1/places (incluye validacion-3-1-lugar; 2 desplazamientos)», con Destino abierto por el usuario con la voz «dos» y el Enter del paso guiado mandado por el maestro; C2a 5/5 y 6/6; C2b; limpieza: lugar borrado y `am force-stop`. El primer intento (14:17 UTC) dio código 3: C1b `INSTALL_FAILED_USER_RESTRICTED` (MIUI había apagado «Instalar vía USB»; se reactivó junto con «Depuración USB (Configuración de seguridad)»). C2c, solo por voz (09:24 de Bogotá): app abierta desde el lanzador, «mapa» → mapa público («StepTracker · Comenzar») → Atrás → Inicio («Te escucho…»); evidencia [`c2-1-inicio.png`, `c2-2-mapa-por-voz.png`, `c2-3-atras-a-inicio.png`](./validation/evidencia/fe-3-1/) (fotogramas de un `screenrecord` de 74 s, sin audio, que no se versiona: 14 MB); no se fijó punto ni se pulsó ▶, así que no hubo líneas `Pdr` ni `dumpsys sensorservice`. **Por decisión del usuario del 2026-10-26** (§2.2 FE-3.1, «Si, por favor. Cambialo y demos por hecho lo que llevamos.») C2 queda solo con la voz y pasan a FE-3.6 la prueba con TalkBack («Ver mapa», fijar inicio y ▶) y el punto de inicio sin tocar el mapa (desde Ubicarme). Hallazgos con TalkBack 17.0.1 en el Xiaomi: al activarlo sale primero su tutorial; el toque con tres dedos abre «Search screen», no el menú de TalkBack; el doble toque en el botón principal de Inicio ejecuta su acción principal (Ubicarme), no «Ver mapa»; cómo abrir las acciones, sin comprobar. Orden por popularidad: BE-5.2 |
| FE-3.2 | 3 | En curso | [3-2](./validation/validation-3-2.md) | — | — | `dev` (`POST /v1/localize`, `GET /v1/admin/videos` para el dataset, `embedding`); local (`files/camera/photos/`, `app.log`) | Código y pruebas listos (ARCHITECTURE 0.9.0, §4.6): `POST /v1/localize` real (`RemoteLocalizacionRepository`: fotos re-codificadas a 1024 px, rumbos en norte verdadero con `ConversionRumbo` y la declinación), `CONSERVAR_FOTOS = false` con la carpeta del escaneo borrada al recibir la respuesta (también las fotos tardías), errores hablados (503 → «El servicio de ubicación no está disponible en este momento»), vista 6.3 y `SesionDeNavegacion` (decisión abierta 15: «En memoria», decisión del usuario del 2026-10-26), destino de 6.4 que llega a 6.3 con su distancia y dirección (sin 6.5 hasta FE-5.1) y distancias reales en Destino con una ubicación vigente. 221 casos JVM (C1a 11, 11 y 5; C2 7; C3a 6; C4a 7); `validate32.py --entorno local` con código 0 (2026-10-26; P1, C1a, C2, C3a, C4a). **Falta** `validate32.py --entorno dev` (hoy da código 2: BE-3.2 «En curso», sin dataset ni calibración) con C1 en el campus (10 puntos, `embedding` encendido, paso guiado C1b y evidencia C1c), C4 de noche (`embedding` apagado, C4b y C4c) y C3b; `validation-3-2` §3 y §5. **Primera ejecución en `dev` (2026-10-26, el maestro, sobre `e3f3d12`):** P1–P5 pasan, `[FALLA] P6 BE-3.2 no está «Hecho»`, P7 no evaluada, `Resultado: bloqueado (código 2)` (informe `.validacion/FE-3.2-20261026-153456.json`): lo esperado hasta que BE-3.2 tenga dataset y calibración. **Prueba de humo en casa (2026-10-26, decisión del usuario; no cuenta como criterio):** Xiaomi con el APK de `076c853`, `embedding` encendido y dataset vacío: Ubicarme → `POST /v1/localize` 200 en 1911 ms con `sin_coincidencias`, 6.3 «No reconocí este lugar», declinación −7,9° y las 10 copias del escaneo borradas ([evidencia](./validation/evidencia/fe-3-2/); ARCHITECTURE §4.6, 0.9.2) |
| FE-3.3 | 3 | Pendiente | [3-3](./validation/validation-3-3.md) | — | — | | Para validar espera BE-3.3 (alertas del backend, fuera del núcleo) |
| FE-3.4 | 3 | Pendiente | [3-4](./validation/validation-3-4.md) | — | — | | |
| FE-3.5 | 3 | Pendiente | [3-5](./validation/validation-3-5.md) | — | — | | Requiere decidir la decisión abierta 18 |
| FE-3.6 | 3 | Pendiente | [3-6](./validation/validation-3-6.md) | — | — | | Fuera del núcleo (decisión del usuario del 2026-10-25: «No necesitamos las alertas por el momento»). Sale de FE-3.1 y FE-3.2. Desde el 2026-10-26 (decisión del usuario al cerrar FE-3.1) lleva también la prueba con TalkBack del mapa (C5) y el punto de inicio del mapa sin tocarlo |
| FE-4.1 | 4 | Pendiente | [4-1](./validation/validation-4-1.md) | — | — | | |
| FE-4.2 | 4 | Pendiente | [4-2](./validation/validation-4-2.md) | — | — | | Puede empezar ya |
| FE-4.3 | 4 | Pendiente | [4-3](./validation/validation-4-3.md) | — | — | | Puede empezar ya (salvo lo que dependa de decisiones) |
| FE-5.1 | 5 | Diferido | — | — | — | | |
| FE-5.2 | 5 | Diferido | — | — | — | | |
| FE-6.1 | 6 | Diferido | — | — | — | | |

---

## 4. Matriz de trazabilidad

| Historia | Lotes de la app que la entregan | Lotes de otras carpetas que la habilitan |
|---|---|---|
| HU-01 Ubicarme con una vuelta | FE-0.2, FE-3.2 | BE-2.4, BE-3.2, EMB-2.1–EMB-3.2, INF-1.1–INF-1.4 |
| HU-02 Conocer mi ubicación y referencias | FE-3.2 | BE-3.1, BE-3.2, EMB-3.2 |
| HU-03 Elegir destino por voz o lista | FE-0.3, FE-3.1 | BE-3.1 |
| HU-04 Ser guiada hasta el destino | FE-5.1 | BE-5.3 |
| HU-05 Avisos de obstáculos | FE-3.6, FE-5.1 | BE-3.3 |
| HU-06 Seguimiento continuo de la posición | FE-0.9, FE-5.1 | BE-5.1, EMB-5.1 |
| HU-07 Personalizar voz y avisos | FE-4.2 | — |
| HU-08 Usar la app solo con voz o TalkBack | FE-0.1, FE-3.5, FE-4.3 | — |
| HU-09 Saber si hay conexión | FE-0.1, FE-1.1 | BE-1.1, INF-1.4 |
| HU-10 Iniciar sesión como admin | FE-0.4, FE-1.2 | BE-1.3, INF-1.4 |
| HU-11 Panel con resumen | FE-0.5, FE-2.2 | BE-2.3 |
| HU-12 Fijar el punto de partida y calibrar el paso | FE-0.10, FE-0.12, FE-2.3 | — |
| HU-13 Recolectar fotos geoetiquetadas | FE-0.11, FE-2.3 | INF-1.2 |
| HU-14 Subir un recorrido | FE-2.1 | BE-2.1, BE-2.2, EMB-2.1, INF-1.2, INF-2.1 |
| HU-15 Gestionar lugares | FE-3.4 | BE-3.1 |
| HU-16 Gestionar alertas en el mapa | FE-0.6, FE-3.3 | BE-3.3 |
| HU-17 Revisar y corregir imágenes | FE-0.7, FE-4.1 | BE-4.1 |
| HU-18 Gestionar recorridos | FE-0.8, FE-4.1 | BE-4.1 |
| HU-19 Ver estadísticas | FE-5.2 | BE-5.2 |
| HU-20 Desplegar automáticamente | FE-1.1, FE-6.1 | INF-0.1, INF-0.2, INF-1.3, BE-1.1, EMB-1.1 |
| HU-21 Mantener el gasto bajo 100 USD/mes | — | INF-0.1, INF-2.1, INF-6.1 |
| HU-22 Diagnosticar fallos | FE-1.1 | INF-3.1, BE-1.1, BE-6.1 |
| HU-23 Privacidad de quien se ubica | FE-3.2 | BE-3.2, INF-1.2 |

---

## 5. Catálogo de historias de usuario (único del proyecto)

> **Propuestas:** el proyecto no tenía historias de usuario; estas se derivan de las vistas y funcionalidades del
> ARCHITECTURE de la app y deben validarse con el equipo y con personas usuarias. Cambiar una historia se registra en
> el `CHANGELOG.md` de esta carpeta. Roles: **usuaria** (persona con discapacidad visual), **admin** (persona vidente
> que mantiene el sistema), **equipo** (quienes desarrollan y operan).

**HU-01 — Ubicarme con una vuelta.** Como usuaria, quiero girar sobre mí misma sosteniendo el teléfono para saber
dónde estoy, sin tener que apuntar la cámara. *Criterios:* la app indica por voz cómo girar y avisa si voy muy rápido
o el teléfono no está vertical; captura 5 fotos sola; el resultado llega en ≤ 10 s desde la última foto; puedo
cancelar en cualquier momento. *Vistas:* 6.2.

**HU-02 — Conocer mi ubicación y referencias.** Como usuaria, quiero escuchar dónde estoy y qué hay a mi alrededor,
con una indicación honesta de cuán segura está la app. *Criterios:* se lee el lugar más cercano y hasta tres
referencias con dirección relativa («a tu derecha»); con confianza baja la app lo dice y ofrece repetir; puedo pedir
que lo repita. *Vistas:* 6.3.

**HU-03 — Elegir destino por voz o lista.** Como usuaria, quiero decir el nombre del lugar al que voy (o elegirlo de
una lista) y que la app confirme antes de seguir. *Criterios:* entiende nombres y alias aproximados; si hay varias
coincidencias, las lee y me deja elegir; pide confirmación «sí / no». *Vistas:* 6.4.

**HU-04 — Ser guiada hasta el destino.** Como usuaria, quiero instrucciones por voz y vibración paso a paso hasta
llegar. *Criterios:* instrucciones cortas («sigue recto 20 m», «gira a la izquierda»); recalcula si me desvío; avisa
al llegar. *Vistas:* 6.5, 6.6.

**HU-05 — Recibir avisos de obstáculos.** Como usuaria, quiero que la app me avise de obstáculos cercanos aunque no
tenga conexión. *Criterios:* el mensaje escrito por el admin se lee al entrar en el radio de la alerta, una vez por
aproximación; las alertas de prioridad alta interrumpen otras instrucciones; funciona en modo avión tras una
sincronización. *Vistas:* 2.5, 6.3, 6.5.

**HU-06 — Seguimiento continuo de la posición.** Como usuaria, quiero que la app siga sabiendo dónde estoy mientras
camino, sin volver a girar. *Criterios:* la posición avanza con mis pasos; se corrige sola con fotos automáticas; si
pierde precisión, me lo dice. *Vistas:* 2.3, 6.5.

**HU-07 — Personalizar voz y avisos.** Como usuaria, quiero ajustar la velocidad de la voz, la vibración, el detalle
de las instrucciones y la unidad de distancia. *Criterios:* los cambios se aplican de inmediato y se conservan.
*Vistas:* 6.7.

**HU-08 — Usar la app solo con voz o con TalkBack.** Como usuaria, quiero hacer todo por voz o con el lector de
pantalla. *Criterios:* toda acción tiene equivalente por voz y táctil; todos los elementos tienen descripción; áreas
táctiles de 56–64 dp; nunca hablan dos voces a la vez. *Vistas:* todas las públicas.

**HU-09 — Saber si hay conexión con el servidor.** Como usuaria, quiero saber si la app puede ubicarme ahora.
*Criterios:* Inicio indica conectado / sin conexión; los errores de red se dicen en voz alta con una salida clara.
*Vistas:* 6.1.

**HU-10 — Iniciar sesión como administrador.** Como admin, quiero entrar con mi correo y contraseña para acceder a
las herramientas de administración. *Criterios:* credenciales inválidas, sin conexión y sin permisos se distinguen;
una cuenta sin rol admin no abre el panel. *Vistas:* 7.1.

**HU-11 — Ver el panel con un resumen.** Como admin, quiero ver de un vistazo el tamaño del dataset, los lugares, las
alertas activas, el último recorrido y lo pendiente de subir. *Vistas:* 7.2.

**HU-12 — Fijar mi punto de partida y calibrar mi paso.** Como admin, quiero marcar exactamente dónde empiezo y medir
mi longitud de paso para que las fotos queden bien ubicadas. *Criterios:* punto y rumbo editables; calibración en un
tramo de ≥ 30 m; la longitud calibrada se usa en la siguiente recolección. *Vistas:* 7.3, 7.3b.

**HU-13 — Recolectar fotos geoetiquetadas caminando.** Como admin, quiero caminar por el campus mientras la app toma
fotos con su coordenada y orientación. *Criterios:* captura por distancia o tiempo; puedo pausar, re-anclarme y
agregar alertas; nada se pierde si la app se cierra. *Vistas:* 7.4.

**HU-14 — Revisar y subir un recorrido.** Como admin, quiero revisar las fotos de un recorrido y subirlo para que se
indexe, aunque la conexión sea mala. *Criterios:* puedo descartar fotos; veo el progreso por foto; una subida
interrumpida se retoma sin duplicar. *Vistas:* 7.5.

**HU-15 — Gestionar lugares.** Como admin, quiero crear, editar y borrar los lugares a los que se puede ir, con
sus alias y descripción. *Vistas:* 7.6, 7.7.

**HU-16 — Gestionar alertas en el mapa.** Como admin, quiero colocar, mover, editar, desactivar y borrar alertas, y
sincronizarlas con todos los teléfonos. *Vistas:* 7.8, 7.9, 7.10.

**HU-17 — Revisar y corregir imágenes del dataset.** Como admin, quiero buscar, filtrar, corregir la coordenada,
reasignar a un lugar o borrar imágenes. *Vistas:* 7.11, 7.12.

**HU-18 — Gestionar recorridos.** Como admin, quiero ver cada recorrido en el mapa, renombrarlo y borrarlo con todas
sus fotos. *Criterios:* borrar exige confirmación reforzada y cambia los resultados de ubicación de inmediato.
*Vistas:* 7.13, 7.14.

**HU-19 — Ver estadísticas de uso y cobertura.** Como admin, quiero saber dónde se ubica la gente, dónde falla y qué
destinos se buscan, para decidir dónde recolectar más. *Vistas:* 7.15.

**HU-20 — Desplegar automáticamente.** Como equipo, queremos que cada cambio integrado en `main` se pruebe y despliegue
sin pasos manuales ni llaves guardadas en GitHub.

**HU-21 — Mantener el gasto bajo 100 USD al mes.** Como equipo, queremos avisos antes de pasarnos del presupuesto y
apagar lo que no se usa.

**HU-22 — Diagnosticar fallos.** Como equipo, queremos encontrar la causa de un error a partir de lo que vio la persona
(un `X-Request-Id`) y recibir alertas cuando algo falla.

**HU-23 — Privacidad de quien se ubica.** Como usuaria, quiero que las fotos que tomo para ubicarme no se guarden ni
se puedan asociar a mí. *Criterios:* el servidor las descarta tras responder; el teléfono no las conserva en
producción; las estadísticas son anónimas.
