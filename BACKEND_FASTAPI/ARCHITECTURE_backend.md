# ARCHITECTURE — Backend (Campus Locator)

Plan y catálogo de **`BACKEND_FASTAPI/`**: la API REST que usa la app Android. Complementa a
`FRONTED_KOTLIN/ARCHITECTURE.md` (qué pide la app: sección 3, modelos y repositorios: 11.6) y a
`INFRASTRUCTURA_TERRAFORM/ARCHITECTURE.md` (dónde corre y qué variables de entorno inyecta: 4.1).

> **Estado (2026-10-14): B0 y B1 están escritas solo en parte y sin ejecutar contra AWS.** El `BACKEND_FASTAPI.zip`
> revisado trae 6 de los archivos del catálogo (`Dockerfile`, `app/config.py`, `app/main.py`, `app/db/engine.py`,
> `alembic/versions/0001_inicial.py`, `scripts/migrar.sh`) y **le faltan 7** que ese código importa o copia (12.2): con lo
> que hay, la imagen no se construiría y `/health` no arrancaría. Este documento es el **diseño** que parte de contratos
> ya fijados en los otros dos. Todo lo marcado con ⚠ es una **propuesta o supuesto sin verificar**.
> La sección 12 es el catálogo del código: se llena **en el mismo cambio** que cada archivo.
>
> **Para quien continúe (persona o IA):** la idea es que este archivo baste para no tener que pedir de nuevo los
> archivos de la app ni los `.tf`. Lo que el backend toma de ellos está en las secciones 3 (infra) y 4 (app).

---

## 1. Qué es y qué no es

| Es | No es |
|---|---|
| API REST (FastAPI) en ECS Fargate detrás del ALB, puerto **8000** | El modelo DINOv2: eso es `SERVICE_EMBEDDING/` (puerto 8001), solo accesible desde el backend |
| Dueño de la base (PostgreSQL + `pgvector`) y de las **migraciones Alembic** | Terraform: no crea tablas; el backend crea hasta `CREATE EXTENSION vector` (infra 12.1) |
| Autenticación (JWT propio, roles `USER` / `ADMIN`) | Un proveedor de identidad (Cognito queda descartado por ahora, infra 9.8) |
| Dueño de los archivos en S3 (dataset y escaneos) | Del mapa base: va directo de la app a OpenStreetMap |
| Quien busca la posición por similitud de vectores | Del cálculo de pasos (PDR): vive en la app |

Regla de oro: **un único sistema de verdad** para metadatos y vectores (Postgres). Borrar un video borra filas,
vectores y objetos de S3 en una sola operación del backend (flujo 2.3).

---

## 2. Flujos principales

### 2.1 Ubicarse (`POST /localize`, 5 fotos)
1. App → ALB → backend con 5 JPG + el `heading` de cada una.
2. Backend → `SERVICE_EMBEDDING` (un solo llamado con las 5 imágenes) → 5 vectores.
3. Por cada vector: vecinos más cercanos en `pgvector` (coseno, `fotos.embedding`).
4. Se agrupan los votos por zona, se estima posición, orientación y confianza (sección 7).
5. Respuesta `{lat, lng, rumbo, confianza, nivel}`. Si `S3_BUCKET_SCANS` no está vacío y la política lo permite,
   las fotos se guardan con expiración (infra 9.6); si no, **se descartan** tras la consulta.

### 2.2 Recolección (`POST /collect/videos` y `/collect/videos/{id}/images`)
1. Admin crea un video (`video_id` lógico que agrupa las fotos).
2. Por foto: archivo → S3 (`S3_BUCKET_DATASET`), embedding → fila en `fotos` con `lat`, `lng`, `rumbo`, `video_id`.
3. Subir fotos es **idempotente** por `(video_id, foto_id)`: la app reintenta con mala conexión (sección 9).

### 2.3 Eliminar un video (`DELETE /admin/videos/{id}`)
Una transacción borra las filas de `fotos` y del video; después se borran los objetos de S3 (`s3:DeleteObject`).
Si S3 falla a medias, el video ya no existe en la base y los objetos huérfanos se registran para limpiarlos
(⚠ tarea de limpieza pendiente). **No** borra alertas ni lugares (app 2.4).

### 2.4 Alertas y lugares
Lectura simple de Postgres; la app las cachea. El CRUD admin escribe en el mismo esquema.

---

