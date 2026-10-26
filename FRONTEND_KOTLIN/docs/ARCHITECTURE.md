# ARCHITECTURE — App Android (`FRONTEND_KOTLIN`)

| Campo | Valor |
|---|---|
| Versión del documento | **0.5.0** (historia en [`CHANGELOG.md`](./CHANGELOG.md)) |
| Fecha | 2026-10-25 |
| Estado del código | Flujos público y de administración con varias vistas construidas sobre datos locales y *stubs*. Desde FE-1.1 existe el cliente HTTP (`data/remote/`, §5.10) y el indicador de conexión de Inicio usa `GET /v1/health` real; desde FE-1.2 el Login usa `POST /v1/auth/login` real, la sesión guarda `expira_en` y una ruta protegida sin sesión vuelve a Login (§5.3). El resto de repositorios siguen siendo *stubs*. El estado por lote está **solo** en [`PLAN.md`](./PLAN.md) §3 |
| Qué se construye y en qué orden | [`PLAN.md`](./PLAN.md) · cómo se comprueba cada lote: [`validation/`](./validation/) |

Este documento describe la app: qué hace, cómo está organizada, qué sistemas la componen y **qué debe tener cada
vista** (con el archivo que la implementa). La sección de vistas está pensada para usarse como brief de diseño
(por ejemplo, para pedirle a una IA que genere los diseños de frontend).

> Todo el código está en `FRONTEND_KOTLIN/project/` (proyecto Gradle; estructura de la carpeta en §3.2).
> Ruta base del código Kotlin: `project/app/src/main/java/com/example/myapplication/`. Las rutas de archivo de este
> documento son relativas a esa carpeta, salvo las que empiezan por `app/` (relativas a `project/`) y las de `assets/`
> (que es `project/app/src/main/assets/`).
>
> **Antes de crear o reutilizar algo, consulta el §5** (catálogo de piezas reutilizables y contratos entre vistas):
> ahí está cómo usar cada pieza sin tener que leer sus archivos.

---

## 1. Propósito, alcance y cómo leer este documento

### 1.1 Qué cubre y qué no
- Cubre la app Android completa: vistas, voz, cámara, sensores (PDR), mapas en `WebView`, almacenamiento local y cómo
  consume el backend.
- No cubre la API del backend ni la infraestructura: se **enlazan** (regla de contratos, abajo).

### 1.2 Regla de contratos del monorepo

| Interfaz | Única fuente de verdad |
|---|---|
| Puentes WebView ↔ Android, almacenamiento local (`manifest.json`, `files/recoleccion/`, `SharedPreferences`), rutas y datos entre vistas, piezas reutilizables, **cómo la app consume la API** (mapeo a modelos, errores, rumbo) y lo propio de sus validadores | **Este documento, §5** |
| Contrato común de los validadores de lotes | `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11 |
| API REST, códigos de error, formato de cada respuesta | `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5 |
| URL pública de la API (`api_base_url`) y encendido de embeddings en `dev` | `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.2, §3.4 y §5.10 |

Un cambio de interfaz se hace primero en el §5 del dueño (subiendo su versión y con entrada en su `CHANGELOG.md`) y
después en el código.

### 1.3 Numeración (cambió en la versión 0.2.0)
- §2 (funcionalidades), §6 (vistas públicas), §7 (vistas de administración) y las **decisiones abiertas 1–16**
  (§8.2; la 17, la 18 y la 19 son nuevas) conservan su numeración anterior: «vista 7.4», «2.6» o «decisión abierta 15» siguen siendo válidos.
- El antiguo **§11** (catálogo y contratos entre vistas) es ahora el **§5**: lo que antes era «11.5» es «5.5».
- El antiguo §4 (estructura de paquetes) es el **§3.2**, y el antiguo §5 (mapa de vistas) es el **§4**.
- El antiguo §10 (estado de implementación), las listas de pendientes de cada vista y el antiguo §11.10 pasaron a
  `PLAN.md` (estado y tareas) y a `CHANGELOG.md` (historia de lo verificado).

---

## 2. Visión general y funcionalidades

Campus Locator es una app Android para **personas con discapacidad visual** que permite:

1. **Ubicarse** dentro del campus (*"¿dónde estoy?"*).
2. **Ser guiado por voz** hasta un lugar del campus (*"quiero ir a…"*).
3. (Admin) **Construir el dataset** de imágenes de referencia que hace posible lo anterior.
4. (Admin) **Editar el mapa** (capa de alertas sobre el mapa de OpenStreetMap) agregando
   **alertas de obstáculo** con un mensaje que se le leerá al usuario ciego cuando se acerque.

Es **una sola app / un solo APK**. La interfaz de administración se habilita únicamente
cuando el usuario inicia sesión con rol `ADMIN`.

### Principios de diseño (aplican a TODAS las vistas públicas)

- **Voz primero:** toda acción importante debe poder hacerse por voz; la pantalla es un
  apoyo, no el medio principal.
- **Accesibilidad:** compatible con TalkBack, `contentDescription` en todo elemento,
  orden de foco lógico, áreas táctiles grandes (mínimo 56–64 dp), alto contraste, texto
  escalable.
- **Pocas acciones por pantalla:** botones muy grandes, poco texto, sin gestos complejos.
- **Retroalimentación multimodal:** cada evento relevante se anuncia por voz, vibración
  y, para quien ve, visualmente.
- **El usuario nunca opera la cámara:** la captura es automática.

### 2.1 Ubicarse (comando "uno")

1. En Inicio, el usuario dice *"uno"* (o toca el botón).
2. La app le indica por voz: *"Sostén el celular al frente y da una vuelta completa
   lentamente."*
3. La app abre la cámara trasera y usa el sensor de orientación (rotation vector) para
   saber cuánto ha girado. **Captura 5 fotos automáticamente**, una cada ~72° a lo largo
   de los 360° (0°, 72°, 144°, 216°, 288°). Cada foto se guarda junto con su `heading`
   (orientación).
4. Se envían las 5 fotos (+ sus rumbos, en norte verdadero) al backend (`POST /v1/localize`: contrato en
   `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5.3; uso desde la app en §5.10).
5. El backend genera embeddings DINOv2, los compara con el dataset y devuelve la posición
   estimada (lat, lng), la orientación probable y un nivel de confianza.
6. La app anuncia por voz el resultado y lo muestra en el mapa.

Casos especiales: usuario gira muy rápido (se le pide ir más lento), foto borrosa o
oscura (se repite esa captura), baja confianza (se pide repetir la vuelta), sin conexión.

> Nota: el control de calidad (foto borrosa/oscura) está **desactivado temporalmente**; ver 6.2.

### 2.2 Ir a un lugar (comando "dos")

1. El usuario dice *"dos"* y después **el nombre del destino** (reconocimiento de voz,
   con coincidencia aproximada contra la lista de lugares y confirmación por voz).
2. Se ejecuta primero el proceso de **2.1** para ubicar al usuario.
3. Se calcula la ruta sobre el grafo de caminos del campus.
4. **Guiado por voz** en tiempo real: *"sigue recto 20 metros"*, *"gira a la izquierda"*,
   *"has llegado"*. Se anuncian también las **alertas de obstáculo cercanas** definidas
   por el admin en el mapa (ver 2.5).
5. Durante el trayecto se mantiene la posición con el sistema híbrido (2.3).
6. Si el usuario se desvía, se **recalcula la ruta** y se avisa.

### 2.3 Seguimiento de posición (sistema híbrido)

Dos sistemas trabajan en paralelo y se fusionan:

| Sistema | Qué usa | Qué aporta | Limitación |
|---|---|---|---|
| **Navegación inercial (PDR)** | Detector de pasos, acelerómetro, giroscopio, rotation vector/magnetómetro, longitud de paso calibrada por dispositivo (7.3b) | Posición continua y en tiempo real, sin red | El error se **acumula** con el tiempo |
| **Corrección visual** | Foto automática periódica → backend → embedding → posición | Posición absoluta que **corrige el error acumulado** | Latencia, depende de red y de buena imagen |

**Fusión:** la posición PDR avanza en cada paso. Cuando llega una posición visual con
buena confianza, se corrige la posición actual (filtro de Kalman o filtro de partículas,
con la posición PDR como predicción y la visual como medición). La captura visual se
dispara **automáticamente** por tiempo (ej. cada N segundos), por distancia recorrida, o
cuando la incertidumbre estimada supera un umbral. **Sin intervención del usuario.**

> **Implementación actual (desde 2026-10-10):** el sistema inercial (PDR) ya existe en Kotlin y es el
> **único** sitio que calcula la posición: `sensors/PdrEngine.kt` (lógica pura),
> `sensors/StepDetector.kt` (pasos por acelerómetro) y `sensors/PdrTracker.kt` (sensores de Android).
> La posición sale de **pasos × longitud de paso** en la dirección del rumbo (la longitud es la **calibrada
> por el admin en 7.3b**, o 0,72 m por defecto si nunca se calibró): la
> velocidad y la aceleración **no** influyen en ella (la velocidad solo se muestra y la aceleración
> detecta los pasos y dibuja una gráfica). **Los pasos salen siempre del acelerómetro** (desde 2026-10-12):
> el sensor de hardware `TYPE_STEP_DETECTOR` se descartó porque tardaba 1–3 s en reaccionar y hacía lentas la
> calibración (7.3b) y la recolección (7.4); con el acelerómetro el primer paso se cuenta en ~0,1 s. La **corrección visual**
> y la **fusión** (`domain/fusion/`) todavía no existen. Detalle en 5.2.

### 2.4 Recolección del dataset (admin)

El dataset es la base del sistema: **cada registro = foto + embedding DINOv2 + coordenada
(+ orientación)**.

1. El admin inicia sesión y entra a "Recolector".
2. **Se ubica manualmente en el mapa** (toca el punto donde está parado, y fija hacia
   dónde mira). Esa es la coordenada inicial exacta.
3. Empieza la grabación de un nuevo **"video"** (ver concepto abajo) y **camina por el campus**. La app usa el mismo sistema inercial (PDR)
   para ir actualizando su coordenada, y **captura fotos automáticamente** (por tiempo y/o
   distancia), guardando cada una con su coordenada estimada y orientación.
4. Puede **reubicarse manualmente** (re-anclar) al pasar por puntos conocidos para
   corregir el error acumulado (ya que aquí no hay dataset previo contra el cual
   corregirse, o bien se corrige contra el dataset ya existente cuando lo hay).
5. Mientras camina puede **agregar alertas de obstáculo en su posición actual** con un
   botón (escribe o dicta el mensaje), sin tener que ir luego al editor de mapa.
6. Al finalizar el video, se sube al backend: se almacenan las fotos, se generan los
   embeddings con DINOv2 y se indexan (subida con URLs prefirmadas y procesamiento
   asíncrono: backend §4.5 y §4.6; uso desde la app en §5.10).

#### El concepto de "video" (recorrido de recolección)

Cada vez que el recolector se ubica en el mapa y empieza a caminar se crea un **video**
(ej. `video1`, `video2`…). **El video como tal no se guarda**: es solo un **identificador
lógico que agrupa todas las fotos tomadas durante ese recorrido**, que están relacionadas
entre sí porque pertenecen a la misma caminata continua.

- Cada foto del dataset guarda su `video_id`: `foto + embedding + coordenada + orientación + video_id`.
- Un video tiene: nombre (autonumerado, **renombrable**, ej. "video1" → "Entrada norte"),
  fecha/hora, duración, distancia, punto de inicio, nº de fotos y estado.
- **Ver un video en el mapa:** al seleccionar un video, el recolector ve en el mapa
  **SOLO las fotos de ese video** (marcadores con su orientación y la trayectoria),
  ocultando las de los demás videos.
- **Eliminar un video:** borra **el video y todas sus fotos** (archivos de imagen,
  embeddings y entradas del índice de búsqueda). Es una acción destructiva e irreversible
  que **cambia de inmediato los resultados de ubicación** del flujo público, por lo que
  exige confirmación explícita (ver vista 7.14).
- Las **alertas de obstáculo** creadas durante un video son **independientes**: borrar el
  video **no** borra esas alertas.
- Reubicarse manualmente (re-anclar) durante la grabación **no crea otro video**: se
  mantiene el mismo video y se corrigen las coordenadas de las fotos afectadas.

### 2.5 Obstáculos y alertas en el mapa

Los obstáculos **no se detectan con la cámara**: son **puntos de alerta que el
recolector/admin coloca manualmente en el mapa** y que el sistema usa para avisarle al
usuario ciego cuando está cerca.

**Qué es una alerta:**

| Campo | Descripción |
|---|---|
| Coordenada | Punto en el mapa donde está el obstáculo o la zona de cuidado |
| **Mensaje** | Texto libre escrito por el admin, que se leerá tal cual al usuario. Ej.: *"Ten cuidado, hay un lago alrededor de la biblioteca"* o *"Ten cuidado, hay bancas cerca, no te vayas a estrellar"* |
| Radio de activación | Distancia (m) a la que se dispara el aviso (ej. 15 m) |
| Tipo (opcional) | Agua, mobiliario, escalones, obra, vehículos, otro (solo para organizar/filtrar y para el ícono) |
| Prioridad | Normal / Alta (las altas interrumpen otras instrucciones de voz) |
| Estado | Activa / Inactiva (permite desactivar sin borrar, ej. obras temporales) |
| Vigencia (opcional) | Fecha de inicio/fin para obstáculos temporales |

**Cómo funciona en el flujo público:**
- La app descarga las alertas (`GET /v1/alerts`, por diferencias; §5.10) y las **guarda en local** para que funcionen sin conexión.
- Durante la **navegación guiada** (y opcionalmente al mostrar el resultado de ubicación),
  se compara la posición estimada del usuario con las alertas: si entra al radio de una
  alerta (sumando la incertidumbre actual de la posición), la app **lee el mensaje por voz**
  y vibra.
- Cada alerta se anuncia **una sola vez por aproximación** (con un tiempo de espera antes de
  repetirse) para no saturar al usuario.
- Las alertas de prioridad alta **interrumpen** la instrucción de voz en curso.
- Se priorizan las alertas que están **en la ruta** o cerca de ella.

**Cómo las crea el admin:** desde el **Editor de mapa y alertas** (vista 7.8) o desde la
vista de **Recolección en curso** con el botón "Agregar alerta aquí" (ver sección 7).

> Importante: las alertas son una **capa propia** que se dibuja encima del mapa base de
> OpenStreetMap (como capa de Leaflet) y se guarda en el backend; **el mapa base nunca se
> modifica**.

### 2.6 Mapa del campus (OpenStreetMap + Leaflet)

> **Decisión de arquitectura:** el archivo `eafit.mbtiles` **se descartó** porque no fue
> posible implementarlo. El mapa ahora se carga **directamente desde internet** desde
> OpenStreetMap, y se dibuja con **Leaflet** dentro de un `WebView`. Ya no hay un archivo de
> mapa dentro de la app ni un endpoint para versionarlo.

- **Mapa base:** teselas raster de OpenStreetMap, con la URL
  `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png` (zoom máximo 19). Se muestra la
  atribución *© OpenStreetMap* (obligatoria; ya está en `app.js`).
- **Render:** Leaflet 1.9.4, en la página web `index.html` + `app.js` ("StepTracker"), que
  se incluye en la app como assets (`app/src/main/assets/`) y se carga en un `WebView`.
- **Coordenadas:** el sistema completo (posición del usuario, fotos del dataset, lugares,
  alertas) usa **latitud / longitud** (WGS84). Leaflet se encarga de la proyección Web
  Mercator de las teselas.
- **Capas** que se dibujan sobre el mapa base: posición y orientación del usuario, punto de
  inicio, trayectoria recorrida y, a medida que se implementen, ruta, lugares de interés,
  **alertas de obstáculo** y, solo para el admin, cobertura de fotos.
- Para el admin, "modificar el mapa" significa editar estas capas (alertas y lugares).
- **Requiere conexión para el mapa base.** Sin red, las teselas que el `WebView` ya
  guardó en caché se siguen viendo y el PDR sigue calculando la posición, pero las zonas no
  visitadas antes aparecen en blanco. Las alertas y la voz funcionan sin red porque no
  dependen de las teselas (alertas en caché local, ver 2.5).

#### Qué implementa hoy `app.js` (StepTracker)

| Función | Detalle |
|---|---|
| Posición inicial | Toque en el mapa (solo si no se está rastreando) o botón GPS (`navigator.geolocation`). Al abrir, intenta usar el GPS automáticamente |
| Seguimiento por pasos (PDR) | **Ya no lo calcula la página.** Kotlin (`PdrEngine`) avanza una longitud de paso (la calibrada en 7.3b, o 0,72 m por defecto) por paso en la dirección del rumbo y envía la posición con `onNativePosition`; la página mueve el marcador, dibuja la trayectoria y calcula las estadísticas de pantalla (cadencia, calorías) |
| Rumbo | El promedio circular de las últimas 6 lecturas lo hace Kotlin (`PdrEngine`); la página solo suaviza la flecha del marcador con un filtro adaptativo. Si Kotlin avisa que no hay brújula (`onNativeBrujula(false)`), aparece una **rueda manual de rumbo** que envía `setManualHeading` |
| Trayectoria | Polilínea punteada con todos los puntos recorridos; botón de reinicio que vuelve al punto inicial |
| Panel de estadísticas | Pasos, velocidad, aceleración (con gráfica en vivo), distancia, cadencia, rumbo, calorías y coordenadas |
| Brújula | Widget con rosa de los vientos y orientación cardinal |
| Centrar | Botón que centra el mapa en la posición actual |

#### Puente WebView ↔ Android (`AndroidBridge`)

En Android **toda la lógica de pasos, rumbo y posición vive en Kotlin** (`sensors/PdrEngine`, ver
2.3 y 5.2). La página solo pide arrancar y parar, le avisa a Kotlin lo que el usuario toca (punto de
partida, rumbo manual, reinicio) y **dibuja** lo que Kotlin le envía. Ya **no hay sensores web de
respaldo** (`devicemotion` / `deviceorientation`): si la página no encuentra `window.AndroidBridge`
(navegador o iOS) el mapa se ve, pero **el seguimiento no funciona**; al pulsar ▶ avisa «El
seguimiento solo funciona dentro de la app».

Funciones del puente, formato de los mensajes y requisitos del lado Kotlin: §5.9, «`AndroidBridge`».

### 2.7 Interacción por voz

- **Entrada:** `SpeechRecognizer` de Android (comandos "uno", "dos", nombres de lugares,
  "sí/no", "repetir", "cancelar", "ayuda").
- **Salida:** `TextToSpeech`, con cola de prioridades (una alerta de obstáculo de prioridad
  alta interrumpe a una instrucción normal).
- Todo comando de voz tiene un **equivalente táctil** y es compatible con TalkBack.

---

## 3. Arquitectura

### 3.1 Arquitectura del sistema

```
┌────────────────────────── App Android ──────────────────────────┐
│  UI (Compose)  →  ViewModels  →  Domain (casos de uso)          │
│                                      │                          │
│              ┌───────────────────────┼───────────────────────┐  │
│              ▼                       ▼                       ▼  │
│        Sensores / PDR          Cámara (CameraX)        Voz (TTS/STT)
│              │                       │                          │
│              └──────────► Data (repositorios) ◄─────────────────┘
└─────────────────────────────────┬───────────────────────────────┘
                                  │ HTTPS (ApiConfig.kt)
┌─────────────────────────────────▼───────────────────────────────┐
│                          Backend                                │
│  API REST → DINOv2 (embeddings) → Búsqueda por similitud        │
│  (índice vectorial) → Dataset: foto + embedding + coordenada    │
│  Auth/roles · Lugares · Alertas · Grafo de caminos · Estadísticas│
└─────────────────────────────────────────────────────────────────┘
```

**El mapa** no pasa por el backend: el `WebView` de la app (Leaflet) pide las teselas
**directamente a OpenStreetMap** por internet.

```
┌──────────── WebView (index.html + app.js · Leaflet) ───────────┐
│  Mapa · marcador · trayectoria · capas (alertas, lugares, ...) │
└───────┬───────────────────────────────────────────────▲────────┘
        │ HTTPS (teselas)                  AndroidBridge │ (sensores, pasos, rumbo)
        ▼                                                │
 tile.openstreetmap.org                       Kotlin: sensors/ (PDR)
```

#### El backend visto desde la app

- La app solo conoce **la URL base de la API** (`ApiConfig.kt` = output `api_base_url` de Terraform + `/v1`). El
  servicio de embeddings, la base de datos, S3 y las colas quedan detrás del backend.
- Arquitectura en AWS (API Gateway HTTPS, ECS Fargate, RDS PostgreSQL + pgvector, S3, SQS):
  `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §2 y §3.
- Endpoints, cuerpos, códigos de error y límites: `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5. La tabla de «endpoints
  propuestos» que vivía aquí se reemplazó por ese contrato (diferencias en `CHANGELOG.md`, versión 0.2.0).
- Cómo los consume la app (mapeo a modelos de Kotlin, errores, rumbo, subida de fotos, caché de alertas): §5.10.
- En `dev`, el servicio de embeddings está apagado por defecto: se enciende a mano antes de probar (tarda 2–3 min) y
  se apaga solo tras 45 min sin uso y a las 22:00 (`INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §3.4 y §5.10).
  Apagado o arrancando, `POST /v1/localize` responde `503 EMBEDDING_NO_DISPONIBLE` y la app debe decirlo (§5.10);
  encendido, el objetivo es ≤ 1 s en el servidor.

### 3.2 Estructura de paquetes

Estructura de la carpeta:

```
FRONTEND_KOTLIN/
├── docs/
│   ├── ARCHITECTURE.md, PLAN.md, CHANGELOG.md
│   └── validation/                validation-<fase>-<n>.md: cómo se comprueba cada lote (§5.11)
└── project/                       todo el código: proyecto Gradle
    ├── settings.gradle.kts, build.gradle.kts, gradle/
    ├── app/                       módulo Android (paquete de abajo en app/src/main/java/…; páginas de mapa en app/src/main/assets/)
    ├── src/
    │   └── ops/                   validate<fase><n>.py y comun.py: validadores de los lotes FE-x.y (§5.11)
    ├── tests/ops/                 pruebas (pytest) de los validadores; las corre el job «validadores» de frontend.yml
    ├── pyproject.toml, uv.lock    dependencias de los validadores (grupo `ops`, vacío: solo biblioteca estándar; `dev`: pytest y ruff)
    └── .validacion/               informes JSON de los validadores (ignorada por Git)
```

CI: `.github/workflows/frontend.yml` en la raíz del monorepo (§4.1).

Paquetes del módulo `app`:

```
com.example.myapplication/
├── MainActivity.kt              # Actividad única, aloja el NavHost y pide los permisos
├── MyApp.kt                     # Application: inicia el registro (AppLog) y captura crashes
├── ApiConfig.kt                 # URL base y configuración del backend
├── logs/                        # AppLog: registro de eventos en Logcat y en archivo
│
├── ui/                          # Capa de presentación (Compose)
│   ├── navigation/              # NavHost, rutas, guardas por rol
│   ├── theme/                   # Colores (alto contraste), tipografía, formas
│   ├── components/              # Componentes reutilizables
│   ├── inicio/
│   ├── ubicacion/
│   ├── destino/
│   ├── navegacion/
│   ├── ajustes/
│   ├── auth/
│   └── admin/
│       ├── panel/
│       ├── recoleccion/     # 7.3 ubicación manual y 7.4 recolección en curso (7.5 pendiente)
│       ├── calibracion/     # 7.3b calibración de la longitud de paso
│       ├── lugares/
│       ├── mapa/            # Editor de mapa y alertas
│       ├── imagenes/
│       ├── videos/          # Lista y detalle de videos de recolección
│       └── estadisticas/
│
├── domain/                      # Lógica de negocio pura (sin Android)
│   ├── model/                   # Posicion, Lugar, Alerta, Ruta, Video, Foto, Usuario...
│   ├── usecase/                 # UbicarUsuario, CalcularRuta, IniciarRecoleccion, DetectarAlertasCercanas...
│   └── fusion/                  # Fusión PDR + posición visual (Kalman/partículas)
│
├── data/                        # Acceso a datos
│   ├── remote/                  # Cliente HTTP (Retrofit + OkHttp, ADR-FE-12), DTOs, mapeo de errores y datos (§5.10)
│   ├── repository/              # Implementaciones de repositorios
│   └── local/                   # Caché local (Room/DataStore), cola de subida offline
│
├── sensors/                     # Sensores y PDR
│   ├── PdrEngine, StepDetector, PdrTracker, OrientationProvider
│
├── camera/                      # CameraX, captura automática (una carpeta por escaneo), calidad de imagen (sin uso por ahora)
├── map/                         # WebView del mapa Leaflet/OSM, AndroidBridge y datos de capas (usuario, ruta, lugares, alertas). Hoy: MapaPublicoScreen, PuentePdr y MapaWebView (fábrica común de los WebView de mapa, 5.9)
├── voice/                       # Wrappers de TextToSpeech y SpeechRecognizer
└── session/                     # Sesión (token, rol, expira_en): SessionManager, AlmacenSesion, VigilanteSesion y EventosSesion (§5.3)
```

Pruebas unitarias (JVM) en `app/src/test/java/com/example/myapplication/`: `data/remote/` (`MapeoErroresApiTest`,
`MapeoDatosApiTest`, `ClienteApiTest`, `RemoteAuthRepositoryTest`) y `session/SesionVencidaTest` (lista y conteos en
§4.1).

> Fuera del código Kotlin, el mapa vive en `app/src/main/assets/`: `index.html` y `app.js`
> (Leaflet + OpenStreetMap, ver 2.6), las páginas del editor, del detalle de video y de la ubicación manual (`ubicacion_manual.html/js`), y la base común `mapa_base.js` (5.9).

> Actualmente en el repo existen `ui/`, `camera/`, `sensors/`, `map/`, `logs/`, `session/`,
> `data/remote/` (desde FE-1.1), `data/repository/`, `domain/model/`, `domain/usecase/`, `ApiConfig.kt`, `MyApp.kt` y
> `MainActivity.kt`; el resto (`domain/fusion/`, `data/local/`, `voice/`,
> `ui/navigation/`) se crea a medida que se implementa. ⚠ Dentro del paquete Kotlin hay archivos que
> no son código de la app (`archivos_zip.py`, `crear_archivos.py`, `out.zip`): sacarlos (`PLAN.md`, FE-4.3).

#### Navegación y roles

- Un único `NavHost`. ⚠ **Hoy vive en `MainActivity.kt` (composable `AppNav`)**, no en
  `ui/navigation/AppNavHost.kt` como se planeó; ver 5.8.
- Rutas públicas: Inicio, Ubicación, Destino, Navegación, Ajustes, Login.
- Rutas `admin/*` protegidas: si no hay sesión con rol `ADMIN` se redirige a Login. ⚠ **Hoy `AppNav`
  no aplica esa protección al entrar en la ruta**: el panel la comprueba en su `init` (`onSinSesion`) y, desde FE-1.2,
  `AppNav` vuelve a Login cuando una petición `/v1/admin/…` o `/v1/collect/…` se queda sin sesión estando en una
  pantalla `admin/…` (`EventosSesion`, §5.3 y 5.8). Guardas al entrar en cada ruta: FE-4.3.
- El acceso a Login desde Inicio debe ser discreto (el usuario final casi nunca lo usa),
  pero accesible para TalkBack.

#### Permisos de Android

| Permiso | Para qué | Tipo |
|---|---|---|
| `INTERNET` | Llamadas al backend y descarga de teselas de OpenStreetMap en el `WebView` | Normal |
| `ACCESS_NETWORK_STATE` | Indicador y aviso de pérdida de conexión | Normal |
| `CAMERA` | Escaneo 360°, corrección visual y recolección | Diálogo |
| `RECORD_AUDIO` | `SpeechRecognizer` (comandos y dictado) | Diálogo |
| `ACTIVITY_RECOGNITION` | **Ya no lo necesita el PDR** (los pasos salen del acelerómetro desde 2026-10-12). Hoy `Permisos.INICIALES` y `Permisos.ACTIVIDAD` lo siguen pidiendo sin efecto: quitarlo de ambos y del Manifest (FE-4.3) | Diálogo |
| `VIBRATE` | Vibración al capturar, girar y alertar | Normal |
| `ACCESS_FINE_LOCATION` | **Opcional.** Solo si se mantiene el botón GPS del mapa web (posición inicial). Requiere también atender los permisos de geolocalización del `WebView` | Diálogo |

No requieren permiso: acelerómetro, giroscopio, magnetómetro, rotation vector, almacenamiento
privado de la app, `keepScreenOn`. La ubicación del usuario **no depende del GPS** (se calcula con
PDR + fotos); el GPS solo es una ayuda opcional para fijar el punto inicial. No se usa
almacenamiento externo.

**Flujo de solicitud (`MainActivity.kt`):**
- **Inicio:** pide cámara, micrófono y actividad física en un solo diálogo del sistema. Inicio
  se muestra aunque se niegue alguno (queda la opción táctil).
- **Ubicarme:** vuelve a comprobar la cámara (indispensable). Si se niega, regresa a Inicio.
- Las pantallas de recolección y navegación deberán usar el mismo `PedirPermisos`.
- **Calibración (7.3b):** la ruta `admin/calibracion` aún pide `Permisos.ACTIVIDAD`, pero ya no hace falta: los pasos salen del acelerómetro, que no requiere permiso (negarlo no cambia nada).
- Si se niega el micrófono: solo botones. La actividad física ya no afecta al PDR; la página solo muestra un aviso
  (`onNativeStepUnavailable`) si el teléfono no tiene acelerómetro.
- El Manifest declara `<queries>` para `RecognitionService` y `TTS_SERVICE` (Android 11+), y
  `uses-feature` con `required="false"` para cámara, micrófono y sensores.

#### Registro de eventos (logs) y depuración

- `logs/AppLog.kt` escribe cada mensaje en **Logcat** y en el archivo `files/logs/app.log`
  (rota a ~1 MB y conserva `app.log.1`).
- `MyApp.kt` inicializa `AppLog` al arrancar y registra los crashes no capturados (tag `CRASH`).
  Debe declararse en el Manifest con `android:name=".MyApp"`.
- Cada escaneo abre una sesión (`AppLog.nuevaSesion("scan")`): sus líneas llevan un id como
  `[scan-12345]` para seguir una vuelta completa.
- Tags usados: `App`, `CRASH`, `EscaneoVM`, `Camara`, `DestinoVM`, desde FE-1.1 `Api` (una línea por petición HTTP
  con su `X-Request-Id`; formato en §5.10) y desde FE-1.2 `Sesion` (`AppLog.w`: una ruta protegida sin sesión o un
  `401` de sesión; sin token ni correo; §5.3).
- Registrar transiciones y decisiones, **no** cada lectura de sensor (50 por segundo).
- No registrar datos sensibles (tokens, credenciales).

**Cómo consultar:**
- Logcat de Android Studio: filtro `package:mine`, o `tag:EscaneoVM`.
- Archivo de log y fotos: *Device Explorer* → `data/data/com.example.myapplication/files/`
  (`logs/app.log` y `camera/photos/`), o con `adb exec-out run-as com.example.myapplication`.

---

## 4. Mapa de vistas

| # | Vista | Archivo | Flujo |
|---|---|---|---|
| 1 | Inicio | `ui/inicio/InicioScreen.kt` | Público |
| 2 | Ubicarse (escaneo 360°) | `ui/ubicacion/EscaneoScreen.kt` | Público |
| 3 | Resultado de ubicación | `ui/ubicacion/ResultadoUbicacionScreen.kt` | Público |
| 4 | Selección de destino | `ui/destino/SeleccionDestinoScreen.kt` | Público |
| 5 | Navegación guiada | `ui/navegacion/NavegacionScreen.kt` | Público |
| 6 | Llegada | `ui/navegacion/LlegadaScreen.kt` | Público |
| 7 | Ajustes | `ui/ajustes/AjustesScreen.kt` | Público |
| 8 | Login | `ui/auth/LoginScreen.kt` | Admin |
| 9 | Panel admin | `ui/admin/panel/PanelAdminScreen.kt` | Admin |
| 10 | Ubicación manual inicial | `ui/admin/recoleccion/UbicacionManualScreen.kt` | Admin |
| 10b | Calibración de la longitud de paso | `ui/admin/calibracion/CalibracionScreen.kt` | Admin |
| 11 | Recolección en curso | `ui/admin/recoleccion/RecoleccionScreen.kt` | Admin |
| 12 | Resumen de video | `ui/admin/recoleccion/ResumenVideoScreen.kt` | Admin |
| 13 | Lista de lugares | `ui/admin/lugares/LugaresScreen.kt` | Admin |
| 14 | Formulario de lugar | `ui/admin/lugares/LugarFormScreen.kt` | Admin |
| 15 | Editor de mapa y alertas | `ui/admin/mapa/EditorMapaScreen.kt` | Admin |
| 16 | Formulario de alerta | `ui/admin/mapa/AlertaFormSheet.kt` | Admin |
| 17 | Lista de alertas | `ui/admin/mapa/AlertasScreen.kt` | Admin |
| 18 | Galería de imágenes | `ui/admin/imagenes/GaleriaScreen.kt` | Admin |
| 19 | Detalle de imagen | `ui/admin/imagenes/DetalleImagenScreen.kt` | Admin |
| 20 | Lista de videos | `ui/admin/videos/VideosScreen.kt` | Admin |
| 21 | Detalle de video (mapa + eliminar) | `ui/admin/videos/VideoDetalleScreen.kt` | Admin |
| 22 | Estadísticas | `ui/admin/estadisticas/EstadisticasScreen.kt` | Admin |

Componentes compartidos en `ui/components/`: `BotonGrande.kt`, `MapaCampus.kt`, `MarcadorAlerta.kt`,
`IndicadorVoz.kt`, `BannerEstado.kt`, `DialogoConfirmacion.kt`, `TopBarAccesible.kt`.

### 4.1 Compilar, probar y CI (FE-1.1)

**Herramientas** (comprobado el 2026-10-25 en la máquina del equipo):

| Dónde | Qué hay | Para qué sirve |
|---|---|---|
| Windows | JDK: JBR 21 en `C:\Users\frank\.jdks\jbr-21.0.11` (el de `C:\Program Files\Android\Android Studio\jbr` es Java 25, que **Gradle 8.7 no admite**); Android SDK en `%LOCALAPPDATA%\Android\Sdk` (plataformas `android-35` y `android-37.0`, build-tools 34.0.0 y 36.0.0, `platform-tools` con `adb.exe`, que no está en el `PATH`); Gradle 8.7 por el *wrapper* | Compilar, pruebas unitarias, `installDebug` y `adb` (el teléfono se conecta por USB a Windows) |
| WSL (Ubuntu-26.04) | `uv`, `gh`, `terraform`, `git`, Python 3.12. **Sin JDK, sin Android SDK y sin `adb`** | Validadores (`uv run`), `terraform output` y `gh`. Gradle y `adb` se llaman en Windows por *interop* (§5.11) |
| CI (`frontend.yml`) | `ubuntu-24.04` con su Android SDK (`ANDROID_HOME`) y Temurin 21 (`actions/setup-java`, caché de Gradle) | Compilar y pruebas unitarias en cada PR y en `main` |

**Comandos** (desde `FRONTEND_KOTLIN/project/`):
- Windows (PowerShell): `$env:JAVA_HOME="C:\Users\frank\.jdks\jbr-21.0.11"; .\gradlew.bat testDebugUnitTest assembleDebug`.
  Resultado esperado: `BUILD SUCCESSFUL`; los XML JUnit quedan en `app/build/test-results/testDebugUnitTest/` y el APK
  en `app/build/outputs/apk/debug/app-debug.apk`.
- WSL, llamando al Gradle de Windows: `export JAVA_HOME='C:\Users\frank\.jdks\jbr-21.0.11' WSLENV=JAVA_HOME` y
  `cmd.exe /c '.\gradlew.bat' testDebugUnitTest` (el `.\` es obligatorio: §5.11, «Trampas»).
- Linux (CI): `chmod +x gradlew && ./gradlew --no-daemon testDebugUnitTest assembleDebug`.
- Pruebas unitarias en la JVM: `app/src/test/java/…`. Desde FE-1.1: `data/remote/MapeoErroresApiTest` (14 casos),
  `MapeoDatosApiTest` (13) y `ClienteApiTest` (7), más el `ExampleUnitTest` de la plantilla. Desde FE-1.2:
  `data/remote/RemoteAuthRepositoryTest` (6) y `session/SesionVencidaTest` (9). Total al cerrar FE-1.2: 50 casos. No
  usan Android: el código probado no llama a `android.util.Log` (el registrador se inyecta, §5.10) ni a
  `EncryptedSharedPreferences` (la sesión se prueba con un `AlmacenSesion` en memoria, §5.3).

**`frontend.yml`** (raíz del monorepo, `.github/workflows/`):

| Elemento | Valor | Quién depende de él |
|---|---|---|
| Disparadores | `pull_request` y `push` a `main` con cambios en `FRONTEND_KOTLIN/project/**` o en el propio `frontend.yml` | Un PR que solo toque `docs/` no lo dispara |
| Job `app` | nombre del check: **`compilar y pruebas unitarias`**; `actions/setup-java` (Temurin 21, `cache: gradle`); `chmod +x gradlew`; `./gradlew --no-daemon --console=plain --stacktrace testDebugUnitTest assembleDebug`; tabla de casos por clase en el resumen del job | `validation-1-1` §3 (C3) cita el nombre del check |
| Job `validadores` | nombre del check: **`validadores`**; `astral-sh/setup-uv` (uv `0.11.32`, como `backend.yml`); `uv sync --frozen --group ops`, `ruff check`, `ruff format --check`, `pytest` | `validation-1-1` §3 (C3) |
| Permisos | `permissions: {}` arriba y `contents: read` por job. No usa AWS ni variables del repositorio | — |
| Acciones | fijadas por SHA con la versión en un comentario (`checkout` v7.0.1 y `setup-uv` v10.3.2, los mismos de `backend.yml`; `setup-java` v6.1.0 = `b843ebf9…`) | — |

No corre pruebas instrumentadas (`connectedDebugAndroidTest`, necesitan dispositivo) ni `lint` (el código de la fase 0
no se ha pasado por `lint`: sin comprobar si pasa). Renombrar un job cambia el nombre del check que pide
`validation-1-1` §3: se actualizan los dos en el mismo cambio. **Sin comprobar** en un runner hasta el primer PR (C3):
la compilación en Linux con el SDK del runner no se ha ejecutado todavía.

**Trampas conocidas**
- `Unable to delete directory '…\app\build\…'` al compilar en Windows con un `app/build` que dejó Android Studio:
  Gradle no pudo borrar esas carpetas (visto el 2026-10-25; la causa exacta, sin comprobar). Solución: borrar
  `app/build` a mano (`Remove-Item -Recurse -Force app\build`) y repetir.
- `gradle/gradle-daemon-jvm.properties` pide un *toolchain* 25: Gradle 8.7 lo ignora (esa función es de Gradle 8.8+).
  Si alguien actualiza el *wrapper*, Gradle intentará usar Java 25 para el *daemon*.
- `gradlew` está en Git sin el bit de ejecución (modo `100644`): en Linux, `chmod +x gradlew` o `bash gradlew`.
- `local.properties` (ruta del SDK) no se versiona; en CI Gradle usa `ANDROID_HOME`.
- En un comentario `/** … */` de Kotlin, el texto `/*` (p. ej. una ruta `admin/` seguida de asterisco) abre un
  comentario anidado y la compilación falla con «Unclosed comment»: escribirlo de otra forma.
- La compilación con `--no-daemon` avisa «a single-use Daemon process will be forked» por `org.gradle.jvmargs`: es
  normal.
- En las pruebas, `assertThrows(X::class.java) { runBlocking { llamar { api.ruta() } } }` no compila («Argument type
  mismatch»): el `ThrowingRunnable` devuelve `void`, Kotlin infiere `T = Unit` para `llamar` y choca con el
  `Response<Dto>`. Hay que dar el tipo: `llamar<Dto> { … }` (así lo hace `SesionVencidaTest`).

### 4.2 Login contra el backend (FE-1.2)

Qué se construyó (detalle y firmas en §5.3, §5.5, §5.6 y §5.10; validación en
[`validation-1-2`](./validation/validation-1-2.md)):

| Pieza | Archivo | Qué hace |
|---|---|---|
| `RemoteAuthRepository` | `data/remote/RemoteAuthRepository.kt` | `POST /v1/auth/login` → `Sesion(token, usuario, expiraEnMs)`; `LoginViewModel.Factory` la usa en lugar de `AuthRepositoryStub` |
| `Sesion.expiraEnMs` | `domain/model/Usuario.kt` | `expira_en` del login en milisegundos; `vencida(ahoraMs)` |
| `SessionManager(almacen, reloj)` + `AlmacenSesion` | `session/SessionManager.kt`, `session/AlmacenSesion.kt` | Guarda `expira_en_ms`; `obtener()` trata una sesión vencida como «sin sesión» y la borra, sin llamar al backend |
| `VigilanteSesion`, `MotivoSinSesion`, `EventosSesion` | `session/VigilanteSesion.kt` | Qué hacer cuando una ruta protegida se queda sin sesión: cerrar sesión y emitir `onSinSesion` |
| `SesionInterceptor`, `SinSesionException` | `data/remote/ClienteApi.kt` | En `/v1/admin/…` y `/v1/collect/…`: sin sesión no envía la petición; `401 TOKEN_EXPIRADO`/`TOKEN_INVALIDO`/`NO_AUTENTICADO` cierra la sesión |
| `MyApp` | `MyApp.kt` | Asigna `ClienteApi.vigilante` (con `onSinSesion = EventosSesion::emitir` y registro con el tag `Sesion`) |
| `AppNav` | `MainActivity.kt` | Recoge `EventosSesion.sinSesion`: en una ruta `admin/…` navega a `login` con la pila `inicio → login` (no cierra la app) |
| Pruebas | `SesionVencidaTest` (9), `RemoteAuthRepositoryTest` (6) | Criterios C3 y C4 de FE-1.2 |
| Validador | `src/ops/validate12.py` + ayudas nuevas de `comun.py` | Login en el teléfono con adb (C1 admin entra al Panel, C2 `user` ve «Sin permisos»), cuenta `user` de prueba con tareas sueltas de `migrate` (§5.11) |

Verificado en local el 2026-10-25: `testDebugUnitTest assembleDebug` → `BUILD SUCCESSFUL` (50 casos, 0 fallos);
`validate12.py --entorno local` → código 0. **Sin comprobar** todavía en `dev` con el teléfono (C1 y C2): lo corre el
maestro (`validation-1-2` §5).

---

## 5. Interfaces (contratos): catálogo de piezas reutilizables y contratos entre vistas

> **Única fuente de verdad** de lo que la app expone hacia dentro (piezas, puentes WebView, almacenamiento local,
> rutas) y de **cómo consume** la API del backend (§5.10). Cambiar algo aquí sube la versión de este documento y exige
> entrada en `CHANGELOG.md`.
>
> **Para qué sirve:** que quien construya una vista nueva (persona o IA) pueda reutilizar lo ya
> hecho **sin leer los archivos de las otras vistas**. Cada entrada dice *qué hace* la pieza,
> *cómo se usa* y *con qué cuidado*.
>
> **Reglas de mantenimiento**
> 1. Antes de crear algo (botón, tarjeta, lógica de voz, repositorio…), buscar aquí si ya existe.
> 2. Al crear o cambiar una pieza que otra vista pueda usar, actualizar su entrada **en el mismo cambio**.
> 3. Lo marcado con ⚠ **no está verificado contra el código**: confirmar antes de depender de ello.
> 4. Lo que vive en `ui/<vista>/componentes/` pertenece a esa vista aunque sea `public`. Si otra vista
>    lo necesita, se mueve a `ui/components/` y se actualiza la tabla 5.5.
> 5. Las fuentes de las entradas verificadas (qué archivo se leyó y cuándo) están en `CHANGELOG.md`; lo que falta
>    documentar o decidir, en `PLAN.md`.

### 5.1 Patrón de vista (se repite en Login, Inicio, Escaneo, Panel admin y Destino)

| Pieza | Convención |
|---|---|
| `XScreen` | Conecta: permisos, ViewModel, ciclo de vida y navegación. No dibuja detalles. |
| `XContent` | Sin lógica: recibe el `UiState` y las acciones, y dibuja. Lleva `@Preview`. |
| `XUiState` | Un `data class` en un único `StateFlow`. La UI solo lo lee; el ViewModel es el único que lo escribe. |
| `XEvento` | `sealed interface` para cosas de una sola vez (navegar, tomar foto). Va por `SharedFlow(extraBufferCapacity = n)` (Inicio, Escaneo, Destino) o `Channel.receiveAsFlow()` (Login; Panel admin con `Channel.BUFFERED`). La pantalla lo recoge en `LaunchedEffect(Unit)`. |
| Navegación | La pantalla **no** conoce `NavController`: recibe lambdas (`onVolver`, `onX`) y `AppNav` las conecta. |
| ViewModel | `AndroidViewModel(app)` si necesita contexto (voz, sonido); `ViewModel` con `Factory` si recibe repositorios (Login, Panel admin, Galería, Lista y Detalle de video). |
| Acciones | Si son muchas, se agrupan en una clase con lambdas (`GaleriaAcciones`, `DestinoAcciones`). |
| Colores | `CampusColors` (5.4). |
| Accesibilidad | `contentDescription` en todo; áreas de 48 dp o más (56–64 dp en las vistas públicas); avisos como *live region*. |

**Variantes verificadas (vistas admin y públicas)** (no son errores, pero conviene unificarlas al tocar cada vista):
- Nombre del `StateFlow` de estado: `state` (Panel, Login), `uiState` (Galería, Lista de videos), `ui` (Editor de mapa, Detalle de video) y `estado` (Inicio, Destino).
- `Factory`: la de `PanelAdminViewModel` recibe un `Context` y lo convierte a `applicationContext` por sí sola; las de `GaleriaViewModel` (`appContext`) y `VideoDetalleViewModel` (`appContext`, `videoId`) **esperan que ya se les pase el de la aplicación**: con el de una `Activity` se filtraría. Las pantallas actuales ya pasan `LocalContext.current.applicationContext`. `VideosViewModel.Factory(appContext)` también **espera el de la aplicación**; `LoginViewModel.Factory(context)` lo convierte por sí sola (como la de Panel). Inicio y Destino son `AndroidViewModel` y no llevan `Factory`.
- El Editor de mapa y el Detalle de video no usan `XEvento`: los eventos llegan de JavaScript a través de una interfaz (`EditorMapaEventos`, `VideoDetalleEventos`; 5.5) y el estado del editor se llama `EditorMapaUi`. Galería, Lista y Detalle de video no tienen flujo de eventos en el ViewModel: salir y navegar lo resuelven las lambdas de la pantalla.
- `@Preview`: lo tienen `PanelAdminContent` (3), `GaleriaContent` (2), `SeleccionDestinoContent` (1) y `LoginContent` (4: vacío, cargando, credenciales inválidas y sin conexión; faltan sin permisos, desconocido y contraseña visible). **No** lo tienen `VideosContent`, `EditorMapaContent`, `VideoDetalleContent` ni `InicioContent` (un `WebView` no se previsualiza, pero `VideosContent` sí podría). `PanelAdminContent` y `LoginContent` son `internal`; los demás `XContent` son públicos.
- Recolección del estado: `collectAsStateWithLifecycle()` en Panel, Editor, Detalle de video, Login, Inicio y Destino; `collectAsState()` en Galería y Lista de videos (sigue recogiendo con la pantalla en segundo plano).
- Acciones agrupadas: `PanelAcciones` (10 lambdas) y `GaleriaAcciones` (14), ambas `data class` con valores `{}` por defecto para los previews. `DestinoAcciones` (12 lambdas) es una `class` simple **sin** valores por defecto: su preview pasa doce `{}` a mano.
- Eventos de una sola vez (verificado en los ViewModels): Inicio y Destino usan `MutableSharedFlow(extraBufferCapacity = 1)` con `tryEmit` y **sin `replay`**: si nadie está recogiendo en ese instante, el evento **se pierde**. Login usa `Channel(BUFFERED)`, que sí espera al colector (pero admite **un solo** colector).
- `InicioContent` recibe parámetros sueltos (`escuchando`, `backendEnLinea`, `permisosFaltantes`…) en vez de `InicioUiState`, y no tiene `modifier`.

### 5.2 Voz, sonido y registro

| Pieza | Ubicación | Cómo se usa | Cuidado |
|---|---|---|---|
| `VoiceController` | `ui/inicio/VoiceController.kt` (paquete `ui.inicio`, aunque lo usan 3 vistas) | `VoiceController(context)` · `speak(texto: String, alTerminar: () -> Unit = {})` · `listen(onResult: (String) -> Unit, onFail: () -> Unit)` · `stopListening()` · `stopAll()` · `release()` en `onCleared`. Envuelve `TextToSpeech` y `SpeechRecognizer` en español de Colombia (`es-CO`). **Solo desde el hilo principal.** Un controlador por ViewModel. | Verificado contra el código. Comportamiento exacto:<br>• `speak` usa `QUEUE_FLUSH`: **corta** lo que se esté diciendo y el `alTerminar` anterior **no** se llama. Solo el último `speak` tiene callback.<br>• `alTerminar` se llama al terminar **o si hay un error** de TTS (no se distinguen).<br>• `stopAll()` no dispara `alTerminar` (no se sobreescribe `onStop`), pero un `alTerminar` que ya estaba encolado en el hilo principal sí llega: por eso el token (abajo) sigue siendo necesario.<br>• Si el TTS aún no está listo, `speak` queda pendiente y **solo se guarda el último**. Si el TTS falla al iniciar, `speak` nunca habla ni llama a `alTerminar`: un flujo que encadena `speak → listen` se queda parado. Poner siempre una salida por toque.<br>• Tras `release()` `speak` no hace nada (tampoco llama a `alTerminar`).<br>• `listen` cancela el reconocimiento anterior, **no** detiene el TTS (escuchar mientras habla capta la propia voz: llamar a `listen` desde el `alTerminar`) y **no** comprueba `RECORD_AUDIO` (sin permiso responde `onFail`).<br>• `onResult` recibe hasta **3 hipótesis unidas por espacio** (`"sí no sí"`); esto importa para `InterpretarRespuesta` (5.7).<br>• `onFail` cubre: reconocimiento no disponible (se llama **de forma síncrona**, antes de que `listen` retorne), error, silencio y sin resultados.<br>Candidato a mover a `voice/`. |
| `Comando` / `ComandoParser` | **Dentro de `ui/inicio/VoiceController.kt`** (no existe `ComandoParser.kt` aparte) | `ComandoParser.parse(texto): Comando` → `UBICARME`, `IR_A_LUGAR` o `NINGUNO`. | Quita tildes y pasa a minúsculas. `UBICARME` si hay la palabra "uno"/"1" o el texto contiene "ubic", "donde estoy", "donde estamos". `IR_A_LUGAR` si hay "dos"/"2" o contiene "ir a", "llevar", "lugar", "destino", "llegar". Si coinciden **ambos** o **ninguno** → `NINGUNO`. Cuidado: "ir a", "ubic" y "lugar" se buscan como *fragmento* del texto, así que también aciona con "salir a", "venir a" o "ubicación". No quita signos de puntuación (`"uno,"` no cuenta como la palabra "uno"). Solo sirve para el menú de Inicio; para nombres de lugares y sí/no, ver 5.7. |
| `FeedbackCaptura` | `ui/ubicacion/FeedbackCaptura.kt` | `FeedbackCaptura(ctx)` · `confirmar()` (vibra 120 ms + pitido de 120 ms) · `liberar()` | Verificado. Es `internal` (visible en todo el módulo), así que otra vista puede usarla. Liberar en `onCleared`. El pitido sale por el canal de **notificaciones** (volumen 80): con el teléfono en silencio solo vibra. Si el sistema no puede crear el generador de tonos, simplemente no suena (no falla). `liberar()` solo libera el tono; no usarla después de liberar. Necesita `VIBRATE` en el Manifest (§3.2). |
| `AppLog` | `logs/AppLog.kt` (`object`) | `AppLog.d(TAG, msg)` · `AppLog.i(TAG, msg)` · `AppLog.w(TAG, msg, t = null)` · `AppLog.e(TAG, msg, t = null)` · `AppLog.nuevaSesion(prefijo): String` · `AppLog.sesion` (lectura/escritura) · `AppLog.init(context)` (solo `MyApp`) | Verificado. **`d` e `i` no reciben excepción**: para registrar una usar `w` o `e`. Cada línea va a Logcat (`[sesion] texto`) y a `files/logs/app.log` con hora, nivel, tag, hilo y sesión. Rota a ~1 MB (pasa a `app.log.1`, que pisa al anterior: historial máximo ≈ 2 MB). **Antes de `AppLog.init` solo escribe en Logcat.** La escritura al archivo es **síncrona en el hilo que llama**: no registrar en bucles calientes (el sensor de orientación llega a ~50 Hz). `nuevaSesion` genera `prefijo-NNNNN` con 5 dígitos del reloj: sirve para seguir una vuelta, **no garantiza unicidad**. Los errores de escritura se tragan en silencio. ⚠ El `SimpleDateFormat` interno es compartido y no es seguro entre hilos: con registros simultáneos desde varios hilos la hora de una línea puede salir corrupta. **No hay función de exportar**: el archivo se consulta como dice la §3.2. Tags en uso: `App`, `CRASH`, `EscaneoVM`, `Camara`, `DestinoVM`, `Api` (FE-1.1: `RequestIdInterceptor`, §5.10, registra cada petición HTTP con `AppLog.i`, también el sondeo de Inicio cada 15 s) y `Sesion` (FE-1.2: `VigilanteSesion`, §5.3, con `AppLog.w`, p. ej. `GET /v1/admin/stats -> 401 TOKEN_EXPIRADO: sesión cerrada`). Verificado: `InicioViewModel`, `LoginViewModel` y `VideosViewModel` **no registran nada** por sí mismos. No registrar tokens ni lecturas de sensores. Se inicia en `MyApp.onCreate` (`AppLog.init(this)`, que además registra fabricante, modelo y versión de Android con el tag `App`). Las excepciones no capturadas se registran con el tag `CRASH` y luego se pasan al manejador anterior del sistema (la app se cierra igual). |

**Patrón de flujo hablado con token** (implementado y verificado en `SeleccionDestinoViewModel`: `hablar`, `escuchar`, `detenerVoz`; detalle en 5.5):
hablar → al terminar, escuchar → interpretar → hablar… Cada interrupción de la persona (toca algo,
pausa, sale) hace `token++` y `voz.stopAll()`; los callbacks de voz que llegan con un token viejo se
ignoran, así el flujo hablado no continúa después de que la persona tomó el control. El token hace
falta aunque `stopAll()` no llame a `alTerminar`: un `alTerminar` ya encolado en el hilo principal
llega igual (ver `VoiceController` arriba). Copiarlo en cualquier vista con diálogo por voz. Inicio y Escaneo no lo usan (Escaneo comprueba su `fase`).

**Ciclo de vida:** en `ON_STOP` la pantalla llama al ViewModel (`alPausar()`), que hace `voz.stopAll()` y baja `escuchando` (Inicio y Destino, verificado). Destino además sube el `token`; Inicio **no tiene token**, así que un `alTerminar` ya encolado todavía puede llamar a `escuchar()` justo después de pausar (⚠ deducido del comportamiento de `VoiceController`, no reproducido).

#### Seguimiento de posición (PDR) (`sensors/PdrEngine.kt`, `sensors/StepDetector.kt`, `sensors/PdrTracker.kt`)

> ⚠ Código entregado el 2026-10-10. Compila con el resto del proyecto (tanda 12, ver `CHANGELOG.md`), pero **no se ha
> probado en dispositivo** (FE-2.3). Confirmar y quitar este aviso.

Es el **único** sitio que calcula la posición a partir de pasos y rumbo (2.3). El mapa público lo usa
a través de `map/MapaPublicoScreen.kt`; la recolección (7.4, ya lo usa desde `RecoleccionViewModel`) y la navegación (6.5) deben usar el mismo
`PdrTracker` en vez de volver a calcular nada en JavaScript.

| Pieza | Firma | Qué hace / cuidado |
|---|---|---|
| `PdrEngine` | `PdrEngine(longitudPasoM = LONGITUD_PASO_DEFECTO_M, ventanaRumbo = 6, ventanaVelocidadMs = 5000)` · `companion { const val LONGITUD_PASO_DEFECTO_M = 0.72 }` | Lógica pura, sin Android (se puede probar con tests unitarios). Propiedades de lectura: `lat`, `lng` (`Double?`), `rumbo`, `pasos`, `distanciaMetros`, `velocidadMps`. |
| `PdrEngine.fijarPosicion` | `(lat, lng)` | Fija el punto de partida y la posición actual. **No** reinicia `pasos`. |
| `PdrEngine.reiniciar` | `()` | Pasos y velocidad a 0 y vuelve al punto de partida. |
| `PdrEngine.onRumboSensor` | `(grados: Float)` | Promedio circular de las últimas 6 lecturas (359° y 1° dan 0°, no 180°). |
| `PdrEngine.fijarRumboManual` | `(grados: Float)` | Rumbo directo, sin promedio (rueda manual). |
| `PdrEngine.onPaso` | `(tMs: Long): Boolean` | Avanza `longitudPasoM` hacia `rumbo`; devuelve `false` si aún no hay posición inicial. Velocidad: pasos de los últimos 5 s (n − 1 intervalos). |
| `StepDetector` | `procesar(x, y, z, tMs, detectar = true): Boolean` · `ultimaDesviacion` · `reiniciar()` | **Fuente única de pasos.** Magnitud − gravedad **con signo**, filtro pasa-bajos (`FILTRO` 0,5) y cuenta el paso en el **flanco de subida** del pico (latencia ~50–100 ms), con histéresis (rearma por debajo del 60 % del umbral) y pausa mínima `PAUSA_MS` = 250 ms. **Umbral adaptativo:** `FACTOR_UMBRAL` (0,5) × el pico típico reciente (media móvil, `PESO_PICO` 0,3, picos recortados a `PICO_MAX` 8), limitado a `UMBRAL_MIN` 1,1 … `UMBRAL_MAX` 4,0 m/s²; arranca en `UMBRAL` = 1,4. Solo cuentan picos positivos. `umbral` (lectura) da el valor vigente; `ultimaDesviacion` es `|filtrada|` para la gráfica; `detectar = false` solo la actualiza. Probado con una réplica en Python (no con el Kotlin): ~100 % de pasos en caminata normal, ~85–95 % en caminata muy suave, 0 pasos falsos quieto o con temblor de mano. `StepDetectorTest` (JUnit4, **no ejecutado en Gradle**) |
| `PdrTracker` | `PdrTracker(context, longitudPasoM: Double = CalibracionPasoRepository(context).longitudPasoM())` | Une los sensores de Android con `PdrEngine`. Todo en el **hilo principal**. La longitud de paso (calibrada en 7.3b, o 0,72 m) se lee **una sola vez al crearlo**: recalibrar no cambia un tracker ya vivo. ⚠ `sensors` depende ahora de `data.repository` (alternativa: que la pantalla inyecte la longitud). |
| `PdrTracker` (control) | `fijarPosicion(lat, lng)` · `fijarRumboManual(grados)` · `reiniciar()` · `iniciar()` · `detener()` · `liberar()` | Orden típico: `fijarPosicion` → `iniciar` → `detener` / `liberar` al salir. |
| `PdrTracker.estado` | `StateFlow<PdrEstado>` | `lat`, `lng`, `rumboGrados`, `pasos`, `distanciaMetros`, `velocidadMps`, `activo`, `fuentePasos` (`FuentePasos`: `NINGUNA`, `ACELEROMETRO` y `ACELEROMETRO_SIN_SENSOR` si no hay acelerómetro; `HARDWARE` y `ACELEROMETRO_SIN_PERMISO` ya no se asignan y quedan solo por compatibilidad). ⚠ Se añadió `ACELEROMETRO`: un `when` exhaustivo sobre `FuentePasos` en otros archivos dejaría de compilar. |
| `PdrTracker.eventos` | `SharedFlow<PdrEvento>` | Avisos de una sola vez, en cada `iniciar()`: `Brujula(disponible)` y `PasosPorAcelerometro("no_sensor")` (solo si no hay acelerómetro; ya no se emite `permission_denied`). |
| `PdrTracker.onAceleracion` | `((Float) -> Unit)?` | Desviación de la aceleración (m/s²), ~20 Hz, solo para gráficas. |

Receta (Compose):

```kotlin
val tracker = remember { PdrTracker(ctx) }
DisposableEffect(Unit) { onDispose { tracker.liberar() } }
tracker.fijarPosicion(lat, lng)   // antes de iniciar
tracker.iniciar()
val e by tracker.estado.collectAsStateWithLifecycle()   // e.lat, e.lng, e.rumboGrados, e.pasos…
```

Cuidados:
- **La posición no depende de la velocidad ni de la aceleración:** es `pasos × longitud de paso` (la calibrada en 7.3b, o 0,72 m
  por defecto) en dirección del rumbo. La velocidad solo es informativa y el acelerómetro detecta los pasos y alimenta la gráfica.
- **Pasos:** siempre `StepDetector` sobre el acelerómetro (`SENSOR_DELAY_GAME`, ~50 Hz), sin permiso. `TYPE_STEP_DETECTOR`
  se descartó (2026-10-12): confirma una secuencia antes de avisar y tardaba 1–3 s. El acelerómetro corre mientras el
  rastreo está activo y alimenta a la vez los pasos y la gráfica.
- **Rumbo:** `TYPE_ROTATION_VECTOR` + declinación magnética (`GeomagneticField`) calculada con la
  posición en `fijarPosicion` / `iniciar` (sin posición, la declinación es 0). Elige el eje según la
  postura: celular plano (|`R[8]`| > 0,7) usa la parte superior del celular; en vertical, la cámara
  trasera. Cerca de ~45° de inclinación puede haber un salto. ⚠ **Es una segunda fuente de rumbo**,
  distinta de `EscucharOrientacion` (acimut −180…180, magnético, solo vertical): no mezclarlas.
- `iniciar()` evalúa brújula y pasos **cada vez**; `detener()` no borra la posición. `reiniciar()` sí
  vuelve al punto de partida.
- `eventos` es un `SharedFlow` sin repetición: si nadie recoge en ese instante, el aviso se pierde
  (`MapaPublicoScreen` lo recoge antes de que el usuario pueda pulsar ▶).
- `rumboGrados` vale 0 hasta la primera lectura: filtrar por `activo` antes de mostrarlo.
- Los sensores no siguen el ciclo de vida: solo se liberan en `liberar()` (⚠ siguen activos en
  segundo plano). `RecoleccionViewModel` lo resuelve para 7.4: la pausa llama a `tracker.detener()` y la pantalla pausa sola en `ON_STOP` (ver «Flujo de captura de la recolección»).
- **Longitud de paso (7.3b):** `RecoleccionViewModel` y `MapaPublicoScreen` crean `PdrTracker(app)` sin argumentos y recogen la longitud calibrada
  sin cambios. `distanciaMetros` es `pasos × longitud`, así que el disparador por distancia de 7.4 dispara cada ≈ `metros / longitud` pasos.
  La calibración usa **su propio** `PdrTracker` (`CalibracionViewModel`): si otra pantalla dejara uno sin liberar, habría dos escuchando sensores.
- ⚠ `app.js` repite un umbral fijo de 2,2 (`accelThreshold`) solo para dibujar la línea de la gráfica; el detector ahora usa
  un umbral **adaptativo** que arranca en `StepDetector.UMBRAL` (1,4), así que la línea ya no coincide. Cambiar el valor de `app.js`
  a 1,4 (o enviar el umbral vigente desde Kotlin).

#### Sensores y cámara (`sensors/OrientationProvider.kt`, `camera/CapturaFoto.kt`)

| Pieza | Firma | Qué hace / cuidado |
|---|---|---|
| `tieneSensorRotacion` | `(ctx: Context): Boolean` | ¿El teléfono tiene `TYPE_ROTATION_VECTOR`? Llamarla **antes** de depender de la orientación. |
| `EscucharOrientacion` | `@Composable (activo: Boolean, onOrientacion: (acimutGrados: Float, cabeceoGrados: Float) -> Unit)` | Registra el sensor mientras `activo` sea `true` y lo libera al pasar a `false` o al salir de la composición. Entrega **acimut** (hacia dónde apunta la cámara trasera; 0° = norte **magnético**) y **cabeceo** (≈0° con el celular derecho). Callback en el hilo principal, ~50 Hz (`SENSOR_DELAY_GAME`). |
| `crearImageCapture` | `(): ImageCapture` | `ImageCapture` en modo `MINIMIZE_LATENCY`. Se enlaza al ciclo de vida junto con la vista previa mediante `VistaCamara` (ver 5.5); sin ese enlace `tomarFoto` falla. |
| `crearCarpetaEscaneo` | `(ctx, mantener: Int = 20): File` | Crea `files/camera/photos/<yyyy-MM-dd_HH-mm-ss>/` y **borra las carpetas más antiguas** de `camera/photos/`, dejando solo las últimas `mantener` (contando la nueva). |
| `ImageCapture.tomarFoto` | `(ctx, carpeta: File, prefijo = "foto", onGuardada: (File) -> Unit, onFallo: () -> Unit)` | Guarda `<prefijo>_<n>.jpg` (n = primer número libre desde 1). Los callbacks llegan en el hilo principal. Si falla, borra el archivo reservado y llama a `onFallo` (también si `takePicture` lanza excepción, p. ej. cámara aún no enlazada; en ese caso `onFallo` se llama **de forma síncrona**). |
| `liberarCamara` | `(ctx)` | `ProcessCameraProvider.unbindAll()`; si falla solo deja un `AppLog.w`. |

Cuidados:
- **El acimut sale en −180…180, no en 0…360** (viene de `getOrientation`, aunque el comentario del archivo diga que "crece hacia la derecha"). Normalizar con `(x + 360) % 360` antes de compararlo con rumbos o con `Foto.rumbo`. Es norte **magnético**, no geográfico.
- `EscucharOrientacion` **no avisa si no hay sensor**: simplemente no llama nunca al callback. Verificar con `tieneSensorRotacion`. Ignora la precisión del sensor (no hay aviso de "calibrar").
- Los ejes están remapeados para el celular **en vertical**; en horizontal el acimut y el cabeceo no sirven.
- Solo se puede usar dentro de una composición (no desde un ViewModel). No sigue el ciclo de vida de la Activity: pasar `activo = false` en `ON_STOP`, o el sensor sigue escuchando en segundo plano (`EscaneoScreen` hoy no lo hace). Para el seguimiento híbrido (2.3), que corre fuera de una pantalla, haría falta una versión con `Flow`.
- **`crearCarpetaEscaneo` es destructiva.** Si la recolección (7.4) reutiliza `camera/photos/`, sus carpetas se borrarán tras 20 escaneos. Usar otra raíz o un `mantener` distinto. La recolección guarda en `files/recoleccion/` (5.6) y no la toca.
- **Las fotos no llevan metadatos.** `tomarFoto` solo escribe el JPG: la posición (`lat`, `lng`) y el `rumbo` hay que guardarlos aparte (el `manifest.json` los exige, ver 5.6). Los archivos quedan en `filesDir` (privados de la app, no visibles en la galería del teléfono) y se llaman `foto_1.jpg`, no `0001.jpg`: la recolección debe asignar el `id` de `Foto` por su cuenta.
- `onFallo` no trae el motivo; el código de error de CameraX solo queda en el log (`Camara`).
- `liberarCamara` desenlaza **todos** los casos de uso del proceso y espera el `Future` en el hilo que la llama: llamarla al salir de la vista de cámara, no mientras otra vista aún la usa.

#### Flujo de captura del escaneo (`ui/ubicacion/EscaneoViewModel.kt`)

Es lo que la recolección (7.4) querrá imitar: gira → foto cada cierto ángulo → feedback. Verificado:

| Pieza | Detalle |
|---|---|
| Creación | `EscaneoViewModel(app: Application) : AndroidViewModel`. Crea él mismo `EscaneoBackendStub`, `VoiceController(app)` y `FeedbackCaptura(app)`. |
| Salidas | `estado: StateFlow<EscaneoUiState>` y `eventos: SharedFlow<EscaneoEvento>` (buffer 4). Eventos vistos: `Capturar` (la pantalla debe llamar a `tomarFoto`) y `Completado`. |
| Entradas (las llama la pantalla) | `iniciar()` · `cancelar()` · `sensorNoDisponible()` · `onOrientacion(acimut, cabeceo)` (~50 Hz) · `onFotoTomada(File)` · `onFotoFallida()` |
| Fases | `PREPARANDO` (instrucciones habladas) → `ESCANEANDO` → `ANALIZANDO` → evento `Completado`; o `ERROR`. Errores: `SIN_SENSOR`, `VUELTA_INCOMPLETA`, `TIEMPO_AGOTADO`, `SIN_CONEXION` (cada uno con `.mensaje`, que se dice por voz). Instrucciones en vivo: `VERTICAL` > `MAS_DESPACIO` > `GIRAR`. |
| ¿Cuándo pide foto? | Si **todo** se cumple: no hay captura en curso, no está en pausa, el cabeceo está dentro de `INCLINACION_MAX`, la velocidad suavizada no supera `VELOCIDAD_MAX`, faltan fotos y el progreso llegó a `fotos × GRADOS_POR_FOTO` (72°). |
| Seguimiento del giro | Diferencia de acimut entre lecturas, normalizada a (−180°, 180°] para cruzar 359°→0°. Velocidad con media móvil exponencial (0,85 / 0,15). El progreso se limita a 0…360°. |
| Voz | `iniciar()` habla las instrucciones y, al terminar, pasa a `ESCANEANDO` **si la fase sigue siendo `PREPARANDO`** (no usa token). Los avisos de inclinación y velocidad se limitan con `AVISO_CADA_MS`; `fallar()` y `analizar()` hablan sin ese límite. Recordar que `speak` corta lo anterior (5.2). |
| Fallos | `onFotoFallida()` pausa 1 s y deja que se reintente solo (sin límite de intentos). Sin avance durante `INACTIVIDAD_MS` → `VUELTA_INCOMPLETA`. Backend: `withTimeout(TIMEOUT_BACKEND_MS)`; el tiempo agotado va **antes** que `CancellationException` en el `catch` porque es subclase suya. |

Cuidados:
- ⚠ **Girar a la izquierda resta progreso.** El comentario del código dice que solo cuenta el giro a la derecha, pero el progreso suma `delta` **con signo** (baja hasta 0). Lo que sí exige ir a la derecha es el reinicio del contador de inactividad (`delta > 0,2°`).
- La normalización de `delta` ya asume que el acimut llega en −180…180 (confirma la nota de `EscucharOrientacion`).
- **`CONSERVAR_FOTOS = true`** (constante privada del archivo): las fotos **no se borran** al cancelar, reiniciar ni destruir el ViewModel. Debe pasar a `false` antes de publicar (decisión abierta 12, FE-3.2). Aun así, una foto que llega fuera de la fase `ESCANEANDO` **no se cuenta y nunca se borra**, ni siquiera con `false`.
- Las excepciones inesperadas del backend se informan como `SIN_CONEXION` (puede disfrazar otros errores).
- `EscaneoEvento.Completado` **no lleva datos** y `backend.analizar` devuelve `Unit`: antes de 6.3 hay que decidir qué entrega (posición estimada) y por dónde viaja (5.8).
- La detección de inactividad solo se evalúa dentro de `onOrientacion`: si el sensor deja de emitir, no hay tiempo límite.
- ⚠ Carrera teórica confirmada: `cancelar()` deja `EscaneoUiState()` con `fase = PREPARANDO`; si un `alTerminar` de `iniciar()` ya estaba encolado, pasaría a `ESCANEANDO` tras cancelar. En la práctica es inofensiva porque `EscaneoScreen` llama a `onCancelar()` justo después y el ViewModel se destruye, pero un flujo nuevo que cancele **sin salir** de la pantalla debe protegerse (por ejemplo con el token de 5.2).
- **Una foto de `Capturar` perdida deja el escaneo atascado.** `eventos` es un `SharedFlow` sin repetición: un evento emitido mientras no hay colector (p. ej. durante una rotación) se pierde. Si es `Capturar`, `capturando` queda en `true` y no se pide otra foto hasta que salte `VUELTA_INCOMPLETA` (20 s). Si es `Completado`, la pantalla se queda en "Analizando…".
- **El acimut de cada foto no se guarda.** El ViewModel lo escribe en el log al pedir la foto pero no lo asocia al archivo, y el contrato `EscaneoBackend.analizar(fotos: List<File>)` solo recibe archivos: el TODO del backend (enviar el *heading* de cada foto, §2.1) obliga a cambiar ambos.
- Todo el cálculo del giro (`onOrientacion`) es **privado** del ViewModel: la recolección no puede reutilizarlo. Candidato a extraer como caso de uso puro (5.7) que reciba `(acimut, cabeceo, instante)` y devuelva progreso, velocidad y qué instrucción dar.

**Parámetros (`EscaneoConfig`, `ui/ubicacion/EscaneoConfig.kt`, `internal object`; verificados):**

| Constante | Valor | Significado |
|---|---|---|
| `TOTAL_FOTOS` | 5 | Fotos por vuelta, a 0°, 72°, 144°, 216° y 288° **medidos desde donde empezó el giro** |
| `GRADOS_POR_FOTO` | 72° | `360 / TOTAL_FOTOS` |
| `VELOCIDAD_MAX` | 45 °/s | Por encima se pide "Más despacio" y no se toman fotos |
| `INCLINACION_MAX` | 20° | Desvío máximo del cabeceo respecto a la vertical |
| `INACTIVIDAD_MS` | 20 000 | Sin avanzar este tiempo → `VUELTA_INCOMPLETA` |
| `AVISO_CADA_MS` | 4 000 | Mínimo entre avisos hablados de inclinación/velocidad |
| `TIMEOUT_BACKEND_MS` | 30 000 | Espera máxima al backend → `TIEMPO_AGOTADO` |

**Estado y eventos (`ui/ubicacion/EscaneoState.kt`; verificado):**
- `Fase`: solo `PREPARANDO`, `ESCANEANDO`, `ANALIZANDO` y `ERROR` (no hay una fase "completado": el final es el evento).
- `EscaneoUiState(fase = PREPARANDO, progreso = 0f, fotos = 0, inclinacionOk = true, instruccion = GIRAR, error = null)`; `progreso` en grados girados 0…360.
- Textos: `Instruccion.GIRAR` "Gira lentamente\nhacia la derecha" (lleva salto de línea), `MAS_DESPACIO` "Más despacio", `VERTICAL` "Mantén el celular vertical". `ErrorEscaneo`: `SIN_CONEXION` "Sin conexión con el servidor", `TIEMPO_AGOTADO` "El análisis tardó demasiado", `VUELTA_INCOMPLETA` "No completaste la vuelta", `SIN_SENSOR` "Este teléfono no tiene sensor de giro".
- `EscaneoEvento` (`sealed interface`): `Capturar` (la pantalla es dueña de CameraX) y `Completado` ("hay que navegar al Resultado").

**Contrato del backend (`ui/ubicacion/EscaneoBackend.kt`; verificado):** `interface EscaneoBackend { @Throws(IOException::class) suspend fun analizar(fotos: List<File>) }` (devuelve `Unit`). `EscaneoBackendStub` espera 2,5 s y no hace nada. ⚠ No sigue la convención de 5.6 (`interface XRepository` en `data/repository/`) y el ViewModel lo instancia directamente (`private val backend = EscaneoBackendStub`), así que cambiarlo exige editar el ViewModel.

**Cómo lo conecta `EscaneoScreen` (verificado):**
- Firma: `EscaneoScreen(onCancelar, onCompletado, onAjustes = {}, viewModel = viewModel())`. ⚠ **`AppNav` no pasa `onAjustes`**: el botón de ajustes de esta vista no hace nada hoy.
- **Comprueba el permiso de cámara por su cuenta** (`checkSelfPermission`; si falta, lo pide con `RequestPermission`), aunque la ruta ya usa `PedirPermisos`. Si se niega, muestra "Necesito permiso de cámara" y no hay forma de reintentar sin salir.
- Con cámara concedida: si hay sensor llama a `nuevoEscaneo()` (abre una carpeta nueva con `crearCarpetaEscaneo(ctx)` y llama a `viewModel.iniciar()`); si no, `viewModel.sensorNoDisponible()`. **"Repetir" abre otra carpeta**, así que cada intento cuenta para el límite de 20 de `crearCarpetaEscaneo`.
- `EscucharOrientacion(activo = camaraOk && tieneSensor, onOrientacion = viewModel::onOrientacion)`: el sensor escucha **todo el tiempo que la pantalla esté en composición**, también en `PREPARANDO`, `ANALIZANDO` y `ERROR` (el ViewModel descarta las lecturas fuera de `ESCANEANDO`). ⚠ **Escaneo no maneja `ON_STOP`**: si la app pasa a segundo plano a mitad de vuelta, el sensor y la voz siguen.
- Eventos en un `LaunchedEffect(Unit)`: `Capturar` → `imageCapture.tomarFoto(ctx, carpeta, prefijo = "escaneo", onGuardada = viewModel::onFotoTomada, onFallo = viewModel::onFotoFallida)` (los archivos se llaman `escaneo_1.jpg`…); `Completado` → `onCompletado()`.
- `DisposableEffect`: mantiene la pantalla encendida (`keepScreenOn`) y, al salir, **llama a `liberarCamara(ctx)`**: ese es el sitio donde se libera la cámara (5.5, `VistaCamara`).
- Cancelar (botón, flecha o atrás del sistema) = `viewModel.cancelar()` + `onCancelar()`.
- Título principal según prioridad: sin cámara → "Necesito permiso de cámara"; `ANALIZANDO` → "Analizando…"; `ERROR` → el mensaje del error; si no, el texto de la instrucción.
- Patrón 5.1: `EscaneoContent` es `private` y **no tiene `@Preview`**; para previsualizarlo habría que volverlo `internal`.

#### Flujo de captura de la recolección (`ui/admin/recoleccion/RecoleccionViewModel.kt`, `domain/usecase/DisparadorCaptura.kt`)

Imita el flujo del escaneo (arriba), pero la foto se dispara por **distancia o tiempo** y no por ángulo. El ViewModel es dueño del
PDR (sobrevive a rotar la pantalla); la **pantalla es dueña de CameraX** (5.5).

| Pieza | Detalle |
|---|---|
| `DisparadorCaptura` | Lógica pura, sin Android. `debeCapturar(distanciaTotalM, ahoraMs): Boolean` · `alCapturar(distanciaTotalM, ahoraMs)` (solo si la foto **se guardó**) · `cambiarModo(ModoCaptura)` · `alReanudar(ahoraMs)` · `reiniciar()` · `modo` (lectura) |
| `ModoCaptura` | `PorDistancia(metros)` y `PorTiempo(segundos)`; `OPCIONES` (3, 5 y 10 m; 3 y 5 s), `POR_DEFECTO` (cada 5 m) y `etiqueta` |
| `Deriva.estimar(distanciaDesdeAnclaM)` | Devuelve `EstimacionDeriva(derivaM, precisionM, nivel)`. **Heurística provisional:** deriva = 4 % de la distancia desde el último ancla (decisión 16). `NivelCalidad`: `ALTA` (< 15 m), `MEDIA` (< 30 m), `BAJA` |
| `RecoleccionViewModel(app)` | `AndroidViewModel` **sin `Factory`**: crea `RecoleccionRepositoryLocal`, `PdrTracker`, `FeedbackCaptura` y `DisparadorCaptura`. Salidas: `ui: StateFlow<RecoleccionUiState>`, `eventos: Flow<RecoleccionEvento>` (`Channel(BUFFERED)`, un solo colector: `Capturar`, `Finalizado(resumen)`, `Descartado`) y `carpetaFotos(): File?` (`null` antes de crear el video) |

Entradas del ViewModel (las llama la pantalla): `alAbrir()` (idempotente: consume `SesionDeRecoleccion.inicio`, crea el video, arranca el PDR; sin inicio, `error = SIN_INICIO`) · `onFotoTomada(File)` / `onFotoFallida()` · `alAlternarPausa()` · `alIrASegundoPlano()` · `alCambiarModo(ModoCaptura)` · `alReubicarse()`, `alMoverReanclaje(lat, lng)`, `alConfirmarReanclaje()`, `alCancelarReanclaje()` · `alAgregarAlerta()`, `alActualizarAlerta(a)`, `alGuardarAlerta()`, `alCancelarAlerta()` · `alPedirFinalizar()`, `alConfirmarFinalizar()`, `alCancelarFinalizar()` · `descartarAviso()`.

`RecoleccionUiState` (`RecoleccionState.kt`): `fase` (`INICIANDO`, `GRABANDO`, `PAUSADA`, `FINALIZANDO`), `error`, `nombreVideo`, `lat` / `lng` (`Double?`), `rumbo` (0…360), `fotosTomadas`, `distanciaMetros`, `pasos`, `duracionSegundos`, `deriva`, `modo`, `destelloCaptura` (contador: la UI parpadea cuando sube), `avisos` (`AvisoRecoleccion`: foto borrosa, poca luz, batería baja, almacenamiento bajo), `aviso` (texto temporal), `fotosJson`, `trayectoriaJson`, `alertasJson`, `alertasActivas`, `reanclaje`, `confirmandoFinalizar`, `formularioAlerta`, `errorAlerta`; calculadas `reubicando`, `enCurso` y `llegoAlMaximo`. Constante pública `MAX_FOTOS_VIDEO = 200`.

Comportamiento:
- **Primera foto inmediata**; luego `debeCapturar`. Solo captura en `GRABANDO`, sin otra captura en curso, sin re-anclaje abierto y con menos de 200 fotos.
- **Foto fallida:** no se llama a `alCapturar`, así que `debeCapturar` seguiría en `true`; el ViewModel pone una **pausa de capturas** (1 s; 5 s tras 5 fallos seguidos), como `EscaneoViewModel.onFotoFallida`.
- **Archivo:** `tomarFoto(ctx, carpetaFotos(), "tmp", …)`; `onFotoTomada` llama a `repo.registrarFoto`, que **renombra** el JPG a `NNNN.jpg` y lo anota en el manifest con la posición y el rumbo del PDR (las fotos no llevan metadatos, ver arriba).
- **Pausa** detiene el PDR (`tracker.detener()`); `alIrASegundoPlano()` (la pantalla lo llama en `ON_STOP`) pausa sola.
- **Re-anclaje manual:** `tracker.fijarPosicion` + desplazamiento **uniforme** de fotos (`repo.desplazarFotos`) y trayectoria desde el último ancla; reinicia la deriva y frena las capturas mientras `reanclaje != null`.
- **Reloj:** tiempo de grabación sin contar pausas (`elapsedRealtime`). Cada 30 s revisa la batería (aviso con ≤ 15 % y sin cargar) y el almacenamiento (aviso con < 200 MB; pausa sola con < 50 MB).
- **Finalizar:** con 0 fotos el video se **borra** (`repo.descartar`) y se emite `Descartado`; si no, `repo.finalizar` y `Finalizado(resumen)`.
- **Trayectoria:** un punto cada 3 pasos (`trayectoriaJson`).
- **Distancia:** `pasos × longitud de paso` del `PdrTracker` (calibrada en 7.3b, leída una vez al crearlo en `alAbrir`; 0,72 m si nunca se calibró).

Cuidados:
- Una foto que se está guardando en el instante del re-anclaje puede quedar con la coordenada vieja.
- La brújula del PDR depende de la declinación magnética calculada al fijar la posición.
- `validarMensajeAlerta` **duplica** la regla de `EditorMapaViewModel` (5.5 pide extraerla).
- Foto borrosa y poca luz nunca se activan (control de calidad desactivado).
- Sin retomar tras matar el proceso (`buscarEnCurso()` existe, pero no se usa).

### 5.3 Permisos y sesión

**Sesión (`SessionManager`, `session/SessionManager.kt`; desde FE-1.2 con `expira_en`)**

| Pieza | Firma | Qué hace / cuidado |
|---|---|---|
| Constructor principal | `SessionManager(almacen: AlmacenSesion, reloj: () -> Long = { System.currentTimeMillis() })` | Lógica pura: guarda en el `AlmacenSesion` que se le pase; `reloj` da la hora en milisegundos Unix (las pruebas lo fijan). |
| Constructor de la app | `SessionManager(context: Context)` | `= SessionManager(AlmacenSesionCifrado(context))`. Es el que usan las `Factory` (Login, Panel) y `MyApp`. El almacén cifrado se crea **de forma perezosa** en el primer uso: ese primer acceso puede tardar y puede lanzar excepción si el Keystore falla (p. ej. tras restaurar una copia de seguridad). Usa `applicationContext`, así que no filtra la `Activity`. |
| `guardar(sesion: Sesion)` | `Unit` | Escribe token, id, nombre, correo, rol y `expira_en` (`apply`, asíncrono). |
| `obtener()` | `Sesion?` | `null` si no hay token, si el rol guardado no es válido, si falta `expira_en` **o si `expira_en` ya pasó** (`Sesion.vencida(reloj())`: `ahora >= expiraEnMs`, sin margen, como el backend); en este último caso **además borra** la sesión. Nunca llama al backend. Si faltan id, nombre o correo, los devuelve como `""`. |
| `esAdmin()` | `Boolean` | `obtener()?.usuario?.rol == Rol.ADMIN` (una sesión vencida da `false`). Lee y descifra toda la sesión en cada llamada: guardar el resultado en el ViewModel en vez de llamarlo en cada recomposición. |
| `cerrarSesion()` | `Unit` | `AlmacenSesion.borrar()`: en la app, `clear()` de todo el archivo (token, datos del usuario y `expira_en`). |

**`AlmacenSesion` (`session/AlmacenSesion.kt`, FE-1.2)** — `interface` con `leer(): Sesion?` (la sesión tal cual, sin mirar
la caducidad; `null` si no hay token, el rol no es un `Rol` o falta `expira_en`), `escribir(sesion)` y `borrar()`.
`AlmacenSesionCifrado(context)` es la de la app: `EncryptedSharedPreferences`, archivo `campus_session`, llaves
AES256-SIV, valores AES256-GCM, llave maestra AES256-GCM en Android Keystore. Claves: `token`, `id`, `nombre`,
`correo`, `rol` (nombre del enum: `ADMIN`/`USER`) y `expira_en_ms` (`Long`, milisegundos Unix). Una sesión guardada
sin `expira_en_ms` (anterior a FE-1.2) no es válida. Existe para probar la sesión en la JVM: `SesionVencidaTest` usa un
almacén en memoria propio (no hay uno en `main`).

**Sin sesión en una ruta protegida (`session/VigilanteSesion.kt`, FE-1.2)**

| Pieza | Firma | Qué hace / cuidado |
|---|---|---|
| `MotivoSinSesion` | `sealed interface`: `SinSesionLocal` (`data object`) · `Rechazada(codigo: String)` | `SinSesionLocal`: no había sesión o su `expira_en` ya pasó, la petición no salió del teléfono. `Rechazada`: el backend respondió `401` con `TOKEN_EXPIRADO`, `TOKEN_INVALIDO` o `NO_AUTENTICADO` (backend §5.2). |
| `VigilanteSesion` | `VigilanteSesion(session: SessionManager, onSinSesion: (MotivoSinSesion) -> Unit, registrar: (String) -> Unit = {})` | Lógica pura (sin Android). La usa `SesionInterceptor` (§5.10) desde los hilos de OkHttp: `onSinSesion` no debe tocar la interfaz (la app pasa `EventosSesion::emitir`). **Nunca lanza**: si el almacén cifrado falla al leer, cuenta como «sin sesión» y lo registra. `registrar` recibe líneas sin token ni correo (la app: `AppLog.w("Sesion", …)`). |
| `token()` | `String?` | Token de la sesión vigente (`null` sin sesión, vencida o con el almacén roto). |
| `sesionParaPeticion(peticion: String)` | `Sesion?` | `peticion` = `"GET /v1/admin/stats"`. Devuelve la sesión vigente; si no hay (o venció: `obtener()` ya la borró), registra «`<peticion>` no se envía: sin sesión o vencida» y llama a `onSinSesion(SinSesionLocal)`. |
| `rechazada(codigo, tokenEnviado, peticion)` | `Unit` | Tras un `401` de sesión: si la sesión guardada sigue siendo la del `tokenEnviado` (o ya no hay), `session.cerrarSesion()`, registra «`<peticion>` -> 401 `<codigo>`: sesión cerrada» y `onSinSesion(Rechazada(codigo))`. Si mientras tanto se guardó **otra** sesión (otro token: el admin volvió a entrar), no hace nada (el rechazo era de la anterior). |
| `EventosSesion` | `object`: `sinSesion: Flow<MotivoSinSesion>` · `emitir(motivo)` | Eventos «sin sesión» de toda la app sobre un `Channel(Channel.CONFLATED)` + `receiveAsFlow()`: **un solo colector** (`AppNav`); sin colector se guarda el último y llega cuando alguien recoja. |

Flujo completo (cómo se cumple «401 → cerrar sesión e ir a Login» y «sesión vencida = sin sesión»):
1. `MyApp.onCreate` borra la sesión (arranque en frío, abajo) y asigna
   `ClienteApi.vigilante = VigilanteSesion(SessionManager(this), EventosSesion::emitir, { AppLog.w("Sesion", it) })`.
2. Toda petición de `ClienteApi.api` a `/v1/admin/…` o `/v1/collect/…` pasa por `SesionInterceptor` (§5.10): sin sesión
   o vencida → no se envía y `llamar` lanza `ApiException(FalloApi.SesionVencida("SIN_SESION_LOCAL"), 401, null)`;
   `401 TOKEN_*`/`NO_AUTENTICADO` → sesión cerrada y `ApiException(FalloApi.SesionVencida(<codigo>), 401, <rid>)`. En
   los dos casos se emite `onSinSesion`.
3. `AppNav` recoge `EventosSesion.sinSesion` y, **solo si la ruta actual empieza por `admin/`**, navega a `login` con
   `popUpTo("inicio")` y `launchSingleTop` (pila `inicio → login`; «Volver al inicio» vuelve a Inicio). En el flujo
   público no navega: una persona ciega nunca acaba en Login por una petición de fondo.
4. El ViewModel que hizo la petición recibe la `ApiException` y no tiene que navegar; basta con no mostrar un error
   propio para `FalloApi.SesionVencida` (`MapeoErroresApi.deExcepcion` la reconoce, también la `SinSesionException`).
5. Las pantallas que miran la sesión sin red (Login con `esAdmin()`, Panel con `obtener()`) ya ven una sesión vencida
   como «sin sesión»: el Panel emite su `SinSesion` y va a Login (5.5).

- Quién lo usa (el Panel admin está verificado en `PanelAdminViewModel`, ver 5.5; Login verificado en `LoginViewModel`, ver 5.5): Login guarda la sesión de un `ADMIN` y, si ya existe una (vigente), entra directo al panel; el Panel admin lee nombre y rol, cierra sesión y usa `onSinSesion`; `ClienteApi.vigilante` lee el token y cierra la sesión ante un `401` de sesión. Un usuario que no es `ADMIN` **no se guarda**.
- ⚠ Cada `SessionManager(context)` crea su propia instancia de `AlmacenSesionCifrado` (y de `EncryptedSharedPreferences`): crear **una por ViewModel**, no una por pantalla ni por recomposición. Todas leen el mismo archivo (Android comparte el `SharedPreferences` de un mismo nombre dentro del proceso), así que lo que guarda Login lo ve el vigilante. Desde FE-1.2 `MyApp` sí guarda una instancia durante toda la vida del proceso: la del `VigilanteSesion` de `ClienteApi`.
- ⚠ **La sesión se borra en cada arranque en frío.** `MyApp.onCreate` llama a `cerrarSesion()` (decisión de producto: "el admin debe iniciar sesión cada vez que se abre la app desde cero"; si falla solo deja un `AppLog.e`). Consecuencias: la sesión **solo sobrevive mientras el proceso siga vivo**; si Android mata la app en segundo plano (p. ej. en una recolección larga), al volver no habrá sesión y el panel dispara `onSinSesion`. Cualquier flujo largo del admin debe tolerarlo. Además vence a las 12 h (`JWT_TTL_MIN` del backend; `expira_en` = `exp` del JWT).
- Nunca registrar el token en `AppLog`.
- Verificado en `LoginViewModel`: `session.esAdmin()` se llama en su `init`, en el hilo principal y **sin `try/catch`**: si el Keystore falla, crear el ViewModel lanza excepción y Login no abre (5.5).
- La hora de caducidad la da el reloj del teléfono: con el reloj adelantado, la app da por vencida una sesión que el backend aún acepta (y al revés, con el reloj atrasado el backend responde `401 TOKEN_EXPIRADO`, que también lleva a Login). No hay margen ni corrección de desfase.

**Permisos**

| Pieza | Ubicación | Cómo se usa | Cuidado |
|---|---|---|---|
| `Permisos` | `MainActivity.kt` (`object`) | `Permisos.CAMARA`, `Permisos.MICROFONO`, `Permisos.INICIALES: Array<String>`, `Permisos.ACTIVIDAD: Array<String>` | Verificado. `INICIALES` = cámara + micrófono + `ACTIVITY_RECOGNITION` (esta última **solo desde Android 10**; en versiones anteriores no se pide). Se piden en un solo diálogo al abrir Inicio, una vez por entrada de navegación (bandera `rememberSaveable`), y Inicio se muestra aunque se niegue alguno. `ACTIVIDAD` = solo `ACTIVITY_RECOGNITION` desde Android 10 (lista **vacía** antes: `PedirPermisos` llama entonces a `onResultado(true)` sin diálogo); la usa la ruta `admin/calibracion`. |
| `PedirPermisos(permisos: Array<String>, onResultado: (todosConcedidos: Boolean) -> Unit)` | `MainActivity.kt` | Se pone en la **ruta**, antes de la pantalla: si ya están concedidos llama a `onResultado(true)` sin mostrar nada (ver la ruta `ubicarme`). | Verificado. Al entrar comprueba `checkSelfPermission` y lanza el diálogo **solo con los que faltan**; el resultado es `true` si todos **los pedidos** se concedieron. Se llama desde un `LaunchedEffect(Unit)`, es decir, **después** de la primera composición (no dibujar nada que dependa del resultado antes). No explica por qué se pide ni abre Ajustes si el permiso quedó negado de forma permanente: en ese caso el diálogo ni aparece y `onResultado(false)` llega al instante. En `ubicarme`, si se niega la cámara la ruta hace `popBackStack()` **sin mostrar ningún mensaje**. En la ruta `inicio` el resultado se **ignora** (se marca `permisosPedidos = true` sea cual sea) y, mientras sale el diálogo, no se dibuja nada. |
| Ayudas de Inicio (`permisosNecesarios`, `permisosFaltantes`, `BannerPermisos`, `abrirAjustesApp`) | `ui/inicio/InicioScreen.kt` | — | Verificado. Son `private`: **no** se pueden reutilizar. Candidato a extraer a `ui/components/`. `permisosNecesarios()` **repite** la lista de `Permisos.INICIALES` y la pantalla pide los permisos por su cuenta además de la ruta (⚠ ver Inicio en 5.5). |
| Comprobación de cámara en Escaneo | `EscaneoScreen.kt` | `checkSelfPermission(CAMERA)` y, si falta, `RequestPermission` | **Duplica** lo que ya hace `PedirPermisos` en la ruta `ubicarme`; sirve de red de seguridad. Si se niega muestra "Necesito permiso de cámara" sin opción de reintento. |
| Comprobación de micrófono en Destino | `SeleccionDestinoScreen.kt` | `checkSelfPermission(RECORD_AUDIO)` sin volver a pedirlo; si falta, `BannerEstado` y la vista sigue solo con toques. Verificado: se comprueba **una sola vez** (`remember`) y `alAbrir` ignora llamadas repetidas, así que conceder el micrófono después (p. ej. desde Ajustes) no se nota hasta que se recree el ViewModel. Inicio y Destino usan `Manifest.permission.*` directamente, no `Permisos`. | Mismo criterio que pide la §3.2 ("sin micrófono: solo botones"). |

### 5.4 Tema y colores

`CampusColors` (`ui/theme/CampusColors.kt`) es la paleta para **toda vista nueva**. Verificado contra el código: es un `object` público de `Color` de Compose y sus 11 valores son exactamente los de esta tabla (ninguno más):

| Token | Valor | Uso típico |
|---|---|---|
| `Fondo` | `#030615` | Fondo de pantalla |
| `Superficie` / `SuperficieAlta` | `#050B24` / `#0B1235` | Tarjetas / elementos sobre tarjetas |
| `Borde` | `#232E78` | Borde fino de tarjetas y chips |
| `Primario` / `Acento` | `#5B3CF5` / `#8B6BFF` | Botones principales / íconos y resaltes |
| `TextoPrincipal` / `TextoSecundario` / `TextoSuave` | `#FFFFFF` / `#B9B2FF` / `#A9B0D9` | Jerarquía de texto |
| `Exito` / `Peligro` | `#2EE887` / `#B84DFF` | Estados |

⚠ Hay paletas privadas que **no** vienen de aquí: `Inicio` (`private val Fondo = #030712`, `Morado`…),
`EscaneoColores` y `GaleriaColores`. Se migran a `CampusColors` cuando se toque cada vista. Tampoco viene de aquí el fondo del `WebView` del editor de mapa (`#0A0E1A`, el mismo de su página web; no es `Fondo` `#030615`): al migrar esa página a la paleta hay que cambiar ambos sitios (el overlay `NoEncontrado` de Detalle de video usa el mismo `#0A0E1A`). `PanelAdminScreen` sí usa `CampusColors` (con el alias `C`), pero con literales propios: `#0C1340` (avatar y círculos de íconos) y el degradado `#3F24C4` → `#241470` de la tarjeta destacada. Las páginas web de los mapas llevan su propia paleta en CSS (fondo `#0A0E1A`, trazo de ruta `#6366f1`, prioridad alta `#ef4444`, normal `#f59e0b`): ahí la prioridad alta es **roja**, mientras `CampusColors.Peligro` es morado.

**`EscaneoColores`** (`ui/ubicacion/EscaneoConfig.kt`) es un `internal object` (no `private`: se ve en todo el módulo, pero no debe usarse en vistas nuevas). Equivalencias aproximadas al migrar a `CampusColors`:

| `EscaneoColores` | Valor | Más parecido en `CampusColors` | Ojo al migrar |
|---|---|---|---|
| `Fondo` | `#030712` | `Fondo` `#030615` | Casi igual |
| `Panel` | `#0B1220` | `Superficie` `#050B24` / `SuperficieAlta` `#0B1235` | Elegir según la altura de la tarjeta |
| `Morado` / `MoradoBoton` | `#7C3AED` / `#6D4AFF` | `Primario` `#5B3CF5` | Un solo primario reemplaza a los dos |
| `MoradoClaro` | `#A78BFA` | `Acento` `#8B6BFF` | |
| `TextoSecundario` | `#9CA3AF` (gris) | `TextoSuave` `#A9B0D9` | `CampusColors.TextoSecundario` es **lila** (`#B9B2FF`), no gris |
| `Verde` | `#22E58B` | `Exito` `#2EE887` | Casi igual |
| `Rojo` | `#EF4444` | `Peligro` `#B84DFF` | ⚠ **`Peligro` es morado, no rojo**: migrar cambia el color de los errores |
| `Pista` | `#2A2F45` | `Borde` `#232E78` | Distinto: `Pista` es gris azulado |

**Paleta privada de Login** (`ui/auth/LoginScreen.kt`, `private val` sueltos; verificado): `Fondo` `#030615`, `Primario` `#5B3CF5`, `Acento` `#8B6BFF`, `TextoSecundario` `#B9B2FF` y `TextoPrincipal` `#FFFFFF` son **idénticos** a los de `CampusColors`; solo `CampoFondo` `#060C25` (≈ `Superficie` `#050B24`) y `CampoBorde` `#2A3485` (≠ `Borde` `#232E78`, más claro) no tienen equivalente exacto, y el degradado del logo usa `#9A7BFF` → `#5B3CF5`. El comentario del archivo («cuando exista ui/theme, mover aquí…») quedó viejo: ya existe `CampusColors`, y migrar Login es casi solo cambiar el origen de cinco valores. `SeleccionDestinoScreen`, en cambio, **sí** usa `CampusColors` (`Fondo`, `Acento`).

**Paleta privada de Inicio** (`ui/inicio/InicioScreen.kt`, `private val` sueltos; verificado): `Fondo` `#030712`, `Morado` `#7C3AED`, `MoradoClaro` `#C4B5FD`, `MoradoOscuro` `#2E1F8A`, `TextoSecundario` `#9CA3AF` (gris), `Verde` `#22E58B`, `Rojo` `#EF4444`, `FondoAviso` `#3B1D1D`, más literales en línea: divisor `#111827` y degradado del orbe `#5B2FD6` / `#7C45EE`. Son los mismos valores que `EscaneoColores` salvo `MoradoClaro` (aquí `#C4B5FD`, allí `#A78BFA`) y los extras (`MoradoOscuro`, `FondoAviso`, divisor y degradado). Al migrar valen las equivalencias de la tabla anterior, incluido el aviso de que `Peligro` es morado y no rojo.

**`GaleriaColores`** (`ui/admin/imagenes/GaleriaScreen.kt`) es un `internal object`, usado por la Galería y también por `VideosScreen` (otro paquete). Equivalencias aproximadas al migrar (TODO que el propio archivo ya anota):

| `GaleriaColores` | Valor | Más parecido en `CampusColors` | Ojo al migrar |
|---|---|---|---|
| `Fondo` | `#0A0A1E` | `Fondo` `#030615` | Distinto: es un azul-morado más claro |
| `Tarjeta` | `#12122B` | `Superficie` `#050B24` / `SuperficieAlta` `#0B1235` | Elegir según la altura |
| `Placeholder` | `#1C1C3C` | `SuperficieAlta` | Solo el fondo de las miniaturas mientras Coil carga |
| `Borde` | `#3D2F8F` | `Borde` `#232E78` | Más morado y más claro |
| `Primario` | `#7C4DFF` | `Primario` `#5B3CF5` | |
| `Acento` | `#B39DFF` | `TextoSecundario` `#B9B2FF` (por tono) o `Acento` `#8B6BFF` | Aquí `Acento` es lila **claro**; el de `CampusColors` es más oscuro |
| `Texto` | `#FFFFFF` | `TextoPrincipal` | Igual |
| `TextoSuave` | `#B4B4CC` | `TextoSuave` `#A9B0D9` | Casi igual |
| `Verde` | `#2ECC71` | `Exito` `#2EE887` | Parecido |
| `Azul` | `#29B6F6` | — | **No existe equivalente**: marca `SUBIDA` y "Pendiente de proceso" |
| `Rojo` | `#FF5252` | `Peligro` `#B84DFF` | ⚠ **`Peligro` es morado, no rojo**: migrar cambia el color de `ERROR`, "Con errores" y "Eliminar" |

⚠ **`MainActivity` envuelve toda la app en el `MaterialTheme` por defecto** (`MaterialTheme { AppNav() }`),
no en un tema propio con `CampusColors`. Los componentes de Material que no reciben color explícito
(por ejemplo `AlertaFormSheet`, 5.5) salen con los colores estándar de Material; cada vista pública
pinta sus colores a mano. Un tema propio sería el sitio natural para unificar las paletas.

### 5.5 Componentes de UI reutilizables

| Componente | Ubicación | Firma | Para qué / cuidado |
|---|---|---|---|
| `BannerEstado` | `ui/components/BannerEstado.kt` | `BannerEstado(tipo: TipoBanner, icono, titulo, mensaje)` | Aviso de error (`TipoBanner.Error`) o advertencia (`TipoBanner.Advertencia`). TalkBack lo anuncia al aparecer. Usado en Login y Destino. |
| `ZonaMicrofono` | `ui/destino/componentes/PanelesVoz.kt` | `ZonaMicrofono(escuchando: Boolean, onClick: () -> Unit)` | Micrófono grande con halo que pulsa y el texto "Escuchando… / Toca para hablar". Sirve para cualquier vista que escuche. Candidato a `ui/components/`. Verificado contra el código (bache 2); detalle abajo. |
| `TarjetaTextoReconocido` | ídem | `(texto: String, onDescartar: () -> Unit)` | Lo que entendió el reconocimiento, con ✕. |
| `TarjetaConfirmacion` | ídem | `(lugar: LugarDestino, onSi, onNo)` | Específica de lugares; para otra confirmación hay que generalizar el título. Siempre dice «Di sí o no.», incluso sin micrófono. Detalle abajo. |
| `BarraSuperior` | `ui/destino/componentes/PanelesVoz.kt` | `(onAtras, onAjustes)` | Confirmada la duplicación: `ui/ubicacion/componentes/PanelesEscaneo.kt` tiene otra con la misma firma pero con **título fijo** ("Ubicarme" / "Captura de entorno") y colores de `EscaneoColores` (ver abajo). Unificar en `ui/components/` con parámetros `titulo` y `subtitulo`. Verificado (bache 2): esta versión usa `BotonIcono` (56 dp) y título fijo «Destino»; la de Ubicarme usa `IconButton` (48 dp). |
| `BotonIcono` | `ui/destino/componentes/Comun.kt` | `internal` · `(icono, descripcion, onClick, tint)` | Botón circular de solo ícono: área de 56 dp, ícono de 28 dp (`tint` por defecto `Acento`); la descripción va en el contenedor y el ícono no lleva descripción propia. Sin parámetro `enabled`. |
| `Modifier.tarjeta(radio)` | ídem | `internal` | Fondo `Superficie` + borde de 1 dp `Borde` con esquinas redondeadas (`radio` 20 dp por defecto; `FilaLugar` usa 18 dp). Aplica recorte, fondo y borde, en ese orden. |
| `CategoriaLugar.icono()` | ídem | `internal` | Ícono de cada categoría (el dominio no conoce Compose). Verificado: es un `when` **exhaustivo, sin `else`**, así que una categoría nueva no compila hasta que se le asigne ícono. Tabla abajo. |
| `AlertaFormSheet` | `ui/admin/mapa/AlertaFormSheet.kt` (`public`) | `(alerta: Alerta, esNueva: Boolean, error: String?, onCambio: (Alerta) -> Unit, onGuardar, onCancelar, onEliminar)` | Hoja inferior (`ModalBottomSheet`) para crear o editar una alerta (vista 7.9). Detalle abajo. |
| `MapaPublicoScreen` | `map/MapaPublicoScreen.kt` (`public`) | `MapaPublicoScreen(modifier: Modifier = Modifier)` | Mapa público (`index.html` + `app.js`) en un `WebView` con seguimiento por pasos. Crea su propio `PdrTracker`, registra el puente `AndroidBridge` (`PuentePdr`) y empuja la posición, el rumbo y los avisos a la página (tabla en 2.6). Aplica `systemBarsPadding()` (el mapa no maneja *insets*). Libera sensores y `WebView` al salir. ⚠ **Hoy no tiene ruta en §5.8** (`admin/ubicacion-manual` abre `UbicacionManualScreen`); comprobar en `AppNav` si queda algún uso. FE-3.1 le da la ruta pública `mapa`. |
| `CalibracionScreen` / `CalibracionContent` | `ui/admin/calibracion/CalibracionScreen.kt` (`public`) | `CalibracionScreen(onVolver, modifier, vm = viewModel())` · `CalibracionContent(ui, acciones, modifier)` | Vista 7.3b completa (detalle abajo, «CalibracionScreen y CalibracionBridge»). **No navega.** |
| `UbicacionManualScreen` / `UbicacionManualContent` | `ui/admin/recoleccion/UbicacionManualScreen.kt` (`public`) | `UbicacionManualScreen(onVolver, onConfirmar: (InicioRecoleccion) -> Unit, onAjustes = {}, onCalibrar = {}, viewModel = viewModel(factory = …))` · `UbicacionManualContent(estado, acciones, modifier, longitudCalibradaM: Double? = null)` | Vista 7.3 completa (detalle abajo, «UbicacionManual»). Sustituye a `MapaPublicoScreen` en la ruta `admin/ubicacion-manual`. |
| `EditorMapaScreen` / `EditorMapaContent` | `ui/admin/mapa/EditorMapaScreen.kt` (`public`) | `EditorMapaContent(alertasJson, lugaresJson, pendientes, borradorJson, eventos, modifier, miPosicion)` | Mapa web de alertas dentro de un `WebView` (vista 7.8). Detalle abajo. |
| `FilaCategorias`, `CampoBusqueda`, `EncabezadoLista`, `FilaLugar`, `EstadoVacio`, `BotonVolver` | `ui/destino/componentes/ListaLugares.kt` | `FilaCategorias(seleccionada: CategoriaLugar?, onElegir: (CategoriaLugar?) -> Unit)` · `CampoBusqueda(texto: String, onCambio: (String) -> Unit)` · `EncabezadoLista(orden: OrdenLugares, onCambiarOrden: () -> Unit)` · `FilaLugar(lugar: LugarDestino, onClick: () -> Unit)` · `EstadoVacio(mensaje: String?, accion: String, onAccion: () -> Unit)` · `BotonVolver(onClick: () -> Unit)` | Verificado contra el código (bache 2). Propios de Destino salvo `EstadoVacio` y `BotonVolver`, que son genéricos. Todos públicos; `ChipCategoria` es privado. Detalle abajo. |
| `EncabezadoPregunta`, `TarjetaOpciones` | `ui/destino/componentes/PanelesVoz.kt` | `EncabezadoPregunta()` · `TarjetaOpciones(opciones: List<LugarDestino>, onElegir: (LugarDestino) -> Unit)` | Verificadas contra el código (bache 2): las firmas coinciden con las llamadas de `SeleccionDestinoScreen`. `TarjetaOpciones` muestra las coincidencias cuando hay varias (5.5, Destino). Detalle abajo. |

**Componentes de `ui/destino/componentes/` en detalle (verificado, bache 2)**

Reparto: `PanelesVoz.kt` (`BarraSuperior`, `EncabezadoPregunta`, `ZonaMicrofono`, `TarjetaTextoReconocido`, `TarjetaConfirmacion`, `TarjetaOpciones`), `ListaLugares.kt` (`FilaCategorias`, `ChipCategoria`, `CampoBusqueda`, `EncabezadoLista`, `FilaLugar`, `EstadoVacio`, `BotonVolver`) y `Comun.kt` (`Modifier.tarjeta`, `CategoriaLugar.icono()`, `BotonIcono`).

- **Visibilidad y estilo:** todo es público salvo `ChipCategoria` (privado) y lo de `Comun.kt` (`internal`). Ninguno de los tres archivos tiene `@Preview` (el de Destino está en la pantalla). Los textos son literales (sin `strings.xml`). Los colores salen de `CampusColors` (`TextoPrincipal`, `TextoSecundario`, `TextoSuave`, `Acento`, `Primario`, `Superficie`, `SuperficieAlta`, `Borde`), salvo dos colores fijos en el degradado del botón del micrófono (`#7B5CFF` y `#3B24C9`) y `Color.White`.
- **Dependencias que frenan moverlos a `ui/components/`:** `ListaLugares.kt` importa `OrdenLugares` de `ui.destino` y Coil (`AsyncImage`); `EncabezadoLista` no se puede mover sin llevarse `OrdenLugares` o abstraerlo. Los de `PanelesVoz.kt` que reciben `LugarDestino` dependen del dominio.

| Componente | Qué dibuja | Cuidados |
|---|---|---|
| `BarraSuperior` | Fila de al menos 64 dp: `BotonIcono` «Volver» (flecha), título fijo «Destino» (22 sp) y `BotonIcono` «Ajustes». | Título fijo: unificar con la de Ubicarme mediante un parámetro `titulo`. |
| `EncabezadoPregunta` | Círculo de 72 dp con ícono de ubicación, título «¿A dónde quieres ir?» (28 sp, marcado como encabezado para TalkBack) y subtítulo «Puedes decir el nombre del lugar o elegirlo de la lista.». Sin parámetros. | El texto escrito no es el hablado: la `PREGUNTA` del ViewModel añade «Di el nombre del lugar.». |
| `ZonaMicrofono` | Zona de 200 dp: botón de 144 dp (degradado, sombra, micrófono de 64 dp) y dos halos de 168 y 196 dp que pulsan (escala 1 → 1,08 en 900 ms) solo mientras escucha. Debajo, «Escuchando…» (con ícono) o «Toca para hablar», como `liveRegion` Polite. La descripción del botón es «Micrófono. Escuchando. Toca dos veces para detener.» o «Micrófono. Toca dos veces para decir el nombre del lugar.». | Solo el botón es táctil. La transición infinita se crea siempre, aunque no escuche. `onClick` es el mismo en ambos estados: ⚠ la descripción promete «detener», pero lo que ocurre al tocar mientras escucha lo decide `alPresionarMicrofono`; confirmarlo en el ViewModel. |
| `TarjetaTextoReconocido` | Tarjeta con ícono, «Texto reconocido:» (14 sp), «“texto”» (22 sp) y ✕ (`BotonIcono` «Descartar texto reconocido»). Los dos textos se fusionan para TalkBack. | La composable añade las comillas «“ ”»: pasar el texto **sin** comillas. No es `liveRegion`: no se anuncia sola. |
| `TarjetaConfirmacion` | Tarjeta con ícono de ubicación, «¿Quieres ir a {nombre}?» (22 sp) y «Di sí o no.». Botones Sí (relleno, `Primario`) y No (contorno) de al menos 64 dp, 22 sp. La pregunta es `liveRegion` Polite; los botones dicen «Sí, ir a {nombre}» y «No, elegir otro lugar». | Título fijo de lugares. Siempre dice «Di sí o no.», incluso con `sinMicrofono` (no recibe ese dato). ⚠ El anuncio de TalkBack se suma a la voz del ViewModel (ver abajo). |
| `TarjetaOpciones` | Tarjeta con «Encontré varios lugares. ¿Cuál quieres?» (`liveRegion` Polite) y un `OutlinedButton` de al menos 56 dp por opción (ícono de categoría + nombre, 18 sp). | No limita cuántas dibuja (el ViewModel entrega 2–3). El botón no incluye la categoría en su descripción: TalkBack lee solo el nombre. El texto difiere del hablado («Encontré N lugares: A, B o C. Di cuál quieres.»). |
| `FilaCategorias` | Fila con scroll horizontal (10 dp entre chips): un chip por cada `CategoriaLugar.DESTACADAS` (texto `etiquetaPlural` + ícono) y al final el chip «Más» con un `DropdownMenu` con `OTRAS`. | **El conmutador está aquí, no en el ViewModel:** tocar un chip destacado ya activo llama `onElegir(null)`. Los del menú «Más» **no** conmutan: se quitan con «Quitar filtro», que solo aparece si hay una de `OTRAS` activa. Con una de `OTRAS` activa, «Más» muestra su nombre e ícono y queda resaltado. No hay chip «Todos». ⚠ El chip «Más» tiene `contentDescription` fijo «Más categorías»: con una categoría activa, TalkBack no dice cuál. |
| `ChipCategoria` (privado) | Píldora de al menos 48 dp; activo = fondo `Primario` al 18 % y borde de 2 dp `Acento`, inactivo = borde de 1 dp `Borde`. Semántica `selected`, rol botón. | Opcionalmente lleva flecha (el chip «Más») y descripción propia. |
| `CampoBusqueda` | `OutlinedTextField` de una línea, al menos 60 dp, placeholder «Buscar un lugar…», lupa y, si hay texto, botón «Borrar búsqueda». La tecla del teclado es Buscar y solo quita el foco: la lista se filtra al escribir. | El valor viene del estado del ViewModel (sin estado local). Cada cambio, incluido borrar, llama `alCambiarBusqueda` y **corta la voz**. ⚠ Sin `label`: comprobar con TalkBack que anuncia el placeholder. |
| `EncabezadoLista` | Título («Lugares cercanos» si el orden es `CERCANIA`, si no «Lugares»; encabezado para TalkBack) y, a la derecha, un botón de al menos 48 dp con `orden.etiqueta` e ícono de intercambio; descripción «{etiqueta}. Toca para cambiar el orden.». | ⚠ Dice «Lugares cercanos» aunque ninguna `distanciaMetros` tenga valor (sin ubicación). |
| `FilaLugar` | Tarjeta (radio 18 dp) clicable: miniatura de 64 dp (`AsyncImage` de Coil con recorte, o el ícono de la categoría si `imagenUrl` es `null`), nombre (18 sp), categoría (`etiqueta` + ícono), distancia («N m», solo si no es `null`) y flecha. Descripción: «{nombre}, {categoría}, a {N} metros. Toca para elegir este destino.». | Coil sin `placeholder` ni `error`: si la URL falla, se ve el cuadro vacío en vez del ícono. La distancia es siempre en metros («1200 m»), sin pasar a km. El nombre no tiene `maxLines`. |
| `EstadoVacio` | Mensaje opcional centrado (18 sp) y una acción de texto debajo (al menos 48 dp): «Limpiar filtros», «Reintentar». | Genérico. Firma invertida respecto a `MensajeVacio` (aquí `mensaje` es opcional y `accion` obligatoria; allí al revés): decidir al unificar. |
| `BotonVolver` | `OutlinedButton` de ancho completo, al menos 64 dp, forma de 18 dp, borde de 2 dp, flecha + «Volver» (20 sp). | Incluye su propio padding (20 dp horizontal, 12 dp vertical). |

Íconos de `CategoriaLugar.icono()` (todos `outlined`): `BIBLIOTECA` → `MenuBook` (versión `AutoMirrored`), `CAFETERIA` → `LocalCafe`, `BANO` → `Wc`, `BLOQUE` → `Apartment`, `AUDITORIO` → `TheaterComedy`, `DEPORTES` → `SportsSoccer`, `ADMINISTRACION` → `AccountBalance`, `ENTRADA` → `MeetingRoom`.

⚠ **Varias voces a la vez (comprobar en un dispositivo con TalkBack):** además de la voz del `VoiceController`, hay **tres** `liveRegion` Polite: el estado de `ZonaMicrofono`, la pregunta de `TarjetaConfirmacion` y el título de `TarjetaOpciones`. Pueden hablar a la vez que el ViewModel, y TalkBack podría estar hablando justo cuando arranca `listen`, de modo que el reconocedor capte esa voz. El código por sí solo no permite saberlo.

**`AlertaFormSheet` en detalle (verificado)**

- **Sin estado propio** sobre la alerta: recibe el borrador `alerta` y avisa cada cambio con `onCambio(alerta.copy(...))`. Quien la use guarda el borrador, valida y persiste. Lo único que guarda por dentro es si está abierto el diálogo "¿Eliminar esta alerta?".
- **Campos:** `mensaje` (máx. `MAX_MENSAJE` caracteres, con contador; si `error != null` lo muestra en lugar de la ayuda), `tipo` (chips: Agua, Mobiliario, Escalones, Obra, Vehículos, Otro), `prioridad` (Normal / Alta), `radio` (deslizador de 5 a 100 m en saltos de 5), `activa` (interruptor) y la posición `lat, lng` **solo de lectura**.
- **Botones** (56 dp mínimo): Cancelar, Eliminar (**solo si `!esNueva`**, con confirmación) y Guardar. Cerrar la hoja (deslizar o tocar fuera) equivale a `onCancelar`.
- **No valida nada**: si el mensaje está vacío, o falta la posición, lo decide el ViewModel y lo devuelve por `error`.
- **"Cada cambio se refleja en vivo en el mapa"**: lo hace quien recibe `onCambio`. En `EditorMapaViewModel` el borrador vive **aparte** de la lista (`formulario` frente a `alertas`), así que cancelar **no necesita revertir** nada.
- **Para reutilizarlo desde la recolección** basta importarlo (es público) y pasarle una `Alerta` con la posición actual. Depende de `Alerta` y de `MAX_MENSAJE` (`const val MAX_MENSAJE = 200`, público, declarado al inicio de `EditorMapaViewModel.kt`, mismo paquete `ui.admin.mapa`). Por la regla 4, si lo usan dos vistas debería moverse a `ui/components/` junto con esa constante.
- La lista de tipos (`private val TIPOS`) está **duplicada**: aquí, en el mapa web y en la tabla de `Alerta`. Verificado: en la web son `TIPOS` y `TIPO_NOMBRE` en `editor_mapa.js` **y** las opciones del `<select id="f-tipo">` de `editor_mapa.html`; añadir un tipo exige cambiar cuatro sitios (esta lista, esos dos y la tabla de `Alerta`).
- Accesibilidad: el `Slider` no lleva descripción propia (el texto "Radio de activación: N m" va aparte), así que TalkBack lo anuncia por su valor; conviene un `stateDescription` del tipo "N metros".

**`EditorMapaViewModel` y el formulario de alerta (verificado, `ui/admin/mapa/EditorMapaViewModel.kt`)**

| Pieza | Detalle |
|---|---|
| `EditorMapaViewModel()` | `ViewModel` sin parámetros. Estado en `ui: StateFlow<EditorMapaUi>`. Todo vive **en memoria**, con datos de ejemplo (`demo1`, `demo2` y el lugar "Biblioteca") que hay que borrar al conectar el repositorio. |
| `EditorMapaUi` | `alertas`, `lugares`, `pendientes: Set<String>` (ids con cambios sin sincronizar), `formulario: Alerta?` (borrador; `null` = cerrado), `formularioEsNuevo`, `error`, `sincronizando`. Calculados para el mapa web: `alertasJson`, `lugaresJson` y `borradorJson` (claves `id`, `lat`, `lng`, `mensaje`, `tipo`, `prioridad`, `radio`, `activa`). |
| `abrirFormulario(id: String?, lat, lng)` | Con un `id` existente abre esa alerta para editar; si no, crea una nueva (`UUID`, mensaje vacío) en esa posición. |
| `actualizarFormulario(a)` | Reemplaza el borrador y limpia el error (es el `onCambio` de `AlertaFormSheet`). |
| `cancelarFormulario()` | Cierra el formulario sin tocar `alertas`. |
| `guardarFormulario()` | Valida el mensaje **ya recortado**: vacío → "Escribe el mensaje que se leerá al usuario."; más de `MAX_MENSAJE` → "Máximo 200 caracteres.". No valida `radio`, `tipo`, `prioridad` ni posición. Si es válido, reemplaza o agrega la alerta, la marca como pendiente y cierra. |
| `mover(id, lat, lng)` · `eliminar(id)` | Se aplican al instante y marcan el id como pendiente; `eliminar` además cierra el formulario si estaba editando esa alerta. |
| `sincronizar()` | Si hay pendientes y no está sincronizando: espera 600 ms (simulado) y **vacía `pendientes`**. TODO: enviar al backend y, si falla, dejarlos intactos. |

Cuidados:
- **Se pierde todo al salir de `admin/mapa`:** el ViewModel pertenece a la entrada de navegación y las alertas están solo en memoria. Hasta que exista el repositorio, nada de lo que cree el admin sobrevive.
- **`pendientes` guarda solo ids, no la operación** (crear, modificar o eliminar). Una alerta creada y eliminada antes de sincronizar deja un id pendiente que el servidor nunca conoció. Antes de conectar la API hay que guardar el tipo de cambio.
- `Alerta.toJson()` es `private`: otra vista que hable con el mapa web tendría que copiarla. Candidata a quedar junto al modelo.
- La validación vive dentro del ViewModel: para reutilizarla desde la recolección conviene extraerla como función pura (5.7).

**`EditorMapaScreen` y `EditorBridge` (verificado, `ui/admin/mapa/EditorMapaScreen.kt`, `assets/editor_mapa.html` y `assets/editor_mapa.js`)**

| Pieza | Detalle |
|---|---|
| `EditorMapaScreen` | `(onVolver, onVerLista, posicionAdmin: () -> Pair<Double, Double>?, modifier = Modifier.fillMaxSize(), vm: EditorMapaViewModel = viewModel())`. Conecta el ViewModel con el mapa y, cuando `ui.formulario != null`, muestra `AlertaFormSheet` encima. Es la que registra el `NavHost` (`admin/mapa`). |
| `EditorMapaContent` | `(alertasJson: String, lugaresJson: String, pendientes: Int, borradorJson: String?, eventos: EditorMapaEventos, modifier, miPosicion: Pair<Double, Double>? = null)`. Solo dibuja el `WebView` de `assets/editor_mapa.html` (Leaflet + OpenStreetMap en línea). No conoce el ViewModel. |
| `EditorMapaEventos` | `interface` pública con 8 funciones: `abrirFormulario(id: String?, lat, lng)`, `cancelarFormulario()`, `moverAlerta(id, lat, lng)`, `eliminarAlerta(id)`, `sincronizar()`, `verLista()`, `pedirMiPosicion()` y `salir()`. |

**Puente `EditorBridge`, web → app** (métodos `@JavascriptInterface`; todos se pasan al hilo principal con `Handler(Looper.getMainLooper())`, porque llegan en un hilo del `WebView`):

| Función | Argumentos / qué hace |
|---|---|
| `listo()` | La página terminó de cargar. Hasta entonces la app no le envía nada. |
| `abrirFormulario(json)` | `{"id": texto o null, "lat", "lng"}`. `id = null` crea una alerta nueva en esa posición. |
| `moverAlerta(id, lat, lng)` · `eliminarAlerta(id)` | Se aplican al instante en el ViewModel. |
| `cancelarFormulario()` · `sincronizar()` · `verLista()` · `pedirMiPosicion()` · `salir()` | Sin argumentos. |

**Puente, app → web** (`evaluateJavascript`; el estado se reenvía completo cada vez que cambia y solo después de `listo()`):

| Función JS | Qué recibe |
|---|---|
| `setInsets(topDp, bottomDp)` | Alto de las barras del sistema **en dp**: `env(safe-area-inset-*)` no funciona en `WebView`, por eso se lo pasa la app. |
| `cargarAlertas(json)` · `cargarLugares(json)` | Un **texto** JSON entre comillas (se arma con `JSONObject.quote`), no un objeto: el JS hace `JSON.parse` (verificado). |
| `setPendientes(n)` | Número de alertas sin sincronizar. |
| `setBorrador(json)` (o `null`) | Vista en vivo del borrador del formulario; `null` = formulario cerrado. |
| `setMiPosicion(lat, lng)` | Solo se llama si `miPosicion != null`. Dibuja el punto y **centra** el mapa con zoom de 18 o más cada vez que se llama. |
| `upsertAlerta(json)` · `quitarAlerta(id)` | Existen en el JS, pero **Kotlin no las llama**: hoy todo entra por `cargarAlertas`, que reemplaza la lista completa y deselecciona si la alerta elegida ya no está. |
| `window.onAtras()` | Lo invoca el botón Atrás del sistema (`BackHandler`). El JS sale de los modos temporales (mover, colocar, formulario) y, al final, llama a `salir()`. |

Cuidados:
- **`posicionAdmin` hoy es `{ null }`** (5.8): el botón de "mi posición" no hace nada y no avisa. La posición se guarda con `remember` (no sobrevive a rotar la pantalla). ⚠ Deducido del código, no probado: como se envía con `LaunchedEffect(listo, miPosicion)`, volver a pedirla con **las mismas coordenadas** no vuelve a centrar el mapa.
- **Sin internet:** `editor_mapa.html` carga Leaflet desde `unpkg.com`. Si falla, `MapaBase.iniciar` (5.9) muestra «No se pudo cargar el mapa. Revisa tu conexión a internet.» y **ya dejó definidos** `window.onAtras` (llama a `salir()`), `setInsets` y el botón Volver; `editor_mapa.js` termina antes de llamar a `listo()`. Resultado: Atrás y Volver funcionan, pero la app nunca envía alertas ni lugares. (Antes el JS terminaba antes de definirlos y ambos botones quedaban muertos.) Probado con jsdom, no en dispositivo.
- **Orden de `window.onAtras()`** (siempre devuelve `true`, y Kotlin ignora el valor): sale de mover → sale de colocar → cancela el borrador (`cancelarFormulario`) → deselecciona → si hay pendientes pide confirmar "Tienes cambios sin sincronizar. ¿Salir de todas formas?" → `salir()`.
- **`sincronizando` y `error` del ViewModel no llegan al mapa:** `EditorMapaContent` solo recibe `pendientes`; `error` solo se ve en la hoja del formulario. Cuando `sincronizar()` llame a la API real habrá que ampliar el puente para mostrar progreso o fallo.
- **Registro fuera de `AppLog`:** usa `android.util.Log` con el tag `EditorMapa` (mensajes de la consola JS y errores de carga de recursos), así que **no queda en `files/logs/app.log`**. Un recurso que falla (por ejemplo, teselas sin internet) solo deja un `Log.e`: no hay aviso en pantalla.
- `WebView.setWebContentsDebuggingEnabled(true)` solo en builds depurables (`chrome://inspect`).
- **Seguridad del puente (verificado):** `addJavascriptInterface` expone `EditorBridge` a todo el JavaScript de la página, y `editor_mapa.html` carga Leaflet 1.9.4 desde `unpkg.com` **sin `integrity`**; además `bindTooltip(l.nombre)` de los lugares hace que Leaflet interprete el texto como HTML. Los demás datos se insertan con `textContent` (patrón a mantener). Con datos locales el riesgo es bajo; reevaluarlo al conectar `/admin/alerts` o servir Leaflet desde `assets/` (decisión 13).
- **Todo en línea:** Leaflet y la fuente Inter (Google Fonts) vienen de internet, y las teselas del servidor público de OpenStreetMap (sujetas a su política de uso). El `viewport` lleva `user-scalable=no`.
- **Prueba sin teléfono:** abrir `editor_mapa.html` en un navegador de escritorio activa un modo demo (3 alertas, el lugar "Biblioteca" y `window.prompt` en lugar del formulario nativo): sirve para iterar la interfaz sin compilar la app.
- **Las dos "Ver lista"** (arriba y en el dock) llaman a `verLista()`; como `onVerLista` está vacío en `AppNav`, **no pasa nada** y no hay aviso (el toast solo sale en el navegador).
- **Eliminar tiene dos confirmaciones distintas:** desde la tarjeta del mapa, un modal web ("¿Eliminar esta alerta? Dejará de avisarse a los usuarios."); desde `AlertaFormSheet`, el diálogo de Compose (5.5).
- **Solo del lado web:** los filtros por tipo, prioridad y estado (nunca ocultan la alerta seleccionada) y las capas `cobertura` y `rutas`, que existen como grupos **vacíos** (sin datos, `PLAN.md`). Las claves de `tipo` y `prioridad` que el JS no reconoce no fallan: `tipo` sale con ⚠️ y el nombre "Alerta", y `prioridad` se pinta como "Normal" en ámbar (`#f59e0b`; alta es `#ef4444`).
- `onRelease` destruye el `WebView`: no guardar referencias a él fuera de la composición.

**`PanelAdminViewModel` (verificado, `ui/admin/panel/PanelAdminViewModel.kt`)**

| Pieza | Detalle |
|---|---|
| Constructor | `PanelAdminViewModel(repo: AdminRepository, session: SessionManager)`. `Factory(context)` crea `AdminRepositoryStub()` y `SessionManager(context.applicationContext)` (uno por ViewModel, como pide 5.3). |
| `state: StateFlow<PanelUiState>` | `nombre` (primer nombre: lo que hay antes del primer espacio del nombre de la sesión), `rolTexto` (fijo: "Administrador del sistema"), `resumen: ResumenAdmin?`, `cargandoResumen` (empieza en `true`), `errorResumen`. |
| `eventos` | `Channel(Channel.BUFFERED)` + `receiveAsFlow()`: cada evento lo recibe **un** recolector y queda guardado si llega antes de que alguien recoja. `PanelEvento.SesionCerrada` (volver al flujo público) y `PanelEvento.SinSesion` (ir a Login). |
| `cargarResumen()` | Pone `cargandoResumen = true` y `errorResumen = false`, llama a `repo.obtenerResumen()` y, ante **cualquier** `Exception`, deja `errorResumen = true`. Sirve también de reintento. |
| `cerrarSesion()` | `session.cerrarSesion()` y emite `SesionCerrada`. |

Cuidados:
- **La guarda de rol corre solo en `init`:** sin sesión, con la sesión vencida (`expira_en` pasado, FE-1.2: `obtener()` da `null`) o con rol distinto de `ADMIN` emite `SinSesion` y no carga nada; mientras el ViewModel viva no se vuelve a comprobar. Las peticiones protegidas que haga después (FE-2.2: `GET /v1/admin/stats`) quedan cubiertas por `SesionInterceptor` + `EventosSesion` (5.3): `AppNav` vuelve a Login aunque el panel no lo pida.
- `session.obtener()` se llama en el hilo principal y sin `try/catch`. ⚠ Deducido de unir esto con 5.3 (el primer acceso al almacén cifrado puede tardar y lanzar excepción si falla el Keystore): ese fallo cerraría la app al abrir el panel.
- Si `cargarResumen()` falla después de haber cargado antes, `resumen` **conserva el dato anterior** junto con `errorResumen = true`: `PanelAdminScreen` muestra entonces el aviso de error **y** los datos viejos, con el chip "En tiempo real" (ver abajo).
- Llamarla dos veces seguidas lanza dos cargas sin cancelar la primera; gana la que termine última.
- `catch (e: Exception)` también traga `CancellationException`; no copiarlo en código que deba cancelarse (Detalle de video sí la relanza). No registra nada en `AppLog`.
- Con el stub (`nombre = "Administrador"`) el saludo sale "Administrador", no un nombre propio.

**`GaleriaViewModel` (verificado, `ui/admin/imagenes/GaleriaViewModel.kt`)**

| Pieza | Detalle |
|---|---|
| Constructor | `GaleriaViewModel(repositorio: VideoRepository)`. `Factory(appContext)` crea `AssetsVideoRepository(appContext)`. Estado en `uiState: StateFlow<GaleriaUiState>`. Carga en `init`. |
| `GaleriaUiState` | `cargando` (empieza en `true`), `error: String?`, `videos`, `todas: List<Foto>` (las fotos de todos los videos), `filtros`, `modo`, `pagina` (desde 1) y `seleccion: Set<String>` con el **`uid`** de cada foto (5.6). Calculadas: `filtradas`, `totalPaginas` (mínimo 1), `paginaActual` y `lugares` (lugares distintos, ordenados). |
| `GaleriaFiltros` | `busqueda`, `lugar`, `videoId`, `estado`, `calidad`; todos opcionales y combinados con **Y**. `hayActivos` dice si hay alguno. |
| `ModoVista` · `FOTOS_POR_PAGINA` | `CUADRICULA` / `MAPA` (`cambiarModo`). `const val FOTOS_POR_PAGINA = 24`, público, en este archivo. |
| Acciones | `cargar()`, `buscar`, `filtrarLugar`, `filtrarVideo`, `filtrarEstado`, `filtrarCalidad`, `limpiarFiltros`, `irAPagina(n)` (se acota a 1…`totalPaginas`), `alternarSeleccion(uid)`, `limpiarSeleccion`, `eliminarSeleccion`, `reasignarSeleccion(lugar)`. |

Cuidados:
- **Eliminar y reasignar no pasan por `VideoRepository` ni por `EdicionesLocales`:** solo cambian `todas` en el estado (y `videos` queda sin tocar). Al salir de la pantalla se pierden, y una foto "eliminada" aquí **sigue apareciendo** en Lista y Detalle de video. `cargar()` (el reintento) también restaura lo eliminado en memoria.
- **No escucha `cambios()`:** carga una sola vez, así que lo que se borre o renombre en Detalle de video solo se ve al volver a entrar en Galería (el `VideoDetalleViewModel` sí lo hace, ver abajo).
- Cambiar cualquier filtro vuelve a la página 1 y **vacía la selección**; cambiar de página **no** la vacía, y `eliminarSeleccion` / `reasignarSeleccion` actúan sobre toda la selección, incluidas fotos de otras páginas que no se ven. La interfaz debe mostrar el total seleccionado, no solo el de la página.
- La búsqueda ignora mayúsculas pero **no tildes**, y mira nombre de archivo, nombre del video y lugar. Según 5.7, `BuscarLugares.filtrar` sí ignora tildes: no son equivalentes.
- `filtradas`, `totalPaginas`, `paginaActual` y `lugares` son *getters* **sin caché**: `filtradas` se recalcula en cada lectura, y `GaleriaContent` lee `filtradas`, `paginaActual` y `totalPaginas` en cada recomposición (el filtro corre **tres veces**). Aceptable con pocos cientos de fotos; con el backend, filtrar y paginar en el servidor.
- `reasignarSeleccion` guarda `lugar.trim()`: con texto en blanco asigna `""` (no `null`) y esa cadena vacía aparece como un lugar más en `lugares`. `GaleriaScreen` ya deshabilita "Reasignar" con el texto en blanco, pero el ViewModel no valida: otra vista que lo llame debe hacerlo.
- Si se eliminan todas las fotos del lugar que está filtrado, el filtro sigue activo pero ese lugar ya no está en `lugares`: lista vacía sin opción visible para quitarlo (`eliminarSeleccion` no limpia filtros) salvo `limpiarFiltros()`.
- `cargar()` captura toda `Exception` con un mensaje fijo ("No se pudieron cargar las imágenes") y no registra nada en `AppLog`.

**`VideoDetalleViewModel` (verificado, `ui/admin/videos/VideoDetalleViewModel.kt`; la pantalla y el puente, más abajo)**

| Pieza | Detalle |
|---|---|
| Constructor | `VideoDetalleViewModel(videoId: String, repositorio: VideoRepository)`. `Factory(appContext, videoId)` crea `AssetsVideoRepository(appContext)`. Estado en `ui: StateFlow<VideoDetalleUiState>`. |
| `VideoDetalleUiState` | `cargando` (empieza en `true`), `noEncontrado`, `videoJson: String?` y `otrosJson` (`"[]"` por defecto). Ya vienen **serializados**: el mapa web recibe JSON. |
| `videoJson` | `{id, nombre, fecha, fotos: [{id, url, thumb, lat, lng, rumbo}]}`. `fecha` = los 10 primeros caracteres de `creadoEn` (espera `"2026-10-09…"`); `rumbo` es número o `null`. **No** incluye `lugar`, `estado`, `calidad` ni `capturadaEn`. |
| `otrosJson` | `[{id, nombre, fotos: [{lat, lng}]}]` con **los demás videos**, para comparar cobertura en el mapa. |
| Acciones | `renombrar(nombre)` (recorta espacios), `eliminarFoto(fotoId)`, `eliminarVideo()`. Lanzan la operación en `viewModelScope` y no esperan resultado. |

Cuidados:
- **Patrón de recarga (copiarlo):** en `init` solo se recoge `repositorio.cambios()`; su primera emisión **es** la carga inicial, así que no hay otra llamada a `cargar()` y se evita la doble carga que advierte 5.6. Cada renombrar o eliminar vuelve a leer **todos** los manifests, porque se filtra por `id` sobre `obtenerVideos()`.
- **`huboVideo`:** una vez visto el video, si desaparece (lo eliminó la propia pantalla) **no** pasa a `noEncontrado` y `videoJson` conserva el último valor. `VideoDetalleScreen` no navega tras `eliminarVideo()`: lo hace el JS, que llama a `salir()` 900 ms después (ver `VideoBridge`, abajo).
- **Errores:** una `Exception` en `cargar()` antes de haber visto el video se muestra como `noEncontrado` (no distingue "no existe" de "falló la lectura"); después se ignora en silencio. Hoy casi no ocurre (un manifest roto se omite), pero con un repositorio remoto un corte de red se vería como "no encontrado": hará falta un estado de error. Sí relanza `CancellationException`.
- **`renombrar`, `eliminarFoto` y `eliminarVideo` no tienen `try/catch`:** si el repositorio lanza una excepción (el futuro `RemoteVideoRepository` con `IOException`), **la app se cierra**. Tampoco hay estado de progreso ni de error: es el pendiente "progreso y reintento del borrado" de la `PLAN.md`. `renombrar` no valida nada: la validación vive en el JS (ver `VideoBridge` más abajo).
- `fecha` solo funciona si `creadoEn` viene en ISO-8601 (5.6: hoy es texto sin convertir).

**`PanelAdminScreen` (verificado, `ui/admin/panel/PanelAdminScreen.kt`)**

| Pieza | Detalle |
|---|---|
| `PanelAdminScreen` | `(onRecolector, onLugares, onMapaAlertas, onImagenes, onVideos, onEstadisticas, onAjustes, onVolverModoPublico, onSesionCerrada, onSinSesion, viewModel = viewModel(factory = PanelAdminViewModel.Factory(LocalContext.current.applicationContext)))`. Recoge `viewModel.eventos` en un `LaunchedEffect(Unit)`: `SesionCerrada` → `onSesionCerrada()`, `SinSesion` → `onSinSesion()`. El `Channel` con búfer es lo que permite que un `SinSesion` emitido en `init` llegue aunque aún no haya colector. |
| `PanelAdminContent` | `internal` · `(state: PanelUiState, acciones: PanelAcciones)`. Sin lógica; 3 `@Preview` privados (normal, cargando, error). |
| `PanelAcciones` | `data class` con 10 lambdas (`{}` por defecto): `onRecolector`, `onLugares`, `onMapaAlertas`, `onImagenes`, `onVideos`, `onEstadisticas`, `onAjustes`, `onCerrarSesion`, `onVolverModoPublico`, `onReintentarResumen`. |
| Piezas privadas | `Encabezado`, `FilaTarjetas` / `TarjetaAcceso` (con `Acceso`), `ResumenRapido`, `TileDato`, `ChipTiempoReal`, `Pie`. No se reutilizan sin extraerlas. |

Cuidados:
- **No lee `cargandoResumen`:** mientras carga no hay indicador; los 5 datos muestran "—", igual que con error.
- Con `errorResumen` aparece "No se pudo cargar el resumen." con un botón "Reintentar" (48 dp), pero si ya había un `resumen` anterior se sigue dibujando.
- **`ChipTiempoReal` ("En tiempo real")** se muestra siempre que `resumen != null`, aunque `errorResumen` sea `true`. El ViewModel carga **una sola vez**, sin sondeo: el texto promete más de lo que hace.
- **"Cerrar sesión" actúa al primer toque, sin confirmación**, y se pinta con `CampusColors.Peligro` (morado, no rojo; 5.4).
- `ResumenAdmin` (verificado contra `ResumenAdmin.kt`, bache 3; ver 5.6): `totalFotos`, `totalLugares`, `alertasActivas`, `ultimoVideoNumero`, `ultimoVideoFecha` (milisegundos) y `fotosPendientes`, en ese orden de constructor. `numero()` usa `NumberFormat.getIntegerInstance()` (separador de miles según la región) y "—" si es nulo; `textoFecha` da "Hoy, HH:mm", "Ayer, HH:mm" o "d MMM, HH:mm".
- Los 5 datos van en **una sola fila** (`weight(1f)` cada uno) con etiquetas de 11 sp: en ~390 dp ya quedan muy angostos. ⚠ No se probó con la fuente grande del sistema.
- `LaunchedEffect(Unit)` captura `onSesionCerrada` y `onSinSesion` de la primera composición (sin `rememberUpdatedState`): no pasar lambdas que dependan de estado que cambie.
- Columna raíz con `systemBarsPadding()` + `verticalScroll`. "Versión X" sale de `packageManager.getPackageInfo(...)` dentro de `runCatching` ("—" si falla); "Panel de administración · Campus Navi" está fijo.
- Accesibilidad: cada tarjeta y cada dato se anuncian combinados (`mergeDescendants`); los títulos llevan `heading()`; Ajustes mide 56 dp.
- `onRecolector`, `onLugares`, `onEstadisticas` y `onAjustes` llevan hoy a rutas placeholder (5.8).

**`GaleriaScreen` y `GaleriaColores` (verificado, `ui/admin/imagenes/GaleriaScreen.kt`)**

| Pieza | Detalle |
|---|---|
| `GaleriaScreen` | `(onVolver, onAbrirImagen: (videoId, fotoId) -> Unit, viewModel = viewModel(factory = GaleriaViewModel.Factory(LocalContext.current.applicationContext)))`. Con selección activa, el botón Atrás **primero limpia la selección** (`BackHandler(enabled = seleccion.isNotEmpty())`). |
| `GaleriaContent` | `(state: GaleriaUiState, acciones: GaleriaAcciones, modifier)`. Público, sin ViewModel, con 2 `@Preview` privados. Cabecera, búsqueda, 4 filtros, selector de modo, cuadrícula de 2 columnas, barra de selección y paginador. |
| `GaleriaAcciones` | `data class` con 14 lambdas (`{}` por defecto): `onVolver`, `onReintentar`, `onBuscar`, `onLugar`, `onVideo`, `onEstado`, `onCalidad`, `onLimpiarFiltros`, `onModo`, `onPagina`, `onAbrirFoto(Foto)`, `onAlternarSeleccion(uid)`, `onEliminar`, `onReasignar(lugar)`. |
| `GaleriaColores` | `internal object` con la paleta de la maqueta; también la usa `VideosScreen`. Equivalencias en 5.4. |

**Piezas privadas de la Galería, candidatas a `ui/components/`** (regla 4: hoy no se pueden importar):

| Pieza | Firma | Qué hace / duplicación |
|---|---|---|
| `CampoTexto` | `(valor, onCambio, placeholder, descripcion, modifier, icono?, trailing?)` | `BasicTextField` de una línea, 56 dp, con ícono y acción final opcionales y `contentDescription` propio. |
| `FiltroChip<T>` | `(etiqueta, seleccionado: T?, opciones: List<T>, textoDe, onSeleccionar: (T?) -> Unit, textoTodos = "Todos")` | Chip de 48 dp con menú y opción "Todos". Genérico: sirve para los filtros pendientes de 7.13. |
| `SelectorModo` | `(modo: ModoVista, onModo)` | Dos segmentos Cuadrícula / Mapa. Atado a `ModoVista`. |
| `Paginador` + `paginasVisibles(actual, total)` | `(actual, total, onPagina)` | Anterior / siguiente y números con "…" (ej. 1 2 3 … 8); solo se dibuja si `total > 1`. `paginasVisibles` es lógica pura: se podría probar sin emulador si se hace `internal`. |
| `BarraSeleccion` + `BotonLote` | `(cantidad, onReasignar, onEliminar)` | "N seleccionadas" y los botones Reasignar / Eliminar. |
| `MensajeVacio` | `(texto, accion?, onAccion)` | **Duplicada** con `Mensaje` (VideosScreen) y con `EstadoVacio` de `ui/destino/componentes/ListaLugares.kt` (arriba; firma invertida: allí `mensaje` es opcional y `accion` obligatoria): unificar. |
| `BarraSuperior` | `(onVolver)` | Volver + título fijo "Galería de imágenes". Otra copia de la barra superior (ver `BarraSuperior` arriba); `VideosScreen` arma la suya en línea. |

Cuidados:
- La **`BarraSeleccion` se dibuja siempre** (en `bottomBar`), también con 0 seleccionadas ("0 seleccionadas", botones deshabilitados); `enModoSeleccion` solo decide qué hace el toque sobre una foto.
- **Selección:** pulsación larga sobre la tarjeta (acción "Seleccionar" para TalkBack); ya en modo selección, el toque alterna. El círculo de la esquina (48 dp de área táctil) está **oculto a la accesibilidad** (`clearAndSetSemantics`).
- **El diálogo de eliminar dice** "del dataset y del sistema de ubicación. Esto no se puede deshacer", pero hoy solo quita las fotos **de la memoria de esta pantalla** (ver `GaleriaViewModel`): el texto promete más de lo que hace.
- **Reasignar:** campo de texto libre con el botón deshabilitado si está en blanco (TODO: selector de lugares reales, 7.6). Cualquier texto crea un "lugar" nuevo.
- El modo `MAPA` solo muestra un mensaje provisional.
- Miniaturas con Coil (`AsyncImage(model = foto.urlMiniatura)`, `contentDescription = null`: la tarjeta ya se anuncia completa con nombre, video, lugar, estado, "alta calidad" y "seleccionada"). Si la URL falla solo queda el fondo `Placeholder`.
- `NumberFormat.getIntegerInstance()` para "N imágenes" (según la región).

**`VideosScreen` y `VideosViewModel` (verificado, `ui/admin/videos/VideosScreen.kt` y `VideosViewModel.kt`)**

| Pieza | Detalle |
|---|---|
| `VideosScreen` | `(onVolver, onAbrirVideo: (videoId) -> Unit, viewModel = viewModel(factory = VideosViewModel.Factory(LocalContext.current.applicationContext)))`. Recoge `viewModel.uiState` con `collectAsState()`. El estado es `VideosUiState(cargando = true, error: String? = null, videos = emptyList())` y el ViewModel tiene `reintentar()` (detalle abajo). |
| `VideosContent` | `(state: VideosUiState, onVolver, onAbrirVideo, onReintentar, modifier)`. Público, **sin `@Preview`**. Muestra cargando, error con "Reintentar", vacío ("Todavía no hay videos.") o la lista con "N videos". |
| Tarjeta de video | Nombre, y una línea con la fecha `dd/MM/yyyy` (los 10 primeros caracteres de `creadoEn`, invertidos), "N fotos" y la distancia (`Video.distanciaMetros`: "N m" o "X,XX km" según la región). Más un estado calculado: **Sin fotos**, **Con errores** (alguna `ERROR`), **Procesado** (todas `PROCESADA`) o **Pendiente de proceso**. El estado va en texto además del color. |

Cuidados:
- El orden es el del repositorio (por carpeta, 5.6); aún no hay orden ni búsqueda (`PLAN.md`).
- Usa `GaleriaColores` del paquete `ui.admin.imagenes`: dependencia cruzada hasta que se muevan a `CampusColors`.
- La fecha supone formato ISO (`2026-10-09…`); con otro formato sale mal.
- **`VideosViewModel` sí recoge `repositorio.cambios()`** (verificado): el ViewModel de la lista sigue vivo en la pila mientras se ve el detalle, y al volver tras renombrar o eliminar un video la lista se recarga sola.
- Accesibilidad: tarjeta con rol de botón y descripción completa ("Video X, fecha, N fotos, distancia, estado"); mínimo 72 dp de alto.

**`VideosViewModel` en detalle (verificado)**

- `VideosViewModel(repositorio: VideoRepository)`; su `Factory(appContext)` crea `AssetsVideoRepository(appContext)` (**espera el contexto de la aplicación**). Expone `uiState` y no tiene flujo de eventos. No usa `AppLog`.
- En el `init` recoge `repositorio.cambios()` y llama a `cargar()` por cada emisión: la primera emisión **es** la carga inicial (no hay otra) y las siguientes llegan cuando el detalle renombra o elimina. Cada una relee **todos** los manifests (5.6).
- `cargar()`: con éxito pone `cargando = false`, `error = null` y `videos`. Con cualquier `Exception` (salvo `CancellationException`, que relanza) pone `cargando = false` y `error = "No se pudieron cargar los videos"` (texto fijo, sin registrar) y **conserva** la lista anterior en `videos`.
- `reintentar()` vuelve a llamar a `cargar()` **sin** poner `cargando = true`: durante el reintento no hay indicador de carga y el error sigue en el estado hasta que termine. Como `cargar()` corre dentro del `collect`, las recargas por `cambios()` son secuenciales, pero un `reintentar()` simultáneo puede solaparse con una (gana la última en terminar).

**`VideoDetalleScreen` y `VideoBridge` (verificado, `ui/admin/videos/VideoDetalleScreen.kt`, `assets/video_detalle.html` y `assets/video_detalle.js`)**

| Pieza | Detalle |
|---|---|
| `VideoDetalleScreen` | `(videoId: String, onVolver, onAbrirImagen: (videoId, fotoId) -> Unit, modifier, vm = viewModel(key = "video-$videoId", factory = VideoDetalleViewModel.Factory(LocalContext.current.applicationContext, videoId)))`. La `key` da un ViewModel distinto por video. Dibuja `VideoDetalleContent` y, encima, `NoEncontrado` si `ui.noEncontrado`. |
| `VideoDetalleContent` | `(videoJson: String?, otrosJson: String, eventos: VideoDetalleEventos, modifier)`. Público, **sin `@Preview`**. Solo el `WebView` de `assets/video_detalle.html` (Leaflet + OpenStreetMap en línea). |
| `VideoDetalleEventos` | `interface` con 5 funciones: `abrirFoto(fotoId)`, `renombrar(nombre)`, `eliminarFoto(fotoId)`, `eliminarVideo()` y `salir()`. |
| `NoEncontrado` | Privado: "No se encontró este video." y un botón "Volver"; fondo fijo `#0A0E1A`. |

**Puente `VideoBridge`, web → app** (`@JavascriptInterface`; todo pasa al hilo principal): `listo()`, `abrirFoto(id)`, `renombrar(nombre)`, `eliminarFoto(id)`, `eliminarVideo()`, `salir()`. **App → web:** `setInsets(topDp, bottomDp)`, `cargarOtros(json)`, `cargarVideo(json)` (solo si `videoJson != null`; ambos como texto JSON entre comillas; el JS hace `JSON.parse`) y `window.onAtras()` (el JS cierra primero el diálogo o la foto seleccionada y al final llama a `salir()`).

Cuidados:
- **Kotlin no navega tras `eliminarVideo()`; lo hace el JS** (verificado): llama a `eliminarVideo`, muestra "Video eliminado" y **900 ms después** llama a `salir()` sin esperar resultado. Si el borrado fallara (futuro `RemoteVideoRepository`, ver el `try/catch` que falta en 5.5), el admin ya habría salido.
- **No usa `ui.cargando`:** mientras llega el JSON se ve el mapa vacío, sin indicador.
- **Sin internet:** si Leaflet (`unpkg.com`) no carga, `MapaBase.iniciar` (5.9) avisa en pantalla y **ya dejó definidos** `window.onAtras` (llama a `salir()`), `setInsets` y el botón Volver; `video_detalle.js` termina antes de llamar a `listo()`, así que Atrás y Volver funcionan pero la app no envía el video. Probado con jsdom, no en dispositivo. El registro va por `Log` con el tag `VideoDetalle`, no por `AppLog`.
- **Orden de `window.onAtras()`:** cierra el diálogo abierto → deselecciona la foto → `salir()` (aquí no hay confirmación de pendientes).
- **Confirmaciones (en el JS):** eliminar el video exige **escribir su nombre** (la `PLAN.md` anota como pendiente una "confirmación por pulsación larga"; hoy es esta). Eliminar una foto es **optimista**: la quita de la lista al instante y, si era la última, ofrece eliminar también el video. El `WebView` no muestra `window.prompt`, por eso hay un diálogo propio (`dialogo()`, `role="alertdialog"`).
- **Renombrar se valida en el JS, no en el ViewModel:** texto no vacío, distinto del actual y de máximo 40 caracteres; **no** se comprueba que el nombre no exista ya en otro video.
- **Formatos duplicados con Kotlin:** el JS calcula su propia distancia (haversine, también en `Video.distanciaMetros`) y la da como "1.25 km" (punto), mientras la lista de videos usa la región ("1,25 km"). La fecha se invierte de `2026-10-09` a `09/10/2026`, igual que la lista.
- ⚠ **Rumbo negativo sale como "undefined":** la orientación (`Math.round(rumbo / 45) % 8` sobre `CARDINALES`) falla con valores negativos, y el acimut de `OrientationProvider` sale en −180…180 (5.2). La recolección debe guardar `rumbo` normalizado a 0…360. Deducido leyendo el código, no probado.
- El encuadre del mapa (`fitBounds`) se hace **solo la primera vez** que llega el video; editar (renombrar, eliminar foto) no lo mueve. "Mostrar otros videos" dibuja puntos grises `#64748b` solo con lat/lng.
- Accesibilidad web: marcadores con `title`, tira de fotos con `aria-label` y `aria-pressed`, tarjeta como región `aria-live`. Las miniaturas que fallan se ocultan (`onerror`).
- `abrirFoto` → `onAbrirImagen` (placeholder: falta 7.12).
- **Infraestructura compartida:** la fábrica del `WebView` (tamaño, fondo `#0A0E1A`, ajustes, depuración, consola, errores, `setInsets`, `BackHandler`) vive ahora en `map/MapaWebView.kt` (`MapaWebView` y `PuenteWeb`, ver 5.9). Aquí solo quedan `VideoPuente` y los `LaunchedEffect` que empujan `cargarOtros` y `cargarVideo`.
- El botón "Volver" de `NoEncontrado` es un `Button` estándar de Material: su alto mínimo (40 dp) queda bajo los 48 dp.

**UbicacionManual (vista 7.3; ⚠ código entregado el 2026-10-11; compila con el proyecto (tanda 12), sin prueba completa en dispositivo (FE-2.3); `ui/admin/recoleccion/` y `assets/ubicacion_manual.*`)**

| Pieza | Detalle |
|---|---|
| `UbicacionManualViewModel` | `ViewModel(videos: VideoRepository, lugares: LugaresRepository)`; `Factory(appContext)` crea `AssetsVideoRepository` y `LugaresRepositoryStub` (**espera el contexto de la aplicación**). Estado en `ui: StateFlow<UbicacionManualUiState>`. Eventos por `Channel(BUFFERED)` + `receiveAsFlow()` (un solo colector; no se pierden). |
| `UbicacionManualUiState` | `lugares`, `punto: PuntoMapa?` (`null` hasta tocar el mapa), `rumbo` (0…360), `brujulaDisponible`, `usandoBrujula`, `cargandoUltima`, `ultimaPosicion: UltimaPosicion?`, `ultimaAplicada`, `nombreVideo`, `nombreSugerido`, `edicion: EdicionCoordenada?`, `centrarSolicitud: Int`, `confirmando`. Calculadas: `puedeConfirmar` (hay punto y no está confirmando), `latitudTexto`, `longitudTexto` (6 decimales, siempre con punto). |
| `UbicacionManualEvento` | Solo `Confirmado(inicio: InicioRecoleccion)`. **No navega.** |
| `UbicacionManualAcciones` | `data class` con 14 lambdas (`{}` por defecto): `onVolver`, `onAjustes`, `onPuntoCambiado(lat, lng)`, `onRumbo`, `onAlternarBrujula`, `onEditarCoordenada`, `onTextoEdicion`, `onAceptarEdicion`, `onCancelarEdicion`, `onUsarUltima`, `onNombre`, `onCancelar`, `onConfirmar`, `onCalibrar`. |
| `InicioRecoleccion` | `domain/model/InicioRecoleccion.kt`: `lat`, `lng`, `rumbo` (0…360), `nombreVideo` (recortado, nunca vacío) y `continuaVideoAnterior`. Es lo que debe recibir la vista 7.4. |
| Acciones del ViewModel | `alAbrir(brujulaDisponible)` (idempotente) · `alPausar()` (ON_STOP: apaga la brújula) · `alReanudar()` (ON_RESUME: reactiva «Confirmar») · `alMoverPunto(lat, lng)` · `alUsarUltimaPosicion()` · `alElegirRumbo(grados)` · `alAlternarBrujula()` · `alLeerBrujula(acimut)` · `alEditarCoordenada(campo)` · `alCambiarTextoEdicion` · `alAceptarEdicion()` · `alCancelarEdicion()` · `alCambiarNombre` · `alConfirmar()`. |
| Lógica pura (`internal`, sin Android) | `Rumbo` (`normalizar`, `diferencia`, `suavizar` —promedio exponencial **circular**—, `cardinal`, `nombreCardinal`), `parsearCoordenada(texto, limite)`, `siguienteNombre(videos)` y `calcularUltimaPosicion(videos)`. Se pueden probar sin emulador. |
| Constantes | `MAX_NOMBRE_VIDEO = 40`, `PREFIJO_VIDEO = "video_"`, `CampusMapa.CENTRO` (⚠ **aproximado**, EAFIT: solo es el encuadre inicial) y `CampusMapa.ZOOM_INICIAL = 17`. |

**Puente `UbicacionBridge`, web → app** (`@JavascriptInterface`, clase `UbicacionPuente : PuenteWeb`, `internal`; todo pasa al hilo principal): `listo()` (heredado), `puntoCambiado(lat, lng)` y `gesto(activo)`.
**App → web** (`mapa.js(...)`, solo tras `listo()`): `setCentro(lat, lng, zoom)`, `setPunto(lat, lng)`, `setRumbo(grados)`, `centrar()`, `zoomMas()`, `zoomMenos()` y `cargarLugares(texto)` (**texto** JSON entre comillas con `literalJs`; el JS hace `JSON.parse`). «Centrar» y +/− los dibuja Compose; el zoom de Leaflet está desactivado.

Comportamiento:
- **Un solo origen de verdad:** el punto vive en el ViewModel. El mapa avisa (`puntoCambiado`) al tocar y, mientras se arrastra, ~10 veces por segundo; el ViewModel lo reenvía con `setPunto`, que el JS **ignora mientras arrastra** (si no, el marcador temblaría).
- **Centrar el mapa:** solo cuando el punto cambia **desde fuera** del mapa (coordenadas editadas o «Usar mi última posición»): el ViewModel sube `centrarSolicitud` y la pantalla llama a `centrar()` (acerca a zoom ≥ 18).
- **Brújula:** `EscucharOrientacion` entrega acimut en −180…180; el ViewModel lo **normaliza**, lo suaviza y solo actualiza el estado si el cambio es ≥ 1,5°. Girar el dial a mano apaga la brújula. Es norte **magnético** (5.2).
- **Editar coordenadas:** si aún no hay punto, la otra coordenada se toma de `CampusMapa.CENTRO`. El diálogo usa `KeyboardType.Text` (no `Decimal`) porque algunos teclados numéricos no traen «−» y la longitud de Colombia es negativa.
- **Última posición:** el «último» video es el de mayor `creadoEn` (ISO-8601 ordena como texto; sin fecha, el último de la lista) y la última foto, la de mayor `capturadaEn`. Si `obtenerVideos()` falla, la fila queda deshabilitada y la vista sigue siendo usable.
- **Nombre autonumerado:** `video_(N+1)`, con N = mayor número entre los videos llamados `video3` / `video_3`…; si ninguno cumple el patrón, la cantidad de videos. Salta nombres ya usados.
- **Confirmar:** `confirmando` evita un doble toque; `alReanudar()` lo libera al volver a la pantalla (p. ej. desde 7.4).
- **Calibrar mi paso (7.3b):** `FilaCalibracion` (privada) va entre «Usar mi última posición» y el nombre del video. La pantalla lee `CalibracionPasoRepository(contexto).guardada()` con `remember` (`null` = valor genérico; se relee al volver porque `NavHost` recompone la ruta) y se la pasa al contenido; no está en el `UiState` ni en el ViewModel. Tocar la fila llama a `onCalibrar`, que la ruta conecta con `navigate("admin/calibracion")` (5.8).
- **Scroll vs. mapa:** el JS avisa `gesto(true/false)` en `touchstart` / `touchend` y la pantalla deshabilita `verticalScroll` mientras haya un dedo sobre el mapa. ⚠ Deducido, no probado: el aviso llega con un pequeño retraso.
- **Diseño adaptable:** la tarjeta de Orientación pone dial y botón lado a lado solo si `screenWidthDp >= 380` y `fontScale <= 1,15`; si no, los apila. (No usa `BoxWithConstraints`: no admite medidas intrínsecas dentro del `Row`.)
- **Reutiliza** `BotonIcono` y `Modifier.tarjeta` de `ui/destino/componentes/Comun.kt` (`internal`, mismo módulo). Por la regla 4 de 11, conviene moverlos a `ui/components/` cuando se toque.

Cuidados:
- ⚠ **Kotlin sin compilar.** Supuestos no verificados contra el código: los paquetes de `AssetsVideoRepository`, `LugaresRepositoryStub`, `VideoRepository` y `LugaresRepository` (`data.repository`), la firma de `BotonIcono` (`icono: ImageVector`), `MapaWebView`, `PuenteWeb.enHiloPrincipal`, `rememberMapaWeb` y `literalJs` (5.9), y `androidx.compose.ui.platform.LocalLifecycleOwner` (deprecado en versiones recientes de Compose).
- **No registra en `AppLog`** (su firma no está documentada aquí): un fallo al cargar videos o lugares no deja rastro. El mapa web usa `Log` con el tag `UbicacionMapa` (vía `MapaWebView`).
- **Sin internet** Leaflet (`unpkg.com`) no carga: la página muestra «No se pudo cargar el mapa…» y **no** llama a `listo()`, así que la app nunca le envía datos. Aun así se pueden escribir las coordenadas a mano y confirmar. Decisión abierta 13 (todo en línea).
- **Cancelar y atrás** hacen lo mismo (`onVolver`) y **no piden confirmación**: no hay nada guardado todavía.
- **Colores:** usa `CampusColors` salvo `ColorCancelar` (`#FF4D7D`, rosa del diseño; `CampusColors.Peligro` es morado, 5.4) y el fondo del mapa `#0A0E1A` (como los demás `WebView`).
- **Etiquetas «Latitud (X)» / «Longitud (Y)»** tal como en el diseño, aunque en rigor X es la longitud: valorar dejar solo «Latitud» y «Longitud».
- **Coordenadas con 6 decimales** (≈ 0,1 m); el diseño mostraba 4 (≈ 11 m), poco para anclar el dataset.
- Las etiquetas de lugares son **no interactivas**: tocar una coloca el punto donde está el dedo, no en las coordenadas del lugar (son aproximadas).
- Accesibilidad: el dial tiene descripción con grados y punto cardinal, acciones personalizadas (±15°, norte) y su leyenda visual oculta a TalkBack; «Usar mi última posición» es *live region* (anuncia «Posición tomada de …»); «Confirmar» deshabilitado dice «Falta marcar tu posición en el mapa». Botones de 48 dp o más (64 dp los de la barra inferior).
- **Previews:** 3 `@Preview` (con punto, sin punto y diálogo con error). El `WebView` no se previsualiza: se muestra un recuadro «Mapa (vista previa)» (`LocalInspectionMode`).
- **Prueba sin teléfono:** abrir `ubicacion_manual.html` en un navegador de escritorio activa un modo demo (3 lugares, punto y rumbo de ejemplo).

**`RecoleccionScreen` y `RecoleccionBridge` (vista 7.4; `ui/admin/recoleccion/` y `assets/recoleccion_mapa.*`)**

| Pieza | Detalle |
|---|---|
| `RecoleccionScreen` | `(onFinalizado: (ResumenRecoleccion) -> Unit, onDescartado: () -> Unit, onVolver: () -> Unit, onAjustes = {}, modifier, vm: RecoleccionViewModel = viewModel())`. **No navega**; la ruta decide (5.8). Es dueña de CameraX: crea el `ImageCapture` con `remember { crearImageCapture() }`, lo enlaza con `VistaCamara` (vista previa en la esquina del mapa), llama a `tomarFoto` en el evento `Capturar` y hace `liberarCamara(ctx)` y `keepScreenOn = false` al salir |
| Estados de la pantalla | `error` → texto «No se pudo iniciar la recolección» con «Volver»; `INICIANDO` → indicador de progreso; si no, columna con scroll: barra superior, aviso temporal, mapa (con «En vivo / Centrar», vista previa, +/− y leyenda), panel de re-anclaje (solo con el alfiler abierto), cuatro contadores, calidad, captura, Pausar / Reubicarme / Marcar punto, «Agregar alerta aquí», intervalo, «Finalizar video», alertas cercanas y panel de avisos |
| Diálogos y hojas | `AlertaFormSheet` cuando `ui.formularioAlerta != null` (siempre `esNueva = true`); selector de intervalo con `ModoCaptura.OPCIONES`; confirmación de finalizar (con 0 fotos avisa que el video se borrará) |
| `RecoleccionMapaContent` | `(control, lat, lng, rumbo: Float, fotosJson, trayectoriaJson, alertasJson, reanclaje: Pair<Double, Double>?, eventos, modifier)`. Solo dibuja el `WebView` (`MapaWebView` con `pasarInsets = false` y `manejarAtras = false`) y empuja el estado con `LaunchedEffect(mapa.listo, …)`. No conoce el ViewModel |
| `RecoleccionMapaControl` | `rememberRecoleccionMapaControl()`; `centrar()`, `zoomMas()`, `zoomMenos()` (botones que dibuja la pantalla, como en 7.3) |
| `RecoleccionMapaEventos` | `data class` con `onPuntoReanclaje(lat, lng)` (la pantalla lo conecta con `vm::alMoverReanclaje`) y `onSeguimiento(activo)` (resalta «En vivo» / «Centrar»); `{}` por defecto |
| `componentes/PanelesRecoleccion.kt` | Todo `internal`: `ChipEstadoVideo`, `TarjetaContador`, `TarjetaCalidad`, `TarjetaCaptura`, `BotonAccion`, `FilaAccion`, `BotonFinalizar`, `PanelReanclaje`, `FilaAlertasCercanas`, `PanelAvisos`, `formatearDistancia`, `formatearDuracion` y los colores `ColorFinalizar` (`#FF4D7D`) y `ColorAviso` (`#F59E0B`) |

**Puente `RecoleccionBridge`, web → app** (clase `RecoleccionPuente : PuenteWeb`, `internal`; todo pasa al hilo principal): `listo()` (heredado) · `puntoCambiado(lat, lng)` (solo con el re-anclaje abierto; arrastre ~10 veces por segundo o toque en el mapa) · `seguimientoCambiado(activo)`.
**App → web** (solo tras `listo()`): `setPosicion(lat, lng, rumbo)` · `cargarFotos(texto)` · `cargarTrayectoria(texto)` · `cargarAlertas(texto)` (los tres, **texto** JSON con `literalJs`; el JS hace `JSON.parse`) · `setReanclaje(lat, lng)` · `quitarReanclaje()` · `centrar()` · `zoomMas()` · `zoomMenos()`.
Formatos JSON: `fotosJson` = `[{id, lat, lng, rumbo|null}]`; `trayectoriaJson` = `[[lat, lng], …]`; `alertasJson` = los campos del editor (`id, lat, lng, mensaje, tipo, prioridad, radio, activa`).

Comportamiento y cuidados:
- **Atrás** (sistema y flecha): con error llama a `onVolver`; con el re-anclaje abierto lo cancela; si no, `alPedirFinalizar()`. `ON_STOP` → `alIrASegundoPlano()`.
- **Mapa:** sigue al admin (`panTo`) hasta que arrastra el mapa con el dedo; «Centrar» reactiva el seguimiento. La primera posición encuadra a zoom 19. Fotos y alertas se actualizan por `id` (el re-anclaje las desplaza). Con el alfiler abierto **no** se sigue al admin y se **ignoran los ecos** de `setReanclaje` mientras se arrastra (patrón de 7.3). Mensajes de alerta con `textContent`.
- **Usa `MapaBase.iniciar`** (a diferencia de 7.3). Como no tiene `#top`, `#dock` ni `#btn-back`, la página los incluye **ocultos** por si `mapa_base.js` no tolera que falten; si ya lo tolera, se pueden borrar. No define `setInsets` ni `onAtras` propio (los maneja la pantalla Compose).
- **Sin internet:** Leaflet (`unpkg.com`) no carga, `MapaBase.iniciar` avisa en pantalla y el mapa nunca llama a `listo()`; la grabación sigue funcionando sin mapa. Teselas de OSM, no satélite como el diseño (decisión 1 y 13).
- Las alertas se dibujan **todas igual** (ámbar si están activas, gris si no): no distinguen `tipo` ni `prioridad`. El CSS de la página duplica estilos de las otras páginas de mapa (candidato `mapa_base.css`). El centro inicial del JS es **aproximado** (EAFIT) y solo se ve antes del primer fix.
- **Prueba sin teléfono:** abrir `recoleccion_mapa.html` en un navegador de escritorio activa un modo demo (alguien camina en círculo, deja fotos y se ve una alerta).
- **Cámara:** la ruta la exige (5.8); la pantalla comprueba el permiso para activar `VistaCamara`. `VistaCamara` sigue sin manejar errores de `bindToLifecycle` (cuidado de 5.5).
- «Marcar punto de interés» está **deshabilitado**. El aviso temporal (`ui.aviso`) es una tarjeta propia que se descarta al tocarla; no usa `BannerEstado`. `ColorFinalizar` y `ColorAviso` son propios porque `CampusColors.Peligro` es morado (5.4).
- Reutiliza `BotonIcono` y `Modifier.tarjeta` de `ui/destino/componentes/Comun.kt` (`internal`): regla 4 de 11, conviene moverlos a `ui/components/`.
- Con fuente grande, los cuatro contadores en fila pueden apretarse. Sin brújula «N» ni giro del mapa.

**`CalibracionScreen` y `CalibracionBridge` (vista 7.3b; `ui/admin/calibracion/` y `assets/calibracion_mapa.*`; entregado el 2026-10-12, compila y se abre en dispositivo, ⚠ pasada completa sin probar)**

| Pieza | Detalle |
|---|---|
| `CalibracionViewModel(app)` | `AndroidViewModel` **sin `Factory`**. Crea su **propio** `PdrTracker` y un `CalibracionPasoRepository`. Salida: `ui: StateFlow<CalibracionUiState>`. Fases `FaseCalibracion`: `PUNTOS → LISTO → CAMINANDO → RESULTADO → GUARDADA` |
| Entradas del ViewModel | `alTocarMapa(lat, lng)` (1.º toque = A, 2.º = B; con ambos puestos se ignora: se arrastran; solo en `PUNTOS`/`LISTO`) · `alMoverPunto(ExtremoTramo, lat, lng)` · `alLimpiarPuntos()` · `alIniciar()` (fija la posición en A, `tracker.iniciar()`, anota `pasosInicio`, reloj de 500 ms) · `alFinalizar()` (lee `pasos − pasosInicio` **antes** de `detener()`, calcula con `CalibracionPaso.calcular` → `RESULTADO`) · `alCancelarMedicion()` · `alRepetir()` · `alGuardar()` (solo con `Valido` en `RESULTADO`) · `alRestablecer()` (vuelve a 0,72 m; no actúa en `CAMINANDO`) · `alIrASegundoPlano()` (ON_STOP: detiene el tracker y, si `CAMINANDO`, cancela con aviso) · `descartarAviso()` |
| `CalibracionUiState` | `fase`, `puntoA` / `puntoB` (`PuntoTramo(lat, lng)?`), `distanciaM`, `pasos`, `segundos`, `resultado`, `longitudActualM`, `calibrada`, `fuentePasos`, `aviso` (`AvisoCalibracion`, p. ej. `VALOR_RESTABLECIDO`, `CANCELADA_SEGUNDO_PLANO`). Calculadas: `puedeIniciar`, `hayPuntos`, `mapaBloqueado` (fuera de `PUNTOS`/`LISTO`), `pasosPorAcelerometro`. `ExtremoTramo`: `A`, `B` |
| `CalibracionScreen` | `(onVolver, modifier, vm: CalibracionViewModel = viewModel())`. **No navega**; la ruta pide `Permisos.ACTIVIDAD` antes de mostrarla (5.8). ON_STOP → `alIrASegundoPlano()`; Atrás durante la medición la cancela, si no → `onVolver`; `keepScreenOn` solo mientras `CAMINANDO` |
| `CalibracionContent` / `CalibracionAcciones` | Contenido sin lógica y `data class` de 11 lambdas (`{}` por defecto); 2 `@Preview` |
| `CalibracionMapaContent` | `(puntoA, puntoB, bloqueado, eventos: CalibracionMapaEventos, modifier)`. Solo dibuja el `WebView` (`MapaWebView` con `pasarInsets = false` y `manejarAtras = false`) y empuja el estado con `LaunchedEffect(mapa.listo, …)`. No conoce el ViewModel |

**Puente `CalibracionBridge`, web → app** (clase `CalibracionPuente : PuenteWeb`, `internal`; todo pasa al hilo principal): `listo()` (heredado) · `toque(lat, lng)` · `puntoMovido(extremo "A"|"B", lat, lng)` (solo al soltar el pin).
**App → web** (solo tras `listo()`): `setCentro(lat, lng, zoom)` (solo si aún no hay A) · `setPuntos(texto)` con `{"a": {lat, lng} | null, "b": …}` (**texto** JSON con `literalJs`) · `setBloqueado(bool)`.

Comportamiento y cuidados:
- El estado vive en el ViewModel; el JS **ignora `setPuntos` mientras se arrastra un pin** (patrón de 7.3) y encuadra el tramo al tener A y B por primera vez. Abrir `calibracion_mapa.html` en un navegador de escritorio activa un **modo demo**.
- **Usa `MapaBase.iniciar` y `MapaBase.crearMapa`** (5.9). ⚠ **No** `base.crearMapa`: ese error dejaba el mapa negro y sin aviso (Logcat: `base.crearMapa is not a function`). La página lleva ocultos `#top`, `#dock` y `#btn-back`.
- **Sin scroll:** el mapa ocupa el espacio sobrante (mín. 180 dp); con fuente muy grande en un teléfono pequeño el mapa se encoge y el resto puede recortarse. Usa el zoom nativo de Leaflet (abajo a la izquierda), no los botones +/− de Compose; el centro inicial es **aproximado** (EAFIT), no `CampusMapa.CENTRO`.
- **Sin internet** Leaflet (`unpkg.com`) no carga, el mapa nunca llama a `listo()` y **no se pueden marcar A y B**: la calibración es inutilizable sin mapa (decisión 13).
- El aviso de acelerómetro solo aparece tras el primer «Inicio» (la fuente de pasos se conoce al llamar a `iniciar()`).
- Una sola medición, sin promedio ni historial; se mide en línea recta A→B, sin compararla con la trayectoria del PDR.
- **Colores:** `CampusColors`, salvo `#FF4D7D` (Fin) y `#F59E0B` (avisos) propios, como en 7.4, porque `CampusColors.Peligro` es morado (5.4).
- Reutiliza `BotonIcono` y `Modifier.tarjeta` de `ui/destino/componentes/Comun.kt` (`internal`): regla 4 de 11, conviene moverlos a `ui/components/`. Los textos están fijos en español dentro del composable (sin recursos de strings).

**Componentes de `ui/ubicacion/componentes/` (verificados; propios de Escaneo, todos `internal`)**

| Componente | Firma | Qué hace / reutilización |
|---|---|---|
| `VistaCamara` | `(imageCapture: ImageCapture, activo: Boolean, modifier = Modifier)` | Vista previa de la cámara trasera (`PreviewView`, `FILL_CENTER`) en una caja negra de esquinas redondeadas con la etiqueta "Vista de cámara". Con `activo = true` hace `unbindAll()` y enlaza **vista previa + `imageCapture`** al `LocalLifecycleOwner`. Con `activo = false` solo muestra la caja negra. **Es la única que enlaza `crearImageCapture()`**: cualquier vista que use `tomarFoto` la necesita (o hacer ese enlace igual). Reutilizable tal cual por la recolección (7.4). |
| `AnilloProgreso` | `(estado: EscaneoUiState)` | Anillo de 0° a 360° (270×240 dp) con arco morado = grados girados (`estado.progreso`), una marca por foto cada `GRADOS_POR_FOTO` (72°, con check si ya se tomó) y, al centro, "Foto X de N" o "Analizando…" (`Fase.ANALIZANDO`). **No es reutilizable hoy**: depende de `EscaneoUiState`, `EscaneoConfig` y `EscaneoColores`. El 0° del anillo es **el inicio del giro**, no el norte. |
| `BarraSuperior` | `(onAtras, onAjustes)` | Volver + título fijo "Ubicarme" / "Captura de entorno" + Ajustes. Duplicada de la de Destino (ver arriba). |
| `InstruccionGrande` | `(texto: String, esError: Boolean)` | Ícono de 52 dp + texto de 28 sp. Con `esError` usa advertencia en rojo; si no, ícono de refrescar en morado. El ícono no se anuncia (el texto ya dice lo mismo). Genérica. |
| `RecordatoriosFijos` | `()` | Dos avisos fijos: "Más despacio" y "Mantén el celular vertical". Textos fijos. |
| `IndicadorInclinacion` | `(inclinacionOk: Boolean)` | Tarjeta verde ("Tu teléfono está en posición correcta") o roja ("Endereza el teléfono: mantenlo vertical"). El color no es la única señal: cambian ícono y texto. |
| `BotonesAccion` | `(onCancelar, onRepetir)` | "Cancelar" (relleno) y "Repetir" (contorno), de 60 dp de alto. Textos fijos. |

Cuidados de estos componentes:
- **Paleta propia:** usan `EscaneoColores` (`Fondo`, `Panel`, `Pista`, `Morado`, `MoradoBoton`, `MoradoClaro`, `Rojo`, `Verde`, `TextoSecundario`) y un gris fijo `#1F2937` para divisores y bordes, no `CampusColors`. Confirma la nota de 5.4.
- **`VistaCamara` no maneja errores:** si `bindToLifecycle` lanza excepción (sin cámara trasera, cámara en uso) ocurre dentro de un listener del hilo principal y **cierra la app**. Tampoco desenlaza al pasar `activo` a `false`: la cámara sigue enlazada hasta que se cierre el ciclo de vida o se llame a `liberarCamara(ctx)`.
- **`VistaCamara` enlaza una sola vez:** el bloque `factory` solo corre al entrar en composición; si se le pasa **otro** `ImageCapture` después, no se vuelve a enlazar. Crear el `ImageCapture` una vez (en el ViewModel o con `remember`).
- No pide el permiso de cámara: espera que la ruta ya lo haya resuelto (5.3).
- Los botones de icono de `BarraSuperior` son `IconButton` estándar (48 dp), por debajo de los 56 dp que piden las vistas públicas (5.1).
- `AnilloProgreso` anuncia siempre "Foto X de N", incluso durante "Analizando…"; y `IndicadorInclinacion` no se marca como *live region*, así que TalkBack no anuncia el cambio de estado por sí solo.

**Inicio (verificado: `ui/inicio/InicioViewModel.kt` e `InicioScreen.kt`)**

| Pieza | Detalle |
|---|---|
| `InicioViewModel(app: Application)` | `AndroidViewModel`, sin `Factory`. Crea su propio `VoiceController` y lo libera en `onCleared`. Expone `estado: StateFlow<InicioUiState>` y `eventos: SharedFlow<InicioEvento>` (`extraBufferCapacity = 1`, `tryEmit`, sin `replay`). |
| `InicioUiState` / `InicioEvento` | `InicioUiState(escuchando = false, backendEnLinea = false)`. `InicioEvento`: `Ubicarme` e `IrALugar` (sin datos). |
| Acciones | `alAbrir()` · `alPresionarOrbe()` · `ubicarme()` · `irALugar()` · `alPausar()` · `explicarPermisos(alTerminar: () -> Unit)`. `BIENVENIDA` es una constante **pública** (`InicioViewModel.BIENVENIDA`). |
| `BackendHealth` | Desde FE-1.1: `interface` en `data/repository/BackendHealth.kt` (`suspend estaEnLinea(): Boolean`, no lanza) e implementación real `RemoteBackendHealth(ClienteApi.api)` (`data/remote/`, §5.10), fijada en `private val backend`. `BackendHealthStub` ya no existe. |
| `InicioScreen` | `(onUbicarme, onIrALugar, onAccesoAdministrador, viewModel = viewModel())`. Recoge `estado` con `collectAsStateWithLifecycle()`. |
| `InicioContent` | `(escuchando, backendEnLinea, permisosFaltantes: List<String>, onOrbe, onUbicarme, onIrALugar, onAccesoAdministrador, onReintentarPermisos, onIrAAjustes)`. Público, **sin `@Preview` ni `modifier`**. |

Flujo:
- Al entrar en composición: con los tres permisos concedidos llama a `alAbrir()` (dice `BIENVENIDA` y al terminar escucha). Si falta alguno llama a `explicarPermisos` (dice para qué se pide cada cosa) y al terminar lanza el diálogo del sistema; el resultado, **sea cual sea**, vuelve a llamar a `alAbrir()`.
- `escuchar()` → `ComandoParser.parse`: `UBICARME` / `IR_A_LUGAR` navegan; `NINGUNO` o fallo → `repetirOpciones()`: dice «No te entendí. …» y vuelve a escuchar. Al **3.er** fallo (`MAX_INTENTOS = 3`) dice «Presiona el botón central cuando quieras hablar.» y deja de escuchar. `intentos` solo vuelve a 0 en `alAbrir` y en `alPresionarOrbe`.
- `navegar()` (salida común): `voz.stopAll()`, `escuchando = false` y emite el evento.
- ON_STOP → `alPausar()` (`stopAll` + `escuchando = false`); ON_RESUME solo refresca la lista de permisos y **no** reanuda la escucha.
- Sondeo de conexión: en el `init`, bucle infinito con `runCatching { estaEnLinea() }` (una excepción cuenta como «sin conexión») y `delay(15_000)` entre intentos. Corre mientras el ViewModel viva, también con la pantalla en segundo plano (una petición cada ~15 s, cada una con su línea `Api` en `AppLog`). Cada intento dura como mucho 5 s (`RemoteBackendHealth.LIMITE_MS`), así que el periodo real es de 15 a 20 s; en modo avión falla al instante (sin DNS). `backendEnLinea` arranca en `false`: hay un instante de «Sin conexión» antes del primer resultado. Textos de la barra: «Conectado» / «Sin conexión» (TalkBack: «Conectado. Backend en línea.» / «Sin conexión. Backend no disponible.»).

Pantalla:
- Orbe de 252 dp (rol botón) con pulso mientras `escuchando`; título de 28 sp que pasa a «Te escucho…»; indicador de señal decorativo; texto fijo «Activa el lector de pantalla»; barra inferior con el punto verde/rojo del backend y «Acceso administrador» (alto ≈ 48 dp).
- Accesibilidad del orbe: «Botón principal. Toca dos veces para iniciar el escaneo de 360 grados y saber dónde estás.» y una acción personalizada de TalkBack «Ir a un lugar». La descripción **no cambia** al escuchar y «Te escucho…» no es *live region*.
- `BannerPermisos` lista los faltantes con nombre legible («Cámara», «Micrófono», «Sensores de actividad») y dos acciones: «Permitir» (relanza el diálogo) y «Ajustes» (`ACTION_APPLICATION_DETAILS_SETTINGS`). La lista se refresca tras cada solicitud y al volver de Ajustes.

Cuidados:
- ⚠ **El orbe ya no escucha, navega.** `alPresionarOrbe()` va directo a Ubicarme (un comentario del código dice que antes hacía `stopAll(); escuchar()`). Consecuencias: (1) la spec 6.1 pide dos botones grandes («Ubicarme» e «Ir a un lugar»), un botón de micrófono y un botón de Ajustes; el código tiene **un solo orbe** y ninguno de los otros; (2) por toque solo se llega a «Ir a un lugar» con la acción de TalkBack; sin TalkBack hay que decir «dos»; (3) el texto en pantalla («Presiona para ubicarte o para llegar a un lugar») y el mensaje hablado tras 3 fallos («Presiona el botón central…») ya no corresponden a lo que hace el toque. Hay que decidir el diseño (decisión abierta); `ubicarme()` e `irALugar()` ya existen para dos botones.
- ⚠ **Doble solicitud de permisos (verificado en `MainActivity.kt`).** La ruta `inicio` muestra `PedirPermisos` **antes** de `InicioScreen` y descarta el resultado (5.8). Cuando por fin se compone la pantalla, o ya están todos (entra directo en `alAbrir()` y **la explicación hablada nunca suena**) o alguno quedó negado (suena la explicación y el diálogo se repite). Es la «explicación previa» que 6.1 y la `PLAN.md` dan por pendiente: el código existe, pero nunca queda antes del primer diálogo. Para arreglarlo, la ruta no debería pedir nada y dejar que `InicioScreen` lo haga.
- Sin micrófono, `listen` responde `onFail` al instante (5.2): la pantalla dice «No te entendí…» tres veces y luego «Presiona el botón central…», sin explicar que falta el micrófono.
- ⚠ Sin token (5.2): un `alTerminar` encolado puede llamar a `escuchar()` justo después de `alPausar()` o `navegar()`.
- ⚠ `alAbrir()` se llama cada vez que la pantalla entra en composición (`LaunchedEffect(Unit)`), p. ej. al volver de Ubicarme: es de esperar que vuelva a leer la bienvenida (deducido, no probado).
- «Permitir» y «Ajustes» son `Text` con `clickable`: alto aproximado de 40 dp (16 sp + 10 dp arriba y abajo), **bajo los 48 dp** de 5.1.
- `BannerPermisos` duplica a `BannerEstado` (con colores propios) y no es *live region*: ⚠ TalkBack no lo anuncia al aparecer y puede leer el mensaje dos veces (descripción del contenedor + hijos).

**`SeleccionDestinoViewModel` (verificado, `ui/destino/SeleccionDestinoViewModel.kt`; la pantalla está en el bloque siguiente)**

| Pieza | Detalle |
|---|---|
| Construcción | `SeleccionDestinoViewModel(app: Application)`, sin `Factory`. Crea directamente `LugaresRepositoryStub()` y su propio `VoiceController(app)` (se libera en `onCleared`). |
| Salidas | `estado: StateFlow<DestinoUiState>` y `eventos: SharedFlow<DestinoEvento>` (`extraBufferCapacity = 1`, `tryEmit`: sin colector en ese instante el evento se pierde). Único evento: `DestinoEvento.Confirmado(lugar: LugarDestino)`. **No navega.** |
| `DestinoUiState` (`SeleccionDestinoState.kt`) | `cargando`, `error: ErrorDestino?` (`SIN_CONEXION`, `DESCONOCIDO`), `sinMicrofono`, `escuchando`, `textoReconocido: String?`, `candidato: LugarDestino?`, `opciones: List<LugarDestino>`, `busqueda`, `categoria: CategoriaLugar?`, `orden: OrdenLugares` (`CERCANIA`, `NOMBRE`) y `lugares` (ya filtrada y ordenada). Valores por defecto (verificado): `cargando = true`, `error = null`, `sinMicrofono = false`, `escuchando = false`, `textoReconocido = null`, `candidato = null`, `opciones = emptyList()`, `busqueda = ""`, `categoria = null`, `orden = CERCANIA`, `lugares = emptyList()`. **Archivo completo verificado (bache 1):** `ErrorDestino`, `OrdenLugares` y `DestinoEvento` van en el mismo archivo. `OrdenLugares(etiqueta)` lleva el texto de cada orden: `CERCANIA` = «Ordenado por cercanía» y `NOMBRE` = «Ordenado por nombre». `DestinoEvento` es una `sealed interface` con **un solo caso**, `Confirmado(lugar: LugarDestino)`: añadir otro evento obliga a ampliar el `when` de la pantalla. Convención del archivo: la UI solo **lee** `DestinoUiState` y el ViewModel es el único que lo escribe. `DestinoUiState` es una `data class` simple, sin `Parcelable` ni guardado propio. |
| Acciones | `alAbrir(microfonoDisponible)` · `reintentarCarga()` · `alPresionarMicrofono()` · `alElegirLugar(lugar)` · `alResponderSi()` · `alResponderNo()` · `descartarTexto()` · `alCambiarBusqueda(texto)` · `alElegirCategoria(categoria?)` · `alCambiarOrden()` · `limpiarFiltros()` · `alPausar()` · `alSalir()`. |
| Constantes y logs | `PREGUNTA` = «¿A dónde quieres ir? Di el nombre del lugar.» (pública) y `MAX_INTENTOS = 3` (privada). Tag `DestinoVM`: cantidad de lugares, «Voz: N coincidencia(s)» (**no** registra lo que se dijo), `id` del destino propuesto y confirmado, y el error de carga. |

Flujo:
- `alAbrir` es **idempotente** (bandera `iniciado`): solo cuenta la primera llamada; el micrófono se decide ahí (`conVoz`) y no se reevalúa si la persona lo concede después.
- Carga → (si hay voz) pregunta → `BuscarLugares.mejores` (reglas y ⚠ en 5.7): 0 → «No encontré ese lugar. Intenta de nuevo.»; 1 → `proponer`; 2–3 → «Encontré N lugares: A, B o C. Di cuál quieres.» y vuelve a escuchar.
- `proponer(lugar)` muestra la tarjeta (`candidato`), pregunta «¿Quieres ir a X? Di sí o no.» y, si hay voz, escucha: `SI` → `confirmar`; `NO` → `rechazar`; `NINGUNA` → repite (a los 3 fallos: «Usa los botones Sí o No cuando quieras.» y deja de escuchar).
- `rechazar` limpia texto, candidato y opciones, y pregunta «De acuerdo. ¿A qué lugar quieres ir?». `confirmar` hace `detenerVoz()`, registra y emite `Confirmado`.
- Sin micrófono (`conVoz = false`): no pregunta ni escucha, pero sí habla las confirmaciones al tocar un lugar; el micrófono de la pantalla solo dice «El micrófono no está disponible. Elige un lugar de la lista.»
- Lista: `refiltrar()` = `BuscarLugares.filtrar` + categoría + orden. `CERCANIA` ordena por `distanciaMetros` con los `null` al final (con el stub todos son `null`: queda el orden original). `NOMBRE` usa el orden normal de `String`, que distingue mayúsculas y tildes («Árbol» quedaría después de «Zeta»).

Cuidados:
- `intentosDestino` solo vuelve a 0 en `alPresionarMicrofono` (al empezar a escuchar) y en `rechazar`; **no** tras un reconocimiento correcto ni al elegir de la lista. `intentosConfirmacion` solo se reinicia en `proponer`: tras 3 fallos, un toque en el micrófono escucha **una sola vez** y, si falla, repite «Usa los botones…».
- `alCambiarBusqueda` **corta la voz** en cada tecla; cambiar categoría, orden o limpiar filtros **no**.
- `alElegirCategoria(categoria)` solo asigna. El comentario dice «si ya estaba activo, lo quita», pero **el ViewModel no hace ese conmutador**: quien llama debe pasar `null` al tocar el chip activo. La pantalla lo pasa tal cual (`onCategoria = viewModel::alElegirCategoria`), y el conmutador está en `FilaCategorias`: tocar un chip destacado activo pasa `null` (verificado, bache 2).
- Un error de carga que no es `IOException` (`DESCONOCIDO`) también dice «Revisa tu conexión y toca reintentar».
- ⚠ **Estado viejo al volver** (verificado en el código de la ruta, el ViewModel y la pantalla; no probado en dispositivo): `candidato` no se limpia al confirmar y `iniciado` sigue en `true`. Como la ruta `destino` navega a `ubicarme` **sin quitarse de la pila** (5.8), al terminar el escaneo `popBackStack()` vuelve a Destino con el mismo ViewModel: la pantalla vuelve a llamar `alAbrir`, que se ignora, así que no repite la pregunta, la tarjeta de confirmación sigue visible y otro «Sí» emitiría `Confirmado` de nuevo. Arreglo mínimo: poner `candidato = null` (y `opciones`) al confirmar, o reiniciar `iniciado` en `alPausar`.
- `onCleared` solo sube el `token` y libera la voz (no llama a `detenerVoz()`).

**`SeleccionDestinoScreen` (verificado, `ui/destino/SeleccionDestinoScreen.kt`)**

| Pieza | Detalle |
|---|---|
| `SeleccionDestinoScreen` | `(onVolver, onDestinoConfirmado: (LugarDestino) -> Unit, onAjustes = {}, viewModel = viewModel())`. Recoge `estado` con `collectAsStateWithLifecycle()`. Solo conecta: micrófono, eventos, ciclo de vida y «atrás». |
| `SeleccionDestinoContent` | `(estado: DestinoUiState, acciones: DestinoAcciones)`. Público, con un `@Preview` privado (`PreviewSeleccionDestino`: escuchando, texto «biblioteca», candidato y 4 lugares de `LUGARES_DE_PRUEBA`). |
| `DestinoAcciones` | `class` pública (no `data class`, **sin valores por defecto**) con 12 lambdas: `onVolver`, `onAjustes`, `onMicrofono`, `onDescartarTexto`, `onSi`, `onNo`, `onElegirLugar`, `onCategoria`, `onBusqueda`, `onCambiarOrden`, `onLimpiarFiltros`, `onReintentar`. |

Conexión:
- **Micrófono:** `remember { checkSelfPermission(RECORD_AUDIO) == GRANTED }` y `viewModel.alAbrir(microfonoOk)` en `LaunchedEffect(Unit)`. No pide el permiso (lo pide la ruta de Inicio).
- **Eventos:** `Confirmado(lugar)` → `onDestinoConfirmado(lugar)`.
- **Salir:** ON_STOP → `alPausar()`. El «atrás» del sistema (`BackHandler`), la flecha de `BarraSuperior` y `BotonVolver` pasan todos por `salir = { alSalir(); onVolver() }`.
- `acciones` se crea con `remember(viewModel)`: captura `salir` y `onAjustes` de la **primera** composición; si el padre cambia esas lambdas, no se actualizan.

Orden del contenido (un solo `LazyColumn`): `EncabezadoPregunta` → `ZonaMicrofono` → si `sinMicrofono`, `BannerEstado` de advertencia «Sin micrófono» → `TarjetaTextoReconocido` (si hay texto) → `TarjetaConfirmacion` (si hay `candidato`) → `TarjetaOpciones` (solo si **no** hay candidato y sí opciones) → `FilaCategorias` → `CampoBusqueda` → `EncabezadoLista` → **una** de: cargando (`CircularProgressIndicator`), error, vacío («No hay lugares con estos filtros» + «Limpiar filtros») o la lista de `FilaLugar`. `BotonVolver` queda fijo abajo, fuera de la lista. Usa `statusBarsPadding`, `navigationBarsPadding`, `imePadding` y `CampusColors.Fondo`.

Cuidados:
- **El error es siempre «Sin conexión / No se pudo cargar la lista de lugares.»** con «Reintentar», aunque el `ErrorDestino` sea `DESCONOCIDO`.
- La lista usa `key = { it.id }`: los `id` de `LugarDestino` deben ser **únicos**; con repetidos Compose lanza una excepción.
- Las tarjetas de texto, confirmación y opciones viajan **dentro** del mismo `LazyColumn` que la lista: si quien ve se desplaza hacia abajo, la confirmación sale de pantalla (a quien usa voz no le afecta).
- Las firmas de 5.5 de `ZonaMicrofono`, `TarjetaTextoReconocido`, `TarjetaConfirmacion`, `BarraSuperior`, `FilaCategorias`, `CampoBusqueda`, `EncabezadoLista`, `FilaLugar`, `EstadoVacio` y `BotonVolver` **coinciden** con cómo las llama esta pantalla y con los propios archivos de `componentes/` (bache 2); lo mismo vale para `EncabezadoPregunta` y `TarjetaOpciones`.

**Login (verificado, `ui/auth/LoginViewModel.kt` y `LoginScreen.kt`)**

| Pieza | Detalle |
|---|---|
| `LoginViewModel` | `ViewModel(auth: AuthRepository, session: SessionManager)`. Su `Factory(context)` convierte a `applicationContext` por sí sola y, desde FE-1.2, **fija** `RemoteAuthRepository()` (backend real, `ClienteApi.api`; antes `AuthRepositoryStub()`). Expone `state: StateFlow<LoginUiState>` y `eventos` (`Channel(BUFFERED)` + `receiveAsFlow()`: un solo colector; sin colector el evento espera, no se pierde). |
| `LoginUiState` | `identificador`, `password`, `mostrarPassword = false`, `cargando = false`, `error: LoginError? = null`. Calculada `puedeEnviar` = identificador no vacío (`isNotBlank`) **y** contraseña no vacía (sin recortar) **y** `!cargando`. |
| `LoginError` | `CredencialesInvalidas`, `SinConexion`, `SinPermisos`, `Desconocido`. El texto que ve la persona lo decide la pantalla (tabla más abajo). |
| `LoginEvento` | Solo `IrAlPanel`. |
| Acciones | `onIdentificadorChange(valor)` y `onPasswordChange(valor)` (ambas borran el error) · `onTogglePassword()` · `iniciarSesion()`. |

`iniciarSesion()`:
1. Si `!puedeEnviar` no hace nada (un doble toque se ignora mientras `cargando`).
2. Llama a `auth.login(identificador.trim(), password)`.
3. `ADMIN` → `session.guardar(sesion)`, vacía `password` y emite `IrAlPanel`.
4. Cualquier otro rol → `session.cerrarSesion()` (**borra también una sesión que ya existiera**), vacía `password` y `error = SinPermisos`.
5. `CredencialesInvalidasException` → `CredencialesInvalidas`; `IOException` → `SinConexion`; cualquier otra `Exception` → `Desconocido`.

Con el backend real (FE-1.2, `RemoteAuthRepository`, 5.6 y §5.10): `401 CREDENCIALES_INVALIDAS` → «Credenciales
inválidas»; sin red, *timeout* o `5xx` de API Gateway (`api` sin tareas: `500 {"message"}`) → «Sin conexión»; el resto
(`429` del *throttling* de API Gateway, 2 req/s en el login; `422`; `503 SERVICIO_OCUPADO` con `Retry-After: 5`;
`503 BASE_NO_DISPONIBLE`; un `200` sin `token` o `expira_en` o con un rol desconocido) → «Algo salió mal», cuyo texto
ya pide intentarlo de nuevo. **Decisión de FE-1.2:** `503 SERVICIO_OCUPADO` no tiene mensaje propio (pasa pocas veces y
reintentar a mano basta); si se ve a menudo, se le da uno. Cada intento deja la línea `Api` de `RequestIdInterceptor`
(`POST /v1/auth/login -> <código> (<n> ms) rid=<uuid>`) para diagnosticar un «Algo salió mal».

Cuidados:
- En el `init`, si `session.esAdmin()` ya es `true` emite `IrAlPanel` (entra directo al panel). Corre en el hilo principal **sin `try/catch`** (ver 5.3). Como `MyApp` borra la sesión en cada arranque en frío, el atajo solo ocurre con el proceso vivo (p. ej. volver al modo público desde el panel y pulsar «Acceso administrador») y con la sesión sin vencer (una vencida da `false`, FE-1.2).
- `catch (e: Exception)` también atrapa `CancellationException` (no la relanza) y los fallos de `session.guardar`: salen como `Desconocido`. No hay `AppLog`: ningún error de login deja rastro (bien para contraseña y token, pero `Desconocido` no se puede diagnosticar).
- Tras un login correcto solo se vacía `password`; `identificador` queda en el estado.

**`LoginScreen` (verificado, `ui/auth/LoginScreen.kt`)**

| Pieza | Detalle |
|---|---|
| `LoginScreen` | `(onLoginExitoso, onVolver, viewModel = viewModel(factory = LoginViewModel.Factory(LocalContext.current.applicationContext)))`. Recoge `state` con `collectAsStateWithLifecycle()` y convierte `LoginEvento.IrAlPanel` en `onLoginExitoso()`. No tiene `BackHandler`: el «atrás» del sistema lo resuelve el `NavHost`. |
| `LoginContent` | `(state: LoginUiState, onIdentificadorChange, onPasswordChange, onTogglePassword, onIniciarSesion, onVolver)`. **`internal`**, con 4 `@Preview` privados. |

Cada `LoginError` se dibuja con `BannerEstado` (5.5):

| `LoginError` | Tipo | Título | Mensaje |
|---|---|---|---|
| `CredencialesInvalidas` | Error | «Credenciales inválidas» | «El usuario o la contraseña son incorrectos.» |
| `SinConexion` | Advertencia | «Sin conexión» | «No se puede conectar con el servidor. Verifica tu conexión a internet.» |
| `SinPermisos` | Error | «Sin permisos» | «Tu cuenta no tiene rol de administrador, por eso no se habilita el panel.» |
| `Desconocido` | Error | «Algo salió mal» | «No pudimos iniciar sesión. Inténtalo de nuevo.» |

Comportamiento:
- **Carga:** `IndicadorCarga` («Verificando credenciales…») con `liveRegion = Polite` y `mergeDescendants`. Mientras `cargando` los dos campos quedan **deshabilitados** y el botón por `puedeEnviar`. Carga y error son excluyentes y comparten una zona con `animateContentSize`.
- **Teclado:** el usuario es `KeyboardType.Email` con `ImeAction.Next` (pasa al campo de contraseña); la contraseña es `Password` con `Done`, que quita el foco y llama a `onIniciarSesion()` (el ViewModel vuelve a comprobar `puedeEnviar`). El botón del ojo mide 56 dp y se anuncia «Mostrar contraseña» / «Ocultar contraseña».
- **Tamaños:** campos y «Iniciar sesión» de 68 dp o más; «Volver al inicio» de 64 dp o más. La pantalla se desplaza (`verticalScroll` + `heightIn(min = maxHeight)`), con `systemBarsPadding` e `imePadding`; «Volver» queda abajo gracias a un `Spacer` con peso.
- **Accesibilidad:** el título «Campus Navi» lleva `heading()` y el logo la descripción «Logo de Campus Navi». Las etiquetas son el `label` de cada campo.

Cuidados:
- ⚠ **Nombre del producto:** la pantalla se llama «Campus Navi» (título y logo) y este documento «Campus Locator». Hay que decidir uno.
- Paleta privada, casi toda igual a `CampusColors` (5.4).
- Los dos campos pierden el foco (y el teclado se cierra) al empezar la carga, porque se deshabilitan; tras un error hay que volver a tocar el campo.
- Faltan `@Preview` para `SinPermisos`, `Desconocido` y contraseña visible.

### 5.6 Datos: repositorios y modelos

Convención: `interface XRepository` + `XRepositoryStub` (o `AssetsX` si lee de `assets/`) + TODO `RemoteX`
en `data/remote/` (Retrofit, `ClienteApi.api`, §5.10). Los ViewModels de hoy crean el stub directamente (verificado: `SeleccionDestinoViewModel` con `LugaresRepositoryStub()` y la `Factory` de Lista de videos con `AssetsVideoRepository`): para pasar al backend se cambian esas líneas, no las pantallas. `InicioViewModel` ya usa `RemoteBackendHealth` (FE-1.1) y la `Factory` de Login, `RemoteAuthRepository` (FE-1.2).

| Repositorio | Métodos | Implementación actual | Usado por |
|---|---|---|---|
| `AuthRepository` | `suspend login(identificador: String, password: String): Sesion` (lanza `CredencialesInvalidasException` o `java.io.IOException`; con el backend real también `ApiException` y `RespuestaInesperadaException`) | **Real** (`RemoteAuthRepository`, `POST /v1/auth/login`, FE-1.2); queda `AuthRepositoryStub` sin uso | `LoginViewModel` (por `Factory`) |
| `AdminRepository` | `suspend obtenerResumen(): ResumenAdmin` (lanza `IOException`, solo documentado en el KDoc) | Stub (`AdminRepositoryStub`, 600 ms) | `PanelAdminViewModel` (por `Factory`). Detalle abajo |
| `VideoRepository` | `suspend obtenerVideos(): List<Video>` (cada `Video` ya trae sus `fotos`) · `suspend renombrarVideo(videoId, nombre)` · `suspend eliminarVideo(videoId)` · `suspend eliminarFoto(videoId, fotoId)` · `cambios(): Flow<Int>` | Local (`AssetsVideoRepository(context)`) | Galería, Lista y Detalle de video |
| `RecoleccionRepository` | `crearVideo(inicio): String` · `carpetaFotos(videoId): File` · `registrarFoto(videoId, archivo, DatosFoto): FotoRecolectada` · `desplazarFotos(videoId, desdeIndice, dLat, dLng)` · `fotos(videoId)` · `finalizar(videoId, duracionS, distanciaM, pasos): ResumenRecoleccion` · `descartar(videoId)` · `buscarEnCurso(): String?` · `contarPendientes(): Int` · `marcarSubida(videoId, fotoIds)` · `espacioLibreBytes(): Long` | Local (`RecoleccionRepositoryLocal(context)`, `data/repository/RecoleccionRepository.kt`) | `RecoleccionViewModel` (lo crea directamente). Detalle abajo |
| `CalibracionPasoRepository` | `guardada(): Double?` · `longitudPasoM(): Double` (la calibrada, o `PdrEngine.LONGITUD_PASO_DEFECTO_M`) · `guardar(Valido, ahoraMs = ahora)` · `restablecer()` (borra todo el archivo) | Local (`CalibracionPasoRepository(context)`, `data/repository/CalibracionPasoRepository.kt`; **sin interfaz**) | `PdrTracker` (valor por defecto del parámetro), `CalibracionViewModel` y `UbicacionManualScreen`. Detalle abajo |
| `LugaresRepository` | `suspend obtenerLugares(): List<LugarDestino>` (lanza `IOException`, solo documentado en el KDoc) | Stub (`LugaresRepositoryStub`, 300 ms; devuelve `LUGARES_DE_PRUEBA`, 6 lugares) | `SeleccionDestinoViewModel` (lo crea directamente); futuras 6.3 y 7.6/7.7 |
| `EscaneoBackend` | `suspend analizar(fotos: List<File>)` → `Unit` (lanza `IOException`). Vive en `ui/ubicacion/EscaneoBackend.kt`, **no** en `data/repository/` | Stub (`EscaneoBackendStub`, 2,5 s) | `EscaneoViewModel` (lo instancia directamente). Detalle en 5.2 |
| `BackendHealth` | `suspend estaEnLinea(): Boolean` (no lanza). `data/repository/BackendHealth.kt` | **Real** (`RemoteBackendHealth`, `GET /v1/health`, §5.10) | `InicioViewModel` (lo fija en una propiedad). Detalle en 5.5 |

| Modelo | Archivo | Notas |
|---|---|---|
| `Usuario`, `Rol`, `Sesion` | `domain/model/Usuario.kt` | Verificado (bache 3; `Sesion` cambió en FE-1.2). `Rol` = `USER` / `ADMIN`; `Usuario(id, nombre, correo, rol)`; `Sesion(token, usuario, expiraEnMs)`. ⚠ El `toString()` de `Sesion` incluye el token. Detalle abajo |
| `ResumenAdmin` | `domain/model/ResumenAdmin.kt` | Verificado (bache 3): 6 campos, 5 datos del panel (el último video usa número y fecha). Detalle abajo |
| `Alerta`, `Lugar(nombre, lat, lng)` | `domain/model/Alerta.kt` | Detalle abajo. `Lugar` lo usa el editor de mapa |
| `LugarDestino`, `CategoriaLugar` | `domain/model/LugarDestino.kt` | Verificado contra el código. `id`, `nombre`, `categoria`, `lat`, `lng`, `alias`, `distanciaMetros?`, `imagenUrl?`. Detalle más abajo |
| `Foto`, `Video`, `EstadoFoto`, `CalidadFoto` | `domain/model/Foto.kt` | Detalle abajo. Ver también 7.11 y 7.14 |
| `InicioRecoleccion` | `domain/model/InicioRecoleccion.kt` | `lat`, `lng`, `rumbo` (0…360, 0 = norte; norte magnético si vino de la brújula), `nombreVideo` y `continuaVideoAnterior`. Lo emite la vista 7.3 y lo consume la 7.4 a través de `SesionDeRecoleccion`. Detalle en 5.5 («UbicacionManual») |
| `FotoRecolectada`, `DatosFoto`, `ResumenRecoleccion` | `domain/model/FotoRecolectada.kt` | Lo que guarda y devuelve `RecoleccionRepository`. `FotoRecolectada` tiene un `uid`. Detalle abajo |
| `SesionDeRecoleccion` | `domain/model/SesionRecoleccion.kt` (`object`) | Holder en memoria entre 7.3, 7.4 y 7.5. Detalle abajo |

**`AuthRepository` en detalle (verificado)**

- `CredencialesInvalidasException` (mensaje "Credenciales inválidas") vive en el mismo archivo. Contrato real: `POST /v1/auth/login` (backend §5.3): `401 CREDENCIALES_INVALIDAS` → `CredencialesInvalidasException`; sin conexión, *timeout* o `5xx` de API Gateway → `IOException` (tabla completa en §5.10). Verificado en `LoginViewModel`: una `IOException` se muestra como «sin conexión» y **cualquier otra** excepción como `LoginError.Desconocido` (5.5).
- **`RemoteAuthRepository(api: CampusApi = ClienteApi.api)`** (`data/remote/RemoteAuthRepository.kt`, FE-1.2): `llamar { api.login(LoginPeticionDto(identificador, password)) }` y `MapeoDatosApi.sesion(dto)` (§5.10). Envía `identificador` tal cual lo recibe (`LoginViewModel` ya lo recorta) y `password` sin recortar. `200` → `Sesion(token, usuario, expiraEnMs)`; `401 CREDENCIALES_INVALIDAS` → `CredencialesInvalidasException`; sin red → `SinConexionException`; otro código → `ApiException` (p. ej. `503 SERVICIO_OCUPADO` → `FalloApi.Desconocido(503, "SERVICIO_OCUPADO")`); `200` sin `token`, sin `expira_en` o con rol desconocido → `RespuestaInesperadaException`. No registra nada propio (solo la línea `Api` de `RequestIdInterceptor`). Lo cubre `RemoteAuthRepositoryTest` (6 casos: 200 admin con la petición exacta, 200 `user`, 401, sin red, 200 sin `expira_en`, 503).
- Un login correcto devuelve la `Sesion` también para un usuario `USER`: **es el `LoginViewModel` quien decide no guardarla** (7.1). El repositorio no filtra por rol.
- **Cuentas del stub** (`AuthRepositoryStub`, sin uso desde FE-1.2; espera simulada de 1,2 s; la contraseña se ignora): `admin@campus.edu.co` → `ADMIN`; `user@campus.edu.co` → `USER`; `offline` → `IOException`; cualquier otro → credenciales inválidas. Se compara el identificador sin espacios y en minúsculas, pero `correo` queda como lo escribió la persona. Su sesión vence a las 12 h (`expiraEnMs = ahora + 12 h`). Cuidado: el stub devuelve `nombre = "Administrador"` y `token = "stub-token"` incluso para `USER`; no usar ese nombre en pruebas de interfaz.
- Nunca registrar `password` ni `token` en `AppLog`.

**`Alerta` y `Lugar` en detalle (verificado)**

| Campo de `Alerta` | Tipo y valores |
|---|---|
| `id`, `lat`, `lng`, `mensaje` | Obligatorios |
| `tipo` | `String`, por defecto `"otro"`. Claves del mapa web: `agua`, `mobiliario`, `escalones`, `obra`, `vehiculos`, `otro` |
| `prioridad` | `String`, por defecto `"normal"`. Valores: `normal`, `alta` |
| `radio` | `Int` en metros, por defecto `15`; el rango válido es 5…100 |
| `activa` | `Boolean`, por defecto `true` |

- `tipo` y `prioridad` son **texto libre, no enums**, y el modelo **no valida** el rango del radio: un error de escritura pasa sin aviso y el mapa web no reconocería la clave. Validar en el formulario (7.9) o convertirlos en enums con las mismas claves.
- `Alerta` no guarda quién la creó ni cuándo.
- `Lugar(nombre, lat, lng)` no tiene `id` ni categoría; `LugarDestino` sí. Esa diferencia es lo que hay que resolver al unificarlos (ver la advertencia de `Lugar` y `LugarDestino` más abajo).

**`VideoRepository` en detalle (verificado)**

- **No hay `obtenerVideo(id)` ni `obtenerFotos`:** todo sale de `obtenerVideos()`, que relee **todos** los manifests en `Dispatchers.IO`. Para un solo video (Detalle) se filtra por `id` en la lista; no llamarlo en cada recomposición.
- **Videos** ordenados por nombre de carpeta; **fotos** de cada video ordenadas por `id` como **texto**: los ids deben ir con ceros a la izquierda (`"0001"`, `"0002"`…); `"10"` quedaría antes que `"9"`. Un video cuyo manifest falla se **omite** (queda un `Log.w`, no una excepción).
- **`cambios(): Flow<Int>`** devuelve el contador de `EdicionesLocales` (un `StateFlow` por dentro): emite el valor actual **apenas se empieza a recoger**. Si el ViewModel carga datos y además recoge `cambios()`, la carga inicial ocurre dos veces salvo que se ignore la primera emisión. El número no significa nada; solo avisa de que "algo cambió, vuelve a pedir".
- **`EdicionesLocales`** (`internal object`): renombrar y eliminar viven **en memoria** y se aplican encima de lo leído de `assets/`; se pierden al cerrar la app. Al renombrar un video, también cambia `videoNombre` en todas sus fotos. Desaparece con el backend (**TODO** `RemoteVideoRepository`).
- **Cómo lo consumen hoy las vistas:** Detalle de video recoge `cambios()` y es la referencia (ver `VideoDetalleViewModel`, 5.5). Galería carga una sola vez, no recoge `cambios()` y sus eliminar/reasignar **no** pasan por el repositorio (ver `GaleriaViewModel`, 5.5). Lista de videos también recoge `cambios()` desde su `init` (ver `VideosViewModel`, 5.5).
- **Lo que falta para ver lo recolectado (FE-2.1):** la recolección (7.4) **no** usa `VideoRepository`: guarda con `RecoleccionRepository` (abajo), así que lo que se recolecta no aparece en Galería, Lista ni Detalle de video. Hace falta un `VideoRepository` **compuesto** (assets + `files/recoleccion/`) y un parser de manifest compartido. Esto cambia lo que pedía este documento (ampliar `VideoRepository` con `crearVideo` y `agregarFoto`): la interfaz sigue siendo de **solo lectura + borrar/renombrar**.
- **Estructura y formato de los videos locales** (fuente única; la usan 7.11, 7.13 y 7.14):

  **Fuente de datos (provisional, local):** `AssetsVideoRepository` lee los videos empaquetados en
  `app/src/main/assets/videos/<video_id>/`. Estructura:

  ```
  videos/
  └── vid_0001/
      ├── manifest.json
      ├── photos/0001.png ...
      └── thumbs/0001.png ...      (si falta una miniatura se usa la foto original)
  ```

  `manifest.json` (un solo archivo por video):

  | Campo | Obligatorio | Descripción |
  |---|---|---|
  | `video_id`, `name`, `created_at` | `name` recomendado | Identificador y nombre visible (renombrable). El código **no lee `video_id`**: el id es el nombre de la carpeta |
  | `photos[].id`, `file`, `lat`, `lng` | Sí | Id dentro del video, ruta relativa y coordenadas (WGS84) |
  | `photos[].thumb` | No | Ruta relativa de la miniatura |
  | `photos[].heading` | No | Rumbo en grados, 0 = norte, sentido horario |
  | `photos[].captured_at` | No | Fecha/hora de captura |
  | `photos[].lugar`, `estado`, `calidad` | No | Valores por defecto: sin lugar, `procesada`, `normal` |

  > El `manifest.json` es solo la semilla local. Cuando exista el backend, la fuente de verdad serán
  > su base de datos (metadatos) y S3 (archivos, bucket privado con URLs prefirmadas de vida corta).
  > Cambiar `AssetsVideoRepository` por un `RemoteVideoRepository` no afecta a las pantallas: `Foto`
  > ya recibe las URLs resueltas.

- **Formato del `manifest.json` que lee hoy el código:** `name` (si falta, usa el nombre de la carpeta), `created_at`, `photos[]` con `id`, `file`, `lat`, `lng` (obligatorios) y `thumb`, `heading`, `captured_at`, `lugar`, `estado`, `calidad` (opcionales). ⚠ **El código no lee `video_id`**: el id del video es el **nombre de la carpeta**, aunque la tabla de 7.11 lo menciona. `estado` y `calidad` se comparan con el **nombre** del enum sin importar mayúsculas (`"alta"`, `"ERROR"`), no con la etiqueta visible, y si falta o no se reconoce usan `PROCESADA` / `NORMAL`.
- Las URLs que arma son `file:///android_asset/videos/<id>/<ruta>`; si la miniatura no existe en `thumbs/`, `urlMiniatura` es la foto original.

**`RecoleccionRepository` y `SesionDeRecoleccion` en detalle** (entregado el 2026-10-11; compila y funciona, sin pruebas automáticas)

- **Por qué es aparte de `VideoRepository`:** éste es la fuente de verdad (futuro `RemoteVideoRepository`); el almacenamiento local de la captura es otra responsabilidad y así no se toca lo que ya funciona.
- **Carpeta:** `files/recoleccion/<rec_NNNN>/photos/NNNN.jpg` + `manifest.json`. El id del video es `rec_` + 4 dígitos (prefijo distinto de `vid_` para no chocar con los datos de prueba); el id de cada foto lleva 4 dígitos con ceros a la izquierda, para ordenar como texto (ver `VideoRepository`).
- **Manifest:** usa las claves del formato de `assets/videos/` (`video_id`, `name`, `created_at`, `photos[].id`, `file`, `lat`, `lng`, `heading`, `captured_at`) más claves **propias que el lector actual ignora**: `estado` (`en_curso` / `finalizado`), `start_lat`, `start_lng`, `start_heading`, `ended_at`, `duration_s`, `distance_m`, `steps` y `photos[].sync` (`pendiente` / `subida`). Es compatible **solo en las claves**: `AssetsVideoRepository` lee de `assets/`.
- **Fechas** en ISO-8601 (`yyyy-MM-dd'T'HH:mm:ssXXX`): ordena como texto (decisión pendiente de la nota de `Video.creadoEn` en 7.14).
- **`registrarFoto`** recibe el JPG que dejó `tomarFoto` (`tmp_<n>.jpg`), lo renombra a `NNNN.jpg` y actualiza el manifest en cada foto (se guarda de forma continua). `desplazarFotos` mueve de forma uniforme las fotos desde un índice (re-anclaje). `finalizar` marca el video como `finalizado` y devuelve el `ResumenRecoleccion`; `descartar` borra la carpeta. `buscarEnCurso`, `contarPendientes` y `marcarSubida` son para retomar y para la subida futura (**aún sin usar**). `espacioLibreBytes` alimenta el aviso de almacenamiento.
- Usa `org.json` (disponible en Android; en pruebas unitarias JVM hace falta la dependencia).
- **`SesionDeRecoleccion`** (`object`): `inicio: StateFlow<InicioRecoleccion?>` · `resumen: StateFlow<ResumenRecoleccion?>` · `iniciar(inicio)` (la llama 7.3 vía `AppNav`) · `consumirInicio()` (la llama 7.4; **devuelve y borra**) · `finalizar(resumen)` (la llama `AppNav` al terminar; la leerá 7.5) · `limpiar()`. Vive en memoria: se pierde si Android mata el proceso (7.4 muestra entonces `SIN_INICIO`).

**`CalibracionPasoRepository` en detalle** (entregado el 2026-10-12; la lógica pura de `CalibracionPaso` se verificó con kotlinc; el repositorio depende de Android y no se probó por separado)

- **Almacén:** `SharedPreferences` `campus_calibracion` (sin cifrar; no es un dato sensible). Claves: `longitud_paso_m`, `pasos`, `distancia_m`, `fecha_ms`. No hay un almacén genérico de preferencias (`SessionManager` es solo de sesión).
- `longitudPasoM()` es lo que lee `PdrTracker` al crearse; un valor guardado **fuera de 0,40–1,20 m se ignora** y se usa el genérico. `restablecer()` borra todo el archivo. `guardar` solo acepta un `ResultadoCalibracion.Valido`.
- La fuente de pasos es única (acelerómetro, `FuentePasos.ACELEROMETRO`), así que ya no hay que guardar con cuál se calibró. **Las calibraciones hechas antes del 2026-10-12 (sensor de hardware) deben rehacerse.**
- Sin interfaz ni `Remote…`: la calibración es **por dispositivo** y no se sincroniza con el backend.

**Modelos de `Foto.kt` (verificado)**

| Modelo | Campos y reglas |
|---|---|
| `EstadoFoto(etiqueta)` | `SUBIDA` "Subida" · `PROCESADA` "Procesada" · `ERROR` "Error" |
| `CalidadFoto(etiqueta)` | `ALTA` "Alta calidad" · `NORMAL` "Normal" · `BAJA` "Baja calidad" |
| `Foto` | `id` (único **solo dentro del video**), `videoId`, `videoNombre`, `urlFoto`, `urlMiniatura`, `lat`, `lng`, `rumbo: Float?` (grados, 0 = norte, sentido horario; `null` si se desconoce), `capturadaEn: String?`, `lugar: String?`, `estado` (por defecto `PROCESADA`), `calidad` (por defecto `NORMAL`). Calculadas: `uid` = `"videoId/id"` (**usarla como clave** en selecciones, listas y `key` de Compose, porque `id` se repite entre videos) y `nombreArchivo` (último tramo de `urlFoto`). |
| `Video` | `id`, `nombre`, `creadoEn: String?`, `fotos: List<Foto>`. `distanciaMetros` (calculada): suma haversine entre fotos consecutivas **en el orden de la lista**; con menos de 2 fotos vale `0.0`. |

- `capturadaEn` y `creadoEn` son **texto tal cual viene del manifest**: nadie los convierte a fecha todavía. Definir el formato (ISO-8601) antes de ordenar o filtrar por fecha.
- La función haversine (`distanciaEntre`) es **`private`**: si otra pieza necesita distancia entre coordenadas (seguimiento, `LugarDestino.distanciaMetros`), hay que extraerla a algo como `domain/util/Geo.kt` en vez de copiarla. No confundir `Video.distanciaMetros` (longitud del recorrido) con `LugarDestino.distanciaMetros?` (distancia desde la persona).

**`LugarDestino` y `CategoriaLugar` en detalle (verificado, bache 1)**

- `LugarDestino` es una `data class` inmutable (para cambiar algo, `copy(...)`). Obligatorios: `id: String`, `nombre: String`, `categoria: CategoriaLugar`, `lat: Double` y `lng: Double`. Con valor por defecto: `alias: List<String> = emptyList()`, `distanciaMetros: Int? = null` e `imagenUrl: String? = null`.
- `alias` son otros nombres que la persona puede decir (p. ej. «biblioteca», «los trillizos») y alimentan `BuscarLugares` (5.7): cuantos más alias cubran cómo habla la gente, mejor acierta la voz.
- `distanciaMetros` son **metros enteros desde la posición actual**; `null` si aún no hay ubicación. Depende de la posición, no del lugar. Al ser `data class`, dos copias del mismo lugar con distinta distancia **no son iguales** (`equals`): comparar lugares por `id`.
- `imagenUrl` es una URL o `file:///android_asset/...`; si es `null`, la lista muestra el ícono de la categoría.
- `CategoriaLugar` tiene 8 valores. `etiqueta` va en singular (filas de la lista y filtro de texto de `BuscarLugares.filtrar`) y `etiquetaPlural`, en los chips de filtro:

| Valor | `etiqueta` | `etiquetaPlural` | Grupo |
|---|---|---|---|
| `BIBLIOTECA` | Biblioteca | Biblioteca | destacada |
| `CAFETERIA` | Cafetería | Cafetería | destacada |
| `BANO` | Baño | Baños | destacada |
| `BLOQUE` | Bloque | Bloques | destacada |
| `AUDITORIO` | Auditorio | Auditorios | otra |
| `DEPORTES` | Deportes | Deportes | otra |
| `ADMINISTRACION` | Administración | Administración | otra |
| `ENTRADA` | Entrada | Entradas | otra |

- `CategoriaLugar.DESTACADAS` = Biblioteca, Cafetería, Baño y Bloque: según el comentario del código, las que tienen chip propio en 6.4. `OTRAS` = el resto (`values()` sin las destacadas); según el mismo comentario van en el menú «Más». Una categoría nueva entra en `OTRAS` sola. Verificado en el bache 2: `FilaCategorias` dibuja `DESTACADAS` como chips y `OTRAS` en el menú «Más» (5.5), y `CategoriaLugar.icono()` (`Comun.kt`) es un `when` exhaustivo sin `else`: una categoría nueva no compila hasta que se le asigne ícono.

⚠ **`Lugar` y `LugarDestino` conviven.** Al construir 7.6 y 7.7 (lista y formulario de lugares) hay que
unificarlos en un solo modelo. Comparación (código y secciones 7.6 y 7.7):
- `LugarDestino` ya trae `nombre`, `lat` y `lng` con los mismos nombres que `Lugar(nombre, lat, lng)`, más `id`, `categoria` y `alias`: es un **superconjunto**, y obtener un `Lugar` desde un `LugarDestino` es copiar tres campos.
- 7.6 y 7.7 piden además descripción (texto que se lee al usuario), referencias cercanas y nº de fotos asociadas. `LugarDestino` **no tiene** ninguno. Sí cubre nombre, alias, categoría, coordenada e `imagenUrl`.
- La validación de 7.7 (nombre único, coordenada obligatoria) no está en el modelo: el modelo no valida nada.
- Sigue sin decidirse si se amplía `LugarDestino` con campos opcionales o se crea un modelo de edición aparte y `LugarDestino` queda como vista de lectura de 6.4.

**`ResumenAdmin`, `Usuario`, `AdminRepository` y `LugaresRepository` en detalle (verificado, bache 3)**

`ResumenAdmin` es una `data class` de 6 campos, sin valores por defecto, en este orden:

| Campo | Tipo | Notas |
|---|---|---|
| `totalFotos` | `Int` | |
| `totalLugares` | `Int` | |
| `alertasActivas` | `Int` | |
| `ultimoVideoNumero` | `Int?` | Número del último video recolectado (`video12` → 12); `null` si aún no hay videos |
| `ultimoVideoFecha` | `Long?` | Fecha y hora de ese video, en milisegundos epoch |
| `fotosPendientes` | `Int` | Fotos guardadas en el teléfono que aún no se han subido (cola local) |

- Son **6 campos pero 5 datos** en el panel: el último video usa número y fecha. Por eso 7.2 («Resumen rápido, con 5 datos») y 5.5 hablan de 5.
- ⚠ **Orígenes mezclados.** Según el KDoc de `AdminRepository`, totales, lugares y alertas activas salen del backend (`GET /v1/admin/stats`) y las fotos pendientes, de la cola local (`data/local`), no del backend. El KDoc **no dice** de dónde sale el último video (¿backend o `VideoRepository`?). La implementación real tendrá que combinar dos orígenes en una sola llamada. Además, `ultimoVideoFecha` es `Long` en milisegundos, pero `Video.creadoEn` es texto del manifest (ver arriba): alguien tiene que convertirlo.

`AdminRepository`: `suspend fun obtenerResumen(): ResumenAdmin`; la `IOException` («si no hay conexión») solo está en el KDoc. `AdminRepositoryStub` espera 600 ms y devuelve 2842 fotos, 48 lugares, 3 alertas, video 12, `ultimoVideoFecha = System.currentTimeMillis()` y 27 fotos pendientes. Cuidados del stub: nunca lanza excepción, así que el estado de error del panel no se puede ver; la fecha es siempre «ahora», por lo que el panel muestra siempre «Hoy, HH:mm»; el último video nunca es nulo, así que no se ve el «—»; y dice 48 lugares mientras `LUGARES_DE_PRUEBA` tiene 6.

`Usuario.kt`: `enum class Rol { USER, ADMIN }`, `Usuario(id: String, nombre: String, correo: String, rol: Rol)` y `Sesion(token: String, usuario: Usuario, expiraEnMs: Long)` (FE-1.2: `expiraEnMs` = `expira_en` del login en milisegundos Unix; `fun vencida(ahoraMs: Long) = ahoraMs >= expiraEnMs`). Las tres son sin valores por defecto, y las dos últimas son `data class`. El KDoc de `Sesion` dice que el token nunca se registra en logs. Coincide con 5.3: `SessionManager.obtener()` devuelve `""` si faltan id, nombre o correo.
- ⚠ **El `toString()` autogenerado de `Sesion` incluye el token y el de `Usuario`, el correo.** Interpolar una `Sesion` o un `Usuario` en un `AppLog` los escribiría en Logcat y en el archivo de logs, contra lo que dice el KDoc. Solución simple: sobrescribir `toString()` en ambas. No se buscó si algún código lo hace hoy.

`LugaresRepository`: `suspend fun obtenerLugares(): List<LugarDestino>`, «con su distancia a la posición actual» (`GET /v1/places`); la `IOException` solo está en el KDoc. `LugaresRepositoryStub` espera 300 ms y devuelve `LUGARES_DE_PRUEBA`, un `val` público del mismo archivo (coordenadas aproximadas, solo mientras no exista backend). Los 6 lugares (ids únicos, apto para `key = { it.id }`):

| `id` | Nombre | Categoría | Alias | `distanciaMetros` |
|---|---|---|---|---|
| `biblioteca-central` | Biblioteca Central | `BIBLIOTECA` | biblioteca, la biblioteca | 85 |
| `cafeteria-principal` | Cafetería Principal | `CAFETERIA` | cafeteria, cafe, la cafeteria | 120 |
| `banos-bloque-a` | Baños Bloque A | `BANO` | banos, bano, los banos | 150 |
| `bloque-trillizos` | Bloque de los Trillizos | `BLOQUE` | trillizos, los trillizos | 200 |
| `auditorio-principal` | Auditorio Principal | `AUDITORIO` | auditorio | 260 |
| `entrada-principal` | Entrada Principal | `ENTRADA` | entrada, porteria | 310 |

Qué casos **no** ejercitan estos datos de prueba:
- Ningún lugar tiene `imagenUrl`: siempre se ve el ícono de la categoría.
- Todos tienen distancia (fija, creciente y en el mismo orden de la lista): no se ve el caso sin ubicación ni el ⚠ de «Lugares cercanos» sin distancias (5.5).
- No hay lugares de `DEPORTES` ni de `ADMINISTRACION`: esos filtros dan «No hay lugares con estos filtros».
- El stub nunca lanza `IOException`: el error de carga de Destino (`SIN_CONEXION`) no se puede ver.
- No existen «Bloque A» y «Bloque B»: el ⚠ 1 de `BuscarLugares` (5.7) no ocurre con estos nombres.

### 5.7 Casos de uso (lógica pura, sin Android)

| Pieza | Ubicación | Cómo se usa | Reglas |
|---|---|---|---|
| `BuscarLugares.mejores(consulta, lugares)` | `domain/usecase/BuscarLugares.kt` | Devuelve 0 (nada se parece), 1 (claro) o 2–3 lugares (empate: hay que pedir que elija). | **Verificado contra el código.** Normaliza (minúsculas, sin tildes, solo letras y números) y quita muletillas (lista fija: «quiero», «ir», «a», «al», «la», «el», «los», «las», «de», «del», «un», «una», «llevame», «llevarme», «lleves», «vamos», «hacia», «hasta», «para», «por», «favor», «me», «en», «donde», «esta», «necesito», «busco», «buscar»); si solo hay muletillas, las conserva. El puntaje de un lugar es el mejor entre su nombre y cada alias: si el texto limpio es **igual** al nombre o alias limpio → 1,0; si no, promedio sobre las palabras **dichas** de su mejor coincidencia en el candidato (igual 1,0; prefijo de 3 letras o más 0,9; parecida por Levenshtein con similitud ≥0,75 → ×0,9), y × 0,95 si el candidato es un nombre (los alias no se penalizan). Umbral 0,70; empate dentro de 0,04 del mejor; máximo 3 (los demás se descartan por orden de la lista). |
| `BuscarLugares.filtrar(lugares, texto)` | ídem | Filtro del buscador de una lista. | **Verificado.** Cada palabra escrita debe estar **contenida** (no solo al inicio) en alguna palabra del nombre, de un alias o de `categoria.etiqueta` (**singular**; no usa `etiquetaPlural`). Texto vacío → lista completa. No quita muletillas. |
| `InterpretarRespuesta.interpretar(texto)` | ídem | Devuelve `Respuesta.SI`, `NO` o `NINGUNA`. | **Verificado.** Compara **palabras completas** tras normalizar. Sí: «si», «claro», «correcto», «dale», «ok», «okay», «vale», «confirmo», «afirmativo», «exacto», «listo», «vamos», «adelante». No: «no», «nop», «nope», «cancela», «cancelar», «negativo», «incorrecto», «otro», «equivocado». Solo sí → `SI`; solo no → `NO`; ambas o ninguna → `NINGUNA` (p. ej. «está bien» o «de acuerdo» dan `NINGUNA`). `Respuesta` vive en el mismo archivo. Sirve para cualquier confirmación por voz. ⚠ `VoiceController.listen` entrega hasta 3 hipótesis **unidas en un solo texto**: si el reconocimiento duda entre "sí" y "no", el texto trae ambas y el resultado es `NINGUNA` (se debe volver a preguntar, no asumir). |
| `CalibracionPaso` | `domain/usecase/CalibracionPaso.kt` (`object`) | `calcular(distanciaM, pasos, duracionS): ResultadoCalibracion` y `distanciaEntre(lat1, lng1, lat2, lng2)` (haversine, R = 6 371 000 m; igual que `map.distance` de Leaflet). Constantes `MIN_PASO_M` 0,40 · `MAX_PASO_M` 1,20 · `MIN_PASOS` 15 · `MIN_DISTANCIA_M` 10 · `DISTANCIA_RECOMENDADA_M` 30. | **Verificado con kotlinc 2.0.21** (13 comprobaciones). `ResultadoCalibracion`: `Valido(longitudPasoM, pasos, distanciaM, duracionS, cadenciaPpm, velocidadMps)` o `Invalido(motivo, longitudPasoM?)`; `MotivoInvalido`: `TRAMO_CORTO`, `POCOS_PASOS`, `PASO_MUY_CORTO`, `PASO_MUY_LARGO` (orden de comprobación: tramo → pasos → rango). Con `duracionS = 0`, cadencia y velocidad valen 0. Los umbrales de 10 m y 15 pasos son elección propia. Test JUnit4 `CalibracionPasoTest` (**no ejecutado en Gradle**) |
| `DisparadorCaptura` y `ModoCaptura` | `domain/usecase/DisparadorCaptura.kt` | Decide cuándo tomar la siguiente foto de la recolección (cada N metros o N segundos). Ver 5.2, «Flujo de captura de la recolección». | Sin estado de Android: se puede probar con pruebas unitarias (todavía no hay). Llamar a `alCapturar` **solo si la foto se guardó** |
| `Deriva.estimar(distanciaDesdeAnclaM)` | ídem | `EstimacionDeriva(derivaM, precisionM, nivel)` con `NivelCalidad` `ALTA` (< 15 m), `MEDIA` (< 30 m) o `BAJA`. | Heurística **provisional**: 4 % de la distancia desde el último ancla (decisión 16) |

Se pueden probar sin emulador (solo Kotlin).

Uso verificado en `SeleccionDestinoViewModel` (5.5): `BuscarLugares.mejores(texto, todos)` → `List<LugarDestino>`, `BuscarLugares.filtrar(todos, busqueda)` e `InterpretarRespuesta.interpretar(texto)` → `Respuesta.SI / NO / NINGUNA`; las firmas coinciden con la tabla. Las **reglas** de la tabla se verificaron contra `BuscarLugares.kt` (bache 1). Dos matices del uso: `mejores` siempre busca en la lista **completa** (ignora la búsqueda y la categoría activas), y el «Di cuál quieres» tras ofrecer opciones vuelve a buscar sobre todos los lugares, no solo sobre las opciones ofrecidas.

**Comportamientos a tener en cuenta en `BuscarLugares`** (leídos en el código y probados con una copia de la lógica en Python; no se ejecutó el Kotlin, y los ejemplos usan nombres de muestra, no los lugares reales del stub):

1. ⚠ **Una coincidencia exacta gana sin preguntar.** Un nombre o alias idéntico al texto puntúa 1,0, mientras que un nombre parcial llega como máximo a 0,95: la diferencia (0,05) supera el margen de empate (0,04), así que un parcial nunca se ofrece junto a un exacto. Agravante: las muletillas también se quitan de los **nombres**, y «a» es muletilla, así que «Bloque A» se evalúa como «bloque». Con «Bloque A» y «Bloque B», decir «bloque» devolvió solo «Bloque A», sin pedir elegir. Con los 6 lugares reales del stub (bache 3) **no ocurre**: no existen «Bloque A» y «Bloque B», y decir «bloque» devuelve dos opciones («Baños Bloque A» y «Bloque de los Trillizos») y se pide elegir. Sigue latente si el backend trae nombres como «Bloque A» y «Bloque B».
2. ⚠ **Las hipótesis unidas de `listen` pueden anular una coincidencia.** El promedio cuenta todas las palabras del texto, sin quitar repetidas. Con «cafeteria cafe teria» no devolvió ningún lugar, mientras que «cafeteria» sola da 1,0. Se repite con los alias reales del stub (bache 3). Falta confirmar en `VoiceController` cómo se unen las hipótesis y si el ViewModel pasa ese texto tal cual. Opciones: puntuar cada hipótesis por separado y quedarse con la mejor, o quitar palabras repetidas.
3. **El umbral efectivo de la coincidencia difusa es mayor que 0,75.** Para llegar a 0,70 con una sola palabra parecida hace falta una similitud de ≈0,82 contra un nombre y ≈0,78 contra un alias. Una palabra de 5 letras con un error no basta contra un nombre, pero sí contra un alias: los alias ayudan más de lo que parece.
4. **El prefijo es asimétrico:** solo cuenta que la palabra **dicha** sea prefijo de la del lugar («cafe» → «cafeteria»), nunca al revés, y exige 3 letras o más.
5. **El comentario del código no coincide con la lógica:** dice «un nombre parcial vale menos que un alias exacto», pero la penalización de 0,95 se aplica a todo nombre que no sea idéntico; un alias parcial no se penaliza.
6. **`filtrar` es una búsqueda por «contiene»:** «a» deja pasar casi todos los lugares. Usa `categoria.etiqueta` (singular): escribir «entradas» no coincide con la categoría «Entrada» aunque el chip diga «Entradas». La `ñ` se normaliza («baño» = «bano»).
7. **Sin estado ni Android:** `BuscarLugares` e `InterpretarRespuesta` son `object` sin estado y solo importan `LugarDestino` y `java.text.Normalizer`; se pueden llamar desde cualquier hilo y probar con pruebas unitarias. `limpiar` es `internal` y la usa `InterpretarRespuesta`.
8. **Un empate de 3 ya llena el máximo.** Con el stub, «principal» devuelve Cafetería, Auditorio y Entrada Principal (0,95 cada una): si el backend trae un cuarto lugar «… Principal», quedaría fuera sin aviso, por el orden de la lista.

### 5.8 Rutas y datos que viajan entre vistas

| Ruta | Pantalla | Recibe | Entrega (callbacks) |
|---|---|---|---|
| `inicio` | `InicioScreen` | — | `onUbicarme` → `ubicarme`, `onIrALugar` → `destino`, `onAccesoAdministrador` → `login` |
| `ubicarme` | `EscaneoScreen` | — | `onCompletado` (**sin datos**; hoy hace `popBackStack()`, TODO resultado 6.3), `onCancelar` → `popBackStack()`. `onAjustes` **no está conectado** (valor por defecto `{}`) |
| `destino` | `SeleccionDestinoScreen` | — | `onDestinoConfirmado(LugarDestino)` (hoy **descarta** el destino y abre `ubicarme`), `onAjustes` → `ajustes`, `onVolver` |
| `login` | `LoginScreen` | — | `onLoginExitoso` → `admin/panel` (quita `login` de la pila), `onVolver` |
| `admin/panel` | `PanelAdminScreen` | — | `onRecolector` → `admin/ubicacion-manual`, `onLugares` → `admin/lugares`, `onMapaAlertas` → `admin/mapa`, `onImagenes` → `admin/imagenes`, `onVideos` → `admin/videos`, `onEstadisticas` → `admin/estadisticas`, `onAjustes` → `ajustes`; `onVolverModoPublico` y `onSesionCerrada` → vuelven a `inicio`; `onSinSesion` → `login` (quita el panel de la pila) |
| `admin/ubicacion-manual` | `UbicacionManualScreen` (7.3) | — | `onVolver` (flecha y «Cancelar») → `popBackStack()`, `onAjustes` → `ajustes`, `onCalibrar` → `navigate("admin/calibracion")`, `onConfirmar(InicioRecoleccion)` → `SesionDeRecoleccion.iniciar(inicio)` y `navigate("admin/recoleccion")` (7.3 queda en la pila: su ViewModel reactiva «Confirmar» con `alReanudar()`). Pide `Permisos.INICIALES` antes de mostrar la pantalla y descarta el resultado |
| `admin/calibracion` | `CalibracionScreen` (7.3b) | — | Pide `Permisos.ACTIVIDAD` antes de mostrar la pantalla y **descarta el resultado** (negarlo no cambia nada: los pasos salen siempre del acelerómetro; quitar este permiso es parte de FE-4.3). `onVolver` → `popBackStack()`. Se llega desde la fila «Calibrar mi paso» de 7.3. No devuelve datos: el resultado se guarda en `CalibracionPasoRepository` (5.6) y lo recoge cada `PdrTracker` al crearse |
| `admin/recoleccion` | `RecoleccionScreen` (7.4) | `InicioRecoleccion` por `SesionDeRecoleccion` (no por la ruta) | Pide **solo la cámara** antes de mostrar la pantalla (como `ubicarme`; si se niega, `popBackStack()`). `onFinalizado(resumen)` → `SesionDeRecoleccion.finalizar(resumen)` y `navigate("admin/recoleccion/resumen") { popUpTo("admin/ubicacion-manual") { inclusive = true } }` (saca 7.3 y 7.4 de la pila); `onDescartado` (video sin fotos) → `popBackStack("admin/panel", inclusive = false)`; `onVolver` (solo con error, p. ej. `SIN_INICIO`) → `popBackStack()`; `onAjustes` → `ajustes` |
| `admin/recoleccion/resumen` | Placeholder (7.5, falta `ResumenVideoScreen`) | `SesionDeRecoleccion.resumen` | Pantalla en blanco: solo se sale con Atrás |
| `admin/mapa` | `EditorMapaScreen` | `posicionAdmin: () -> Pair<Double, Double>?` (hoy `{ null }`) | `onVolver`, `onVerLista` (hoy vacío; el comentario dice «vista 17», que corresponde a la lista de alertas 7.10) |
| `admin/imagenes` | `GaleriaScreen` | — | `onVolver`, `onAbrirImagen(videoId, fotoId)` (placeholder, falta 7.12) |
| `admin/videos` | `VideosScreen` | — | `onVolver`, `onAbrirVideo(id)` → `admin/videos/<id>` |
| `admin/videos/{videoId}` | `VideoDetalleScreen` | `videoId` (argumento de ruta, texto) | `onVolver`, `onAbrirImagen(videoId, fotoId)` (placeholder, falta 7.12) |

Rutas con placeholder vacío (pantalla en blanco, no cierran la app): `admin/recoleccion/resumen`, `admin/lugares`,
`admin/estadisticas`, `ajustes`. Registrar una ruta **dos veces** hace que la última
reemplace a la primera (un placeholder puede tapar la pantalla real); navegar a una ruta **no
registrada** cierra la app con un error.

**Verificado en `MainActivity.kt` (`AppNav`):**
- **El `NavHost` vive en `MainActivity.kt`**, no en `ui/navigation/AppNavHost.kt` (§3.2). Ruta
  inicial: `inicio`. Cada pantalla crea su propio ViewModel; `AppNav` **no** crea ni comparte ninguno.
- **Único dato que viaja por ruta:** `videoId`, como argumento de texto sin `navArgument` declarado y sin
  codificar. El id del video es el nombre de su carpeta (5.6): no usar `/` ni caracteres especiales.
  Si el argumento falta, la ruta no dibuja nada.
- **La recolección no usa argumentos de ruta:** los datos viajan por `SesionDeRecoleccion` (5.6; decisión 15).
- **Sin protección al entrar en las rutas `admin/*`:** `AppNav` no comprueba la sesión al entrar en `admin/mapa`,
  `admin/imagenes` ni `admin/videos[/{id}]`; el panel dispara `onSinSesion` en su `init`. ⚠ Confirmar si cada
  pantalla admin lo comprueba por su cuenta. Ojo con la restauración tras matar el proceso: `MyApp`
  ya habrá borrado la sesión (5.3) y Android puede restaurar la pila en una pantalla admin.
- **Vuelta a Login por sesión perdida (FE-1.2):** `AppNav` tiene un `LaunchedEffect(nav)` que recoge
  `EventosSesion.sinSesion` (5.3). Si la ruta actual (`nav.currentDestination?.route`) empieza por `admin/`, hace
  `nav.navigate("login") { popUpTo("inicio"); launchSingleTop = true }`: la pila queda `inicio → login` y la app no se
  cierra. En cualquier otra ruta (flujo público, `login`) ignora el evento. Así cualquier pantalla admin que llame a
  `/v1/admin/…` o `/v1/collect/…` con la sesión vencida o rechazada vuelve a Login sin código propio.
- **Permisos en la ruta:** `inicio` pide los iniciales y `ubicarme` la cámara antes de mostrar la
  pantalla (ver 5.3). `admin/recoleccion` pide solo la cámara; la ruta de navegación (6.5) deberá hacer lo mismo. `admin/calibracion` pide solo `Permisos.ACTIVIDAD`.
  `admin/ubicacion-manual` ya pide `Permisos.INICIALES` y descarta el resultado (la 7.3 en sí no necesita
  ninguno: la brújula usa el sensor de rotación; el de actividad física ya no lo usa nadie, porque los pasos salen siempre del acelerómetro; 5.2).
- **`inicio` (verificado en el código):** `PedirPermisos` va **antes** de `InicioScreen` y su resultado se ignora (`permisosPedidos = true` sea cual sea); mientras tanto no se dibuja nada. Por eso la explicación hablada de `InicioScreen` nunca suena antes del primer diálogo (5.5, Inicio).
- **`destino` → `ubicarme`:** `onDestinoConfirmado` hace `nav.navigate("ubicarme")` **sin quitar** `destino` de la pila (queda `[inicio, destino, ubicarme]`). Al terminar el escaneo, `popBackStack()` vuelve a Destino con su ViewModel intacto (5.5).
- **Bordes del sistema:** `MainActivity` llama a `enableEdgeToEdge()`, así que cada pantalla debe aplicar `statusBarsPadding` / `navigationBarsPadding` (o `systemBarsPadding`) y, con teclado, `imePadding`. Inicio, Destino y Login ya lo hacen.

⚠ **Brecha en el flujo público** (la recolección ya la resolvió con `SesionDeRecoleccion`): hoy **no hay dónde guardar datos compartidos entre vistas públicas** (el destino elegido, la
posición estimada, si hay una ubicación vigente). Hay que resolverlo antes de 6.3 y 6.5 (ver decisión
abierta 15). Dos puntos concretos donde se pierde información hoy: `onDestinoConfirmado` descarta el
`LugarDestino`, y el `EscaneoEvento.Completado` no lleva resultado (`backend.analizar` devuelve `Unit`; ver "Flujo de captura del escaneo" en 5.2).

Verificado en los ViewModels: `DestinoEvento.Confirmado` **sí** lleva el `LugarDestino` completo (se pierde después, en `AppNav`); `InicioEvento` y `LoginEvento.IrAlPanel` no llevan datos. Además, `SeleccionDestinoViewModel` conserva `candidato` tras confirmar y `destino` sigue en la pila (ver arriba): al volver del escaneo, la confirmación queda pendiente (5.5).

### 5.9 Puentes WebView ↔ Android

Cada mapa es una página en `assets/` (HTML + JS con Leaflet) con su puente Kotlin: `AndroidBridge`
(mapa público, 2.6), `EditorBridge` (7.8), `VideoBridge` (7.14), `UbicacionBridge` (7.3), `RecoleccionBridge` (7.4) y `CalibracionBridge` (7.3b). Los datos viajan como JSON. Las funciones de los tres primeros están al final de esta
sección; las de los tres últimos, en 5.5. Funciones y cuidados del `EditorBridge` y de `VideoBridge` en 5.5.
`env(safe-area-inset-*)` no funciona en `WebView`, así que la app pasa el alto de las barras en dp con
`setInsets(top, bottom)` (el mapa público no lo usa: su pantalla aplica `systemBarsPadding()`).

> ⚠ **Código entregado el 2026-10-10.** El lado web se probó con jsdom (27 comprobaciones, incluido el caso
> «Leaflet no carga»); el lado Kotlin **no se compiló** ni se probó en dispositivo. Confirmar y quitar este aviso.

**Infraestructura común (dos piezas):**

| Pieza | Ubicación | Qué hace |
|---|---|---|
| `MapaBase` (JS) | `assets/mapa_base.js` | Se carga **después de Leaflet y antes** del script de la página. No hace nada al cargarse. |
| `MapaWebView` (Kotlin) | `map/MapaWebView.kt` | Una sola fábrica del `WebView` para todas las pantallas de mapa. |

**`MapaBase` (JS)** — `window.MapaBase`:
- `iniciar({ puente })` → `{ existe(), call(fn, ...args), leaflet }`. Se llama **primero**, antes de comprobar Leaflet, y deja
  listo lo que Kotlin necesita aunque el mapa no cargue: `window.setInsets`, un `window.onAtras` por defecto (llama a
  `salir()`), el botón `#btn-back`, las medidas (`--toph` / `--dockh` con `ResizeObserver`; usa los ids `top` y `dock`) y,
  si no hay Leaflet, el aviso «No se pudo cargar el mapa…». La página termina con `if (!base.leaflet) return;` y después
  reemplaza `window.onAtras` por el suyo. `call` devuelve `true` si había puente; si no, la página usa datos de demo.
- ⚠ **`crearMapa` no es parte del objeto que devuelve `iniciar`:** se llama `MapaBase.crearMapa(...)`. Solo `base.existe`, `base.call` y `base.leaflet` cuelgan de `base`; `toast`, `dialogo`, `confirmar`, `medir`, `$`, `ic`, `esc` y `puente` también son de `MapaBase`. Escribir `base.crearMapa(...)` lanza `TypeError` y deja el mapa **negro y sin aviso** (pasó en `calibracion_mapa.js`, corregido el 2026-10-12). ⚠ **Revisar que `recoleccion_mapa.js` use `MapaBase.crearMapa`** (se escribió con el mismo supuesto).
- `crearMapa({ centro, zoom, maxZoom })` → mapa Leaflet con las teselas de OSM (nativas hasta el zoom 19; `maxZoom` mayor las
  amplía: el detalle de video usa 21), atribución «© OSM» y control de zoom, ambos abajo a la izquierda.
- `toast`, `dialogo({ texto, label, peligro, input, valor, placeholder, valida, ok })`, `confirmar(texto, ok, label = 'Eliminar')`,
  `medir`, `$`, `ic`, `esc` y `puente(nombre)`.
- `app.js` (mapa público) **solo** usa `MapaBase.puente('AndroidBridge').call` en lugar de su antiguo `bridgeCall`: no tiene
  `dialogo`, `medir` ni `setInsets`, y su `toast` es otro (`#toast-container`). Por eso carga `mapa_base.js` pero no llama a `iniciar`.

**`MapaWebView` (Kotlin)** — paquete `map`:

| Pieza | Firma | Qué hace / cuidado |
|---|---|---|
| `MapaWeb` / `rememberMapaWeb()` | `class MapaWeb` · `listo: Boolean` (estado) · `js(codigo)` | Controlador de una pantalla: `listo` pasa a `true` cuando la página llama a `listo()`; `js` ejecuta JavaScript (hilo principal). Usar `LaunchedEffect(mapa.listo, dato)` para empujar estado. |
| `literalJs(s)` | `(String) -> String` | Texto → literal de JavaScript (`JSONObject.quote`), para `cargarX(${literalJs(json)})`. |
| `PuenteWeb(mapa)` | `open class` · `listo()` · `enHiloPrincipal { }` | Base de los puentes: ya trae `listo()`. Cada subclase añade sus `@JavascriptInterface` y los pasa por `enHiloPrincipal` (llegan en un hilo del `WebView`). **Debe ser pública o `internal`, nunca `private`** (el `WebView` la invoca por reflexión). |
| `MapaWebView` | `(mapa, html, puente, nombrePuente, tag, modifier = fillMaxSize(), pasarInsets = true, manejarAtras = true)` | Crea el `WebView` (tamaño, fondo `#0A0E1A`, JS, DOM storage, depuración solo en builds depurables, consola y errores a Logcat con `tag`), registra el puente, carga `file:///android_asset/<html>`, envía `setInsets` y conecta el `BackHandler` con `window.onAtras()`. `pasarInsets = false` si la página no define `setInsets`. `onRelease` destruye el `WebView`. |

Receta para una pantalla de mapa nueva (como `EditorMapaContent` y `VideoDetalleContent`):

```kotlin
val mapa = rememberMapaWeb()
val eventosActuales by rememberUpdatedState(eventos)
val puente = remember(mapa) { MiPuente(mapa) { eventosActuales } }   // internal class MiPuente(...) : PuenteWeb(mapa)
MapaWebView(mapa, html = "mi_mapa.html", puente = puente, nombrePuente = "MiBridge", tag = "MiMapa")
LaunchedEffect(mapa.listo, json) { if (mapa.listo) mapa.js("cargarX(${literalJs(json)})") }
```
Y en la página: `<script>` de Leaflet, `mapa_base.js`, el JS de la página; en este, `const base = MapaBase.iniciar({ puente: 'MiBridge' }); if (!base.leaflet) return;`.

Cuidados:
- **Falta migrar `MapaPublicoScreen`** (FE-4.3) (⚠ su código no se revisó en este cambio): sigue con su propia fábrica de `WebView`.
  `MapaWebView` acepta cualquier objeto como `puente` (sirve `PuentePdr`) y `pasarInsets = false`, y el modificador
  `Modifier.systemBarsPadding()`; los `window.onNative*` se siguen enviando con `evaluateJavascript` desde esa pantalla.
- Los datos del usuario o del repositorio siempre con `textContent` o `esc()`, nunca interpolados en `innerHTML` (excepción: `bindTooltip` del editor).
- Las tres páginas (`index.html`, `editor_mapa.html`, `video_detalle.html`) siguen cargando Leaflet 1.9.4 desde `unpkg.com`
  sin `integrity` y las fuentes de Google Fonts, y llevan `user-scalable=no` en el `viewport` (decisión abierta 13).
- Un `onAtras` por defecto que llama a `salir()` evita el defecto anterior (sin Leaflet, Atrás y Volver no hacían nada).
  Aun así, sin Leaflet la página nunca llama a `listo()` y la app no le envía datos.
- `RecoleccionBridge` (7.4) es una página **embebida** en una tarjeta de Compose: usa `MapaBase.iniciar` y `crearMapa`, pero con `pasarInsets = false` y `manejarAtras = false` (Atrás lo maneja la pantalla); lleva ocultos `#top`, `#dock` y `#btn-back` por si `MapaBase.iniciar` no tolera que falten (5.5).
- `CalibracionBridge` (7.3b) es igual de embebido que `RecoleccionBridge` (`pasarInsets = false`, `manejarAtras = false`, mismos elementos ocultos); marca A y B con toques y pines arrastrables y usa el zoom nativo de Leaflet (5.5).

#### Funciones de `AndroidBridge` (mapa público, 2.6)

| Dirección | Función | Descripción |
|---|---|---|
| Web → Kotlin | `AndroidBridge.startSensors()` | Empieza a leer pasos, aceleración y rumbo |
| Web → Kotlin | `AndroidBridge.stopSensors()` | Detiene los sensores |
| Web → Kotlin | `AndroidBridge.setPosition(lat, lng)` | Punto de partida (toque en el mapa o GPS) |
| Web → Kotlin | `AndroidBridge.setManualHeading(grados)` | Rumbo de la rueda manual (solo si no hay brújula) |
| Web → Kotlin | `AndroidBridge.reset()` | Vuelve al punto de partida con los pasos en cero |
| Kotlin → Web | `window.onNativePosition(lat, lng, pasos, distanciaM, velocidadMps)` | Posición calculada tras cada paso (y al fijar o reiniciar). Con `pasos = 0` no se suma punto a la trayectoria |
| Kotlin → Web | `window.onNativeHeading(grados)` | Rumbo 0–360, norte real, ya promediado (~20 Hz, solo con el seguimiento activo) |
| Kotlin → Web | `window.onNativeAccel(desviacion)` | Desviación de la aceleración respecto a la gravedad (m/s²), solo para la gráfica |
| Kotlin → Web | `window.onNativeBrujula(disponible)` | Se envía en cada `startSensors()`; si es `false` aparece la rueda manual |
| Kotlin → Web | `window.onNativeStepUnavailable(motivo)` | El teléfono no tiene acelerómetro (`'no_sensor'`); solo muestra un aviso. Ya no se envía `'permission_denied'` (el acelerómetro no necesita permiso) |

Se eliminaron `onNativeStep(count)` y la firma anterior `onNativeAccel(x, y, z)`.

Requisitos del lado Kotlin (`map/MapaPublicoScreen.kt` y `map/PuentePdr.kt`): JavaScript activado en
el `WebView`, `addJavascriptInterface(PuentePdr(tracker), "AndroidBridge")` y llamar a las funciones
`window.onNative*` con `evaluateJavascript` **desde el hilo principal**. Los métodos
`@JavascriptInterface` llegan en un hilo del `WebView`, así que `PuentePdr` los reenvía al hilo
principal, que es donde vive `PdrTracker`. El mapa se carga con `file:///android_asset/index.html`.

#### Funciones de `EditorBridge` (editor de mapa y alertas, 7.8)

Los datos viajan como JSON; la alerta tiene los
campos `id, lat, lng, mensaje, tipo, prioridad, radio, activa` (tipo: `agua`, `mobiliario`,
`escalones`, `obra`, `vehiculos`, `otro`; prioridad: `normal` o `alta`).

| Dirección | Función | Descripción |
|---|---|---|
| Web → Kotlin | `listo()` | La página cargó; Kotlin responde enviando alertas, lugares y pendientes |
| Web → Kotlin | `abrirFormulario({id, lat, lng})` | Abre el formulario (`id` nulo = alerta nueva) |
| Web → Kotlin | `cancelarFormulario()` | El usuario salió del formulario desde el mapa (botón Atrás) |
| Web → Kotlin | `moverAlerta(id, lat, lng)` | Nueva posición confirmada con "Listo" |
| Web → Kotlin | `eliminarAlerta(id)` | Eliminación confirmada |
| Web → Kotlin | `sincronizar()` / `verLista()` / `pedirMiPosicion()` / `salir()` | Acciones de los botones |
| Kotlin → Web | `cargarAlertas(json)` / `cargarLugares(json)` | Reemplazan los datos del mapa |
| Kotlin → Web | `setPendientes(n)` | Actualiza el chip y el punto del botón Guardar |
| Kotlin → Web | `setBorrador(json \| null)` | Dibuja (o quita) el borrador del formulario |
| Kotlin → Web | `setMiPosicion(lat, lng)` | Dibuja la posición del admin y centra el mapa |
| Kotlin → Web | `onAtras()` | Lo invoca el `BackHandler`; el JS decide qué cerrar y llama a `salir()` |

#### Funciones de `VideoBridge` (detalle de video, 7.14)

| Dirección | Función | Descripción |
|---|---|---|
| Web → Kotlin | `listo()` | La página cargó; Kotlin responde con insets, otros videos y el video |
| Web → Kotlin | `abrirFoto(id)` | "Ver detalle" de la foto (→ vista 7.12) |
| Web → Kotlin | `renombrar(nombre)` | Nuevo nombre confirmado |
| Web → Kotlin | `eliminarFoto(id)` | Eliminación de una foto confirmada |
| Web → Kotlin | `eliminarVideo()` | Eliminación del video confirmada |
| Web → Kotlin | `salir()` | Volver a la lista |
| Kotlin → Web | `cargarVideo(json)` | Reemplaza el video mostrado |
| Kotlin → Web | `cargarOtros(json)` | Fotos de los demás videos (capa de contexto) |
| Kotlin → Web | `setInsets(top, bottom)` | Alto de las barras del sistema (en dp) |
| Kotlin → Web | `onAtras()` | Lo invoca el `BackHandler`; el JS decide qué cerrar |

Formato de los datos:
- Video: `{ id, nombre, fecha, fotos: [{ id, url, thumb, lat, lng, rumbo }] }` (`fecha` como
  `"2026-10-09"`; `rumbo` puede ser `null`).
- Otros videos: `[{ id, nombre, fotos: [{ lat, lng }] }]`.

### 5.10 Consumo de la API del backend

> El contrato de la API (rutas, cuerpos, errores) es del backend: `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5. Aquí se
> fija solo **lo que hace la app** con él. Desde FE-1.1 existen el cliente, el mapeo de errores, el mapeo de datos y
> `RemoteBackendHealth`; desde FE-1.2, el login (`RemoteAuthRepository`) y la sesión de las rutas protegidas
> (`SesionInterceptor`). Los demás repositorios siguen siendo *stubs* o datos locales (§5.6) hasta su lote.

**Configuración y cliente**
- `ApiConfig.kt` (`object ApiConfig`, paquete raíz): `API_BASE_URL` = output `api_base_url` de Terraform
  (`INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.2), sin barra final, hoy
  `https://fuzq99kddb.execute-api.us-east-1.amazonaws.com`; `BASE_URL = "$API_BASE_URL/v1"`;
  `TIMEOUT_CONEXION_S = 10`, `TIMEOUT_LECTURA_S = 30`, `TIMEOUT_ESCRITURA_S = 30`. Si la API se recrea, la URL cambia
  y hay que actualizar `API_BASE_URL` (lo detecta `validate11.py` C4a). El validador lee las dos líneas `const val
  API_BASE_URL = "…"` y `const val BASE_URL = "$API_BASE_URL/v1"` con una expresión regular: no cambiar su forma.
- Solo HTTPS: el Manifest declara `android:usesCleartextTraffic="false"` (ADR-FE-13; antes estaba en `true`).
- Cliente HTTP: **Retrofit 2.11.0 + OkHttp 4.12.0 + Gson 2.10.1** (ADR-FE-12). Los repositorios `Remote*` viven en
  `data/remote/` y cumplen las mismas interfaces de §5.6, así que las pantallas no cambian.
- Encabezados: `Authorization: Bearer <token>` solo en rutas `/v1/admin/…` y `/v1/collect/…`: en la app lo pone
  `SesionInterceptor` con el token de la sesión vigente (FE-1.2; sin sesión la petición no sale); sin vigilante
  (pruebas), `AutenticacionInterceptor` si hay token. `X-Request-Id` (UUID v4 nuevo por petición, salvo que la petición
  ya traiga uno) que se escribe en `AppLog` para cruzar con los logs del servidor (`RequestIdInterceptor`). El backend
  devuelve el mismo id en su respuesta (backend §5.1; visto en `dev` el 2026-10-25).
- Tiempos máximos: conexión 10 s; lectura 30 s, igual que `TIMEOUT_BACKEND_MS` del escaneo (5.2) y que el límite de
  API Gateway (`/v1/localize` tarda como máximo ~20 s en el backend). `RemoteBackendHealth` corta además la llamada
  entera a 5 s.

**Piezas de `data/remote/` (FE-1.1; FE-1.2 añade el login y la sesión)** — paquete
`com.example.myapplication.data.remote`:

| Pieza | Archivo | Firma y uso |
|---|---|---|
| `CampusApi` | `CampusApi.kt` | Interfaz Retrofit. Hoy: `@GET("health") suspend fun salud(): Response<SaludDto>` y (FE-1.2) `@POST("auth/login") suspend fun login(@Body cuerpo: LoginPeticionDto): Response<LoginRespuestaDto>`. Cada lote añade aquí sus rutas, **sin barra inicial** (`"auth/login"`, no `"/auth/login"`: con barra Retrofit descarta el `/v1`) y devolviendo siempre `Response<T>` |
| `ClienteApi` | `ClienteApi.kt` (`object`) | `ClienteApi.api: CampusApi` (instancia única, `lazy`, contra `ApiConfig.BASE_URL`, registra con `AppLog.i("Api", …)`; usa el `vigilante` que haya **al crearse**). `ClienteApi.vigilante: VigilanteSesion?` (`@Volatile var`, `null` por defecto; FE-1.2: `MyApp.onCreate` lo asigna antes de que nadie use `api`; sustituye al `proveedorToken` de FE-1.1, que ya no existe). `ClienteApi.crear(urlBase = ApiConfig.BASE_URL, token = { null }, registrar: (String) -> Unit, vigilante: VigilanteSesion? = null): CampusApi` (añade la barra final que exige Retrofit) y `ClienteApi.okHttp(token = { null }, registrar, vigilante = null): OkHttpClient` para pruebas (MockWebServer) o clientes propios. Con `vigilante`, las rutas protegidas pasan por `SesionInterceptor` y `token` no se usa; sin él, por `AutenticacionInterceptor(token)` |
| `RequestIdInterceptor(registrar)` | `ClienteApi.kt` | Pone `X-Request-Id` y registra **una línea por petición**: `GET /v1/health -> 200 (85 ms) rid=<uuid>` o `GET /v1/health -> falla UnknownHostException (3 ms) rid=<uuid>`. Solo método, ruta sin parámetros, código y duración: nunca encabezados ni cuerpos. `rid` es el de la respuesta si la trae, si no el enviado. `validate11.py` C1a busca esta línea en `files/logs/app.log`: cambiar el formato exige cambiar `PATRON_SALUD` del validador. Una petición que `SesionInterceptor` no deja salir **no** deja línea `Api` (deja la `Sesion` del vigilante) |
| `AutenticacionInterceptor(token)` | `ClienteApi.kt` | Regex `RUTA_PROTEGIDA` = `.*/v1/(admin\|collect)(/.*)?` sobre la ruta; `/v1/administrar` no la cumple. Solo cuando `ClienteApi` no tiene vigilante |
| `SesionInterceptor(vigilante: VigilanteSesion)` | `ClienteApi.kt` (FE-1.2) | En las rutas de `RUTA_PROTEGIDA` (las demás pasan sin tocar): 1) `vigilante.sesionParaPeticion("<MÉTODO> <ruta>")`; si da `null` lanza `SinSesionException(ruta)` sin llamar al backend; 2) envía con `Authorization: Bearer <token de esa sesión>`; 3) si la respuesta es `401` y `MapeoErroresApi.codigoError(peekBody(64 KB))` está en `CODIGOS_SESION`, `vigilante.rechazada(codigo, token, …)`. Devuelve la respuesta intacta (`llamar` la convierte en `ApiException(SesionVencida(codigo))`) |
| `SinSesionException(ruta)` | `ClienteApi.kt` (FE-1.2) | `IOException` (desde un interceptor OkHttp solo admite esas: otra excepción cerraría la app en su hilo). `llamar` la convierte en `ApiException(FalloApi.SesionVencida(MapeoErroresApi.SIN_SESION_LOCAL), http = 401, requestId = null)`, **nunca** en «sin conexión» (el `401` es por equivalencia: no hubo HTTP) |
| `RemoteAuthRepository(api = ClienteApi.api)` | `RemoteAuthRepository.kt` (FE-1.2) | `AuthRepository` real: `llamar { api.login(LoginPeticionDto(identificador, password)) }` → `MapeoDatosApi.sesion(dto)`. Errores en §5.6 («`AuthRepository` en detalle») |
| `llamar(peticion): T` | `ErroresApi.kt` (función `suspend` de nivel superior) | `llamar { api.salud() }` devuelve el cuerpo de un 2xx o lanza: `SinConexionException` (red, *timeout*, 5xx de API Gateway), `CredencialesInvalidasException` (la de `data/repository/AuthRepository.kt`), `ApiException` (el resto, también la sesión perdida de `SesionInterceptor`) o `RespuestaInesperadaException` (2xx sin cuerpo o JSON roto). La cancelación de la corrutina se propaga |
| `llamarSinCuerpo(peticion)` | `ErroresApi.kt` | Igual, para rutas `204` declaradas `Response<Unit>` (en un 204 Retrofit da `body() == null` y `llamar` lo trataría como respuesta inesperada) |
| `FalloApi` | `ErroresApi.kt` (`sealed interface`) | `SinConexion`, `CredencialesInvalidas`, `SesionVencida(codigo)`, `SinPermisos`, `DemasiadosIntentos`, `EmbeddingNoDisponible`, `Validacion(http, codigo, mensaje, campos: List<CampoInvalido(campo, motivo)>)`, `Desconocido(http: Int?, codigo: String?)`. Una fila por fila de la tabla de abajo |
| `ApiException(fallo, http, requestId)` | `ErroresApi.kt` | Lo que lanza `llamar` salvo «sin conexión» y «credenciales». `requestId` = `X-Request-Id` de la respuesta: el ViewModel lo registra en «Algo salió mal» |
| `SinConexionException(requestId = null, causa = null)` | `ErroresApi.kt` | **Es una `IOException`**: `LoginViewModel` y los demás que ya atrapan `IOException` la tratan como «sin conexión» sin cambios |
| `RespuestaInesperadaException(mensaje, causa)` | `ErroresApi.kt` | 2xx que no cumple el contrato (falta un campo obligatorio, rol desconocido, JSON roto). Para la UI es «Algo salió mal» |
| `MapeoErroresApi` | `ErroresApi.kt` (`object`) | `clasificar(http: Int, cuerpo: String?): FalloApi` (lógica pura) · `excepcion(fallo, http, requestId): Exception` · `deExcepcion(t: Throwable): FalloApi` (para un `catch` genérico en un ViewModel; desde FE-1.2 reconoce `SinSesionException` como `SesionVencida(SIN_SESION_LOCAL)`) · `CODIGOS_SESION` (`TOKEN_EXPIRADO`, `TOKEN_INVALIDO`, `NO_AUTENTICADO`) · FE-1.2: `codigoError(cuerpo: String?): String?` (`error.codigo` de un cuerpo de §5.1, o `null`) y `SIN_SESION_LOCAL = "SIN_SESION_LOCAL"` (código de `SesionVencida` cuando la petición no salió del teléfono; el backend nunca lo envía) |
| DTOs | `DtosApi.kt` | `SaludDto`, `LoginPeticionDto` (FE-1.2, el único que envía la app), `UsuarioDto`, `LoginRespuestaDto`, `LugarPublicoDto`, `AlertaDto`, `EstadisticasAdminDto` (+ `UltimoVideoDto`), `ImagenAdminDto` (+ `ReferenciaDto`), `VideoResumenDto` (con `fotos` opcional). El JSON del backend tal cual, con `@SerializedName` en snake_case y propiedades en camelCase. **Todos los campos de respuesta anulables y con valor por defecto** (trampa abajo) |
| `MapeoDatosApi` | `MapeoDatosApi.kt` (`object`) | `enumDe<E>(valor): E?` · `usuario(UsuarioDto?): Usuario` · `expiraEnMs(LoginRespuestaDto): Long` · `sesion(LoginRespuestaDto): Sesion` (FE-1.2: `token` no vacío + `usuario` + `expiraEnMs`; si falta algo, `RespuestaInesperadaException`) · `lugarDestino(LugarPublicoDto): LugarDestino?` (`null` = categoría desconocida: se descarta) · `alerta(AlertaDto): Alerta` · `resumenAdmin(EstadisticasAdminDto, fotosPendientes: Int): ResumenAdmin` · `estadoFoto(String?): EstadoFoto?` · `foto(ImagenAdminDto, videoNombre): Foto` · `video(VideoResumenDto): Video` · `isoAMilis(String?): Long?` |
| `RemoteBackendHealth(api, limiteMs = 5_000)` | `RemoteBackendHealth.kt` | `BackendHealth` real: `true` solo con `200` y `"estado": "ok"`; cualquier otra cosa (sin red, *timeout*, 5xx, otro `estado`) es `false`; nunca lanza salvo cancelación. `LIMITE_MS = 5_000` |

**Cómo se añade una ruta**: 1) DTO en `DtosApi.kt` (campos anulables); 2) método en `CampusApi`
que devuelve `Response<Dto>`; 3) `Remote<X>Repository(api: CampusApi = ClienteApi.api)` en `data/remote/` que llama
`llamar { api.ruta(…) }` y convierte con `MapeoDatosApi`; 4) la `Factory` o el ViewModel cambia el stub por el
`Remote*`; 5) prueba con MockWebServer (`ClienteApi.crear(urlBase = servidor.url("/v1").toString(), registrar = {})`).
Una ruta `/v1/admin/…` o `/v1/collect/…` no necesita nada más para la sesión: `ClienteApi.api` le pone el token y, si
la sesión venció o el backend la rechaza, cierra la sesión y `AppNav` vuelve a Login (§5.3); el ViewModel recibe
`ApiException(FalloApi.SesionVencida)` y solo tiene que no mostrar un error propio. Para probarla con sesión, pasar un
`VigilanteSesion` a `ClienteApi.crear(…, vigilante = …)` o `okHttp(…, vigilante = …)` como hace `SesionVencidaTest`.

Login (FE-1.2, hecho): `POST /v1/auth/login` con cuerpo `LoginPeticionDto` → `{"identificador":"…","password":"…"}`
(backend §5.3) → `LoginRespuestaDto` → `MapeoDatosApi.sesion(dto)`. `503 SERVICIO_OCUPADO` sigue en `Desconocido`
(decisión en §5.5, «Login»).

**Detalles internos del cliente (para no abrir `data/remote/`)**
- Campos de los DTOs (propiedad Kotlin ← clave JSON; todos `T? = null` salvo el de la petición):
  `LoginPeticionDto(identificador: String, password: String)` (FE-1.2; su `toString()` no muestra los valores) ·
  `SaludDto(estado, version, commit)` ·
  `UsuarioDto(id, nombre, correo, rol)` · `LoginRespuestaDto(token, expiraEn ← expira_en, usuario: UsuarioDto?)` ·
  `LugarPublicoDto(id, nombre, categoria, lat, lng, alias: List<String>?, descripcion, referencias, imagenUrl ←
  imagen_url, distanciaM ← distancia_m)` · `AlertaDto(id, lat, lng, mensaje, tipo, prioridad, radioM ← radio_m:
  Int?, activa, vigenciaDesde, vigenciaHasta, actualizadoEn, version: Int?)` · `EstadisticasAdminDto(totalFotos,
  totalLugares, alertasActivas, ultimoVideo: UltimoVideoDto(numero, creadoEn)?)` · `ReferenciaDto(id, nombre)` ·
  `ImagenAdminDto(id, videoId, orden, lat, lng, rumbo: Double?, capturadaEn, estado, error, calidad, lugar:
  ReferenciaDto?, notas, url, urlMiniatura, urlExpiraEn)` · `VideoResumenDto(id, numero, nombre, refCliente, estado,
  creadoEn, totalFotos, fotos: List<ImagenAdminDto>?)`. `VideoResumenDto` **no** trae todavía `iniciado_en`,
  `finalizado_en`, `duracion_s`, `distancia_m`, `pasos`, `inicio`, `conteo` ni `creado_por`: el lote que los necesite
  (FE-2.1, FE-4.1) los añade.
- Orden de los interceptores en `ClienteApi.okHttp`: primero `SesionInterceptor` (con vigilante, la app) o
  `AutenticacionInterceptor` (sin él), después `RequestIdInterceptor` (el que registra; ve el encabezado
  `Authorization` pero nunca lo escribe). Sin `HttpLoggingInterceptor`: no lo añadas, imprimiría el token.
- `SesionInterceptor` lee el cuerpo de un `401` con `peekBody` (como mucho 64 KB), así que `llamar` todavía puede leerlo
  para clasificarlo. El token que compara `VigilanteSesion.rechazada` es el **mismo** que envió (lo tomó de la sesión
  que validó antes de enviar), no el que haya en ese momento.
- Retrofit con funciones `suspend` encola la llamada: los interceptores corren en los hilos de OkHttp, no en el de la
  corrutina. Por eso `VigilanteSesion` no toca la interfaz y `EventosSesion` es un `Channel`.
- `ClienteApi.crear(…)` construye un `OkHttpClient` y un `Retrofit` **nuevos** en cada llamada: en la app se usa siempre
  `ClienteApi.api` (uno solo, con su *pool* de conexiones); `crear` es para pruebas.
- Convertidor: `GsonConverterFactory.create()` con un `Gson()` por defecto (sin política de nombres y **sin escribir
  los `null`**). Para los cuerpos que envía la app (p. ej. el login de FE-1.2: `{"identificador", "password"}`), usar
  un `data class` con `@SerializedName` en cada campo; un campo `null` se omite del JSON (cómo lo trata cada ruta
  del backend, sin comprobar: verlo en backend §5 antes de enviar `null`).
- `requestId` en las excepciones: `ApiException` y la `SinConexionException` de un 5xx de API Gateway llevan el
  `X-Request-Id` de la respuesta; la `SinConexionException` de un fallo de red lleva `requestId = null` (el id enviado
  solo queda en la línea `Api` de `AppLog`). `CredencialesInvalidasException` no lleva id.
- `RemoteBackendHealth.estaEnLinea()` atrapa cualquier `Exception` (salvo `CancellationException`, que relanza) y
  devuelve `false`; `withTimeoutOrNull(limiteMs)` da `false` si se pasa del límite.
- `MapeoDatosApi.usuario`: `nombre` ausente → `""`; `id`, `correo` y `rol` obligatorios.
- Pruebas: `ClienteApi.crear(urlBase = servidor.url("/v1").toString(), token = { "t" }, registrar = { lineas += it })`
  con `MockWebServer` (`okhttp3.mockwebserver`, `testImplementation(libs.okhttp.mockwebserver)`); las corrutinas con
  `kotlinx.coroutines.runBlocking` (no hay `kotlinx-coroutines-test` en el build). `SocketPolicy.DISCONNECT_AT_START`
  simula «sin red»; `SocketPolicy.NO_RESPONSE`, un *timeout*. Para rutas protegidas que `CampusApi` aún no tiene,
  `SesionVencidaTest` declara una interfaz Retrofit propia (`admin/stats`, `collect/videos`, `admin/videos/{id}`,
  `places`) sobre `ClienteApi.okHttp(registrar = {}, vigilante = …)`, con `SessionManager(almacenEnMemoria, reloj = {
  ahora })`; un `Dispatcher` de MockWebServer permite cambiar la sesión mientras la petición está en el servidor.

**Trampas del cliente**
- **Gson y Kotlin:** Gson crea los objetos sin pasar por el constructor, así que un campo que falta en el JSON queda en
  `null` aunque el tipo de Kotlin no lo admita, y los valores por defecto no se aplican. Por eso los DTOs son todos
  anulables y las comprobaciones se hacen en `MapeoDatosApi` (`RespuestaInesperadaException` si falta algo).
- **JSON roto en un 2xx:** Gson lanza `MalformedJsonException`, que **hereda de `IOException`**; `llamar` la atrapa
  antes y la convierte en `RespuestaInesperadaException` (si no, se vería como «sin conexión»).
- **Mayúsculas de los enumerados:** `uppercase(Locale.ROOT)`; con el teléfono en turco, `"biblioteca".uppercase()`
  daría `BİBLİOTECA` y no coincidiría con el enum (lo prueba `MapeoDatosApiTest`).
- **Fechas:** `isoAMilis` usa `SimpleDateFormat` en UTC y no `java.time`, porque `minSdk = 24` (`java.time` llega en la
  API 26 sin *desugaring*). Acepta solo la zona `Z` (la que usa el backend) y descarta las fracciones de segundo.
- **`EstadoFoto` aún sin `PENDIENTE`:** `estadoFoto("pendiente_subida")` da `null` y `foto()` lo muestra como `SUBIDA`
  hasta que FE-2.1 añada `EstadoFoto.PENDIENTE` y su caso en `MapeoDatosApi.estadoFoto` (y en el `when` de colores de
  `GaleriaScreen`, que es exhaustivo).
- **URLs de fotos:** `url` y `url_miniatura` llegan `null` hasta BE-4.1; `foto()` las deja en `""`.
- **Registrar:** el registrador por defecto (`AppLog.i`) llama a `android.util.Log`, que en las pruebas de la JVM no
  existe: las pruebas pasan su propio `registrar`.

**Errores → modelos de la app**

| Respuesta | Qué hace la app |
|---|---|
| Sin red, *timeout*, `5xx` con cuerpo `{"message": …}` (generado por API Gateway) | `IOException` → «sin conexión» (`LoginError.SinConexion`, `ErrorDestino.SIN_CONEXION`, banner de Inicio) |
| `401 CREDENCIALES_INVALIDAS` | `CredencialesInvalidasException` → `LoginError.CredencialesInvalidas` |
| `401 TOKEN_EXPIRADO` / `TOKEN_INVALIDO` / `NO_AUTENTICADO` en `/v1/admin/…` o `/v1/collect/…` (y, sin llamar al backend, una sesión ausente o con `expira_en` pasado) | `SessionManager.cerrarSesion()`, `onSinSesion` y, desde una pantalla `admin/…`, la ruta va a Login sin cerrar la app (FE-1.2: `SesionInterceptor` + `VigilanteSesion` + `EventosSesion`, §5.3). El ViewModel recibe `ApiException(FalloApi.SesionVencida(codigo))`, con `codigo = SIN_SESION_LOCAL` si no se llamó al backend |
| `403 SIN_PERMISOS` | Igual que «sin permisos» de Login (7.1) |
| `429` (cuerpo `{"message": …}`) | «Demasiados intentos, espera un momento» |
| `503 EMBEDDING_NO_DISPONIBLE` | Escaneo (6.2) termina en error hablado: «El servicio de ubicación no está disponible en este momento» (en `dev`, con embeddings apagado o arrancando, infra §3.4) |
| `409` / `422` | Mensaje del campo afectado (`detalle.campos`) en formularios de admin |
| Cualquier otro | «Algo salió mal» (`LoginError.Desconocido`, `ErrorDestino.DESCONOCIDO`) y se registra el `X-Request-Id` |

Implementación (FE-1.1): `MapeoErroresApi.clasificar(http, cuerpo)` aplica estas reglas **en este orden** (la primera
que cumple decide): `429` → `DemasiadosIntentos` (con cualquier cuerpo) · `5xx` con cuerpo `{"message": …}` sin clave
`error` → `SinConexion` · `401` + `CREDENCIALES_INVALIDAS` → `CredencialesInvalidas` · `401` + `TOKEN_EXPIRADO`,
`TOKEN_INVALIDO` o `NO_AUTENTICADO` → `SesionVencida(codigo)` · `403` + `SIN_PERMISOS` → `SinPermisos` · `503` +
`EMBEDDING_NO_DISPONIBLE` → `EmbeddingNoDisponible` · `409` o `422` → `Validacion` (con `detalle.campos` si viene) ·
el resto → `Desconocido(http, codigo)`. Así, `500 ERROR_INTERNO`, `503 BASE_NO_DISPONIBLE`, `503 SERVICIO_OCUPADO`,
`404`, un `401`/`403` con otro código o un cuerpo que no es JSON son `Desconocido`. Sin respuesta (DNS, conexión,
*timeout*) no hay código: `llamar` lanza `SinConexionException` directamente. Lo cubre `MapeoErroresApiTest` fila por
fila.

**Mapeo de datos**

| Backend (JSON) | App (Kotlin) |
|---|---|
| Enumerados en minúsculas (`"biblioteca"`, `"admin"`, `"alta"`) | `enum.valueOf(valor.uppercase())` (`CategoriaLugar`, `Rol`); `tipo` y `prioridad` de alertas se quedan como texto en `Alerta` |
| `LugarPublico` | `LugarDestino` (`distancia_m` → `distanciaMetros: Int?` redondeado; `imagen_url` → `imagenUrl`) |
| `Alerta.radio_m` | `Alerta.radio` |
| `GET /v1/admin/stats` | `ResumenAdmin`: `ultimo_video.numero` → `ultimoVideoNumero`; `ultimo_video.creado_en` (ISO-8601) → `ultimoVideoFecha` en milisegundos; `fotosPendientes` sale de la cola local de subida, no del backend |
| `usuario` del login | `Usuario`; `expira_en` → `Sesion.expiraEnMs` (milisegundos) y se guarda con la sesión (`expira_en_ms`, §5.3) |
| `VideoResumen` / `ImagenAdmin` | `Video` / `Foto`. El `id` del video pasa a ser UUID (hoy es el nombre de la carpeta); `uid` de `Foto` sigue siendo `videoId/id`. `EstadoFoto` necesita un valor `PENDIENTE` para `pendiente_subida` (FE-2.1) |
| Fechas ISO-8601 | `creadoEn` / `capturadaEn` siguen siendo texto en los modelos actuales; convertir solo donde se ordene o filtre |

Implementación (FE-1.1), por fila: `MapeoDatosApi.enumDe` (desconocido → `null`; en `usuario`, un rol desconocido es
`RespuestaInesperadaException`) · `lugarDestino` (categoría desconocida → `null`, el lugar se descarta; `distancia_m`
con `roundToInt`) · `alerta` (`tipo` por defecto `otro`, `prioridad` `normal`, `radio` 15, `activa` `true` si faltan) ·
`resumenAdmin(dto, fotosPendientes)` · `usuario` + `expiraEnMs`, unidos en `sesion(dto)` (FE-1.2: `Sesion(token,
usuario, expiraEnMs)`) · `video` (fotos ordenadas por `orden`; `Foto.id` = UUID de la imagen, así `uid` =
`<uuid video>/<uuid imagen>`; `lugar` = nombre del lugar) y `foto` · `isoAMilis`. Obligatorios (si faltan,
`RespuestaInesperadaException`): `id`, `correo` del usuario; `id`, `nombre`, `lat`, `lng` del lugar; `id`, `lat`, `lng`,
`mensaje` de la alerta; los tres totales de `stats`; `id`, `video_id`, `lat`, `lng` de la imagen; `id` del video. Lo
cubre `MapeoDatosApiTest` con los ejemplos JSON del contrato del backend.

**Rumbo (backend ADR-BE-12)**: todo rumbo que se envía va en grados [0, 360), **norte verdadero**, sentido horario.
- Recolección (7.4) y `PdrTracker`: ya es norte verdadero; solo normalizar a [0, 360).
- Escaneo 360° (6.2): `EscucharOrientacion` da acimut **magnético** en (−180, 180]. Antes de enviar:
  `(acimut + declinación + 360) % 360`, con la declinación de `GeomagneticField` (como hace `PdrTracker`). Además hay
  que **guardar el acimut de cada foto** (hoy solo se escribe en el log; §5.2, «Flujo de captura del escaneo»).
- `correccion_rumbo_grados` de la respuesta se suma al rumbo de la brújula mientras dure la sesión de navegación.

**Ubicarse (`POST /v1/localize`)**: hasta 5 fotos JPEG re-codificadas por la app a lado mayor 1024 px y calidad 85
(≤ 1,5 MB cada una), en el mismo orden que `rumbos`. El resultado viaja a la vista 6.3 por el holder que resuelva la
decisión abierta 15. `referencias[].rumbo_grados` es absoluto: la app lo convierte en «a tu derecha / izquierda / al
frente / detrás» con el rumbo actual corregido.

**Subida de un recorrido (7.5)**: cola persistente en `data/local/` (sobrevive al cierre de la app). Antes de subir, cada
JPEG se re-codifica a lado mayor 1600 px y calidad 90, para quedar por debajo de los 4 MB que acepta el backend. Orden:
`POST /v1/collect/videos` con `ref_cliente` = id local (`rec_NNNN`) → lotes de 50 en
`POST /v1/collect/videos/{id}/images` → `PUT` de cada JPEG a la URL prefirmada con **exactamente** los encabezados
recibidos → `POST …/complete`. Un `403` de S3 significa URL vencida: pedir URLs de nuevo. Todas las llamadas son
idempotentes, así que reintentar es seguro. El progreso por foto se lee de `GET /v1/admin/videos/{id}`.
La **cola** es el propio `manifest.json` de cada recorrido (§5.6, «Recolección»): `photos[].sync` pasa de `pendiente` a
`subida` cuando su `PUT` responde 200, y se añaden dos claves de video, `remote_video_id` (UUID que devuelve
`POST /v1/collect/videos`) y `subida_estado` (`sin_subir`, `subiendo`, `completada`). Al abrir la app se retoman los
recorridos `finalizado` con `subida_estado = subiendo`. «Fotos pendientes» del Panel (7.2) = número de
`photos[].sync = pendiente` en los manifests con `estado = finalizado`.

**Alertas sin conexión (2.5)**: caché local en Room, base `campus_locator.db` (en `databases/` de la app), tabla
`alertas` (los campos de `Alerta`) y tabla `sincronizacion` (clave `alertas_generado_en`). Primera vez,
`GET /v1/alerts` (foto completa); después, `GET /v1/alerts?desde=<generado_en anterior>`. Si la respuesta trae
`completo = true`, se reemplaza la caché; si no, se actualiza, se quitan las que llegan con `activa = false` y se
borran los ids de `eliminadas`. **Cuándo sincroniza:** al arrancar la app (Inicio), al volver la conexión y como mucho
una vez cada 5 minutos mientras está en primer plano. La vigencia se evalúa al anunciar. **Dónde se anuncian:** en el
mapa público (`MapaPublicoScreen`, ruta `mapa`, posición por PDR) desde FE-3.1; en el Resultado (6.3) desde FE-3.2;
en la navegación (6.5) con FE-5.1.

**Editor de alertas (7.8)**: los UUID siguen generándose en la app. «Guardar / Sincronizar» envía los pendientes
con `POST /v1/admin/alerts/sincronizar`; cada id sale de «pendientes» solo si su resultado es `ok`. Para no perder la
operación, los pendientes deben guardar **qué** cambió (crear o editar → `upsert`; borrar → `eliminar`), no solo el id
(hoy `EditorMapaViewModel` guarda solo ids; §5.5).

### 5.11 Validadores de la app

El contrato común (nombres, argumentos, códigos de salida, informe, reglas de datos de prueba) está en
`INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Aquí solo lo propio de la app.

- **Dónde corren:** en la máquina de desarrollo, desde `FRONTEND_KOTLIN/project/`, con Python 3.12 (`pyproject.toml`
  propio, grupo `ops`). No forman parte del APK.
- **Qué usan:**
  - `./gradlew` para compilar y ejecutar pruebas unitarias (`testDebugUnitTest`), instrumentadas
    (`connectedDebugAndroidTest`, con `AccessibilityChecks` en las vistas públicas) y `lint`.
  - `adb` contra un **dispositivo físico** conectado (`ANDROID_SERIAL` si hay varios) para instalar el APK de depuración,
    leer archivos privados de la app con `run-as` (por ejemplo, comprobar que no quedan fotos de escaneo) y leer
    `files/logs/app.log`.
  - Comprobaciones estáticas sobre el código (buscar archivos, permisos o URLs que no deben estar).
  - La API de `dev` del backend (`VALIDACION_API_URL`, `VALIDACION_ADMIN_CORREO`, `VALIDACION_ADMIN_PASSWORD`, igual que
    los validadores del backend) para preparar datos de prueba y comprobar lo que la app envió.
- **Entornos:** `local` = sin dispositivo ni backend: compilación, pruebas unitarias en la JVM (el cliente HTTP se prueba
  con MockWebServer) y comprobaciones estáticas; `dev` = dispositivo físico con la app apuntando a `dev`. La app no se
  conecta a un backend local: solo usa HTTPS (§5.10). Los lotes se cierran con `dev`.
- **Pruebas instrumentadas:** `connectedDebugAndroidTest` instala el APK de pruebas y **al terminar desinstala la app y
  borra sus datos** (recorridos sin subir, calibración). Un validador que la use lo dice en sus precondiciones y pide
  confirmación si encuentra recorridos con `photos[].sync = pendiente`.
- **Argumentos propios:** los lotes que trabajan sobre un recorrido real lo indican con `--video <nombre>` (contrato
  común, infra §5.11).
- **Comprobaciones manuales:** son frecuentes en la app (caminar con el PDR, TalkBack, modo avión). El validador las
  lista con instrucciones precisas y la evidencia esperada (capturas, video corto o el registro de pruebas en
  dispositivo), que se adjunta al PR.
- **Datos de prueba:** los mismos prefijos `validacion-` en lo que el validador o la persona nombran (lugares, alertas,
  videos de prueba); los recorridos reales del campus son dataset y se quedan. En el dispositivo, el validador borra
  los datos de la app con `pm clear` solo si su documento lo indica. La cuenta `validacion+user@campus.edu.co` se crea,
  reactiva y desactiva como en backend §5.11 (en la app, con `crear_usuario_validacion` y
  `desactivar_usuario_validacion` de `comun.py`, desde FE-1.2).

**Dónde se ejecutan hoy (FE-1.1; FE-1.2 añade la CLI `aws`)**: en WSL (`uv`, `terraform`, `gh`, `aws` v2), llamando por
*interop* al Gradle y al `adb` de Windows, porque el JDK, el SDK y el USB del teléfono están en Windows (§4.1). Las
llamadas a AWS (FE-1.2: identidad, secreto del admin, tareas sueltas de `migrate`, logs) usan la CLI `aws` de WSL con
`AWS_PROFILE`, no boto3 (ADR-FE-15). Variables:

| Variable | Uso | Valor en la máquina del equipo (WSL) |
|---|---|---|
| `VALIDACION_GRADLE` | Comando para Gradle, separado por espacios (no admite rutas con espacios). Por defecto `cmd /c gradlew.bat` en Windows y `bash gradlew` en el resto | `cmd.exe /c .\gradlew.bat` |
| `JAVA_HOME` + `WSLENV` | JDK del Gradle de Windows; `WSLENV` pasa la variable tal cual al proceso de Windows | `JAVA_HOME='C:\Users\frank\.jdks\jbr-21.0.11'`, `WSLENV=JAVA_HOME:ANDROID_SERIAL` |
| `VALIDACION_ADB` | Comando para `adb`. Por defecto el `adb` del `PATH` o `$ANDROID_HOME/platform-tools/adb` | `/mnt/c/Users/frank/AppData/Local/Android/Sdk/platform-tools/adb.exe` |
| `ANDROID_SERIAL` | Elegir dispositivo si hay varios (también lo lee el `installDebug` de Gradle, por eso va en `WSLENV`) | — |
| `VALIDACION_API_URL` | URL base con `/v1`. Solo se usa si `terraform output` no está disponible (Terraform manda) | — |
| `AWS_PROFILE` | Leer `terraform output` (estado en S3) y, desde FE-1.2, la CLI `aws` (cuenta, secreto, `ecs run-task`, logs) | `campus-admin` |
| `VALIDACION_ADMIN_CORREO`, `VALIDACION_ADMIN_PASSWORD` | FE-1.2: credenciales del admin (hacen falta las dos). Si falta alguna y es `dev`, se leen de `campus-locator/dev/admin-inicial` (claves `correo` y `password`), como `credenciales_admin` del backend (§5.11 del backend) | — (se usa el secreto) |
| `UV_PROJECT_ENVIRONMENT` | Opcional: el `.venv` fuera de `/mnt/c` (más rápido) | `/root/.cache/uv-envs/fe-ops` |

**Entornos y códigos (lo propio de la app)**: en `local` las comprobaciones que necesitan teléfono o red se marcan
`omitida` con el motivo (no cuentan para el código). En las precondiciones, lo que falta en la máquina (Gradle, `adb`,
dispositivo, URL de la API) da **3**; solo «otro lote no está listo» (borde HTTPS sin respuesta, `GET /v1/health` sin
`200 ok`) da **2**. Se evalúan primero las de herramientas y después las de otros lotes. Los validadores imprimen las
manuales también en `local`.

**Ayudas comunes (`project/src/ops/comun.py`, FE-1.1).** Solo biblioteca estándar. Esta tabla basta para escribir un
validador nuevo sin leer el código; si cambian, se actualiza en el mismo cambio.

| Elemento | Qué hace |
|---|---|
| `Validador(lote=, validacion=, descripcion=, comprobaciones=[…], entornos=("local", "dev"), grupos={…})` | Ciclo de vida (infra §5.11). `comprobaciones`: IDs válidos para `--solo`; `grupos`: alias (`{"C4": ["C4a", "C4b"]}`). `v.correr(cuerpo, argv=None)` lee `--entorno`, `--informe`, `--solo`, `--sin-limpieza`, ejecuta `cuerpo(v)`, limpia (orden inverso, también si algo falló), escribe el informe y devuelve el código. Error de uso, entorno no admitido o excepción en `cuerpo` → 3. `v.entorno`, `v.sello` (`AAAAMMDD-HHMMSS` UTC) |
| `v.precondicion(id, fn)` → `bool` | `fn()` devuelve el detalle. `Bloqueo` o `Falla` → 2; `ErrorConfiguracion` → 3 |
| `v.precondicion_no_evaluada(id, motivo)`, `v.precondiciones_cumplidas()` | Las que dependen de una que falló; ¿pasaron todas? |
| `v.comprobacion(id, fn)` | `omitida` si `--solo` la excluye; `Falla` → `falla` (1); `ErrorConfiguracion` o imprevisto → `error` (3, con la traza en stderr). Mide `duracion_ms` |
| `v.omitir(id, motivo)` | Comprobación que no aplica en este entorno (estado `omitida`) |
| `v.incluida(id)`, `v.alguna_incluida(*ids)`, `v.manual(id, instruccion)`, `v.al_limpiar(descripcion, fn)` | Como en infra §5.11 |
| `Falla`, `Bloqueo`, `ErrorConfiguracion` | Excepciones que deciden el código |
| `ejecutar(comando, entrada=, timeout=300, cwd=PROYECTO, entorno=)` → `Resultado(codigo, salida, error)` (`.texto`) | Programa externo sin imprimir nada; no instalado → `ErrorConfiguracion`; *timeout* → `Falla` |
| `gradle(*args, timeout=1800)`, `comando_gradle()` | Gradle con `--console=plain` (ver `VALIDACION_GRADLE`) |
| `resultados_clase(clase, directorio=None)` → `ResultadoClase(clase, pruebas, fallos, errores, omitidas)` (`.ok` = ≥ 1 caso y 0 fallos y errores) o `None`; `archivo_resultados(clase)`, `borrar_resultados(clases)` | XML JUnit de `app/build/test-results/testDebugUnitTest/TEST-*.<clase>.xml` (por nombre simple). Borrar antes de ejecutar evita leer un resultado viejo y obliga a Gradle a repetir la tarea |
| `adb(*args, timeout=120)`, `comando_adb()` | `adb` con `-s $ANDROID_SERIAL` si está definida |
| `dispositivos(texto)`, `dispositivo_fisico()` → serial | Lee `adb devices`; sin dispositivo, varios sin `ANDROID_SERIAL`, estado distinto de `device` o emulador (`ro.kernel.qemu = 1`) → `ErrorConfiguracion` |
| `leer_archivo_app(ruta)` → `str \| None` | `adb exec-out run-as com.example.myapplication cat <ruta>` (solo APK de depuración); `None` si no existe |
| `url_api_config(ruta=API_CONFIG)` | `ApiConfig.BASE_URL` leída del código, resolviendo `$API_BASE_URL`; otra forma → `Falla` |
| `url_api_vigente()` → `(url, origen)` | `terraform output -raw api_base_url` + `/v1` o, sin Terraform, `VALIDACION_API_URL`; ninguna → `ErrorConfiguracion`. `comprobar_forma_url(url, origen)` exige `https://…/v1`; `normalizar_url` quita la barra final |
| `terraform_output_raw(nombre, directorio=DIR_TF_DEV)` | Una lectura del estado; sin `init` o sin credenciales → `ErrorConfiguracion` |
| `http_get(url, timeout=15)` → `RespuestaHttp(estado, encabezados, cuerpo, duracion_ms)` (`.json()`) | `GET` con `X-Request-Id` propio; 4xx/5xx se devuelven; sin respuesta → `ErrorRed` |
| `avisar`, `resumir`, `commit_actual()` | Progreso a stderr; recorte; commit corto con `-dirty` si hay cambios en archivos versionados de `project/` (con `core.autocrlf=input`, trampa abajo) |
| `PROYECTO`, `RAIZ_REPO`, `DIR_INFORMES`, `DIR_TF_DEV`, `API_CONFIG`, `DIR_RESULTADOS_PRUEBAS`, `PAQUETE`, `ACTIVIDAD` (`com.example.myapplication/.MainActivity`), `LOG_APP` (`files/logs/app.log`) | Constantes |

Ayudas que añadió FE-1.2 (para los validadores que inician sesión en el teléfono, usan la cuenta `user` de prueba o
llaman a AWS; FE-2.1, FE-2.2, FE-3.3, FE-3.4 y FE-4.1 las reutilizan):

| Elemento | Qué hace |
|---|---|
| `reloj()`, `dormir(s)` | `time.monotonic()` y `time.sleep()` detrás de una función: las pruebas los sustituyen por un reloj falso (dormir avanza el reloj). Todo lo que espera en `comun` y `validate12` los usa |
| `lote_hecho(texto_plan, lote)` → `bool`; `PLAN_APP` | ¿La fila `\| <lote> \| <fase> \| Hecho \| …` de la tabla de estado de un PLAN dice «Hecho» en la tercera celda? (una fila de §2.1 no cuenta). `PLAN_APP` = `FRONTEND_KOTLIN/docs/PLAN.md` |
| `http_post_json(url, cuerpo, timeout=15)` → `RespuestaHttp`; `codigo_error(r)` → `str \| None` | `POST` JSON con `X-Request-Id` propio; 4xx/5xx se devuelven, sin respuesta → `ErrorRed`. Un `429` **de API Gateway** (cuerpo `{"message"}`) se reintenta tras 1, 2 y 4 s (el login tiene *throttling* de 2 req/s). Nunca imprime el cuerpo enviado. `codigo_error` = `error.codigo` de §5.1 del backend |
| `aws(*args, timeout=120)` → `Resultado`; `aws_json(*args, accion=, timeout=120, mostrar_error=True)` → JSON | CLI `aws` con `--region us-east-1 --output json --no-cli-pager` (perfil de `AWS_PROFILE`). En `aws_json`: credenciales o permisos (`AccessDenied*`, `ExpiredToken`, `InvalidClientTokenId`, `UnrecognizedClientException`, «Unable to locate credentials», perfil inexistente…) → `ErrorConfiguracion`; otro error → `ErrorAws(mensaje, codigo)` (hereda de `Falla`; `.codigo` = el de AWS, p. ej. `ResourceNotFoundException`). `mostrar_error=False` deja en el mensaje solo el código (para comandos con secretos en los parámetros) |
| `cuenta_aws()` → ARN | `aws sts get-caller-identity`; cuenta distinta de `CUENTA` (`648617469176`) → `ErrorConfiguracion` |
| `terraform_outputs(directorio=DIR_TF_DEV)` → `{nombre: valor}` | `terraform output -json` (los valores, sin el envoltorio `{"value": …}`); sin `init` o sin credenciales → `ErrorConfiguracion`. Nunca se imprime |
| `leer_secreto(secreto, lote="INF-1.2")` → `dict` | `secretsmanager get-secret-value --query SecretString`; no existe → `Bloqueo` del `lote`; sin permiso → `ErrorConfiguracion`; no es un objeto JSON → `ErrorConfiguracion` |
| `credenciales_admin(entorno)` → `(correo, password)` | `VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` si están las dos; si no y es `dev`, las claves `correo` y `password` de `SECRETO_ADMIN` (`campus-locator/dev/admin-inicial`); si no, `ErrorConfiguracion` |
| `salidas_tarea(outputs)` → `(cluster, familia, red)` | De los outputs de infra §5.2: `ecs_cluster`, `familias_tarea["migrate"]` y la red de `run-task` (`subredes_tareas` + `sg_migrate`, `assignPublicIp = ENABLED`). Si falta alguno → `Bloqueo` (INF-1.1/INF-1.3) |
| `tarea_cli(outputs, argumentos, entorno=None, leer_log=True, limite_s=900)` → `ResultadoTarea(arn, id, codigo, motivo, eventos)` | `python -m app.cli <argumentos>` en una tarea suelta de la última revisión ACTIVA de `campus-locator-dev-migrate` (Fargate, `--started-by validacion-app`, contenedor `app`). `entorno` va en `containerOverrides.environment` por un archivo temporal (`--overrides file://…`, permisos 600), nunca en la línea de comandos ni en mensajes; queda visible en `describe-tasks` para quien tenga acceso a la cuenta: solo valores de prueba. Espera con `aws ecs wait tasks-stopped` (máx. 10 min del *waiter*) y lee con `describe-tasks --query` solo `exitCode` del contenedor `app` y `stoppedReason` (no trae los *overrides*). Con código ≠ 0 lee `LOG_MIGRATE` (`/campus-locator/dev/migrate`, stream `migrate/app/<id>`, hasta 6 intentos con 5 s) y guarda en `eventos` los `evento` de sus líneas JSON (`eventos_log(mensajes)`) |
| `motivo_tarea(t)` | Texto para un detalle: código, eventos de fallo (`usuario_rechazado`, `usuario_no_encontrado`, `comando_fallido`, `configuracion_incompleta`, `base_no_disponible`) y `stoppedReason` |
| `crear_usuario_validacion(outputs)` → contraseña; `desactivar_usuario_validacion(outputs, tolerar_inexistente=True)` → detalle; `USUARIO_VALIDACION`, `NOMBRE_USUARIO_VALIDACION` | `crear-usuario --correo validacion+user@campus.edu.co --nombre validacion-user --rol user` con `CREAR_USUARIO_PASSWORD = validacion-pw-<uuid4>` (crea o reactiva; la contraseña se devuelve y nunca se imprime) y `desactivar-usuario --correo …`; `Falla` con `motivo_tarea` si no dan 0 (con `tolerar_inexistente`, «no existe» —1 con `usuario_no_encontrado`— no es fallo). Tardan ~1–2 min cada una |
| `exigir_adb_permitido(r, que)`; `MENSAJE_SEGURIDAD_MIUI` | Si la salida de adb trae `SecurityException`, `INJECT_EVENTS`, `GRANT_RUNTIME_PERMISSIONS` o `Permission Denial` → `ErrorConfiguracion` «el teléfono no deja a adb `<que>`… en MIUI/HyperOS activa «Depuración USB (Configuración de seguridad)»…». La usan `tocar`, `escribir_texto`, `tecla`, `desplazar_hacia_abajo` y el `pm grant` de `validate12` |
| `Nodo(texto, descripcion, clase, limites, habilitado, contrasena)` (`.centro`, `.es_campo`, `.dice(v)`, `.contiene(f)`); `parsear_ui(xml)` → `list[Nodo]` | Un nodo de `uiautomator dump`: `text`, `content-desc`, `class`, `bounds` (`(x1, y1, x2, y2)`), `enabled`, `password`. `dice` = texto o descripción igual; `es_campo` = clase `…EditText`. XML roto → `Falla` |
| `volcar_pantalla(intentos=3)` → `list[Nodo]`; `RUTA_UI` | `adb exec-out "uiautomator dump /data/local/tmp/validacion-ui.xml 2>&1; cat …; rm -f …"` (una sola orden: el volcado puede llevar lo escrito en un campo y no queda en el teléfono). Toma el XML desde `<hierarchy` (antes llega «UI hierchary dumped to: …»). Reintenta con 1 s si no sale; si no → `Falla`, con «could not get idle state» en el mensaje si uiautomator lo dijo |
| `textos_visibles(nodos, limite=12)` | Textos de la pantalla para un diagnóstico, **sin** campos de texto ni contraseñas |
| `tocar(nodo)`, `tecla(codigo)` (`TECLA_ATRAS = "4"`), `teclado_visible()`, `tamano_pantalla()`, `desplazar_hacia_abajo()` | `input tap` en el centro; `input keyevent`; `dumpsys input_method` contiene `mInputShown=true` (o `mIsInputViewShown`/`isInputViewShown`); `wm size` (el `Override size` si existe); `input swipe` del 70 % al 30 % del alto por el centro (300 ms) |
| `escapar_input_text(texto)`; `escribir_texto(texto)` | Escape para `adb shell input text`: espacio → `%s`; lo que no sea `[A-Za-z0-9@._-+,:=/]`, con `\` delante (el `sh` del teléfono lo deja literal). Un texto con `%s` no se puede escribir (`input` lo vuelve espacio) y uno con caracteres no ASCII imprimibles tampoco → `ErrorConfiguracion` (sin el texto en el mensaje). `escribir_texto` nunca imprime el texto ni la salida de adb |
| `abrir_app()` | `am force-stop` + `am start -W -n ACTIVIDAD` (arranque en frío: `MyApp` borra la sesión) |
| `esperar_nodo(encontrar, limite_s, que)` → `(nodo, nodos)`; `primero(nodos, dice=, contiene=)`; `campos_texto(nodos)` | Vuelca cada ~1 s hasta que `encontrar(nodos)` dé un nodo (puede lanzar `Falla` para abortar antes); si no, `Falla` «en N s no apareció `<que>`; en pantalla: …». `campos_texto` = los `EditText` de arriba abajo |
| `abrir_login(limite_s=30)` | `abrir_app()`, espera y toca «Acceso administrador» (Inicio), espera Login (dos campos e «Iniciar sesión»). Los permisos de Inicio deben estar concedidos antes (si no, el diálogo del sistema tapa Inicio) |
| `enviar_credenciales(correo, password)` → instante del toque | Toca el primer campo y escribe el correo, toca el segundo y escribe la contraseña, toca «Iniciar sesión» (si el teclado tapa el campo o el botón, Atrás **solo si** `teclado_visible()`); devuelve `reloj()` justo antes del toque. Botón deshabilitado → `Falla` |
| `CUENTA`, `REGION`, `SECRETO_ADMIN`, `LOG_MIGRATE` | Constantes (`648617469176`, `us-east-1`, `campus-locator/dev/admin-inicial`, `/campus-locator/dev/migrate`) |

Cambio de FE-1.2 en lo existente: `adb(…)` pasa la entrada estándar vacía (`entrada=""`), así `adb shell` no abre un
PTY (con PTY se mezclan stderr y stdout y los finales de línea pasan a `\r\n`).

Forma de un validador (`validate11.py` es el ejemplo): `import comun`, `main(argv=None)` crea el `Validador` y devuelve
`v.correr(cuerpo, argv)`, el módulo termina con `sys.exit(main())`. Sus pruebas (`tests/ops/test_validate11.py`)
sustituyen `comun.gradle`, `comun.adb`, `comun.http_get`, etc. con `monkeypatch` y recorren `main()` entero; corren en
el job `validadores` de `frontend.yml`. `uv run --frozen pytest` desde `project/` (29 casos al cerrar FE-1.1; 73 con
FE-1.2: `test_validate12.py` y `test_comun_login.py`).

**Detalles internos de los validadores**
- `ejecutar` añade al entorno del proceso hijo `TF_IN_AUTOMATION=1`, `TF_INPUT=0`, `NO_COLOR=1`, `GH_PAGER=` y
  `PAGER=cat`; decodifica la salida como UTF-8 con `errors="replace"`. `http_get` envía `User-Agent: validacion-app`
  y un `X-Request-Id` UUID propio.
- Estados en el informe: precondiciones `pasa`, `falla` o `no evaluada`; comprobaciones `pasa`, `falla`, `error`
  (código 3: `ErrorConfiguracion` o imprevisto) u `omitida`; manuales en la lista `manuales`. Línea en stdout:
  `[PASA]`, `[FALLA]`, `[ERROR]`, `[OMITIDA]`, `[NO EVALUADA]`, `[MANUAL]` y al final `Resultado: <resultado> (código N)`.
  Informe por defecto: `project/.validacion/<lote>-<sello>.json`.
- `validate11.py`: `CLASES_C2 = ["MapeoErroresApiTest", "MapeoDatosApiTest"]`; `ESPERA_C1A_S = 60` (lee `app.log`
  cada 3 s); `PATRON_SALUD` = `^(AAAA-MM-DD HH:MM:SS)\.mmm I/Api .*GET /v1/health -> (\S+)(?: \S+)? \((\d+) ms\)
  rid=(\S+)`; `lineas_salud(texto, desde)` → `[(hora, resultado, rid)]`; IDs `C1a, C2, C4a, C4b` con grupos `C1 →
  [C1a]` y `C4 → [C4a, C4b]`. Un validador nuevo copia esa forma: `Contexto` con lo que comparten las comprobaciones,
  una función por precondición y por comprobación.
- `validate12.py` (FE-1.2; es el ejemplo de un validador que maneja la interfaz del teléfono y usa la cuenta `user`):
  IDs `C1, C2, C3, C4` sin grupos. Constantes: `CLASE_C3 = "SesionVencidaTest"`, `CLASE_C4 = "RemoteAuthRepositoryTest"`,
  `MINIMO_CASOS` (4 y 3), `LIMITE_LOGIN_S = 15`, `INTENTOS_DESPLAZAR = 4`, `PERMISOS_INICIO` (`CAMERA`,
  `RECORD_AUDIO`) + `PERMISO_ACTIVIDAD` (`ACTIVITY_RECOGNITION`, solo con SDK ≥ 29, como `Permisos.INICIALES`),
  `ERRORES_LOGIN` (los títulos de banner «Credenciales inválidas», «Sin conexión», «Algo salió mal»: si aparecen, C1 o
  C2 fallan en el acto con ese texto). `saludo_esperado(nombre)` = «Hola, <antes del primer espacio>» o «Hola» (como
  `PanelAdminViewModel`). `Contexto`: `preparar_telefono()` (una vez: registra la limpieza `am force-stop`,
  `installDebug` —`INSTALL_FAILED_USER_RESTRICTED` → código 3 con «Instalar vía USB»— y `pm grant` de los permisos de
  Inicio con `exigir_adb_permitido`), `asegurar_usuario()` (una vez: registra `desactivar_usuario_validacion` **antes**
  de lanzar `crear-usuario`, así la limpieza la desactiva aunque la creación falle a medias) y `pruebas()` (una sola
  ejecución de Gradle con las clases de C3 y C4 que estén incluidas). P3 (AWS) solo se evalúa si C2 está incluida;
  con `--solo` sin C2 queda «no evaluada». Las pruebas (`tests/ops/test_validate12.py`) simulan el teléfono entero
  (clase `Telefono`: pantallas Inicio, Login y Panel en XML de uiautomator, `input tap/text/keyevent/swipe`, `pm grant`
  con o sin `SecurityException`, teclado que tapa el botón) y sustituyen `comun.tarea_cli`, `comun.reloj` y
  `comun.dormir`; comprueban además que la contraseña, el token y `validacion-pw-` no salen ni por stdout, ni por
  stderr, ni en el informe.
- `pyproject.toml`: `requires-python >= 3.12`, `[tool.uv] package = false`, grupos `ops = []` y `dev = [pytest>=8.3,
  ruff>=0.8]`; ruff con `line-length = 120`, `target-version = "py312"`, reglas `E, F, W, I, B, UP` sobre
  `src/ops/**` y `tests/**`; pytest con `testpaths = ["tests"]` y `pythonpath = ["src/ops"]` (por eso las pruebas
  hacen `import comun`). Un validador que necesite una biblioteca la añade al grupo `ops` y regenera `uv.lock`
  (`uv lock`).

**Trampas de los validadores**
- **`cmd.exe` desde WSL no busca en el directorio actual** (`NoDefaultCurrentDirectoryInExePath=1`): `cmd.exe /c
  gradlew.bat` falla con «no se reconoce como un comando»; hay que escribir `.\gradlew.bat`. Y `VALIDACION_GRADLE` se
  separa por espacios, no con `shlex`, para no comerse la barra invertida.
- `adb.exe` de Windows se ejecuta desde WSL sin problema; el teléfono debe estar conectado a Windows y con la
  depuración USB autorizada.
- La hora de `app.log` es la del teléfono: C1a compara contra `adb shell date`, no contra el reloj de la máquina.
- **Finales de línea:** la copia de trabajo de esta carpeta la sacó el Git de Windows (`core.autocrlf=true`: archivos
  con CRLF, índice con LF). El Git de WSL, sin esa opción, ve ~100 archivos de `project/` como modificados (comprobado
  el 2026-10-25). Por eso `commit_actual()` usa `git -c core.autocrlf=input status …` (así solo cuenta los cambios
  reales) y **los commits de esta carpeta se hacen con el Git de Windows** o con `-c core.autocrlf=input` en WSL.
- **MIUI/HyperOS (Xiaomi):** además de «Instalar vía USB» (sin ella `installDebug` da `INSTALL_FAILED_USER_RESTRICTED`,
  FE-1.1), `pm grant` e `input` exigen **«Depuración USB (Configuración de seguridad)»** en Opciones de desarrollador;
  sin ella fallan con `SecurityException` (`GRANT_RUNTIME_PERMISSIONS`, `INJECT_EVENTS`). `exigir_adb_permitido` lo
  convierte en código 3 con la solución. MIUI suele pedir una cuenta Mi y SIM para activarla (sin comprobar en el
  Xiaomi del equipo).
- **`uiautomator dump` solo vuelca lo visible:** omite los nodos fuera de la pantalla (p. ej. «Cerrar sesión» al pie del
  Panel), por eso C1 desliza hasta 4 veces. Compose expone el árbol **sin fusionar**: el texto de un botón es un nodo
  hijo (`TextView text="Iniciar sesión"`) y el botón (`android.widget.Button`) no tiene texto; tocar el centro del
  hijo pulsa el botón. Por lo mismo, `enabled` del hijo puede decir `true` aunque el botón esté deshabilitado (el
  control de `enviar_credenciales` solo detecta el caso contrario). Un `EditText` de Compose lleva en `text` lo escrito
  (por eso `textos_visibles` omite los campos y `volcar_pantalla` borra el XML del teléfono en la misma orden).
  `uiautomator dump` espera a que la interfaz quede quieta (hasta ~10 s); si una animación sin fin sigue mandando
  eventos de accesibilidad, responde «ERROR: could not get idle state» y no vuelca nada. Inicio tiene un orbe
  animado: que no lo provoque está **sin comprobar** en el teléfono (en las capturas de FE-1.1 «Acceso administrador»
  se ve sin desplazar).
- **`input text` y el `sh` del teléfono:** `adb shell input text X` une los argumentos y los pasa a `sh -c` en el
  teléfono: sin escapar, `$`, `'`, `;`, `&`… se interpretan; y `input` cambia cada `%s` por un espacio (no hay forma de
  escribir un `%s` literal). Probado con un `sh` de Linux (`test_comun_login.py`); **sin comprobar** con `"` o `\` a
  través del `adb.exe` de Windows llamado desde WSL (las contraseñas que usa el validador son alfanuméricas con `-`).
- **Teclado en pantalla:** al escribir, el teclado puede tapar el segundo campo o «Iniciar sesión». `enviar_credenciales`
  pulsa Atrás solo si `dumpsys input_method` dice `mInputShown=true` (con el teclado cerrado, Atrás volvería a Inicio).
  El nombre exacto de ese campo en el Android del Xiaomi está **sin comprobar**.
- **CLI `aws`:** `aws ecs wait tasks-stopped` se rinde a los 10 min (100 × 6 s) con código 255; `get-log-events` puede
  devolver vacío los primeros segundos (por eso los reintentos). `run-task` recibe la contraseña de `crear-usuario` por
  archivo y su error se resume solo con el código de AWS (`mostrar_error=False`).

---

## 6. Especificación de vistas públicas

> Para todas: alto contraste, textos grandes, botones de mínimo 64 dp, `contentDescription`
> completo, y cada mensaje importante se lee en voz alta automáticamente.

### 6.1 Inicio — `ui/inicio/InicioScreen.kt`

![alt text](<../assets/inicio.png>)

**Propósito:** punto de entrada. Permite elegir entre ubicarse o ir a un lugar.

**Elementos:**
- Título de la app y mensaje de bienvenida (se lee por voz al abrir): *"Di uno para saber
  dónde estás, o dos para ir a un lugar."*
- **Botón grande 1: "Ubicarme"** (ocupa ~40 % de la pantalla). Acción: iniciar flujo 2.1.
- **Botón grande 2: "Ir a un lugar"** (ocupa ~40 % de la pantalla). Acción: abrir selección
  de destino.
- **Indicador de escucha por voz** (micrófono animado + texto "Te escucho…") que muestra
  cuando la app está atenta al comando.
- Botón de **micrófono** para activar/reactivar la escucha manualmente.
- Botón pequeño de **Ajustes** (esquina).
- Acceso discreto a **"Acceso administrador"** (texto pequeño/ícono) que lleva a Login.
- Indicador de **estado de conexión** con el backend.

**Comportamiento:**
- Al abrir, lee las instrucciones y empieza a escuchar.
- Reconoce "uno", "dos" y sinónimos ("ubicarme", "ir a").
- Si no entiende, repite las opciones.
- Pide los permisos (cámara, micrófono, actividad física) en un único diálogo del sistema la
  primera vez. *Pendiente (FE-3.5):* la explicación hablada previa al diálogo.

---

### 6.2 Ubicarse (escaneo 360°) — `ui/ubicacion/EscaneoScreen.kt`

![alt text](<../assets/ubicarse.png>)

**Propósito:** guiar al usuario para dar la vuelta completa mientras la app captura
5 fotos automáticamente.

**Elementos:**
- **Vista previa de la cámara** (apoyo visual para quien ve; el usuario no la necesita).
- **Indicador circular de progreso de giro** (anillo de 0° a 360°) con 5 marcas que se
  llenan al capturar cada foto.
- **Contador de fotos**: "Foto 2 de 5".
- **Texto de instrucción grande**: "Gira lentamente hacia la derecha", "Más despacio",
  "Mantén el celular vertical".
- **Indicador de inclinación del teléfono** (si no está vertical, avisa).
- Botón **"Cancelar"** (grande, siempre visible).
- Botón **"Repetir"** (aparece si falla). Abre una carpeta de escaneo nueva.
- Animación/estado de **"Analizando…"** tras la quinta foto, mientras se espera al backend.

**Comportamiento:**
- Instrucciones por voz al entrar. Un sonido/vibración corto confirma cada captura.
- Se captura automáticamente según los grados girados (rotation vector), una foto cada 72°.
- Avisos hablados si gira demasiado rápido o si el celular no está vertical.
- **Control de calidad: desactivado temporalmente.** Toda foto que CameraX guarda se acepta;
  no se emiten avisos de imagen borrosa/oscura. `camera/CalidadImagen.kt` se conserva sin
  usar, para reactivarlo más adelante.
- Al completar la vuelta, avisa *"Listo, analizando"* y navega a Resultado.
- Estados de error: sin conexión, tiempo agotado, vuelta incompleta.

**Almacenamiento de las fotos:**
- Cada escaneo crea su propia carpeta, nombrada con la fecha y hora de inicio:
  `files/camera/photos/<yyyy-MM-dd_HH-mm-ss>/` (almacenamiento privado de la app).
- Dentro: `escaneo_1.jpg` … `escaneo_5.jpg`.
- Se conservan solo los **20 escaneos más recientes**; los más antiguos se borran al crear
  una carpeta nueva (`crearCarpetaEscaneo`).
- La constante `CONSERVAR_FOTOS` (en `EscaneoViewModel.kt`) decide si las fotos se borran al
  cancelar, repetir o salir de la pantalla. Hoy está en `true` (no se borran) para depurar.
  **Debe ponerse en `false` antes de publicar** (decisión abierta 12, FE-3.2).
- Para verlas: Device Explorer de Android Studio o `adb` (ver "Registro de eventos (logs) y
  depuración", en la §3.2).

**Módulos que lo implementan:**

| Archivo | Responsabilidad |
|---|---|
| `ui/ubicacion/EscaneoScreen.kt` | Pantalla: conecta permisos, sensor, cámara, carpeta del escaneo y ViewModel |
| `ui/ubicacion/EscaneoViewModel.kt` | Lógica del giro, disparo de fotos y backend (sin control de calidad por ahora) |
| `ui/ubicacion/EscaneoState.kt` | Estado (`EscaneoUiState`) y eventos (`EscaneoEvento`) |
| `ui/ubicacion/EscaneoConfig.kt` | Parámetros ajustables y paleta |
| `ui/ubicacion/EscaneoBackend.kt` | Contrato con el backend (stub temporal) |
| `ui/ubicacion/FeedbackCaptura.kt` | Vibración y sonido de confirmación |
| `ui/ubicacion/componentes/` | `VistaCamara`, `AnilloProgreso`, `PanelesEscaneo` |
| `camera/CapturaFoto.kt` | Captura automática y creación de la carpeta de cada escaneo |
| `camera/CalidadImagen.kt` | Control de calidad (**sin uso por ahora**) |
| `sensors/OrientationProvider.kt` | Acimut y cabeceo del rotation vector |
| `logs/AppLog.kt` | Registro de eventos (ver §3.2) |

---

### 6.3 Resultado de ubicación — `ui/ubicacion/ResultadoUbicacionScreen.kt`

![alt text](<../assets/resultados_de_ubicacion.png>)

**Propósito:** informar dónde está el usuario y qué hacer después.

**Elementos:**
- **Texto principal grande** con la ubicación: *"Estás cerca de la biblioteca"*.
- **Descripción de referencias**: *"El bloque de los trillizos está a tu derecha"*.
- **Mapa del campus** con el punto del usuario, flecha de orientación y puntos de interés
  cercanos.
- **Indicador de confianza** (alta/media/baja) en texto simple.
- **Alertas cercanas** (si hay alguna dentro del radio): se muestran y se leen después de la ubicación, ej. *"Ten cuidado, hay un lago alrededor de la biblioteca"*.
- Botón **"Repetir en voz alta"**.
- Botón **"Ir a un lugar desde aquí"** (→ Selección de destino, con posición ya fijada).
- Botón **"Volver a ubicarme"** (si la confianza es baja o el usuario no está de acuerdo).
- Botón **"Volver al inicio"**.

**Comportamiento:** lee el resultado automáticamente. Si la confianza es baja, lo dice y
sugiere repetir la vuelta. Cuando esta vista se usa como paso previo a la navegación, tras
confirmar avanza automáticamente a la guía.

---

### 6.4 Selección de destino — `ui/destino/SeleccionDestinoScreen.kt`

![alt text](<../assets/seleccion_de_destino.png>)

**Propósito:** elegir el lugar al que se quiere ir.

**Elementos:**
- Pregunta hablada y escrita: *"¿A dónde quieres ir?"*
- **Botón de micrófono grande** para dictar el destino.
- **Texto reconocido** mostrado en pantalla.
- **Diálogo de confirmación**: *"¿Quieres ir a la biblioteca? Di sí o no."* con botones
  Sí / No grandes.
- **Lista de lugares** (alternativa táctil): buscador + lista con nombre y categoría,
  ordenada por cercanía/popularidad.
- **Chips de categorías** (biblioteca, cafetería, baños, bloques…).
- Botón **Volver**.

**Comportamiento:** coincidencia aproximada con los nombres de lugares; si hay varias
coincidencias, las lee y pide elegir. Tras confirmar, si aún no hay ubicación vigente,
lanza el escaneo 360° y luego la navegación.

**Implementación actual:** con una lista de lugares de prueba (stub). Lo que falta (backend real con distancias,
fotos de los lugares, orden por popularidad y pasar el destino a la vista 6.5) está en `PLAN.md`, lotes FE-3.1 y FE-3.2.

**Voz:** usa el mismo `VoiceController` de Inicio y Escaneo. Si se negó el micrófono, la vista
funciona solo con toques y muestra un aviso. Tocar, pausar o salir invalida el flujo hablado en
curso (ver patrón de token en 5.2).

**Varias coincidencias:** si lo dicho se parece a 2 o 3 lugares, se leen y se muestran como botones
para elegir.

**Navegación:** al confirmar emite `DestinoEvento.Confirmado(lugar)`. Hoy `AppNav` abre `ubicarme`
(**TODO, FE-3.2:** pasar el destino y abrir la vista 6.5 tras el escaneo; ver decisión abierta 15).

**Módulos que lo implementan:**

| Archivo | Responsabilidad |
|---|---|
| `ui/destino/SeleccionDestinoScreen.kt` | Pantalla (`SeleccionDestinoScreen`: permiso de micrófono, ciclo de vida, navegación), contenido sin estado (`SeleccionDestinoContent`), `DestinoAcciones` y preview |
| `ui/destino/SeleccionDestinoViewModel.kt` | Flujo hablado (preguntar → escuchar → confirmar sí/no), búsqueda, filtros y orden |
| `ui/destino/SeleccionDestinoState.kt` | Estado (`DestinoUiState`), `OrdenLugares`, `ErrorDestino` y evento `DestinoEvento.Confirmado` |
| `ui/destino/componentes/` | `PanelesVoz` (barra, micrófono, texto reconocido, confirmación, opciones), `ListaLugares` (chips, buscador, lista, botón Volver) y `Comun` (tarjeta, íconos por categoría) |
| `domain/usecase/BuscarLugares.kt` | Coincidencia aproximada, filtro del buscador e interpretación de "sí" / "no" |
| `domain/model/LugarDestino.kt` | `LugarDestino` y `CategoriaLugar` |
| `data/repository/LugaresRepository.kt` | Contrato (`GET /v1/places`) y stub temporal (**TODO:** reemplazar por un `Remote*` en `data/remote/` sobre `ClienteApi`, §5.10) |

---

### 6.5 Navegación guiada — `ui/navegacion/NavegacionScreen.kt`

![alt text](<../assets/navegacion_guiada.png>)

**Propósito:** guiar en tiempo real hasta el destino.

**Elementos:**
- **Instrucción actual en texto muy grande**: "Sigue recto 20 m", "Gira a la izquierda".
- **Flecha direccional grande** indicando hacia dónde avanzar respecto a la orientación
  actual.
- **Distancia restante** y **tiempo estimado**.
- **Nombre del destino**.
- **Mapa** con ruta, posición actual, orientación y destino (vista de apoyo).
- **Banner de alerta de obstáculo** (ámbar/rojo, alto contraste, aparece sobre todo lo demás)
  con **el mensaje escrito por el admin** y el ícono según el tipo, ej. *"Ten cuidado, hay
  bancas cerca, no te vayas a estrellar"*. Se mantiene visible unos segundos o hasta que el
  usuario se aleje.
- **Marcadores de alertas** en el mapa de apoyo (las cercanas a la ruta).
- Botón **"Repetir alerta"**.
- **Indicador de estado de seguimiento**: precisión estimada y cuándo se hizo la última
  corrección visual (discreto).
- Botón **"Repetir instrucción"** (grande).
- Botón **"Pausar"** / **"Reanudar"**.
- Botón **"Cancelar ruta"** (con confirmación).
- Botón **"No sé dónde estoy / Reubicarme"** (lanza un escaneo 360° nuevo).
- Vista previa de cámara pequeña/oculta (la captura es automática y en segundo plano).

**Comportamiento:**
- Instrucciones por voz y vibración: patrón distinto para izquierda, derecha, giro y
  llegada.
- Posición actualizada por PDR y corregida con fotos automáticas.
- Cuando la posición del usuario entra al radio de una alerta, se lee el mensaje por voz y
  se vibra; las de prioridad alta tienen máxima prioridad en la cola de voz. Cada alerta se
  anuncia una vez por aproximación.
- Recalcula la ruta si el usuario se desvía y lo informa.
- Avisos si hay poca confianza en la posición o pérdida de conexión (continúa con PDR).
- Al llegar, navega a la vista de Llegada.

---

### 6.6 Llegada — `ui/navegacion/LlegadaScreen.kt`

![alt text](<../assets/llegada.png>)

**Propósito:** confirmar que se llegó al destino.

**Elementos:**
- Mensaje grande: *"Has llegado a la biblioteca"* (se lee por voz).
- Descripción breve de lo que hay alrededor.
- Botón **"Ir a otro lugar"**.
- Botón **"Volver al inicio"**.
- Pregunta opcional de retroalimentación: *"¿Llegaste bien?"* (Sí / No) para mejorar el
  sistema.

---

### 6.7 Ajustes — `ui/ajustes/AjustesScreen.kt`

![alt text](<../assets/ajustes.png>)

**Propósito:** personalizar la experiencia.

**Elementos:**
- **Velocidad de la voz** (slider + botón de prueba).
- **Volumen de avisos / voz**.
- **Intensidad de vibración** (apagada / suave / fuerte).
- **Detalle de las instrucciones** (breve / detallado).
- **Unidad de distancia**: metros / pasos.
- **Anticipación de alertas** (avisar más lejos / más cerca) y opción de repetir alertas ya anunciadas.
- **Idioma de voz**.
- Botón **"Probar voz"**.
- Información de la app / versión.

Todos los controles deben ser operables por TalkBack y con áreas grandes.

---

## 7. Especificación de vistas de administración

> Estas vistas las usa un administrador vidente, por lo que pueden ser más densas
> visualmente, pero deben seguir siendo claras y usables en el celular mientras camina.

### 7.1 Login — `ui/auth/LoginScreen.kt`

![alt text](<../assets/login.png>)

**Propósito:** autenticar al administrador para habilitar las vistas `admin/*`.

**Elementos:**
- **Logo** (pin con órbita, dibujado en `Canvas`), nombre "Campus Navi" y lema.
- Campo **correo o usuario**.
- Campo **contraseña** con botón mostrar/ocultar.
- Botón **"Iniciar sesión"** (se deshabilita si hay campos vacíos o mientras carga).
- **Indicador de carga**: "Verificando credenciales…".
- **Mensajes de error** (uno a la vez, con `BannerEstado`):
  - *Credenciales inválidas* (rojo).
  - *Sin conexión* (ámbar).
  - *Sin permisos*, si la cuenta no tiene rol `ADMIN` (rojo).
  - *Algo salió mal*, para errores inesperados (rojo).
- Botón **"Volver al inicio"** al flujo público.

**Comportamiento:**
- Al iniciar sesión se llama a `POST /v1/auth/login` (token + rol + `expira_en`; real desde FE-1.2,
  `RemoteAuthRepository`, 5.6).
- **Rol `ADMIN`:** se guarda la sesión (con su `expira_en`) y se navega a `admin/panel`, quitando Login de la
  pila de navegación.
- **Sesión vencida o rechazada (FE-1.2):** una sesión con `expira_en` pasado cuenta como «sin sesión» sin llamar al
  backend, y un `401 TOKEN_EXPIRADO`/`TOKEN_INVALIDO`/`NO_AUTENTICADO` en `/v1/admin/…` o `/v1/collect/…` cierra la
  sesión; en los dos casos, desde una pantalla `admin/…` la app vuelve a Login sin cerrarse (5.3, 5.8).
- **Rol distinto de `ADMIN`:** se informa que no tiene permisos, **no se guarda la sesión**
  y no se habilita el panel.
- Si al abrir Login ya existe una sesión `ADMIN` guardada, se entra directo al panel. (Solo dentro
  de la misma ejecución: `MyApp` borra la sesión cada vez que la app arranca desde cero; ver 5.3.)
- La sesión se guarda cifrada (`EncryptedSharedPreferences`, llave en Android Keystore).
  `SessionManager.cerrarSesion()` borra token y datos; se invoca desde el botón
  **Cerrar sesión** del Panel admin (vista 7.2).
- No se registran tokens ni credenciales en los logs.
- Al tocar los campos, el error se limpia. Se envía con el botón o con "Listo" del teclado.

**Accesibilidad:** los banners y el indicador de carga son *live regions* (TalkBack los
anuncia al aparecer); el botón de contraseña describe su acción ("Mostrar/Ocultar
contraseña"); botones y campos de 64 dp o más.

**Módulos que lo implementan:**

| Archivo | Responsabilidad |
|---|---|
| `ui/auth/LoginScreen.kt` | Pantalla (`LoginScreen`) y contenido sin estado (`LoginContent`), con previews |
| `ui/auth/LoginViewModel.kt` | Estado (`LoginUiState`), errores (`LoginError`), evento `IrAlPanel` y lógica del login |
| `ui/components/BannerEstado.kt` | Banner de error/advertencia reutilizable |
| `session/SessionManager.kt`, `session/AlmacenSesion.kt` | Sesión cifrada: `guardar`, `obtener` (vencida = `null`), `esAdmin`, `cerrarSesion` |
| `session/VigilanteSesion.kt` | Sin sesión en una ruta protegida: `VigilanteSesion`, `MotivoSinSesion`, `EventosSesion` (5.3) |
| `data/repository/AuthRepository.kt` | Contrato del login (`AuthRepository`) y el stub de antes (sin uso) |
| `data/remote/RemoteAuthRepository.kt` | Login real: `POST /v1/auth/login` (FE-1.2, §5.10) |
| `domain/model/Usuario.kt` | `Rol` (USER/ADMIN), `Usuario`, `Sesion` (con `expiraEnMs`) |

**Navegación:** ruta `login` en `AppNav` (`MainActivity.kt`); conexiones en §5.8.

---

### 7.2 Panel admin — `ui/admin/panel/PanelAdminScreen.kt`

![alt text](<../assets/panel_admin.png>)

**Propósito:** hub del administrador.

**Elementos:**
- **Encabezado**: avatar, saludo con el primer nombre del admin ("Hola, Alejandro"), rol
  ("Administrador del sistema") y botón de **Ajustes** (esquina superior derecha, lleva a la
  vista pública 6.7).
- **Tarjetas de acceso** (cuadrícula de 2 columnas): **Recolector de imágenes** (destacada),
  **Lugares**, **Mapa y alertas**, **Imágenes**, **Videos**, **Estadísticas**. Cada una muestra
  ícono, título, descripción corta y chevron.
- **Resumen rápido**, con 5 datos:
  - total de fotos del dataset,
  - lugares registrados,
  - alertas activas,
  - último video recolectado (número y fecha/hora, ej. "12 · Hoy, 09:24"),
  - fotos pendientes de subir.
- Chip **"En tiempo real"** (solo aparece cuando el resumen cargó correctamente).
- Botón **Cerrar sesión**.
- Botón **Volver a modo público**.
- Pie con nombre del panel y versión de la app.

**Comportamiento:**
- **Guarda de rol:** al abrir el panel se verifica la sesión. Si no hay sesión `ADMIN` (o venció: FE-1.2), se
  redirige a Login.
- **Cerrar sesión:** llama a `SessionManager.cerrarSesion()` (borra token y datos) y regresa
  a Inicio. No pide confirmación.
- **Volver a modo público:** regresa a Inicio **sin** cerrar la sesión.
- **Resumen:** mientras carga muestra "—". Si falla, muestra "No se pudo cargar el resumen"
  con botón **Reintentar**.
  - Totales, lugares, alertas y último video vienen del backend (`GET /v1/admin/stats`).
  - Las **fotos pendientes** vienen de la **cola local de subida** (`data/local`), no del backend.
- Los números se formatean según el idioma del teléfono (puede verse "2.842" o "2,842").
- Cada tarjeta navega a su vista:

  | Tarjeta | Ruta | Vista |
  |---|---|---|
  | Recolector de imágenes | `admin/ubicacion-manual` | 7.3 |
  | Lugares | `admin/lugares` | 7.6 |
  | Mapa y alertas | `admin/mapa` | 7.8 |
  | Imágenes | `admin/imagenes` | 7.11 |
  | Videos | `admin/videos` | 7.13 |
  | Estadísticas | `admin/estadisticas` | 7.15 |
  | Ajustes (ícono) | `ajustes` | 6.7 |

**Accesibilidad:** cada tarjeta es un solo elemento para TalkBack (título + descripción); cada
dato del resumen se lee completo ("2.842 fotos en el dataset"); botones de 64 dp o más.
Los tamaños de texto están pensados para pantallas de ~400 dp de ancho y respetan la escala
de fuente del sistema; las tarjetas crecen en alto si el texto se agranda.

**Módulos que lo implementan:**

| Archivo | Responsabilidad |
|---|---|
| `ui/admin/panel/PanelAdminScreen.kt` | Pantalla (`PanelAdminScreen`), contenido sin estado (`PanelAdminContent`), `PanelAcciones` y previews |
| `ui/admin/panel/PanelAdminViewModel.kt` | Estado (`PanelUiState`), eventos (`SesionCerrada`, `SinSesion`), carga del resumen y cierre de sesión |
| `data/repository/AdminRepository.kt` | Contrato del resumen (`AdminRepository`) y stub temporal (**TODO:** reemplazar por la implementación real) |
| `domain/model/ResumenAdmin.kt` | Modelo del resumen: 6 campos que dan los 5 datos del panel (el último video usa número y fecha) |
| `ui/theme/CampusColors.kt` | Colores compartidos de las vistas admin |
| `session/SessionManager.kt` | Lectura de la sesión (nombre, rol) y `cerrarSesion()` |

**Navegación:** ruta `admin/panel`; a qué ruta lleva cada tarjeta está en la tabla de arriba y las conexiones en §5.8.

---

### 7.3 Ubicación manual inicial — `ui/admin/recoleccion/UbicacionManualScreen.kt`

![alt text](<../assets/ubicacion_manual_iniciada.png>)

**Propósito:** fijar la coordenada exacta de partida antes de recolectar.

**Elementos:**
- **Mapa del campus a pantalla casi completa**, con zoom y desplazamiento.
- **Marcador arrastrable** (o toque para colocarlo) que representa dónde está parado.
- **Selector de orientación**: flecha rotatoria o botón "Usar brújula del teléfono" para
  fijar hacia dónde mira.
- Campos de **coordenadas** (x, y / lat, lon) mostrados y editables.
- Botón **"Usar mi última posición"** (para continuar desde el final del video anterior; crea un video nuevo).
- Fila **"Calibrar mi paso"** (vista 7.3b): muestra la longitud de paso en uso (calibrada o genérica de 0,72 m) y abre la calibración.
- Botón **"Confirmar y comenzar"**: crea el nuevo video (ej. `video3`) y empieza la recolección.
- Campo opcional **nombre del video** (por defecto autonumerado).
- Botón **Cancelar**.
- Mensaje de ayuda: "Colócate en un punto reconocible y marca tu posición exacta".

**Implementación actual (2026-10-11):** en `ui/admin/recoleccion/UbicacionManualScreen.kt`
(con `UbicacionManualViewModel.kt` y `UbicacionManualState.kt`) y su mapa `assets/ubicacion_manual.html` +
`ubicacion_manual.js` (compila y se ha abierto en dispositivo, 2026-10-12; el JS pasó `node --check`; ⚠ sin prueba funcional completa).
Detalle de piezas y cuidados en 5.5 («UbicacionManual»).

- **Mapa** Leaflet/OSM con **marcador arrastrable** (o toque para colocarlo), flecha de rumbo y etiquetas de
  los lugares conocidos (`LugaresRepository`). «Centrar» y +/− los dibuja Compose encima del `WebView`.
- **Orientación:** dial que se gira con el dedo (con acciones de TalkBack de ±15° y «Apuntar al norte») y botón
  «Usar brújula del teléfono» (`EscucharOrientacion`; norte **magnético**). Sin sensor de rotación el botón
  queda deshabilitado y queda el dial.
- **Coordenadas** (lat/lng, 6 decimales) **editables** en un diálogo; acepta coma o punto y valida ±90 / ±180.
- **«Usar mi última posición»:** copia punto y rumbo de la última foto del video más reciente; **no** confirma sola.
  Deshabilitado si no hay videos anteriores.
- **«Calibrar mi paso»** (2026-10-12): fila bajo «Usar mi última posición» que muestra la longitud en uso («0,72 m (valor genérico)» o «… (calibrada)»)
  y navega a `admin/calibracion` (7.3b). La longitud se lee al abrir la pantalla; al volver de la calibración se relee.
- **Nombre del video** autonumerado (`video_N`, constante `PREFIJO_VIDEO`; máx. 40 caracteres); vacío = el sugerido.
- **«Confirmar y comenzar»** deshabilitado hasta que haya punto. **No crea el video:** emite
  `UbicacionManualEvento.Confirmado(InicioRecoleccion)` (`domain/model/InicioRecoleccion.kt`).
- **Se quitó el botón GPS** de esta vista: ya no aplica aquí (decisión abierta 14 sigue abierta para `MapaPublicoScreen`).

Del diseño no se hicieron la **foto de referencia** ni el **badge de brújula «N»** (no hay especificación de la
foto; Leaflet no rota el mapa). «Confirmar y comenzar» **ya entrega** `InicioRecoleccion` a la vista 7.4 por
`SesionDeRecoleccion` (5.6, decisión abierta 15) y `AppNav` navega a `admin/recoleccion` (5.8). Lo pendiente de esta vista está en `PLAN.md` (FE-2.3 y FE-4.3).

---

### 7.3b Calibración de la longitud de paso — `ui/admin/calibracion/CalibracionScreen.kt`

*(Vista nueva sin diseño de referencia: no hay imagen en `assets/`. Se llega desde la fila «Calibrar mi paso» de 7.3.)*

**Propósito:** medir la longitud de paso **real del admin** con **una sola pasada** sobre un tramo de distancia conocida, para que el PDR
convierta pasos en metros con su paso y no con el valor genérico (0,72 m). Es la respuesta a la decisión abierta 16.

**Flujo (fases `PUNTOS → LISTO → CAMINANDO → RESULTADO → GUARDADA`):**
1. **Marcar el tramo:** el admin toca el mapa para fijar **A** (inicio) y **B** (fin); ambos se pueden arrastrar. La distancia A→B sale de la
   fórmula de haversine. «Limpiar puntos» los borra. Recomendado un tramo de **30 m o más** (mínimo 10 m).
2. **Inicio:** fija la posición del PDR en A, arranca el contador de pasos y anota los pasos de partida.
3. **Caminar** de A a B **como lo hará al recolectar** (mismo ritmo y forma de llevar el teléfono). Se muestran tramo, pasos y tiempo.
4. **Fin:** pasos = (`PdrEstado.pasos` al final) − (al inicio); `longitud = distancia / pasos`.
5. **Resultado:** si es válido muestra la longitud (y, solo como información, cadencia y velocidad); el admin puede **Guardar**, **Repetir** o
   cancelar. **Restablecer** vuelve al valor genérico de 0,72 m.

**Validación** (orden: tramo → pasos → rango): tramo ≥ 10 m, ≥ 15 pasos y longitud entre 0,40 y 1,20 m. Los umbrales de 10 m y 15 pasos son
**elección propia** (constantes de `CalibracionPaso`); el rango viene del encargo. Un valor guardado fuera de rango se ignora.

**Qué hace con el resultado:** se guarda en el dispositivo (`SharedPreferences` `campus_calibracion`) y **reemplaza** el valor genérico: al
crear un `PdrTracker`, la longitud se lee una sola vez, y de ahí en adelante `distanciaMetros = pasos × longitud calibrada` en la
recolección (7.4: contadores, disparador por distancia, deriva y trayectoria), sin más cambios (5.2).

**Implementación actual (2026-10-12):** construida en cinco baches (C1–C5).

| Módulo | Archivos | Detalle |
|---|---|---|
| Dominio | `domain/usecase/CalibracionPaso.kt` (`CalibracionPaso`, `ResultadoCalibracion`, `MotivoInvalido`) | Lógica pura; 5.7 |
| Almacenamiento | `data/repository/CalibracionPasoRepository.kt` | `SharedPreferences`; 5.6 |
| PDR | parches a `sensors/PdrEngine.kt` y `sensors/PdrTracker.kt` | `LONGITUD_PASO_DEFECTO_M` y parámetro `longitudPasoM`; 5.2 |
| Estado y lógica | `ui/admin/calibracion/CalibracionState.kt`, `CalibracionViewModel.kt` | Su propio `PdrTracker`; 5.5 |
| Mapa A→B | `assets/calibracion_mapa.html`, `assets/calibracion_mapa.js`, `ui/admin/calibracion/componentes/MapaCalibracion.kt` | Puente `CalibracionBridge` (5.5 y 5.9) |
| Pantalla | `ui/admin/calibracion/CalibracionScreen.kt` | Sin scroll: el mapa ocupa el espacio sobrante (mín. 180 dp) |
| Pruebas | `test/.../domain/usecase/CalibracionPasoTest.kt` | JUnit4, **no ejecutado en Gradle** |
| Navegación | `MainActivity.kt` (`Permisos.ACTIVIDAD`, ruta `admin/calibracion`), punto de entrada en `UbicacionManualScreen.kt` | 5.3 y 5.8 |

**Verificado:** `CalibracionPaso.kt` y `PdrEngine.kt` compilan con kotlinc 2.0.21 y pasan 13 comprobaciones (haversine ≈ 33,4 m para
0,0003° de latitud; `longitud = distancia/pasos`; los cuatro motivos de rechazo; límites 0,40 y 1,20 m válidos; `duracionS = 0` sin
romper; sin posición no cuenta pasos; `distancia = pasos × longitud inyectada`; valor por defecto 0,72). El proyecto compila con todas las
piezas y la pantalla se abre en dispositivo desde 7.3. **Error corregido en dispositivo:** el mapa salía en negro porque
`calibracion_mapa.js` llamaba a `base.crearMapa(...)` (no existe) en vez de `MapaBase.crearMapa(...)` (5.9).
⚠ **Falta la prueba funcional completa:** calibrar en un tramo de ≥ 30 m, guardar, iniciar una recolección y comprobar que
`distanciaMetros ≈ pasos × longitud guardada` y que el disparador de 5 m dispara cada ≈ `5 / longitud` pasos.

**Decisiones tomadas:**
- **Calibración por dispositivo con una sola pasada A→B**, no por cadencia ni por altura: resuelve la decisión abierta 16 (longitud de paso).
- La longitud se **inyecta en `PdrTracker`** (parámetro del constructor) y se lee **una sola vez, al crearlo**: recalibrar no cambia un tracker ya creado.
- La calibración usa **su propio `PdrTracker`** y mide por **resta** de `PdrEstado.pasos` (Fin − Inicio), porque `PdrEngine.onPaso` no cuenta pasos sin posición inicial.
- Valor genérico por defecto **0,72 m** (`PdrEngine.LONGITUD_PASO_DEFECTO_M`). El encargo decía 0,70 m: **sin confirmar**; basta cambiar la constante.
- Almacén `SharedPreferences` sin cifrar (`campus_calibracion`; claves en 5.6). No es un dato sensible y no hay un almacén genérico de preferencias.
- Pantalla **sin scroll**: un `WebView` dentro de un scroll vertical se pelea con el arrastre del mapa.

**Limitaciones conocidas:**
- ⚠ **Recalibrar tras el cambio de detector (2026-10-12):** una longitud guardada con el sensor de hardware ya no sirve; el detector por acelerómetro cuenta distinto. Hasta recalibrar, `distanciaMetros` puede salir sesgada. Como ya hay una sola fuente de pasos, desaparece el riesgo de calibrar con una y recolectar con otra (antes pendiente: guardar la `FuentePasos`).
- La precisión depende de **marcar bien A y B**: con ~2 m de error total, un tramo de 10 m da hasta ~20 % de error y uno de 30 m, ~7 %.
- **Sin internet el mapa no carga** y no se pueden marcar A y B: la calibración es inutilizable sin mapa (decisión 13).
- **No corrige la deriva de la brújula** ni hace fusión (`domain/fusion/`).

Las tareas pendientes (probar la pasada completa en dispositivo, ejecutar `CalibracionPasoTest`, promediar varias
pasadas y la relación con la unidad «metros / pasos» de Ajustes) están en `PLAN.md` (FE-2.3, FE-4.3 y FE-4.2).

---

### 7.4 Recolección en curso — `ui/admin/recoleccion/RecoleccionScreen.kt`

![alt text](<../assets/recoleccion_en_curso.png>)

**Propósito:** recolectar fotos con coordenadas mientras el admin camina.

**Elementos:**
- **Mapa en vivo** con la trayectoria recorrida, la posición actual y la orientación, y
  los puntos donde ya se tomaron fotos (marcadores/heatmap de cobertura).
- **Vista previa de cámara** (pequeña, esquina).
- **Contadores**: fotos tomadas, distancia recorrida, pasos, duración del video.
- **Indicador de calidad del seguimiento** (precisión estimada / deriva acumulada).
- **Indicador de captura automática** (parpadeo al tomar cada foto).
- Botón **"Pausar / Reanudar"**.
- Botón **"Reubicarme manualmente"** (re-anclar en el mapa para corregir el error
  acumulado).
- Botón **"Marcar punto de interés"** (asocia la coordenada actual a un lugar existente
  o nuevo).
- Botón **"Agregar alerta aquí"**: abre el formulario de alerta (vista 7.9) con la coordenada
  actual ya cargada; el admin escribe o dicta el mensaje y guarda sin interrumpir la
  recolección.
- Las **alertas ya existentes** se muestran en el mapa en vivo.
- Botón **"Finalizar video"** (con confirmación).
- **Nombre del video actual** visible en la parte superior (ej. "video3").
- Ajustes rápidos: intervalo de captura automática (por tiempo/distancia).
- Alertas: foto borrosa, poca luz, batería baja, almacenamiento bajo.

**Comportamiento:** actualiza la coordenada con PDR y toma fotos automáticamente
guardándolas con coordenada y orientación; guarda localmente de forma continua para no
perder datos si la app se cierra; mantiene la pantalla activa y funciona en primer plano.

**Implementación actual (2026-10-11):** construida en cinco baches. Compila y funciona según quien la escribió
(sin pruebas automáticas). Diseño: `assets/recoleccion_en_curso.png`.

| Módulo | Archivos | Detalle |
|---|---|---|
| Dominio | `domain/model/FotoRecolectada.kt` (`FotoRecolectada`, `DatosFoto`, `ResumenRecoleccion`), `domain/model/SesionRecoleccion.kt` (`SesionDeRecoleccion`), `domain/usecase/DisparadorCaptura.kt` (`DisparadorCaptura`, `ModoCaptura`, `Deriva`) | 5.6 y 5.7 |
| Almacenamiento | `data/repository/RecoleccionRepository.kt` (`RecoleccionRepositoryLocal`) | `files/recoleccion/<rec_NNNN>/` (5.6) |
| Estado y lógica | `ui/admin/recoleccion/RecoleccionState.kt`, `RecoleccionViewModel.kt` | Dueño del PDR (5.2, «Flujo de captura de la recolección») |
| Mapa en vivo | `assets/recoleccion_mapa.html`, `assets/recoleccion_mapa.js`, `ui/admin/recoleccion/componentes/MapaRecoleccion.kt` | Puente `RecoleccionBridge` (5.5 y 5.9) |
| Pantalla | `ui/admin/recoleccion/RecoleccionScreen.kt`, `componentes/PanelesRecoleccion.kt` | Dueña de CameraX (5.5) |
| Navegación | `MainActivity.kt` (`AppNav`) | Rutas `admin/recoleccion` y `admin/recoleccion/resumen` (5.8) |

**Qué incluye la implementación actual:** mapa en vivo (posición con rumbo, trayectoria, fotos tomadas y alertas), vista previa
de cámara, los cuatro contadores (fotos de 200, distancia, pasos, duración), calidad del seguimiento (precisión y deriva),
indicador de captura (destello y «Foto tomada»), Pausar / Reanudar, **Reubicarme manualmente** (alfiler arrastrable en el mapa),
**Agregar alerta aquí** (con `AlertaFormSheet`), **Finalizar video** (con confirmación), nombre del video, intervalo de captura
(cada 3, 5 o 10 m, o cada 3 o 5 s; por defecto 5 m) y avisos de batería baja y almacenamiento bajo. Se guarda en disco **de forma
continua** (`manifest.json` actualizado en cada foto) y la pantalla se mantiene encendida; en segundo plano (`ON_STOP`) la grabación se pausa sola.

**Decisiones tomadas:**
- **Datos entre vistas con un holder en memoria** (`SesionDeRecoleccion`), no argumentos de ruta: resuelve la decisión abierta 15 para este flujo (7.3 → 7.4 → 7.5).
- **Almacenamiento propio** (`RecoleccionRepository`), separado de `VideoRepository`: éste es la fuente de verdad (futuro `RemoteVideoRepository`); no se amplió como pedía 5.6. Ver «Pendiente» más abajo.
- Fotos y manifest en `files/recoleccion/<rec_NNNN>/photos/NNNN.jpg` y `manifest.json` (misma forma que `assets/videos/`); prefijo `rec_` para no chocar con los datos de prueba (`vid_`); fechas en ISO-8601 (`yyyy-MM-dd'T'HH:mm:ssXXX`).
- Deriva estimada = 4 % de la distancia desde el último ancla (heurística provisional; decisión abierta 16).
- **Distancia = pasos × longitud de paso calibrada** (7.3b; 0,72 m si no hay calibración): el `PdrTracker` de 7.4 la lee una vez al crearse, así que calibrar **antes** de entrar a 7.4.

**Pendiente:** está en `PLAN.md`: FE-2.1 (subida y vista 7.5, ver lo recolectado en Galería y Videos), FE-3.3
(alertas existentes y persistencia de las nuevas), FE-3.4 («Marcar punto de interés»), FE-2.3 (retomar tras matar el
proceso) y FE-4.3 (control de calidad de imagen y detalles de diseño).

---

### 7.5 Resumen de video — `ui/admin/recoleccion/ResumenVideoScreen.kt`

![alt text](<../assets/resumen_de_video.png>)

**Elementos:**
- Nombre del video (editable) y estadísticas: duración, distancia, nº de fotos.
- **Mapa con la trayectoria final** y cobertura.
- **Revisión rápida de fotos** (carrusel) con opción de descartar.
- Botón **"Subir y procesar"** (con barra de progreso y estado por foto: pendiente /
  subida / embedding generado / error).
- Botón **"Guardar y subir después"**.
- Botón **"Descartar video"** (con confirmación; borra el video y todas sus fotos locales).
- Opción de **corregir la trayectoria** (re-anclar puntos) antes de subir.

---

### 7.6 Lista de lugares — `ui/admin/lugares/LugaresScreen.kt`

![alt text](<../assets/lista_de_lugares.png>)

**Elementos:**
- Barra de búsqueda y filtro por categoría.
- **Lista de lugares**: nombre, categoría, nº de fotos asociadas, coordenada.
- Botón flotante **"Nuevo lugar"**.
- Toque en un lugar → editar. Opciones: editar, eliminar (con confirmación), ver fotos.
- Alternar entre **vista de lista** y **vista de mapa**.

### 7.7 Formulario de lugar — `ui/admin/lugares/LugarFormScreen.kt`

![alt text](<../assets/formulario_de_lugar.png>)

**Elementos:**
- Campos: **nombre**, **sinónimos/alias** (para el reconocimiento de voz), **descripción**
  (texto que se lee al usuario), **categoría**.
- **Selector de coordenada en mapa** (punto de llegada/entrada del lugar).
- **Referencias cercanas** (texto para describir alrededores).
- Fotos asociadas (lista, solo lectura o con enlace a galería).
- Botones **Guardar** / **Cancelar** / **Eliminar**.
- Validaciones (nombre único, coordenada obligatoria).

---

### 7.8 Editor de mapa y alertas — `ui/admin/mapa/EditorMapaScreen.kt`

![alt text](<../assets/editor_de_mapa_y_alertas.png>)

**Propósito:** permitir al admin modificar el mapa agregando, moviendo, editando y eliminando
alertas de obstáculo (y visualizando lugares). El mapa es **OpenStreetMap en línea con Leaflet**,
dentro de un `WebView` (ver 2.6); el formulario de alerta (7.9) es nativo.

**Elementos:**
- **Cabecera**: botón Atrás, título y chip de estado: **"Cambios pendientes (n)"** (ámbar) o
  **"Todo sincronizado"** (verde).
- **Marcadores de alertas** con ícono según tipo y color del borde según prioridad (rojo = Alta,
  ámbar = Normal); las inactivas se ven atenuadas. Al tocar un marcador se abre una **tarjeta**
  con tipo, prioridad, mensaje, posición, radio de activación y los botones Mover / Editar /
  Eliminar.
- **Círculo del radio de activación** de la alerta seleccionada. El radio se cambia desde el
  formulario (7.9) y el círculo se redibuja en vivo.
- Botón flotante **"Nueva alerta"** → modo colocar: se toca el mapa para fijar el punto y se
  abre el formulario de alerta.
- **Mover** una alerta desde su tarjeta: el marcador se vuelve arrastrable (ver detalle abajo).
- **Selector de capas** (alertas, lugares, cobertura de fotos, rutas). *Cobertura y rutas ya
  tienen su interruptor, pero todavía no se cargan datos.*
- **Filtros** desplegables: tipo, prioridad y estado.
- Botón **"Mi posición"** (centra el mapa en la posición actual del admin).
- Botón **"Ver lista"** (arriba a la derecha y abajo) → Lista de alertas (7.10).
- Botón **Guardar / Sincronizar** con un punto indicador (ámbar con pendientes, verde sin ellos).
- **Atribución "© OSM"** visible en el mapa (obligatoria por la licencia de OpenStreetMap).

**Comportamiento:** guardar, mover o eliminar se aplica al instante en el mapa y queda como
cambio pendiente; **"Guardar / Sincronizar"** los envía al backend, y desde ahí se propagan a
los dispositivos de los usuarios en su siguiente sincronización.

**Detalle de la implementación:**
- **Local primero:** guardar, mover o eliminar una alerta se aplica de inmediato en el repositorio
  local y su `id` se agrega al conjunto de **pendientes** (el número del chip son alertas con
  cambios, no operaciones). "Guardar / Sincronizar" los envía; si falla, siguen pendientes. Si no
  hay pendientes, avisa "No hay cambios pendientes".
- **Colocar:** "Nueva alerta" activa el modo colocar (el botón pasa a "Cancelar"); el siguiente
  toque en el mapa fija el punto y abre el formulario de alerta (7.9).
- **Mover:** el botón "Mover" de la tarjeta vuelve arrastrable **solo ese marcador**; un aviso
  inferior ofrece "Listo" y "Cancelar" (cancelar restituye la posición original). La tarjeta se
  oculta mientras se mueve.
- **Borrador en vivo:** mientras el formulario está abierto, la alerta en edición se dibuja en el
  mapa con sus cambios (radio, prioridad, tipo) antes de guardarse. El ViewModel lo envía al mapa
  como `borradorJson`.
- Tocar el mapa vacío deselecciona. Eliminar pide confirmación (en la tarjeta y en el formulario).
- **Botón Atrás** (del sistema o de la cabecera): sale primero de los modos temporales, en este
  orden: mover → colocar → formulario abierto → alerta seleccionada. Si no queda ninguno y hay
  cambios sin sincronizar, pide confirmar antes de salir.
- Los filtros nunca ocultan la alerta seleccionada ni el borrador.
- Reglas: radio por defecto **15 m** (slider de 5 a 100 m, de 5 en 5); mensaje obligatorio,
  máximo **200 caracteres**.

**Módulos que lo implementan:**

| Archivo | Responsabilidad |
|---|---|
| `ui/admin/mapa/EditorMapaScreen.kt` | `EditorMapaScreen` (la que usa el NavHost: conecta ViewModel, formulario y navegación), `EditorMapaContent` (solo dibuja el mapa con `MapaWebView`), interfaz `EditorMapaEventos` y el puente `EditorPuente` |
| `ui/admin/mapa/EditorMapaViewModel.kt` | Estado (`EditorMapaUi`), formulario en edición, validación, pendientes y sincronización (**hoy simulada**) |
| `ui/admin/mapa/AlertaFormSheet.kt` | Formulario de alerta (vista 7.9), hoja inferior de Material 3 |
| `domain/model/Alerta.kt` | Modelos `Alerta` y `Lugar` |
| `app/src/main/assets/editor_mapa.html` | Interfaz del editor (estilos y estructura) |
| `app/src/main/assets/editor_mapa.js` | Capas, filtros, modos (colocar / mover) y borrador; usa `mapa_base.js` para el puente, `toast`, `confirmar`, medidas y mapa (5.9) |
| `app/src/main/assets/mapa_base.js` | Base común de las páginas de mapa: puente, `toast`, `dialogo`, medidas, `setInsets`, `onAtras` por defecto y mapa Leaflet (5.9) |
| `map/MapaWebView.kt` | `MapaWebView`, `MapaWeb` y `PuenteWeb`: la fábrica común del `WebView` de todos los mapas (5.9) |

**Puente WebView ↔ Android:** `EditorBridge`; funciones y formato de los datos en §5.9.

**Navegación:** ruta `admin/mapa`; parámetros y conexiones en §5.8.

**Requisitos:** `editor_mapa.html` y `editor_mapa.js` en la raíz de `assets/`, permiso `INTERNET`,
y conexión a internet (Leaflet y las teselas se descargan en línea; ver decisión abierta 13). Si
la página no carga, `EditorMapa` en Logcat muestra los errores del `WebView`.

**Pendiente:** `PLAN.md`, FE-3.3 (repositorio local y API real, posición real del admin, formulario completo) y
FE-4.1 (capas de cobertura y rutas).


### 7.9 Formulario de alerta — `ui/admin/mapa/AlertaFormSheet.kt`

![alt text](<../assets/formulario_de_alerta.png>)

Hoja inferior (bottom sheet) o diálogo reutilizable desde el editor de mapa y desde la
recolección.

**Implementación actual:** `ui/admin/mapa/AlertaFormSheet.kt` (mensaje, tipo, prioridad, radio, estado, validación
y eliminar con confirmación). Lo que falta (dictado por voz, «Escuchar cómo sonará», vigencia y «Ajustar en el mapa»)
está en `PLAN.md`, FE-3.3.

**Elementos:**
- **Campo de mensaje** (texto libre, multilínea) con botón de **dictado por voz**. Texto de
  ayuda: "Escribe exactamente lo que se le dirá al usuario".
  Ej.: *"Ten cuidado, hay bancas cerca, no te vayas a estrellar"*.
- Botón **"Escuchar cómo sonará"** (previsualiza el mensaje con la voz de la app).
- **Tipo** (selector): agua, mobiliario, escalones, obra, vehículos, otro.
- **Prioridad** (Normal / Alta).
- **Radio de activación** (slider en metros, con vista previa del círculo en el mapa).
- **Coordenada** (mostrada, con botón "Ajustar en el mapa").
- **Estado** (switch Activa/Inactiva).
- **Vigencia** opcional (fecha inicio/fin).
- Botones **Guardar**, **Cancelar**, **Eliminar** (con confirmación, solo si ya existe).
- Validaciones: mensaje obligatorio y de longitud razonable (para que se lea en pocos
  segundos), coordenada obligatoria.

### 7.10 Lista de alertas — `ui/admin/mapa/AlertasScreen.kt`

![alt text](<../assets/lista_de_alertas.png>)

**Elementos:**
- Buscador por texto del mensaje y filtros por tipo, prioridad y estado.
- **Lista**: ícono de tipo, mensaje (resumido), prioridad, radio, estado y fecha de
  modificación.
- Acciones por fila: **editar**, **activar/desactivar**, **ver en el mapa**, **eliminar**.
- Botón flotante **"Nueva alerta"**.
- Alternar a la **vista de mapa**.

### 7.11 Galería de imágenes — `ui/admin/imagenes/GaleriaScreen.kt`

![alt text](<../assets/galeria_de_imagenes.png>)

**Implementación actual:** con datos locales (`assets/`). Lo que falta está en `PLAN.md`, FE-4.1.

**Elementos:**
- **Encabezado**: contador de imágenes (según los filtros activos) y chip "Página x de y".
- **Búsqueda** por nombre de archivo, lugar o video, con botón para borrar el texto.
- **Filtros** (menús desplegables, opción "Todos/Todas" para quitarlos): **lugar**, **video**,
  **estado** (subida / procesada / error) y **calidad** (alta / normal / baja). Los filtros activos
  se resaltan. Cambiar un filtro vuelve a la página 1 y limpia la selección.
- **Cuadrícula** de 2 columnas. Cada tarjeta muestra la miniatura, el nombre del archivo, el lugar
  ("Sin lugar" si no tiene), el estado con punto de color (azul = subida, verde = procesada,
  rojo = error) y una estrella si es de alta calidad.
- **Selección múltiple**: pulsación larga sobre la tarjeta o toque en el círculo de la esquina.
  Con una selección activa, un toque alterna la foto en vez de abrirla, y el botón Atrás primero
  cancela la selección.
- **Barra de acciones en lote** (siempre visible, con el contador de seleccionadas): **Reasignar**
  (diálogo para escribir el lugar) y **Eliminar** (diálogo de confirmación). Se habilitan solo con
  al menos una foto seleccionada.
- **Paginación** de 24 fotos por página (`FOTOS_POR_PAGINA`), con paginador numérico (ej. `1 2 3 … 8`)
  visible solo si hay más de una página. No hay scroll infinito.
- **Alternar cuadrícula / mapa**. Hoy la opción Mapa muestra un mensaje provisional con el número de
  fotos filtradas.
- Toque en una foto (sin selección activa) → **Detalle de imagen** (vista 7.12).
- Estados vacíos: indicador de carga, mensaje de error con "Reintentar" y "No hay imágenes con estos
  filtros" con "Limpiar filtros".

**Accesibilidad:** botones y chips de 48 dp o más; cada tarjeta se lee como un solo elemento
(archivo, video, lugar, estado, calidad y si está seleccionada); la selección se hace con pulsación
larga, que TalkBack expone como acción ("Seleccionar"); el encabezado está marcado como título.

**Fuente de datos (provisional, local):** `AssetsVideoRepository` lee los videos empaquetados en
`app/src/main/assets/videos/<video_id>/`; estructura de carpetas y formato del `manifest.json` en §5.6
(«`VideoRepository` en detalle»).

**Módulos que lo implementan:**

| Archivo | Responsabilidad |
|---|---|
| `ui/admin/imagenes/GaleriaScreen.kt` | Pantalla (`GaleriaScreen`), contenido sin estado (`GaleriaContent`), `GaleriaAcciones` y previews |
| `ui/admin/imagenes/GaleriaViewModel.kt` | Estado (`GaleriaUiState`, `GaleriaFiltros`, `ModoVista`), filtros, búsqueda, selección, paginación y acciones en lote |
| `data/repository/VideoRepository.kt` | Contrato (`VideoRepository`) e implementación local (`AssetsVideoRepository`) (**TODO:** `RemoteVideoRepository`) |
| `domain/model/Foto.kt` | `Foto`, `Video`, `EstadoFoto`, `CalidadFoto` |

**Dependencia:** Coil para cargar imágenes (`io.coil-kt:coil-compose:2.7.0`); entiende las URLs
`file:///android_asset/...` y, más adelante, las URLs prefirmadas de S3.

**Navegación:** ruta `admin/imagenes`; conexiones en §5.8.

**Pendiente:** `PLAN.md`, FE-4.1 (vista de mapa, filtro por fecha, backend, navegar al detalle, «Subir imágenes»)
y FE-4.3 (paleta).

### 7.12 Detalle de imagen — `ui/admin/imagenes/DetalleImagenScreen.kt`

![alt text](<../assets/detalles_de_imagen.png>)

**Elementos:**
- Imagen grande con zoom.
- **Metadata**: coordenada, orientación, fecha/hora, **video al que pertenece** (enlace al detalle del video), dispositivo, estado de
  procesamiento/embedding.
- **Minimapa** con el punto donde se tomó.
- **Corregir coordenada** (arrastrar en el mapa).
- Campo de **notas**.
- Botones: **Eliminar**, **Reasignar a lugar**, **Reprocesar embedding**.

---

### 7.13 Lista de videos — `ui/admin/videos/VideosScreen.kt`

![alt text](<../assets/lista_de_videos.png>)

**Propósito:** ver todos los recorridos de recolección ("videos") y elegir uno para
inspeccionarlo o eliminarlo.

**Elementos:**
- **Lista de videos**: nombre (ej. "video1"), fecha, duración, distancia, nº de fotos y
  estado (en curso / pendiente de subir / procesado / con errores).
- **Minimapa o miniatura de trayectoria** por video.
- Ordenar por fecha / nombre / nº de fotos; buscador por nombre.
- Toque en un video → **Detalle de video** (vista 7.14).
- Acciones por fila (menú): **renombrar**, **reintentar subida**, **reprocesar
  embeddings**, **eliminar** (con la confirmación descrita en 7.14).
- Selector de videos para **comparar** cobertura (opcional): mostrar varios a la vez con
  distinto color.
- Indicador de videos pendientes sin sincronizar.
- Botón **"Nuevo video"** (lleva a la ubicación manual inicial).

---

### 7.14 Detalle de video — `ui/admin/videos/VideoDetalleScreen.kt`

![alt text](<../assets/detalle_de_video.png>)

**Implementación actual:** con datos locales (`assets/`). Lo que falta está en `PLAN.md`, FE-4.1.

**Propósito:** al seleccionar un video, ver en el mapa **SOLO las fotos de ese video** y
poder renombrarlo o eliminarlo por completo. Se llega desde la Lista de videos (7.13).

**Elementos:**
- **Mapa** (OpenStreetMap con Leaflet, dentro de un `WebView`, igual que 7.8) donde se dibujan
  **únicamente** las fotos del video: un **marcador numerado por foto** (1, 2, 3… en orden de
  captura) con una **flecha de orientación** (0° = norte, sentido horario; sin flecha si la
  foto no tiene rumbo) y la **trayectoria** que las une. Al abrir, el mapa se encuadra para
  mostrar todo el recorrido (solo la primera vez: editar no mueve el mapa).
- **Conmutador "Mostrar otros videos"** (apagado por defecto): dibuja las fotos de los demás
  videos como puntos grises tenues, solo como contexto. Con un único video no muestra nada.
- **Encabezado**: botón Atrás, nombre del video, fecha de creación, nº de fotos y distancia
  recorrida (suma de los tramos entre fotos consecutivas).
- Al tocar un marcador: **tarjeta de vista previa** con la miniatura, la coordenada (6
  decimales), la orientación (grados y punto cardinal, p. ej. "180° S") y los botones
  **"Ver detalle"** (→ Detalle de imagen, vista 7.12) y **"Eliminar foto"**.
- **Tira de miniaturas** del video, sincronizada con el mapa: al tocar una miniatura se
  selecciona y se centra el mapa en su marcador (en el área libre entre la cabecera y el panel
  inferior); al tocar un marcador, la tira se desplaza hasta su miniatura. Tocar el mapa vacío
  o la ✕ de la tarjeta deselecciona.
- Botón **"Renombrar"**: diálogo con el nombre actual; "Guardar" se habilita solo si el
  nombre no está vacío y cambió (máx. 40 caracteres).
- Botón **"Eliminar video"** (rojo, separado del resto para evitar toques accidentales).

**Flujo de eliminación del video:**
1. Diálogo que indica el alcance: *"Vas a eliminar «video1» y sus 6 fotos. Esto quitará esas
   fotos del sistema de ubicación y no se puede deshacer."*
2. Confirmación reforzada: hay que **escribir el nombre exacto del video**; el botón
   "Eliminar video" permanece deshabilitado hasta que coincida.
3. Aviso "Video eliminado" y regreso automático a la lista de videos.
4. *(Pendiente con backend, FE-4.1)* progreso del borrado (imágenes, embeddings e índice) y, si falla
   parcialmente, informar y permitir reintentar sin dejar fotos "huérfanas". En local el
   borrado es instantáneo y no puede fallar.

**Eliminar una foto:** botón en la tarjeta de vista previa, con confirmación. Si el video
queda con 0 fotos, se ofrece eliminarlo.

**Botón Atrás** (del sistema o de la cabecera): cierra primero el diálogo abierto, luego
deselecciona la foto y, si no queda nada, sale a la lista.

**Reglas:**
- Eliminar un video elimina **todas** sus fotos (y, con backend, sus embeddings y entradas del
  índice).
- No elimina alertas de obstáculo ni lugares.
- Los cambios se aplican de inmediato en la pantalla; el ViewModel los guarda en el
  repositorio y la Lista de videos (7.13) se refresca sola.

**Fuente de datos (provisional, local):** `AssetsVideoRepository` (ver 7.11) lee
`assets/videos/<video_id>/manifest.json`. Como los assets son de solo lectura, renombrar y
eliminar se guardan **en memoria** (`EdicionesLocales`, un objeto único del proceso): se
pierden al cerrar la app. Al cambiar algo, el repositorio emite por `cambios()` y las
pantallas abiertas (7.13 y 7.14) vuelven a cargar.

> `VideoRepository` ganó `renombrarVideo`, `eliminarVideo`, `eliminarFoto` y `cambios()`.
> Con el backend, `RemoteVideoRepository` los implementa con llamadas a la API y `EdicionesLocales`
> desaparece; las pantallas no cambian.

**Módulos que lo implementan:**

| Archivo | Responsabilidad |
|---|---|
| `ui/admin/videos/VideoDetalleScreen.kt` | `VideoDetalleScreen` (la que usa el NavHost: conecta ViewModel y navegación), `VideoDetalleContent` (solo dibuja el `WebView`) e interfaz `VideoDetalleEventos` |
| `ui/admin/videos/VideoDetalleViewModel.kt` | Carga el video y los demás, los serializa a JSON para el mapa y delega renombrar / eliminar foto / eliminar video al repositorio |
| `app/src/main/assets/video_detalle.html` | Interfaz (estilos y estructura): cabecera, tarjeta, tira de miniaturas y barra inferior |
| `app/src/main/assets/video_detalle.js` | Leaflet + OSM, marcadores con rumbo, trayectoria, selección sincronizada y diálogos; usa `mapa_base.js` para el puente, `toast`, `dialogo`, medidas y mapa (5.9) |
| `data/repository/VideoRepository.kt` | Contrato e implementación local (ver arriba) |
| `domain/model/Foto.kt` | `Video.distanciaMetros` (fórmula de haversine) |

**Puente WebView ↔ Android:** `VideoBridge`; funciones y formato de los datos en §5.9.

**Navegación:** ruta `admin/videos/{videoId}`; conexiones en §5.8.

**Requisitos:** `video_detalle.html` y `video_detalle.js` en la raíz de `assets/`, permiso
`INTERNET` y conexión a internet (Leaflet y las teselas se descargan en línea; ver decisión
abierta 13). Las fotos se cargan desde `file:///android_asset/...`. Si la página no carga,
`VideoDetalle` en Logcat muestra los errores del `WebView`.

**Accesibilidad:** botones de 48 dp o más (miniaturas de 64 dp); cada miniatura y marcador
lleva su número ("Foto 3 de 6"); los diálogos son `alertdialog` y el campo de texto recibe el
foco al abrir.

**Pendiente:** `PLAN.md`, FE-4.1.

---

### 7.15 Estadísticas — `ui/admin/estadisticas/EstadisticasScreen.kt`

![alt text](<../assets/estadisticas.png>)

**Elementos:**
- Filtro de periodo (hoy / 7 días / 30 días / personalizado).
- **Tarjetas resumen**: ubicaciones realizadas, rutas iniciadas, rutas completadas, tasa
  de éxito, confianza media.
- **Gráfico de barras**: lugares más buscados como destino.
- **Gráfico de líneas**: uso por día / tendencia.
- **Gráfico circular**: distribución por categoría de lugares.
- **Mapa de calor**: zonas donde más se ubican los usuarios y zonas con baja confianza
  (indica dónde falta recolectar fotos).
- **Alertas más activadas** (cuáles se anuncian más) y zonas con muchas alertas.
- Lista de **zonas con baja cobertura** o errores frecuentes.

---

## 8. Decisiones de diseño

### 8.1 Decisiones tomadas (ADR)

Registran decisiones que ya estaban aplicadas en el código o en este documento; su fecha está en `CHANGELOG.md`.

**ADR-FE-01 — Una sola app y un solo APK con flujo público y flujo de administración (aceptada).**
La interfaz de administración solo se habilita con una sesión de rol `ADMIN` (7.1, 7.2).

**ADR-FE-02 — Mapa base de OpenStreetMap con Leaflet dentro de un `WebView` (aceptada).**
Se descartó `eafit.mbtiles` porque no fue posible implementarlo (2.6). *Consecuencia:* el mapa depende de internet
(decisiones abiertas 1 y 13).

**ADR-FE-03 — Toda la lógica de pasos, rumbo y posición vive en Kotlin; las páginas web solo dibujan (aceptada).**
`PdrEngine` es el único sitio que calcula la posición (2.3, 5.2). No hay sensores web de respaldo.

**ADR-FE-04 — Los pasos salen siempre del acelerómetro (aceptada, 2026-10-12).**
`TYPE_STEP_DETECTOR` tardaba 1–3 s en reaccionar. *Consecuencia:* las longitudes de paso calibradas antes de ese
cambio deben rehacerse (7.3b).

**ADR-FE-05 — Longitud de paso calibrada por dispositivo con una pasada A→B (aceptada).**
Resuelve la decisión abierta 16 en lo que toca a la longitud (7.3b).

**ADR-FE-06 — Datos entre vistas de la recolección con un *holder* en memoria, `SesionDeRecoleccion` (aceptada).**
Resuelve la decisión abierta 15 para 7.3 → 7.4 → 7.5 (5.6, 5.8). El flujo público sigue abierto.

**ADR-FE-07 — Recolección «local primero» (aceptada).**
Se graba sin red en `files/recoleccion/` con un almacenamiento propio, separado de `VideoRepository`, y se sube al
terminar (7.5) con URLs prefirmadas del backend (backend ADR-BE-04, §5.10).

**ADR-FE-08 — Patrón de vista `Screen` / `Content` / `UiState` / `Evento` (aceptada).** §5.1.

**ADR-FE-09 — Base común para todas las páginas de mapa: `mapa_base.js` + `MapaWebView` (aceptada).** §5.9.

**ADR-FE-10 — La app adapta su lenguaje al contrato del backend en la capa `data/remote/` (aceptada, 2026-10-23).**
Enumerados en minúsculas, rumbo en norte verdadero [0, 360), fechas ISO-8601, rutas con `/v1` (§5.10). Los modelos de
dominio actuales no cambian salvo `EstadoFoto` (nuevo valor `PENDIENTE`).

**ADR-FE-11 — Control de calidad de imagen desactivado temporalmente (aceptada, provisional).**
`camera/CalidadImagen.kt` se conserva sin uso hasta que el flujo de captura esté estable (6.2, 7.4).

**ADR-FE-12 — Cliente HTTP: Retrofit + OkHttp + Gson (aceptada, 2026-10-25, FE-1.1).**
Opciones: Retrofit + OkHttp o Ktor Client. Se eligió Retrofit 2.11.0 sobre OkHttp 4.12.0 con el convertidor de Gson
porque OkHttp y Gson **ya estaban en el build** (no se añade un motor nuevo), las pruebas del cliente usan
**MockWebServer**, que es de OkHttp (§5.11 ya lo pedía), los encabezados de §5.10 (`X-Request-Id`, `Authorization`) son
interceptores de OkHttp de pocas líneas, y Retrofit da rutas declarativas con funciones `suspend`. Ktor habría
añadido su motor, su sistema de *plugins* y kotlinx.serialization (con su *plugin* de compilación) para lo mismo.
*Consecuencias:* las rutas devuelven `Response<T>` y pasan por `llamar` (§5.10); los DTOs deben ser anulables por cómo
crea objetos Gson; si algún día se activa R8 (`isMinifyEnabled`), los DTOs ya llevan `@SerializedName`, pero hará
falta revisar las reglas de Retrofit (sin comprobar).

**ADR-FE-13 — Solo HTTPS (aceptada, 2026-10-25, FE-1.1).**
El Manifest pasa a `android:usesCleartextTraffic="false"`: la API solo existe por HTTPS (infra §5.13) y las páginas
de `assets/` solo cargan recursos `https://` (Leaflet, fuentes, teselas). El valor `true` venía de un prototipo que
llamaba a una IP por `http://` (el antiguo `ApiConfig.PREDICT_URL`).

**ADR-FE-14 — La sesión perdida se resuelve en el cliente HTTP y se avisa con un evento global (aceptada, 2026-10-25,
FE-1.2).**
Hacía falta que un `401` de sesión en **cualquier** ruta `/v1/admin/…` o `/v1/collect/…`, y una sesión con `expira_en`
pasado, cerraran la sesión y volvieran a Login sin cerrar la app. Opciones: que cada ViewModel admin lo resolviera al
atrapar `ApiException(SesionVencida)`; o un único punto en OkHttp. Se eligió el interceptor (`SesionInterceptor`) más
un `VigilanteSesion` de lógica pura y un `EventosSesion` (`Channel`) que recoge `AppNav`: ningún lote siguiente puede
olvidarlo, la sesión vencida se detecta **antes** de enviar (no gasta una petición ni deja pasar un token caducado) y
se prueba en la JVM con MockWebServer (`SesionVencidaTest`). La navegación solo ocurre desde rutas `admin/…`, para no
llevar a Login a una persona del flujo público. Se separó el almacén (`AlmacenSesion`) de `SessionManager` para poder
probar la caducidad sin `EncryptedSharedPreferences`. *Consecuencias:* `ClienteApi.proveedorToken` desaparece
(`ClienteApi.vigilante`); `Sesion` lleva `expiraEnMs`; la caducidad depende del reloj del teléfono (5.3); un `401` de
un token anterior no cierra una sesión nueva.

**ADR-FE-15 — Los validadores llaman a AWS con la CLI `aws`, no con boto3 (aceptada, 2026-10-25, FE-1.2).**
`validate12.py` necesita la identidad, un secreto, tareas sueltas de ECS y sus logs. Los validadores de la app solo
usan la biblioteca estándar (grupo `ops` vacío, §5.11) y ya llamaban a programas externos (`terraform`, Gradle, `adb`);
la CLI `aws` v2 está en la máquina del equipo (WSL) y se sustituye fácil en las pruebas (`comun.aws`). boto3 habría
añadido una dependencia, su `uv.lock` y dobles de botocore. *Consecuencias:* hace falta `aws` v2 en el `PATH`; la
contraseña de `crear-usuario` va por un archivo temporal (`--overrides file://…`) y no por la línea de comandos; las
consultas usan `--query` (JMESPath) para no traer de vuelta los *overrides*.

### 8.2 Decisiones abiertas

La numeración se conserva: otras secciones y documentos citan «decisión abierta N».

1. **Proveedor y uso de teselas del mapa:** hoy se usa `tile.openstreetmap.org` directamente.
   El servidor público de OSM tiene una política de uso aceptable que **no está pensada para
   tráfico intensivo** de una app en producción. Antes de publicar, decidir si se mantiene, si
   se cambia a un proveedor de teselas con plan/clave propia o si se monta un servidor propio.
   Si el campus tiene interiores donde el mapa no llega, definir cómo se representan.
2. **Grafo de caminos:** para calcular rutas se necesita un grafo de zonas transitables.
   ¿Lo dibuja el admin en el editor de mapa (nueva herramienta), o se deriva de las
   trayectorias recolectadas? **Aplazada a la Fase 5** (backend ADR-BE-11; `GET /v1/route` reservado).
3. **Alertas de obstáculo:** son puntos manuales en el mapa con mensaje. **Radio por defecto: 15 m** (lo fija el
   contrato del backend, §5.5 de su documento). Queda por decidir si se anuncian solo las alertas cercanas a la ruta o
   todas, y si se complementa a futuro con detección por cámara (fuera del alcance actual).
4. **Frecuencia de corrección visual** durante la navegación (tiempo / distancia /
   incertidumbre) y su impacto en datos móviles y batería.
5. **Algoritmo de fusión** PDR + visual: filtro de Kalman vs. filtro de partículas.
6. **Funcionamiento sin conexión:** ¿se permite navegar solo con PDR si se pierde la red?
   Recordar que el mapa base de OSM necesita internet (solo se ve lo que está en caché); la
   navegación por voz sí podría continuar sin teselas.
7. **Privacidad de las fotos de ubicación: resuelta.** El backend las descarta tras responder y solo guarda un evento
   anónimo (backend ADR-BE-06). Queda por decidir si la app lo dice en voz alta antes del primer escaneo.
8. **SDK mínimo/objetivo** y dispositivos soportados (sensores y cámara).
9. **Moderación de alertas: resuelta en parte.** Cualquier admin puede crear, editar y borrar; el historial queda en
   la tabla `auditoria` del backend. No hay rol revisor.
10. **Eliminación de videos: resuelta.** Borrado definitivo (sin papelera): los vectores salen de la búsqueda al
    instante y los archivos se purgan en segundo plano; queda registro de quién y cuándo, y cualquier admin puede
    borrar videos de otros (backend ADR-BE-07).
11. **Autenticación: resuelta.** JWT propio de 12 h emitido por el backend, roles `USER` / `ADMIN` (backend ADR-BE-03).
12. **Conservación de fotos de escaneo:** hoy `CONSERVAR_FOTOS = true` guarda hasta 20
    escaneos en el teléfono. Con la decisión 7 resuelta, lo coherente es `false` en producción (borrarlas tras
    enviarlas); se aplica en FE-3.2, junto con el envío real de las fotos.
13. **Dependencias externas del `WebView`:** `index.html` carga Leaflet desde `unpkg.com` y
    las fuentes desde Google Fonts. Si no hay red, la página del mapa ni siquiera carga.
    Decidir si se **empaquetan localmente** en `assets/` (recomendado: así solo las teselas
    dependen de internet).
14. **GPS en el mapa:** ¿se conserva el botón GPS (requiere `ACCESS_FINE_LOCATION` y atender la
    geolocalización del `WebView`) o la posición inicial se fija solo manualmente / por fotos? Hoy `MapaPublicoScreen` **no** atiende la
    geolocalización: el botón GPS muestra un error. La vista 7.3 (`UbicacionManualScreen`) **ya no tiene** botón GPS.
15. **Datos compartidos entre vistas:** **resuelta para el flujo de recolección** (7.3 → 7.4 → 7.5) con un holder
    en memoria, `SesionDeRecoleccion` (5.6): `AppNav` no pasa argumentos de ruta. **Sigue abierta para el flujo
    público** (el destino elegido, la posición estimada y su corrección de rumbo, si hay ubicación vigente): la opción
    natural es el mismo patrón (por ejemplo `SesionDeNavegacion`, único por proceso, con `StateFlow`). Hay que
    decidirlo en FE-3.2, antes de 6.3 y 6.5; al hacerlo, actualizar 5.8.
16. **Longitud de paso del PDR:** **resuelta** con la calibración por dispositivo de 7.3b (una pasada A→B; se guarda y
    reemplaza el 0,72 m genérico, que queda solo como valor por defecto). **Sigue abierto:** la deriva de la brújula, la deriva
    estimada de 7.4 (heurística provisional del 4 %, que habrá que reemplazar cuando exista corrección visual) y si conviene
    promediar varias pasadas (ver 7.3b).
17. **Nombre del producto** *(nueva)*: «Campus Locator» en la documentación y «Campus Navi» en `LoginScreen`.
18. **Interacción de Inicio** *(nueva)*: el código tiene un solo orbe que navega a Ubicarse; la especificación 6.1 pide
    dos botones grandes, micrófono y Ajustes (detalle en 5.5, «Inicio»).
19. **Nombre por defecto de los videos** *(nueva)*: la app propone `video_N`; el backend acepta cualquier nombre y, si
    llega vacío, asigna `video_<numero>`. Decidir si la app deja de proponerlo y usa el del servidor.

---

## 9. Riesgos y notas para quien implemente

### 9.1 Riesgos

| ID | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | La deriva del PDR (brújula, longitud de paso) etiqueta mal las fotos del dataset y empeora la ubicación | Alta | Alto | Calibrar el paso antes de recolectar, re-anclar en puntos conocidos (7.4), probar recorridos conocidos (FE-2.3) |
| R2 | Varias piezas están marcadas ⚠ (sin probar en dispositivo) | Alta | Medio | FE-2.3: pruebas en dispositivo físico antes de recolectar el dataset real |
| R3 | Los mapas dependen de internet (Leaflet en `unpkg.com`, teselas de OSM y su política de uso) | Media | Medio | Decisiones abiertas 1 y 13; empaquetar Leaflet en `assets/` |
| R4 | Rumbos en referencias distintas (magnético en el escaneo, verdadero en el PDR) | Alta | Medio | Convertir antes de enviar (§5.10, FE-3.2) |
| R5 | Reconocimiento de voz no disponible o voces superpuestas con TalkBack | Media | Alto | Proteger `SpeechRecognizer` con `isRecognitionAvailable`; probar con TalkBack (FE-3.5); toda acción tiene equivalente táctil |
| R6 | La sesión se borra si Android mata el proceso durante una recolección larga | Media | Medio | La recolección ya guarda en disco; la subida (7.5) pide login de nuevo y retoma por idempotencia |
| R7 | Eventos de una sola vez perdidos (`SharedFlow` sin repetición) dejan pantallas atascadas | Baja | Medio | Ver 5.2 (escaneo) y 5.1; migrar a `Channel` donde importe |
| R8 | En `dev` la ubicación no funciona mientras embeddings está apagado (por defecto, y siempre desde las 22:00) | Alta | Bajo | Mensaje claro con `503 EMBEDDING_NO_DISPONIBLE` (§5.10); encender embeddings antes de probar (infra §3.4) |
| R9 | Ediciones de admin hechas sobre datos locales se pierden al cerrar la app (`EdicionesLocales`, editor de alertas) | Alta | Bajo | Desaparece al conectar los repositorios remotos (FE-3.3, FE-4.1) |

### 9.2 Notas para quien implemente

- La **calibración de la longitud de paso** ya existe (7.3b): pedirle al admin que calibre en un tramo de 30 m o más **antes de la
  primera recolección** y que **camine igual** que al calibrar. Falta la calibración de la **deriva de la brújula** (FE-5.1).
- Las capturas deben tener **control de calidad** (blur, exposición) antes de enviarse (FE-4.3).
- Las subidas deben tolerar **mala conexión** (cola local con reintentos).
- Mantener un **registro de pruebas reales en dispositivo físico**: el emulador no
  reproduce sensores ni cámara de forma útil.
- Pruebas reales hechas en un Xiaomi 23028RA60L (Android 14). El reconocimiento de voz registra
  `not connected to the recognition service`: revisar que el teléfono tenga un servicio de voz
  activo y proteger la creación del `SpeechRecognizer` con `isRecognitionAvailable`.
- Probar el mapa en un **dispositivo físico**: los sensores llegan por `AndroidBridge` y el
  emulador no los reproduce bien. Si el mapa sale en blanco, revisar conexión a internet y
  que el `WebView` tenga JavaScript activado.
- **PDR:** la posición acumula error (longitud de paso calibrada una sola vez, deriva de la brújula) y todavía no hay
  corrección visual. Probarlo caminando un recorrido conocido en un dispositivo físico antes de
  usarlo para etiquetar fotos (7.4).
- Los sensores del PDR solo se liberan al salir de la composición (`PdrTracker.liberar()`): no hay
  manejo de `ON_STOP`, así que siguen activos si la app pasa a segundo plano (FE-2.3).
- Cualquier cambio de arquitectura debe reflejarse en este archivo (con su entrada en `CHANGELOG.md`) y, si cambia la
  estructura general, en el `README.md` raíz.
- Al crear o cambiar una pieza que otra vista pueda reutilizar, actualizar su entrada en el
  §5 **en el mismo cambio** (las entradas con ⚠ no están verificadas contra el código).
