# ARCHITECTURE — Campus Locator

Este documento describe la arquitectura completa del proyecto: qué hace, cómo está
organizado, qué sistemas lo componen y **qué debe tener cada vista** (con el archivo que
la implementa). La sección de vistas está pensada para usarse como brief de diseño
(por ejemplo, para pedirle a una IA que genere los diseños de frontend).

> Ruta base del código: `app/src/main/java/com/example/myapplication/`
> Todas las rutas de archivo de este documento son relativas a esa carpeta.

---

## 1. Visión general

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

---

## 2. Funcionalidades en detalle

### 2.1 Ubicarse (comando "uno")

1. En Inicio, el usuario dice *"uno"* (o toca el botón).
2. La app le indica por voz: *"Sostén el celular al frente y da una vuelta completa
   lentamente."*
3. La app abre la cámara trasera y usa el sensor de orientación (rotation vector) para
   saber cuánto ha girado. **Captura 5 fotos automáticamente**, una cada ~72° a lo largo
   de los 360° (0°, 72°, 144°, 216°, 288°). Cada foto se guarda junto con su `heading`
   (orientación).
4. Se envían las 5 fotos (+ headings) al backend.
5. El backend genera embeddings DINOv2, los compara con el dataset y devuelve la posición
   estimada (x, y), la orientación probable y un nivel de confianza.
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
| **Navegación inercial (PDR)** | Detector de pasos, acelerómetro, giroscopio, rotation vector/magnetómetro, longitud de paso estimada | Posición continua y en tiempo real, sin red | El error se **acumula** con el tiempo |
| **Corrección visual** | Foto automática periódica → backend → embedding → posición | Posición absoluta que **corrige el error acumulado** | Latencia, depende de red y de buena imagen |

**Fusión:** la posición PDR avanza en cada paso. Cuando llega una posición visual con
buena confianza, se corrige la posición actual (filtro de Kalman o filtro de partículas,
con la posición PDR como predicción y la visual como medición). La captura visual se
dispara **automáticamente** por tiempo (ej. cada N segundos), por distancia recorrida, o
cuando la incertidumbre estimada supera un umbral. **Sin intervención del usuario.**

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
   embeddings con DINOv2 y se indexan.

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
- La app descarga las alertas y las **guarda en local** para que funcionen sin conexión.
- Durante la **navegación guiada** (y opcionalmente al mostrar el resultado de ubicación),
  se compara la posición estimada del usuario con las alertas: si entra al radio de una
  alerta (sumando la incertidumbre actual de la posición), la app **lee el mensaje por voz**
  y vibra.
- Cada alerta se anuncia **una sola vez por aproximación** (con un tiempo de espera antes de
  repetirse) para no saturar al usuario.
- Las alertas de prioridad alta **interrumpen** la instrucción de voz en curso.
- Se priorizan las alertas que están **en la ruta** o cerca de ella.

**Cómo las crea el admin:** desde el **Editor de mapa y alertas** (vista 15) o desde la
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
| Seguimiento por pasos (PDR) | Cada paso avanza la posición `stepLength` (0,72 m) en la dirección del rumbo actual |
| Rumbo | Promedio circular de las últimas 6 lecturas; la flecha del marcador se suaviza con un filtro adaptativo. Si no hay brújula, aparece una **rueda manual de rumbo** |
| Trayectoria | Polilínea punteada con todos los puntos recorridos; botón de reinicio que vuelve al punto inicial |
| Panel de estadísticas | Pasos, velocidad, aceleración (con gráfica en vivo), distancia, cadencia, rumbo, calorías y coordenadas |
| Brújula | Widget con rosa de los vientos y orientación cardinal |
| Centrar | Botón que centra el mapa en la posición actual |

#### Puente WebView ↔ Android (`AndroidBridge`)

En Android **todos los sensores vienen del lado nativo (Kotlin)**; registrar además los
sensores web duplicaba los pasos y mezclaba dos brújulas distintas. Si la página **no**
encuentra `window.AndroidBridge` (navegador o iOS), usa como alternativa los sensores web
(`devicemotion` y `deviceorientation`).