## 3. Lo que la infra inyecta y exige (contrato con Terraform)

Variables de entorno **con estos nombres exactos** (infra 4.1 y 11.4):

| Variable | Contenido | Cuidado |
|---|---|---|
| `APP_ENV` | `dev` / `prod` | |
| `AWS_REGION` | `us-east-1` | La CLI local está en `us-east-2` (infra 12.11) |
| `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME` | Salidas del módulo `database` | El puerto llega como **texto** |
| `DATABASE_SECRET_ARN` | Secreto que administra RDS | ⚠ Se espera JSON con usuario y contraseña (infra 11.4): confirmarlo al escribir el cliente |
| `S3_BUCKET_DATASET` | Bucket del dataset | |
| `S3_BUCKET_SCANS` | Bucket de escaneos | Llega **vacío** si no existe |
| `EMBEDDING_SERVICE_URL` | `http://embedding.campus.internal:8001` | Solo resuelve dentro de la VPC |
| `JWT_SECRET_ARN` | Secreto del JWT | Queda en el state de Terraform (infra 12.7): tratarlo como sensible |

Requisitos que la infra le pide al backend:
- Escuchar en `0.0.0.0:8000`; `GET /health` → `200` **sin autenticación** (health check del ALB, 2 sanos / 3 no sanos, cada 30 s).
- **Imagen `X86_64`** (el módulo `ecs_service` lo usa por defecto; si CI construye ARM, hay que pasar `cpu_architecture`).
- RDS fuerza TLS (`rds.force_ssl = 1`): la conexión debe usar `sslmode=require` o superior.
- Permisos del rol de tarea: leer/escribir/borrar objetos y listar los dos buckets, y `GetSecretValue` de los dos secretos. **Nada más** (por ejemplo, sin otros servicios de AWS).
- Recursos de dev: **512 CPU / 1024 MB**. Sin modelos de ML en este proceso.
- ALB con `idle_timeout` de 60 s: una subida o `/localize` que tarde más se corta.
- Sin NAT en dev: las tareas están en subredes públicas con IP pública y SG cerrados; el backend no debe depender de internet salvo S3/Secrets (alcanzables).

---

## 4. Lo que la app espera (contrato con `FRONTED_KOTLIN`)

Fuente: sección 3 y 11.6 del `ARCHITECTURE.md` de la app.

### 4.1 Convenciones de datos (⚠ propuestas para que el `RemoteX` de la app no necesite adaptadores)
- **Coordenadas:** `lat`, `lng` en WGS84 (grados decimales).
- **`rumbo`/`heading`:** grados **0…360**, 0 = norte, sentido horario. La app (`OrientationProvider`) entrega el acimut en **−180…180** y **magnético**: el backend debe **normalizar** con `(x + 360) % 360` al recibir y no asumir norte geográfico.
- **Fechas:** ISO-8601 con zona (`2026-10-14T07:57:00-05:00`); `ultimo_video_fecha` en milisegundos epoch (así lo espera `ResumenAdmin`).
- **Ids de foto con ceros a la izquierda** (`"0001"`…): la app ordena por id como texto (11.6). Id de video: texto sin `/` (viaja como argumento de ruta sin codificar).
- **Claves JSON en `snake_case`** iguales a las del `manifest.json` (`video_id`, `name`, `created_at`, `photos[].id|file|lat|lng|heading|captured_at|lugar|estado|calidad`): así el parser de manifest que la app ya tiene sirve para la API.
- **Enums como texto** con los nombres del enum de la app: `estado` ∈ `SUBIDA|PROCESADA|ERROR`, `calidad` ∈ `ALTA|NORMAL|BAJA`, `categoria` ∈ `BIBLIOTECA|CAFETERIA|BANO|BLOQUE|AUDITORIO|DEPORTES|ADMINISTRACION|ENTRADA`, `tipo` de alerta ∈ `agua|mobiliario|escalones|obra|vehiculos|otro`, `prioridad` ∈ `normal|alta`. El backend **valida** (la app no lo hace: `tipo` y `prioridad` son texto libre allí).
- **URLs de fotos:** prefirmadas de S3 con vida corta (app 7.11); `url_miniatura` aparte o igual a la foto.

### 4.2 Endpoints

Roles: **P** = público (sin token), **U** = cualquier usuario con token, **A** = solo `ADMIN`. ⚠ La app hoy no manda token en las rutas públicas.

| Endpoint | Rol | Entrada | Salida |
|---|---|---|---|
| `GET /health` | P | — | `200 {"status":"ok"}` |
| `POST /auth/login` | P | `{identificador, password}` | `{token, usuario:{id, nombre, correo, rol}}`; credenciales malas → **401**; cuenta sin permiso → el rol viaja en la respuesta (la app decide no guardar `USER`, app 7.1) |
| `POST /localize` | P | multipart: 1–5 `fotos` + `headings` (lista, mismo orden) | `{lat, lng, rumbo, confianza, nivel}` (`nivel` ∈ `ALTA|MEDIA|BAJA`) |
| `POST /localize/frame` | P | 1 foto + `heading` + posición PDR opcional | igual que `/localize` (corrección visual) |
| `GET /places?lat&lng` | P | posición opcional | lista de `{id, nombre, categoria, lat, lng, alias, distancia_metros, imagen_url}`; `distancia_metros` **entero** o `null` si no hay posición |
| `GET /alerts` | P | `?desde` opcional | alertas **activas** y vigentes: `{id, lat, lng, mensaje, tipo, prioridad, radio, activa}` |
| `GET /route?from&to` | P | — | ⚠ opcional; la app podría calcular la ruta (app decisión 2) |
| `POST /collect/videos` | A | `{nombre?, start_lat, start_lng, start_heading}` | `{video_id, nombre}` (autonumerado si no hay nombre) |
| `POST /collect/videos/{id}/images` | A | multipart: `foto` + `{id, lat, lng, heading, captured_at}` | `{id, estado}`; idempotente por `(video_id, id)` |
| `GET /admin/videos` | A | — | videos con `{video_id, name, created_at, n_fotos, distancia_m, estado}` |
| `GET /admin/videos/{id}/images` | A | — | fotos de un solo video (forma del manifest, con URLs prefirmadas) |
| `PATCH /admin/videos/{id}` | A | `{name}` | video actualizado (máx. 40 caracteres) |
| `DELETE /admin/videos/{id}` | A | — | `204`; ver flujo 2.3 |
| `DELETE /admin/videos/{id}/images/{foto}` | A | — | `204` (la app borra fotos sueltas, app 7.14) |
| `GET/POST/PUT/DELETE /admin/places` | A | — | CRUD de lugares (⚠ campos extra de 7.6/7.7: descripción, referencias cercanas, nº de fotos) |
| `GET/POST/PUT/DELETE /admin/alerts` | A | — | CRUD de alertas |
| `GET /admin/images` | A | filtros: `lugar`, `video_id`, `estado`, `calidad`, paginación | galería (**paginar y filtrar en servidor**: la app filtra en memoria hoy) |
| `GET /admin/stats` | A | — | `{total_fotos, total_lugares, alertas_activas, ultimo_video_numero, ultimo_video_fecha, ...}` |

Notas de contrato:
- **Las fotos pendientes** del panel (`ResumenAdmin.fotosPendientes`) vienen de la cola local de la app, **no** del backend.
- **Sincronización de alertas del admin:** la app guarda `pendientes` como ids sin el tipo de operación (app 11.5). Antes de conectar, ⚠ acordar si el backend recibe un lote `{upserts, borrados}` o llamadas sueltas.
- **Reglas de alerta:** `mensaje` obligatorio y ≤ 200 caracteres; `radio` 5…100 m (múltiplos de 5 es solo de la interfaz); coordenada obligatoria.
- **Errores:** JSON `{"detail": "...", "codigo": "..."}`. Códigos que la app distingue: 401 credenciales, y cualquier fallo de red como `IOException`. ⚠ Decidir que 5xx también sea tratable como «sin conexión» en la app.
- El contrato actual de la app `EscaneoBackend.analizar(fotos: List<File>)` **no envía los `heading`** ni devuelve nada: ambos extremos cambian (app 11.2); este documento asume que se enviarán.

---

## 5. Estructura de `BACKEND_FASTAPI/` (⚠ propuesta)