| Dirección | Función | Descripción |
|---|---|---|
| Web → Kotlin | `AndroidBridge.startSensors()` | Empieza a enviar pasos, aceleración y rumbo |
| Web → Kotlin | `AndroidBridge.stopSensors()` | Detiene los sensores |
| Kotlin → Web | `window.onNativeStep(count)` | Pasos acumulados desde `startSensors()` (contador de hardware) |
| Kotlin → Web | `window.onNativeStepUnavailable(reason)` | No hay contador de pasos (`'permission_denied'` u otro motivo); la web cambia a pasos por acelerómetro |
| Kotlin → Web | `window.onNativeAccel(x, y, z)` | Aceleración para la gráfica y, si hace falta, para detectar pasos |
| Kotlin → Web | `window.onNativeHeading(degrees)` | Rumbo en grados (0–360, norte real) |

Requisitos del lado Kotlin: JavaScript activado en el `WebView`, exponer el objeto con
`addJavascriptInterface(..., "AndroidBridge")` y llamar a las funciones `window.onNative*`
con `evaluateJavascript` **desde el hilo principal**. Estos sensores son los mismos del
paquete `sensors/` (ver sección 4).

### 2.7 Interacción por voz

- **Entrada:** `SpeechRecognizer` de Android (comandos "uno", "dos", nombres de lugares,
  "sí/no", "repetir", "cancelar", "ayuda").
- **Salida:** `TextToSpeech`, con cola de prioridades (una alerta de obstáculo de prioridad
  alta interrumpe a una instrucción normal).
- Todo comando de voz tiene un **equivalente táctil** y es compatible con TalkBack.

---

## 3. Arquitectura del sistema

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

### Responsabilidades del backend (resumen de endpoints)

| Endpoint (propuesto) | Quién lo usa | Función |
|---|---|---|
| `POST /localize` | Público | Recibe 1–5 fotos (+ headings), devuelve posición, orientación y confianza |
| `POST /localize/frame` | Público | Corrección visual durante la navegación (1 foto) |
| `GET /places` | Público | Lista de lugares/destinos |
| `GET /alerts` | Público | Alertas de obstáculo activas (se cachean en el dispositivo) |
| `GET /route?from&to` | Público | Ruta entre dos coordenadas (o se calcula en el dispositivo) |
| `POST /auth/login` | Todos | Inicio de sesión, devuelve token + rol |
| `POST /collect/videos` | Admin | Crea un video (recorrido) y devuelve su `video_id` |
| `POST /collect/videos/{id}/images` | Admin | Sube fotos del video con coordenada y orientación |
| `GET /admin/videos` | Admin | Lista de videos con resumen (nº de fotos, fecha, estado) |
| `GET /admin/videos/{id}/images` | Admin | Fotos de un solo video (para verlas en el mapa) |
| `PATCH /admin/videos/{id}` | Admin | Renombrar el video |
| `DELETE /admin/videos/{id}` | Admin | Elimina el video y **todas** sus fotos, embeddings y entradas del índice |
| `GET/POST/PUT/DELETE /admin/places` | Admin | CRUD de lugares |
| `GET/POST/PUT/DELETE /admin/alerts` | Admin | CRUD de alertas de obstáculo |
| `GET /admin/images` | Admin | Galería con filtros (incluye filtro por `video_id`) |
| `GET /admin/stats` | Admin | Estadísticas de uso |

---