```
BACKEND_FASTAPI/
├── Dockerfile                  ← imagen X86_64, usuario no root, uvicorn en 0.0.0.0:8000
├── pyproject.toml              ← dependencias fijadas (uv/pip-tools); sin ML pesado
├── alembic.ini
├── alembic/versions/           ← 0001: CREATE EXTENSION vector + tablas
├── app/
│   ├── main.py                 ← crea la app, routers, manejo de errores, /health
│   ├── config.py               ← Settings (pydantic-settings) leyendo SOLO las variables de la sección 3
│   ├── deps.py                 ← dependencias: sesión de BD, usuario actual, exige rol
│   ├── security.py             ← hash de contraseñas, emisión y verificación de JWT
│   ├── db/                     ← motor, sesión, modelos SQLAlchemy
│   ├── schemas/                ← modelos Pydantic = contratos JSON de la sección 4
│   ├── routers/                ← auth, localize, places, alerts, collect, admin_*
│   ├── services/
│   │   ├── embedding_client.py ← httpx hacia EMBEDDING_SERVICE_URL
│   │   ├── localization.py     ← lógica pura de la sección 7 (sin FastAPI)
│   │   ├── storage.py          ← S3: subir, borrar, URL prefirmada
│   │   └── secrets.py          ← Secrets Manager (BD y JWT)
│   └── tasks/                  ← limpieza de huérfanos (⚠ pendiente)
├── scripts/crear_admin.py      ← crea la primera cuenta ADMIN (no hay registro público)
└── tests/                      ← unitarias de localization.py y security.py; integración con Postgres+pgvector local
```

Convenciones:
- **Routers delgados, servicios con la lógica, `localization.py` puro** (se prueba sin red ni BD).
- **Una sola fuente de configuración** (`config.py`); ningún otro archivo lee `os.environ`.
- **Secretos solo desde Secrets Manager** con el rol de la tarea; nunca en variables en claro ni en logs (ni contraseñas ni tokens, igual que la app).
- Los nombres de campos JSON viven en `schemas/` y son el contrato: cambiarlos exige actualizar la sección 4 y el `RemoteX` de la app.

---

## 6. Datos (PostgreSQL + `pgvector`) — ⚠ propuesta

Migración inicial: `CREATE EXTENSION IF NOT EXISTS vector;` y las tablas. Necesita PostgreSQL ≥ 15.2 (RDS usa 16.15).

| Tabla | Campos clave | Notas |
|---|---|---|
| `usuarios` | `id`, `correo` (único), `nombre`, `password_hash`, `rol` (`USER`/`ADMIN`), `activo` | Sin registro público; admin creado por script |
| `videos` | `id` (texto), `nombre`, `creado_en`, `inicio_lat`, `inicio_lng`, `inicio_rumbo`, `estado`, `duracion_s`, `distancia_m`, `pasos` | `id` sin `/`. ⚠ La app genera `rec_NNNN` en local: decidir si el backend reutiliza ese id o asigna el suyo y lo devuelve |
| `fotos` | `video_id` (FK, borrado en cascada), `id` (texto, `"0001"`), `lat`, `lng`, `rumbo` (0…360, nulo si no se sabe), `capturada_en`, `lugar_id` (nulo), `estado`, `calidad`, `s3_key`, `embedding vector(D)` | PK `(video_id, id)`; **índice HNSW** `vector_cosine_ops` sobre `embedding` |
| `lugares` | `id`, `nombre` (único), `categoria`, `lat`, `lng`, `alias` (arreglo), `descripcion`, `referencias`, `imagen_s3_key` | Superconjunto de `LugarDestino` (app 11.6) |
| `alertas` | `id` (UUID, lo genera la app), `lat`, `lng`, `mensaje`, `tipo`, `prioridad`, `radio`, `activa`, `vigencia_inicio`, `vigencia_fin`, `actualizada_en` | Independientes de los videos |
| `consultas` | `id`, `creada_en`, `tipo` (`localize`/`frame`), `confianza`, `lat`, `lng` | Para estadísticas (7.15); **sin fotos ni datos de usuario** (privacidad) |

- **Dimensión `D` del vector:** depende de `MODEL_NAME` del embedding (⚠ `dinov2_vits14` = 384, `dinov2_vitb14` = 768; infra 9.4 asumió `vitb14`). **Cambiar de modelo obliga a reindexar todo el dataset** (nueva columna o tabla y recalcular): fijar el modelo antes de recolectar mucho.
- **Normalizar los vectores** (L2) al guardarlos y al consultar: así coseno y producto interno coinciden.
- **Alertas "activas":** `activa = true` y `ahora` dentro de la vigencia (si la tiene).
- Fotos de ids repetidos entre videos son normales: la identidad es `(video_id, id)` (como `Foto.uid` en la app).

---

## 7. Localización (`services/localization.py`) — ⚠ diseño, sin probar

Entrada: hasta 5 vectores con su `heading` relativo (la app captura cada ~72° desde donde empezó el giro, así que el
`heading` de cada foto es **absoluto magnético** según el sensor, normalizado a 0…360).

1. **Vecinos:** top-`K` (⚠ `K` ≈ 10, a ajustar) por foto con distancia coseno.
2. **Voto espacial:** cada vecino aporta un voto en su `(lat, lng)` ponderado por similitud; se agrupan votos a pocos metros (⚠ radio por calibrar) y se elige el grupo con más peso.
3. **Posición:** promedio ponderado dentro del grupo ganador.
4. **Orientación:** compara el `heading` de cada foto de consulta con el `rumbo` de su vecino ganador; el resultado es el promedio **circular** de las diferencias aplicado al `heading` del escaneo. Fotos sin `rumbo` no votan.
5. **Confianza:** combina (a) similitud media del grupo ganador, (b) fracción de las fotos de consulta que votaron en ese grupo, (c) separación respecto al segundo grupo. `nivel`: ALTA / MEDIA / BAJA con umbrales ⚠ **a calibrar con datos reales**; no se publican como definitivos.
6. **Casos:** dataset vacío → error claro («aún no hay fotos»); ninguna similitud sobre el mínimo → `BAJA` y la app pedirá repetir; menos de 5 fotos → se acepta con menos confianza.

Pendiente de medir: latencia total (5 imágenes en CPU Fargate + consulta), efecto del tamaño de `K`, y si el
filtro por zona (usar la posición PDR cuando viene) mejora la precisión de `/localize/frame`.

---

## 8. Seguridad

- **JWT** firmado con el secreto de `JWT_SECRET_ARN` (⚠ HS256), caducidad corta (⚠ p. ej. 12 h); contiene `sub` (id) y `rol`. El rol se **vuelve a comprobar en el servidor** en cada ruta `/admin/*` y `/collect/*`: la guarda de la app es solo de interfaz (la app no protege las rutas, app 11.8).
- **Contraseñas:** hash con argon2 o bcrypt; límite de intentos por correo (⚠ pendiente); respuesta de login igual para «no existe» y «clave mala».
- **Rutas públicas** aceptan fotos de usuarios: limitar tamaño (⚠ p. ej. 5 MB por foto, máx. 5), tipos (`image/jpeg`) y tasa por IP.
- **Subidas del admin:** validar que el JPG se decodifica antes de guardarlo; nombrar el objeto en S3 por `video_id/foto_id`, nunca con texto del cliente.
- **CORS:** la app es nativa, no hace falta; desactivado por defecto. (Si algún día hay subida directa a S3 con URL prefirmada, habrá que añadir CORS al bucket: infra 12.10.)
- **Logs:** nunca registrar tokens, contraseñas ni el contenido de fotos; registrar ids y duraciones.
- **Privacidad (app decisión 7):** por defecto las fotos de `/localize` **no se guardan**; si el bucket de escaneos existe, solo con la expiración configurada en infra (1 día).
- **Conexión interna al embedding sin TLS** dentro de la VPC (SG: solo backend → embedding).

---

## 9. Operación y robustez

- **Arranque:** el servicio debe iniciar aunque el embedding aún no esté sano (tarda en cargar el modelo, infra 11.5): `/health` del backend es **superficial** (solo el proceso); un `/health/ready` opcional comprueba BD y embedding **sin** usarlo en el ALB, para no reiniciar tareas por una caída ajena.
- **Reintentos:** `embedding_client` con timeout (⚠ ~20 s para 5 fotos) y un reintento; si falla, `503` con mensaje que la app trate como «sin conexión».
- **Idempotencia** de subidas del admin (cola con reintentos en la app).
- **Migraciones:** `alembic upgrade head` al desplegar, no al arrancar cada tarea (varias réplicas en prod competirían). ⚠ Decidir si CI lo corre como tarea aparte de ECS (necesita estar dentro de la VPC: infra 12.1).
- **Despliegue:** CI construye la imagen con el SHA del commit y registra una definición de tarea nueva (infra 7); `ignore_changes = [task_definition]` evita que Terraform lo revierta.
- **Pruebas locales:** `docker compose` con Postgres+`pgvector` y un embedding simulado (vectores deterministas), para no necesitar el modelo.