## 4. Estructura de paquetes

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
│       ├── recoleccion/
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
│   ├── remote/                  # Retrofit/Ktor, DTOs, API
│   ├── repository/              # Implementaciones de repositorios
│   └── local/                   # Caché local (Room/DataStore), cola de subida offline
│
├── sensors/                     # Sensores y PDR
│   ├── StepDetector, OrientationProvider, PdrEngine
│
├── camera/                      # CameraX, captura automática (una carpeta por escaneo), calidad de imagen (sin uso por ahora)
├── map/                         # WebView del mapa Leaflet/OSM, AndroidBridge y datos de capas (usuario, ruta, lugares, alertas)
├── voice/                       # Wrappers de TextToSpeech y SpeechRecognizer
└── session/                     # Sesión, token, rol (USER / ADMIN)
```

> Fuera del código Kotlin, el mapa vive en `app/src/main/assets/`: `index.html` y `app.js`
> (Leaflet + OpenStreetMap, ver 2.6).

> Actualmente en el repo existen `ui/`, `camera/`, `sensors/`, `logs/`, `ApiConfig.kt`,
> `MyApp.kt` y `MainActivity.kt`; el resto de paquetes se crean a medida que se implementan.

### Navegación y roles

- Un único `NavHost` en `ui/navigation/AppNavHost.kt`.
- Rutas públicas: Inicio, Ubicación, Destino, Navegación, Ajustes, Login.
- Rutas `admin/*` protegidas: si no hay sesión con rol `ADMIN` se redirige a Login.
- El acceso a Login desde Inicio debe ser discreto (el usuario final casi nunca lo usa),
  pero accesible para TalkBack.

### Permisos de Android

| Permiso | Para qué | Tipo |
|---|---|---|
| `INTERNET` | Llamadas al backend y descarga de teselas de OpenStreetMap en el `WebView` | Normal |
| `ACCESS_NETWORK_STATE` | Indicador y aviso de pérdida de conexión | Normal |
| `CAMERA` | Escaneo 360°, corrección visual y recolección | Diálogo |
| `RECORD_AUDIO` | `SpeechRecognizer` (comandos y dictado) | Diálogo |
| `ACTIVITY_RECOGNITION` | Detector de pasos del PDR (Android 10+) | Diálogo |
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
- Si se niega el micrófono: solo botones. Si se niega actividad física: el PDR necesita un
  detector de pasos propio basado en el acelerómetro.
- El Manifest declara `<queries>` para `RecognitionService` y `TTS_SERVICE` (Android 11+), y
  `uses-feature` con `required="false"` para cámara, micrófono y sensores.

### Registro de eventos (logs) y depuración

- `logs/AppLog.kt` escribe cada mensaje en **Logcat** y en el archivo `files/logs/app.log`
  (rota a ~1 MB y conserva `app.log.1`).
- `MyApp.kt` inicializa `AppLog` al arrancar y registra los crashes no capturados (tag `CRASH`).
  Debe declararse en el Manifest con `android:name=".MyApp"`.
- Cada escaneo abre una sesión (`AppLog.nuevaSesion("scan")`): sus líneas llevan un id como
  `[scan-12345]` para seguir una vuelta completa.
- Tags usados: `App`, `CRASH`, `EscaneoVM`, `Camara`.
- Registrar transiciones y decisiones, **no** cada lectura de sensor (50 por segundo).
- No registrar datos sensibles (tokens, credenciales).

**Cómo consultar:**
- Logcat de Android Studio: filtro `package:mine`, o `tag:EscaneoVM`.
- Archivo de log y fotos: *Device Explorer* → `data/data/com.example.myapplication/files/`
  (`logs/app.log` y `camera/photos/`), o con `adb exec-out run-as com.example.myapplication`.

---

## 5. Mapa de vistas

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

---

## 6. Especificación de vistas públicas

> Para todas: alto contraste, textos grandes, botones de mínimo 64 dp, `contentDescription`
> completo, y cada mensaje importante se lee en voz alta automáticamente.

### 6.1 Inicio — `ui/inicio/InicioScreen.kt`

![alt text](<assets/inicio.png>)

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
  primera vez. *Pendiente:* la explicación hablada previa al diálogo.

---

### 6.2 Ubicarse (escaneo 360°) — `ui/ubicacion/EscaneoScreen.kt`

![alt text](<assets/ubicarse.png>)

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
  **Debe ponerse en `false` antes de publicar** (ver decisión abierta 12).
- Para verlas: Device Explorer de Android Studio o `adb` (ver "Registro de eventos (logs) y
  depuración", en la sección 4).

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
| `logs/AppLog.kt` | Registro de eventos (ver sección 4) |

---

### 6.3 Resultado de ubicación — `ui/ubicacion/ResultadoUbicacionScreen.kt`

![alt text](<assets/resultados_de_ubicacion.png>)

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

![alt text](<assets/seleccion_de_destino.png>)

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

---

### 6.5 Navegación guiada — `ui/navegacion/NavegacionScreen.kt`

![alt text](<assets/navegacion_guiada.png>)

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

![alt text](<assets/llegada.png>)

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

![alt text](<assets/ajustes.png>)

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

![alt text](<assets/login.png>)

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
- Al iniciar sesión se llama a `POST /auth/login` (token + rol).
- **Rol `ADMIN`:** se guarda la sesión y se navega a `admin/panel`, quitando Login de la
  pila de navegación.
- **Rol distinto de `ADMIN`:** se informa que no tiene permisos, **no se guarda la sesión**
  y no se habilita el panel.
- Si al abrir Login ya existe una sesión `ADMIN` guardada, se entra directo al panel.
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
| `session/SessionManager.kt` | Sesión cifrada: `guardar`, `obtener`, `esAdmin`, `cerrarSesion` |
| `data/repository/AuthRepository.kt` | Contrato del login (`AuthRepository`) y stub temporal (**TODO:** reemplazar por Retrofit/Ktor con `ApiConfig.kt`) |
| `domain/model/Usuario.kt` | `Rol` (USER/ADMIN), `Usuario`, `Sesion` |

admin@campus.edu.co

**Navegación (`AppNavHost`):**
```kotlin
composable("login") {
    LoginScreen(
        onLoginExitoso = {
            navController.navigate("admin/panel") { popUpTo("login") { inclusive = true } }
        },
        onVolver = { navController.popBackStack() },
    )
}
```
---

### 7.2 Panel admin — `ui/admin/panel/PanelAdminScreen.kt`

![alt text](<assets/panel_admin.png>)

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
- **Guarda de rol:** al abrir el panel se verifica la sesión. Si no hay sesión `ADMIN`, se
  redirige a Login.
- **Cerrar sesión:** llama a `SessionManager.cerrarSesion()` (borra token y datos) y regresa
  a Inicio. No pide confirmación.
- **Volver a modo público:** regresa a Inicio **sin** cerrar la sesión.
- **Resumen:** mientras carga muestra "—". Si falla, muestra "No se pudo cargar el resumen"
  con botón **Reintentar**.
  - Totales, lugares, alertas y último video vienen del backend (`GET /admin/stats`).
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
| `domain/model/ResumenAdmin.kt` | Modelo con los 5 datos del resumen |
| `ui/theme/CampusColors.kt` | Colores compartidos de las vistas admin |
| `session/SessionManager.kt` | Lectura de la sesión (nombre, rol) y `cerrarSesion()` |

**Navegación (`AppNav` en `MainActivity.kt`):**
```kotlin
composable("admin/panel") {
    PanelAdminScreen(
        onRecolector = { nav.navigate("admin/ubicacion-manual") },
        onLugares = { nav.navigate("admin/lugares") },
        onMapaAlertas = { nav.navigate("admin/mapa") },
        onImagenes = { nav.navigate("admin/imagenes") },
        onVideos = { nav.navigate("admin/videos") },
        onEstadisticas = { nav.navigate("admin/estadisticas") },
        onAjustes = { nav.navigate("ajustes") },
        onVolverModoPublico = { nav.popBackStack("inicio", inclusive = false) },
        onSesionCerrada = { nav.popBackStack("inicio", inclusive = false) },
        onSinSesion = { nav.navigate("login") { popUpTo("admin/panel") { inclusive = true } } },
    )
}
```

---

### 7.3 Ubicación manual inicial — `ui/admin/recoleccion/UbicacionManualScreen.kt`

![alt text](<assets/ubicacion_manual_iniciada.png>)

**Propósito:** fijar la coordenada exacta de partida antes de recolectar.

**Elementos:**
- **Mapa del campus a pantalla casi completa**, con zoom y desplazamiento.
- **Marcador arrastrable** (o toque para colocarlo) que representa dónde está parado.
- **Selector de orientación**: flecha rotatoria o botón "Usar brújula del teléfono" para
  fijar hacia dónde mira.
- Campos de **coordenadas** (x, y / lat, lon) mostrados y editables.
- Botón **"Usar mi última posición"** (para continuar desde el final del video anterior; crea un video nuevo).
- Botón **"Confirmar y comenzar"**: crea el nuevo video (ej. `video3`) y empieza la recolección.
- Campo opcional **nombre del video** (por defecto autonumerado).
- Botón **Cancelar**.
- Mensaje de ayuda: "Colócate en un punto reconocible y marca tu posición exacta".

**Estado de implementación:** el mapa Leaflet de `app.js` ya permite colocar el punto con un
**toque**, usar el **GPS**, fijar el rumbo con la **brújula del dispositivo** o con la **rueda
manual** y ver las coordenadas. Falta: marcador arrastrable, campos de coordenadas editables
y los botones "Usar mi última posición" y "Confirmar y comenzar".

---

### 7.4 Recolección en curso — `ui/admin/recoleccion/RecoleccionScreen.kt`

![alt text](<assets/recoleccion_en_curso.png>)

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
- Botón **"Agregar alerta aquí"**: abre el formulario de alerta (vista 16) con la coordenada
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

---

### 7.5 Resumen de video — `ui/admin/recoleccion/ResumenVideoScreen.kt`

![alt text](<assets/resumen_de_video.png>)

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

![alt text](<assets/lista_de_lugares.png>)

**Elementos:**
- Barra de búsqueda y filtro por categoría.
- **Lista de lugares**: nombre, categoría, nº de fotos asociadas, coordenada.
- Botón flotante **"Nuevo lugar"**.
- Toque en un lugar → editar. Opciones: editar, eliminar (con confirmación), ver fotos.
- Alternar entre **vista de lista** y **vista de mapa**.

### 7.7 Formulario de lugar — `ui/admin/lugares/LugarFormScreen.kt`

![alt text](<assets/formulario_de_lugar.png>)

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

![alt text](<assets/editor_de_mapa_y_alertas.png>)

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
| `ui/admin/mapa/EditorMapaScreen.kt` | `EditorMapaScreen` (la que usa el NavHost: conecta ViewModel, formulario y navegación), `EditorMapaContent` (solo dibuja el `WebView`) e interfaz `EditorMapaEventos` |
| `ui/admin/mapa/EditorMapaViewModel.kt` | Estado (`EditorMapaUi`), formulario en edición, validación, pendientes y sincronización (**hoy simulada**) |
| `ui/admin/mapa/AlertaFormSheet.kt` | Formulario de alerta (vista 7.9), hoja inferior de Material 3 |
| `domain/model/Alerta.kt` | Modelos `Alerta` y `Lugar` |
| `app/src/main/assets/editor_mapa.html` | Interfaz del editor (estilos y estructura) |
| `app/src/main/assets/editor_mapa.js` | Leaflet + OSM, capas, filtros, modos (colocar / mover), borrador y puente con Kotlin |

**Puente WebView ↔ Android (`EditorBridge`):** los datos viajan como JSON; la alerta tiene los
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

**Navegación (`AppNav` en `MainActivity.kt`):**
```kotlin
composable("admin/mapa") {
    EditorMapaScreen(
        onVolver = { nav.popBackStack() },
        onVerLista = { /* vista 7.10 aún no existe */ },
        posicionAdmin = { null },   // luego: la posición del PDR, como Pair(lat, lng)
    )
}
```

**Requisitos:** `editor_mapa.html` y `editor_mapa.js` en la raíz de `assets/`, permiso `INTERNET`,
y conexión a internet (Leaflet y las teselas se descargan en línea; ver decisión abierta 13). Si
la página no carga, `EditorMapa` en Logcat muestra los errores del `WebView`.

**Pendiente:** conectar el repositorio local (Room) y la API real (`/admin/alerts`), cargar las
capas de cobertura y rutas, pasar la posición real del admin en `posicionAdmin`, y completar el
formulario (dictado por voz, "Escuchar cómo sonará", vigencia y "Ajustar en el mapa").


### 7.9 Formulario de alerta — `ui/admin/mapa/AlertaFormSheet.kt`

![alt text](<assets/formulario_de_alerta.png>)

Hoja inferior (bottom sheet) o diálogo reutilizable desde el editor de mapa y desde la
recolección.

**Estado:** implementada en `ui/admin/mapa/AlertaFormSheet.kt` (mensaje, tipo, prioridad, radio,
estado, validación y eliminar con confirmación). Faltan dictado por voz, "Escuchar cómo sonará",
vigencia y "Ajustar en el mapa".

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

![alt text](<assets/lista_de_alertas.png>)

**Elementos:**
- Buscador por texto del mensaje y filtros por tipo, prioridad y estado.
- **Lista**: ícono de tipo, mensaje (resumido), prioridad, radio, estado y fecha de
  modificación.
- Acciones por fila: **editar**, **activar/desactivar**, **ver en el mapa**, **eliminar**.
- Botón flotante **"Nueva alerta"**.
- Alternar a la **vista de mapa**.

### 7.11 Galería de imágenes — `ui/admin/imagenes/GaleriaScreen.kt`

![alt text](<assets/galeria_de_imagenes.png>)

**Elementos:**
- **Cuadrícula** de miniaturas del dataset.
- **Filtros**: por lugar, **por video**, por fecha, por estado (subida / procesada / error),
  por calidad.
- Selección múltiple con acciones en lote (eliminar, reasignar).
- Contador total y paginación/scroll infinito.
- Alternar a **vista de mapa** (ver dónde hay fotos y dónde falta cobertura). Con un filtro de video activo, el mapa muestra solo las fotos de ese video.
- Botón **"Subir imágenes"** (opcional, adicionales).

### 7.12 Detalle de imagen — `ui/admin/imagenes/DetalleImagenScreen.kt`

![alt text](<assets/detalles_de_imagen.png>)

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

![alt text](<assets/lista_de_videos.png>)

**Propósito:** ver todos los recorridos de recolección ("videos") y elegir uno para
inspeccionarlo o eliminarlo.

**Elementos:**
- **Lista de videos**: nombre (ej. "video1"), fecha, duración, distancia, nº de fotos y
  estado (en curso / pendiente de subir / procesado / con errores).
- **Minimapa o miniatura de trayectoria** por video.
- Ordenar por fecha / nombre / nº de fotos; buscador por nombre.
- Toque en un video → **Detalle de video** (vista 21).
- Acciones por fila (menú): **renombrar**, **reintentar subida**, **reprocesar
  embeddings**, **eliminar** (con la confirmación descrita en 7.14).
- Selector de videos para **comparar** cobertura (opcional): mostrar varios a la vez con
  distinto color.
- Indicador de videos pendientes sin sincronizar.
- Botón **"Nuevo video"** (lleva a la ubicación manual inicial).

---

### 7.14 Detalle de video — `ui/admin/videos/VideoDetalleScreen.kt`

![alt text](<assets/detalle_de_video.png>)

**Propósito:** al seleccionar un video, ver en el mapa **SOLO las fotos de ese video** y
poder eliminarlo por completo.

**Elementos:**
- **Mapa**  donde se dibujan **únicamente** las fotos del video
  seleccionado (marcador por foto con flecha de orientación) y la **trayectoria**
  recorrida. Las fotos de otros videos **no se muestran**.
- **Conmutador "Mostrar otros videos"** (apagado por defecto) para ver el contexto en gris
  tenue, opcional.
- **Encabezado**: nombre del video (editable), fecha, duración, distancia, nº de fotos.
- Al tocar un marcador: **vista previa de la foto** con su coordenada y orientación y
  acceso al **Detalle de imagen** (vista 19).
- **Tira o cuadrícula de fotos** del video sincronizada con el mapa (al tocar una foto se
  centra el mapa en su marcador y viceversa).
- Botón **"Eliminar foto"** (una sola) dentro del video.
- Botón **"Renombrar"**.
- Botón **"Eliminar video"** (rojo, separado del resto para evitar toques accidentales).

**Flujo de eliminación:**
1. Diálogo de confirmación que indica claramente el alcance: *"Vas a eliminar «video1» y
   sus 142 fotos. Esto quitará esas fotos del sistema de ubicación y no se puede
   deshacer."*
2. Confirmación reforzada: escribir el nombre del video o mantener presionado el botón.
3. Se muestra progreso (borrado de imágenes, embeddings e índice) y, al terminar, un
   mensaje de éxito; se vuelve a la lista de videos.
4. Si falla parcialmente, se informa y se permite reintentar (no deben quedar fotos
   "huérfanas" sin video).

**Reglas:**
- Eliminar un video elimina **todas** sus fotos, embeddings y entradas del índice.
- No elimina alertas de obstáculo ni lugares.
- Cuando un video queda con 0 fotos (por eliminarlas una a una) se ofrece eliminarlo.

---

### 7.15 Estadísticas — `ui/admin/estadisticas/EstadisticasScreen.kt`

![alt text](<assets/estadisticas.png>)

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

## 8. Decisiones abiertas (por definir)

1. **Proveedor y uso de teselas del mapa:** hoy se usa `tile.openstreetmap.org` directamente.
   El servidor público de OSM tiene una política de uso aceptable que **no está pensada para
   tráfico intensivo** de una app en producción. Antes de publicar, decidir si se mantiene, si
   se cambia a un proveedor de teselas con plan/clave propia o si se monta un servidor propio.
   Si el campus tiene interiores donde el mapa no llega, definir cómo se representan.
2. **Grafo de caminos:** para calcular rutas se necesita un grafo de zonas transitables.
   ¿Lo dibuja el admin en el editor de mapa (nueva herramienta), o se deriva de las
   trayectorias recolectadas?
3. **Alertas de obstáculo (ya definido):** son puntos manuales en el mapa con mensaje. Queda
   por decidir: radio por defecto, si se anuncian solo las alertas cercanas a la ruta o
   todas, y si se complementa a futuro con detección por cámara (fuera del alcance actual).
4. **Frecuencia de corrección visual** durante la navegación (tiempo / distancia /
   incertidumbre) y su impacto en datos móviles y batería.
5. **Algoritmo de fusión** PDR + visual: filtro de Kalman vs. filtro de partículas.
6. **Funcionamiento sin conexión:** ¿se permite navegar solo con PDR si se pierde la red?
   Recordar que el mapa base de OSM necesita internet (solo se ve lo que está en caché); la
   navegación por voz sí podría continuar sin teselas.
7. **Privacidad:** las fotos de usuarios públicos enviadas al backend: ¿se almacenan o se
   descartan tras la consulta? ¿se avisa al usuario?
8. **SDK mínimo/objetivo** y dispositivos soportados (sensores y cámara).
9. **Moderación de alertas:** ¿cualquier admin puede crear/editar alertas, o hay un rol
   revisor? ¿Se guarda historial de cambios?
10. **Eliminación de videos:** ¿borrado definitivo inmediato, o "papelera" con recuperación
    durante unos días? ¿Se guarda un registro (quién y cuándo eliminó)? ¿Se permite
    que cualquier admin elimine videos de otros?
11. **Autenticación:** proveedor y modelo de roles (¿solo `USER`/`ADMIN` o más?).
12. **Conservación de fotos de escaneo:** hoy `CONSERVAR_FOTOS = true` guarda hasta 20
    escaneos en el teléfono. Definir si en producción se borran siempre tras enviarlas al
    backend (relacionado con la decisión 7, privacidad).
13. **Dependencias externas del `WebView`:** `index.html` carga Leaflet desde `unpkg.com` y
    las fuentes desde Google Fonts. Si no hay red, la página del mapa ni siquiera carga.
    Decidir si se **empaquetan localmente** en `assets/` (recomendado: así solo las teselas
    dependen de internet).
14. **GPS en el mapa:** ¿se conserva el botón GPS (requiere `ACCESS_FINE_LOCATION` y atender la
    geolocalización del `WebView`) o la posición inicial se fija solo manualmente / por fotos?

---

## 9. Notas para quien implemente

- La **calibración del PDR** (longitud de paso, deriva de la brújula) es crítica: conviene
  una pantalla/etapa de calibración en la primera sesión del admin.
- Las capturas deben tener **control de calidad** (blur, exposición) antes de enviarse.
- Las subidas deben tolerar **mala conexión** (cola local con reintentos).
- Mantener un **registro de pruebas reales en dispositivo físico**: el emulador no
  reproduce sensores ni cámara de forma útil.
- Pruebas reales hechas en un Xiaomi 23028RA60L (Android 14). El reconocimiento de voz registra
  `not connected to the recognition service`: revisar que el teléfono tenga un servicio de voz
  activo y proteger la creación del `SpeechRecognizer` con `isRecognitionAvailable`.
- Reactivar el control de calidad (`CalidadImagen.kt`) cuando el flujo de captura esté estable.
- Probar el mapa en un **dispositivo físico**: los sensores llegan por `AndroidBridge` y el
  emulador no los reproduce bien. Si el mapa sale en blanco, revisar conexión a internet y
  que el `WebView` tenga JavaScript activado.
- Quitar de `README.md` y de cualquier script/documentación las referencias a
  `eafit.mbtiles` (ya no se usa).
- Cualquier cambio de arquitectura debe reflejarse en este archivo y en `README.md`.