---

## 10. Plan de implementación por fases

| Fase | Contenido | Aceptación | Estado (2026-10-14) |
|---|---|---|---|
| **B0. Esqueleto** | `main.py`, `config.py`, `/health`, `Dockerfile` X86_64 | La imagen sube a ECR y `GET /health` responde 200 por el ALB (cierra infra 12.13, pasos 1–4) | **Parcial.** Escritos `Dockerfile`, `config.py`, `main.py`; faltan `pyproject.toml` y `services/secrets.py` (12.2). Sin construir ni subir |
| **B1. Datos** | Modelos + Alembic 0001 (con `vector`) | Se conecta con TLS desde dentro de la VPC y `CREATE EXTENSION vector` funciona (infra 12.1) | **Parcial.** Escritos `engine.py`, `0001_inicial.py`, `migrar.sh`; faltan `alembic.ini`, `alembic/env.py`, `models.py`, `session.py`, `secrets.py` (12.2). Sin ejecutar |
| **B2. Auth** | `/auth/login`, JWT, `crear_admin.py`, guarda de roles | La app (con `RemoteAuthRepository`) inicia sesión y un `USER` no pasa a `/admin/*` | Sin empezar |
| **B3. Lectura pública** | `/places`, `/alerts` con datos reales | `LugaresRepository` y alertas de la app dejan de usar stubs | Sin empezar |
| **B4. Recolección** | `/collect/*`, S3, cliente de embedding | Un video de la app llega completo (fotos + vectores) | Sin empezar |
| **B5. Localización** | `/localize` (sección 7) | Con un dataset real, 5 fotos devuelven una posición plausible | Sin empezar |
| **B6. Admin** | `/admin/videos|images|places|alerts|stats` | Galería, Videos, Editor y Panel sin stubs; eliminar video limpia BD y S3 | Sin empezar |
| **B7. Endurecer** | Límites, tasa, pruebas, limpieza de huérfanos | Pruebas en CI; sin huérfanos tras un borrado fallido | Sin empezar |

Orden recomendado: B0 → B1 primero (desbloquean la infra), y B2 antes de cualquier ruta admin. La fase 5 de infra
(CI/CD) no debe empezar hasta terminar B0.

---

## 11. Decisiones abiertas (⚠ por confirmar)

1. **Modelo de embedding** (`vits14` 384 / `vitb14` 768) y dimensión de la columna: fijar antes de recolectar; cambiarlo reindexa todo. La migración `0001` ya fija `EMBEDDING_DIM = 768` (`vitb14`).
2. **Id de video:** ¿el backend acepta el `rec_NNNN` que genera la app o asigna uno propio?
3. **Heading en `/localize`:** confirmar que la app enviará un `heading` por foto (hoy `EscaneoBackend` no lo hace).
4. **Sincronización de alertas:** lote `{upserts, borrados}` o llamadas sueltas.
5. **Privacidad de escaneos** (infra 9.6 / app decisión 7): ¿se guardan las fotos de `/localize`? Hoy: no.
6. **Autorización de rutas públicas:** ¿exigir un token anónimo o una clave de app para frenar abusos?
7. **Grafo de caminos / `GET /route`:** ¿se calcula en el servidor o en el dispositivo? (app decisión 2).
8. **Papelera y auditoría de borrados** (app decisión 10): borrado definitivo inmediato hoy; ¿registro de quién y cuándo?
9. **Dónde corren las migraciones** en CI (tarea ECS aparte vs. otra vía dentro de la VPC). Hoy: `scripts/migrar.sh` las lanza a mano como tarea ECS (⚠ sin probar); falta decidir si CI hace lo mismo.
10. **HTTPS:** hasta que infra resuelva la fase 4, la API solo habla HTTP y Android (API 28+) la bloquea: sirve para `curl`, no para el teléfono.

---

## 12. Catálogo del código existente

> Revisado el 2026-10-14 sobre `BACKEND_FASTAPI.zip`: se leyó el código completo de los archivos presentes y se comprobó
> la sintaxis (`py_compile`, `bash -n`). **Nada se ha ejecutado** contra AWS ni con Python (no se instalaron
> dependencias). Lo no verificado lleva ⚠.

### 12.1 Archivos presentes

| Archivo | Qué expone | Lo usan | Cuidados |
|---|---|---|---|
| `Dockerfile` | Imagen `python:3.12-slim`, `WORKDIR /srv`, usuario no root (`appuser`, uid 10001), `uvicorn app.main:app` en `0.0.0.0:8000` con `--proxy-headers --forwarded-allow-ips "*"`. Copia `pyproject.toml`, `alembic.ini`, `alembic/` y `app/` (no `scripts/`) | CI / ECS / `migrar.sh` | Construir con `docker buildx build --platform linux/amd64`; sin HEALTHCHECK propio (lo hace el ALB). Las dependencias salen de `[project].dependencies` con `tomllib` (rangos, sin lock). `"*"` en `--forwarded-allow-ips` solo es aceptable porque el SG deja pasar únicamente al ALB. ⚠ **Los `COPY` de `pyproject.toml` y `alembic.ini` fallarían: no están en el zip** |
| `app/config.py` | `Settings` (pydantic-settings, `extra="ignore"`) y `get_settings()` con caché. Campos de la sección 3 con valor por defecto (`app_env="dev"`, `aws_region="us-east-1"`, `database_port=5432` como `int`, `database_name="campus"`, el resto `""`), más `local_database_url` y la propiedad `is_prod` | Todo | Es el único archivo que lee el entorno. `LOCAL_DATABASE_URL` no se valida aquí: se rechaza en prod dentro de `engine.py`. `jwt_secret_arn` y los `s3_*` aún no los usa nadie |
| `app/main.py` | App FastAPI (`Campus Locator API`, `0.1.0`); `GET /health` → `{"status":"ok"}` (superficial); `GET /health/ready` (`SELECT 1` en la BD y `GET {EMBEDDING_SERVICE_URL}/health` con timeout de 3 s; responde 200, o 503 con `{status, database, embedding}`); manejador de `HTTPException` → `{detail, codigo: "http_<status>"}` | ALB (`/health`), operador (`/health/ready`) | Sin routers todavía. `/docs` y `/openapi.json` se desactivan en prod; `/redoc` siempre. Solo se maneja `HTTPException`: los **422 de validación** conservan el formato de FastAPI (`detail` como lista, sin `codigo`); ⚠ decidir si se unifican. `/health/ready` da 503 mientras `EMBEDDING_SERVICE_URL` esté vacío (`"sin configurar"`), también en dev con el embedding apagado. Importa `get_engine` al cargar el módulo: un fallo de importación en `app.db.engine` (p. ej. falta `services/secrets.py`) tumba también `/health` |
| `app/db/engine.py` | `get_engine()` (con caché). En AWS cada conexión **nueva** lee el secreto (`secrets.get_secret_json`), conecta con `psycopg` (`sslmode=require`, `connect_timeout=10`) y, si hay `OperationalError`, invalida la caché del secreto y reintenta una vez. Pool de 5 + 5 de desborde, `pool_pre_ping`, `pool_recycle=1800`. Con `LOCAL_DATABASE_URL` (solo fuera de prod) usa esa URL | `/health/ready`; Alembic y `session.py` cuando existan | Lanza `RuntimeError` si faltan `DATABASE_HOST` o `DATABASE_SECRET_ARN`. El reintento atrapa **cualquier** `OperationalError`: con la BD inalcanzable cada conexión espera hasta 2 × 10 s. Hasta 10 conexiones por tarea: ⚠ contrastarlo con el límite de conexiones de RDS al subir réplicas. Espera del secreto `username` y `password` (⚠ sin confirmar). Usa `psycopg` (v3) y `app.services.secrets` (no incluido) |
| `alembic/versions/0001_inicial.py` | `CREATE EXTENSION IF NOT EXISTS vector`, 6 tablas (`usuarios`, `videos`, `lugares`, `fotos`, `alertas`, `consultas`) e índice HNSW coseno (`m=16`, `ef_construction=64`) sobre `fotos.embedding`. `downgrade` borra tablas e índice y deja la extensión | `alembic upgrade head` (`migrar.sh`) | Autocontenida: no importa `models.py` y fija a propósito `EMBEDDING_DIM = 768`, categorías y tipos de alerta. Coincide con la sección 6, salvo: `fotos.embedding` **admite nulo**; ids acotados (`videos.id` 64, `fotos.id` 16, `videos.nombre` 40); y la BD aplica `CHECK` de `rumbo` (0 ≤ x < 360), estado, calidad, categoría, tipo, prioridad y `radio` 5–100. Sin índices en `fotos.lugar_id` ni `alertas.activa` (⚠ valorar al medir). Requiere `pgvector` y SQLAlchemy ≥ 2.0 (`sa.Uuid`) |
| `scripts/migrar.sh` | Lanza `alembic upgrade head` como tarea ECS Fargate única: toma subredes, SG y definición de tarea del servicio `backend` (el primero del clúster cuyo ARN contiene `backend`), sobrescribe el comando, espera a que termine y sale con error si `exitCode` ≠ 0 | Operador / CI | `AWS_REGION` (por defecto `us-east-1`) y `CLUSTER` (`campus-locator-dev-cluster`). `assignPublicIp=ENABLED` va fijo: vale en dev (subredes públicas); en prod con subredes privadas hay que cambiarlo. Necesita la imagen ya en ECR y credenciales de AWS CLI. ⚠ Sin probar. Deducido del código: lee la configuración del servicio, así que debería funcionar con `encendido=false` (0 tareas). Si la tarea no llega a arrancar, informa `exitCode=None`: ver el motivo con `describe-tasks`. Logs en `/ecs/campus-locator-dev-backend` |
| `README.md` | **Copia idéntica de este documento** (mismo contenido, 24 341 bytes) | — | ⚠ No es un README: falta el «cómo ejecutar» (construir, migrar, probar en local) o quitarlo para no mantener dos copias. El zip también trae una copia de `ARCHITECTURE_backend.md` |

### 12.2 Archivos del catálogo que no estaban en el zip

| Archivo | Para qué | Quién lo necesita |
|---|---|---|
| `pyproject.toml` | Dependencias. Las que el código presente ya importa: `fastapi`, `uvicorn`, `pydantic-settings`, `sqlalchemy` (≥ 2.0), `psycopg` (v3, con binarios), `httpx`, `alembic`, `pgvector`; y `boto3` si `secrets.py` usa el SDK (⚠ supuesto) | `Dockerfile` (`COPY`) |
| `alembic.ini` | Configuración de Alembic | `Dockerfile` (`COPY`), `migrar.sh` |
| `alembic/env.py` | Entorno de Alembic, solo modo online, con `get_engine()` | `migrar.sh`: sin él `alembic upgrade head` no corre |
| `app/services/secrets.py` | `get_secret_string/json(arn)` con caché de 5 min e `invalidate(arn)`; `engine.py` usa `get_secret_json(arn)` → dict con `username` y `password` e `invalidate(arn)` | `db/engine.py` y, por su importación, `main.py` |
| `app/db/models.py` (con `EMBEDDING_DIM = 768`), `app/db/session.py`, `app/deps.py` | Modelos de la sección 6, `get_sessionmaker()` y dependencia `get_db` | Routers de B2 en adelante (no bloquean B0 ni la migración) |

### 12.3 Para cerrar B0 y B1

1. Añadir `pyproject.toml`, `alembic.ini` y `app/services/secrets.py`: sin ellos la imagen no se construye y `/health` no arranca.
2. Construir con `--platform linux/amd64`, subir a ECR, encender y probar `GET /health` por el ALB (aceptación de B0, infra 12.13, pasos 1–4).
3. Añadir `alembic/env.py` y correr `scripts/migrar.sh` (aceptación de B1, infra 12.1).

Plantilla por módulo: **ruta** · **responsabilidad** · **entradas/salidas (tipos o JSON)** · **variables de entorno que lee** · **qué tabla toca** · **qué consume de otros módulos** · **cómo probarlo**.

---

## 13. Cómo mantener este documento

- Cambio en `BACKEND_FASTAPI/` → actualizar este archivo **en el mismo PR**, sobre todo la sección 12 (catálogo).
- Un endpoint nuevo o cambiado → sección 4.2 **y** el `RemoteX` correspondiente en `FRONTED_KOTLIN/ARCHITECTURE.md` (11.6).
- Una variable de entorno nueva → primero en `INFRASTRUCTURA_TERRAFORM/ARCHITECTURE.md` (4.1 y 11.4) y luego en la sección 3.
- Un campo de modelo nuevo → secciones 4.1 y 6, y el modelo de la app (11.6).
- Cuando una decisión de la sección 11 se tome, moverla a donde aplique y tacharla de la lista.
- Lo marcado con ⚠ no está verificado: confirmarlo antes de depender de ello.