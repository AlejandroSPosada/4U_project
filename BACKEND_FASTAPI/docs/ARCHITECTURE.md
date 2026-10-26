# ARCHITECTURE — Backend (`BACKEND_FASTAPI`)

| Campo | Valor |
|---|---|
| Versión del documento | **0.12.0** (historia en [`CHANGELOG.md`](./CHANGELOG.md)) |
| Fecha | 2026-10-25 |
| Estado | En construcción: hay código de BE-1.1 a BE-2.2, BE-2.4 y BE-3.1 (`project/`), todo validado en `dev` (BE-3.1 con `validate31.py` sobre `86fc024`), y de BE-3.2 (`POST /v1/localize` y `validate32.py`, §4.10), probado en local y **sin validar en `dev`**: espera el dataset real (FE-2.1), el conjunto de EMB-3.2 y la calibración de los umbrales. Lo de los demás lotes es diseño propuesto; las alertas pasaron a BE-3.3, fuera del núcleo y sin código (§4.9) |
| Qué se construye y en qué orden | [`PLAN.md`](./PLAN.md) · cómo se comprueba cada lote: [`validation/`](./validation/) |

El backend es la **única puerta** de la app hacia los datos: autentica, guarda metadatos y vectores en PostgreSQL
+ pgvector, firma las subidas a S3, consume las colas de ingesta y purga, y calcula la posición de la persona a partir
de sus fotos. Es el único componente que habla con el servicio de embeddings, la base de datos y el almacenamiento.

Su **§5 es la única fuente de verdad** de: la API REST (pública, de recolección y de administración), los códigos de
error, el esquema de la base de datos, el formato de los mensajes de las colas, los procesos de la imagen y los
parámetros operativos del backend.

---

## 1. Propósito y alcance

### 1.1 Qué cubre
- API REST para la app Android (flujo público y de administración).
- Algoritmo de localización por similitud de imágenes.
- Ingesta asíncrona del dataset (miniaturas, vectores, estados) y purga de lo borrado.
- Esquema y migraciones de la base.

### 1.2 Qué no cubre
- Cómo se calcula un vector: `SERVICE_EMBEDDING/docs/ARCHITECTURE.md`.
- Recursos de AWS, variables de entorno inyectadas, permisos y despliegue:
  `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md`.
- Seguimiento continuo de la posición (PDR) y fusión con la corrección visual: viven en la app
  (`FRONTEND_KOTLIN/docs/ARCHITECTURE.md` §2.3).
- Cálculo de rutas (diferido, ADR-BE-11).

### 1.3 Regla de contratos
Este documento solo define lo que el backend **expone**. Lo que **consume** se enlaza:

| Consume | Definido en |
|---|---|
| Variables de entorno y secretos (`DB_*`, `JWT_SECRET`, `S3_BUCKET_DATASET`, `SQS_URL_*`, `EMBEDDING_URL`…) | `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.4 |
| Bucket, prefijos y notificación S3 → SQS; atributos de las colas | Infra §5.5 y §5.6 |
| `POST /v1/embed`, `GET /v1/info`, `GET /health/ready` y el formato del vector | `SERVICE_EMBEDDING/docs/ARCHITECTURE.md` §5 |

Un cambio de interfaz se hace primero en el §5 del dueño, con entrada en su `CHANGELOG.md`, y luego en el código.

---

## 2. Contexto en el sistema

```
 App Android ──HTTPS──► API Gateway ──VPC Link──► api (FastAPI) ──────HTTP──────► embedding (DINOv2)
      │                                             │   │   │                          ▲
      │ PUT prefirmado                              │   │   └── SendMessage ─► SQS purga ──┐
      ▼                                             │   ▼                                 │
     S3 dataset/ ──ObjectCreated──► SQS ingesta ──► worker ──────────────HTTP──────────────┘
                                                    │   │
                                                    ▼   ▼
                                     PostgreSQL 17 + pgvector  (RDS)
```

| Proceso | Responsabilidad | Toca |
|---|---|---|
| `api` | Endpoints HTTP, autenticación, firma de URLs, localización síncrona, encolar purgas y re-procesados, reconciliador de purgas | RDS, S3 (firmar y `HEAD`), SQS (enviar), embedding |
| `worker` | Ingesta (miniatura + vector + estado, BE-2.2) y purga (borrar objetos y filas, BE-4.1) | RDS, S3 (leer, escribir, borrar), SQS (recibir, borrar, devolver), embedding |
| `migrate` | Migraciones Alembic y creación del admin inicial | RDS |

Los tres salen de **la misma imagen** con distinto comando (§5.9).

---

## 3. Arquitectura en AWS (vista del backend)

- Corre en ECS Fargate, `X86_64`, como servicios `api` y `worker` y tarea suelta `migrate` (tamaños y escalado:
  infra §3.4). El servicio de embeddings también, con 2 vCPU (infra ADR-INF-14).
- `api` recibe tráfico solo desde API Gateway por VPC Link en el puerto `8000`. Detrás de API Gateway: máximo 30 s
  por petición y 10 MB de cuerpo; por eso las fotos del dataset no pasan por la API (ADR-BE-04).
- `embedding` está **apagado por defecto** en `dev`: se enciende a mano (`embedding.py encender` de infra) y se apaga solo
  tras 45 min sin uso y a las 22:00 (infra §3.4 y §5.10). Apagado, `/v1/localize` responde
  `503 EMBEDDING_NO_DISPONIBLE` y los mensajes de ingesta esperan en la cola.
- `worker` escala de 0 a 1 según la profundidad de las colas, **solo con `embedding` encendido** (infra §5.10).
- La base es RDS PostgreSQL 17 con pgvector 0.8.x, accesible solo desde la VPC y con TLS obligatorio.
- Logs a CloudWatch (`/campus-locator/dev/<proceso>`) en una línea JSON por evento (§5.10).
- Despliegue: `backend.yml` construye la imagen, ejecuta `migrate` (desde BE-1.2) y actualiza `api` y `worker`
  (infra §5.9; detalles del backend en §4.2).

---

## 4. Componentes y funcionamiento (por lote)

### 4.1 Estructura del código

```
BACKEND_FASTAPI/
├── docs/
│   ├── ARCHITECTURE.md, PLAN.md, CHANGELOG.md
│   └── validation/              validation-<fase>-<n>.md: cómo se comprueba cada lote (§5.11)
└── project/                     todo el código
    ├── src/
    │   ├── app/
    │   │   ├── main.py          crear_app(): routers, middleware, manejadores de error y (BE-4.1) el reconciliador
    │   │   ├── config.py        Settings (pydantic-settings): lee las variables de infra §5.4 y los parámetros de §5.10
    │   │   ├── logs.py          Logs JSON por línea (§5.10) y `request_id` de la petición en curso
    │   │   ├── middleware.py    X-Request-Id, evento `peticion` y 500 ante fallos no previstos (§4.2)
    │   │   ├── errores.py       ErrorApi; excepciones → formato de §5.1 con los códigos de §5.6; BaseNoDisponible → 503 (BE-1.3)
    │   │   ├── api/
    │   │   │   ├── dependencias.py  obtener_ajustes, obtener_motor, obtener_cola_hash (BE-1.3, §4.4); obtener_almacen (BE-2.1, §4.5)
    │   │   │   ├── cuerpo.py    leer_cuerpo: el cuerpo de la petición en memoria, con tope (BE-2.4, §4.8)
    │   │   │   └── v1/          Routers: salud (BE-1.1), auth y reservados (BE-1.3), collect y admin_videos (BE-2.1), admin_diagnostico (BE-2.4), lugares (BE-3.1: `router_publico` en /v1 y `router_admin` en RUTAS_ADMIN, §4.9), localizar (BE-3.2: `router` en /v1, público, §4.10); __init__.py monta /admin y /collect con requiere_admin (§4.4). Después: alerts (BE-3.3), admin_*
    │   │   ├── esquemas/        Modelos Pydantic de entrada y salida (son el contrato de §5.3–§5.5): errores, salud, auth (BE-1.3); comun y videos (BE-2.1, §4.5); diagnostico (BE-2.4, §4.8); lugares (BE-3.1, §4.9); localizacion (BE-3.2, §4.10)
    │   │   ├── dominio/         Lógica pura y probable sin red ni base: enumerados.py, validaciones.py (BE-1.2 y BE-1.3; qué ofrecen, en §4.3 y §4.4); recoleccion.py (BE-2.1, §4.5); imagenes.py (Pillow) y mensajes.py (BE-2.2, §4.6); multipart.py y fotos.py (BE-2.4, §4.8); lugares.py y geo.py (BE-3.1, §4.9); localizacion.py (BE-3.2: el algoritmo, con la corrección de rumbo, §4.10)
    │   │   ├── servicios/       Casos de uso: migracion (BE-1.2); autenticacion, usuarios y auditoria (BE-1.3, §4.4); recoleccion, videos y limpieza (BE-2.1, §4.5); ingesta (BE-2.2, §4.6); diagnostico (BE-2.4, §4.8); lugares (BE-3.1, §4.9); localizar (BE-3.2, §4.10); purgar, alertas (BE-3.3), estadisticas
    │   │   ├── db/              modelos.py (SQLAlchemy), sesion.py (motor, conexiones y `transaccion`), esquema.py (§5.7 comprobable), qué ofrecen en §4.3 y §4.4; consultas.py (la búsqueda de vecinos, BE-2.4, §4.8)
    │   │   ├── clientes/        embedding.py (httpx: `esta_listo` desde BE-1.1, `vectorizar` desde BE-2.2); s3.py (boto3 en hilos de anyio, BE-2.1, §4.5; `descargar` y `escribir` desde BE-2.2); sqs.py (BE-2.2, §4.6)
    │   │   ├── seguridad/       hash.py (argon2id, §4.3), tokens.py (JWT, §5.2) y dependencias.py (requiere_admin), BE-1.3 (§4.4)
    │   │   ├── worker.py        Bucle de consumo de `ingesta` (python -m app.worker, BE-2.2, §4.6); `purga` llega con BE-4.1
    │   │   └── cli.py           python -m app.cli: migrar y verificar-esquema (BE-1.2), crear-usuario y desactivar-usuario (BE-1.3), limpiar-validacion (BE-2.1)
    │   └── ops/                 validate<fase><n>.py y comun.py: validadores de los lotes BE-x.y (§5.11)
    ├── migrations/              Alembic: env.py y versions/ (SQL explícito; 0001 = esquema inicial de §5.7)
    ├── tests/                   unit/, api/, contrato/ (vs §5), base/ (marca `base`: PostgreSQL efímero, §4.3) y ops/ (validadores)
    ├── docker-compose.yml       entorno `local` (§5.11)
    ├── Dockerfile               python:3.12-slim, usuario sin privilegios, puerto 8000 (§5.9)
    ├── .dockerignore            la imagen solo recibe src/app/, migrations/, pyproject.toml, uv.lock y .python-version
    ├── pyproject.toml           uv; ruff; pytest; grupo `ops` para los validadores; boto3 en las dependencias de la imagen desde BE-2.1 y Pillow (12.3) desde BE-2.2
    └── uv.lock, .python-version dependencias fijadas y Python 3.12: imagen y CI instalan con `uv sync --frozen`
```

Reglas internas:
- `dominio/` no importa nada de FastAPI, SQLAlchemy ni boto3: se prueba sin infraestructura.
- Los routers solo validan, llaman a un servicio y traducen errores de dominio a los códigos de §5.6.
- Ningún log incluye tokens, contraseñas, URLs prefirmadas ni bytes de imagen. Tampoco los valores de una sentencia
  SQL: los motores usan `hide_parameters` y las trazas omiten el `DETAIL` de PostgreSQL, que copia la fila rechazada
  (§4.3, §5.10).

### 4.2 BE-1.1 — Base del servicio
FastAPI con un único proceso de uvicorn (la tarea tiene 0,25 vCPU). Un middleware ASGI asigna `X-Request-Id` (o
respeta el del cliente, con las reglas de §5.1), lo pone en cada línea de log y registra el evento `peticion` de cada
solicitud (§5.10). Si una excepción no controlada llega hasta él, responde `500 ERROR_INTERNO` con el formato de §5.1
(y su `X-Request-Id`) y deja la traza en una sola línea JSON. Los manejadores de FastAPI convierten al mismo formato el
404 de una ruta inexistente, el 405, el cuerpo mal formado y los errores de validación (§5.6). `/v1/health` no toca la
base ni embeddings (lo usan la app y el *health check* del contenedor); `/v1/health/ready` sí (§5.3).

**Logs.** uvicorn también escribe en JSON y su log de acceso se desactiva: lo reemplaza `peticion`, que lleva el
`request_id`. Las respuestas correctas de `/v1/health` se registran en `DEBUG`, porque el *health check* llama cada 30 s
y en `dev` `LOG_LEVEL = INFO`. Los loggers de `httpx`, `httpcore`, `botocore`, `boto3`, `urllib3` y `s3transfer` quedan
en `WARNING`: en niveles más bajos escriben URLs completas, que podrían ser prefirmadas (§4.1). `asyncio` también,
por ruido.

**`worker` provisional (hasta BE-2.2).** `backend.yml` despliega `api` y `worker` con la misma imagen (infra §5.9).
Para que una tarea de `worker` no fallara al arrancar, en BE-1.1 `python -m app.worker` solo registraba un latido cada
60 s (`evento = latido`, `modo = sin_consumo`) y terminaba limpio con SIGTERM, sin consumir las colas. Desde BE-2.2
consume `ingesta` (§4.6); ese modo queda solo para cuando falta configuración (§4.6, «Arranque»). La purga llega con
BE-4.1 (§4.11): hasta entonces los mensajes de `purga` siguen en la cola.

**Despliegue con `backend.yml`** (`.github/workflows/` de la raíz del monorepo). Sigue la secuencia de infra §5.9; el
paso `migrate`, desde BE-1.2, está en §4.3. Lo propio del backend:
- Disparadores: PR y *push* a `main` con cambios en `BACKEND_FASTAPI/project/**` o en el propio `backend.yml` (infra
  §3.9). En los dos, `uv sync --frozen --group ops`, `ruff check`, `ruff format --check` y `pytest`, con un PostgreSQL
  efímero desde BE-1.2 (§4.3). En `main`, el despliegue solo empieza si las pruebas pasan.
- Mismas convenciones que `infra.yml`: `permissions: {}` y los permisos mínimos en cada job, acciones fijadas por SHA
  con la versión en un comentario, `persist-credentials: false`, `allowed-account-ids` y uv 0.11.32 (el que copia el
  `Dockerfile`). Una ejecución nueva de un PR cancela la anterior; los despliegues de `main` van en fila.
- El *login* en ECR usa `aws ecr get-login-password` y la comprobación de la etiqueta, `ecr batch-get-image`: son los
  permisos que tiene `gha-deploy` (infra §5.8), que no incluyen `ecr:DescribeImages`.
- La imagen se construye con `--build-arg GIT_COMMIT=${GITHUB_SHA}` (§5.9). Si la etiqueta ya existe en ECR (reintento
  del workflow), no se vuelve a publicar: las etiquetas son inmutables.
- Cada revisión nueva de `campus-locator-dev-migrate` (desde BE-1.2), `campus-locator-dev-api` y
  `campus-locator-dev-worker` parte de la última de su familia (la de Terraform o la del despliegue anterior) y solo
  cambia la imagen del contenedor `app`; se quitan los campos de solo
  lectura de `describe-task-definition` (`taskDefinitionArn`, `revision`, `status`, `requiresAttributes`,
  `compatibilities`, `registeredAt`, `registeredBy`, `deregisteredAt` y `deleteRequestedAt`). Así `worker` conserva
  su comando (`python -m app.worker`) y `migrate`, el suyo (`python -m app.cli migrar`).
- Si `api` tiene `desiredCount = 0` (primer despliegue), pasa a 1.
- Tras `wait services-stable`, comprueba que el despliegue `PRIMARY` de `api` sea la revisión nueva con
  `rolloutState = COMPLETED` (espera hasta 2 min más a que llegue a ese estado); si el *circuit breaker* hizo
  *rollback*, el workflow falla. `worker` se actualiza pero no se espera: escala solo y suele estar en 0.
- Para volver a desplegar el mismo commit (p. ej. tras un cambio de Terraform en una tarea, infra ADR-INF-09) se usa
  «Re-run all jobs» en la última ejecución de `main`. Un commit que solo toca `backend.yml` también despliega (con su
  propio SHA y el mismo `project/`); BE-1.1 C3a lo acepta porque compara el contenido de `project/`, no solo el SHA.
- El job de despliegue **no** declara `environment:`: el rol `gha-deploy` solo confía en
  `sub = repo:<github_repo>:ref:refs/heads/main` (infra §5.8), y con un entorno el `sub` cambiaría.

### 4.3 BE-1.2 — Base de datos y migraciones
SQLAlchemy 2 asíncrono sobre `asyncpg` (`app/db/sesion.py`): un motor por proceso, con TLS según `DB_SSLMODE`
(`require` en AWS, porque RDS lo exige) y `DB_CONNECT_TIMEOUT_S` para abrir cada conexión (§5.10). `api` crea el suyo
al arrancar, sin conectarse: arranca aunque la base no responda, y lo informa `GET /v1/health/ready` (§5.3). Cualquier
fallo al **abrir** una conexión (red, DNS, TLS, credenciales, falta de permiso `CONNECT`, base inexistente, tiempo
agotado) es «base no disponible», si se abre con `conectar` (abajo); después, solo lo son los de red (un `OSError`
que no sea de archivos), el tiempo agotado, la clase 08 de PostgreSQL, el servidor que se apaga o aún no acepta
conexiones (57P01, 57P03) y las conexiones que SQLAlchemy da por perdidas. Los motores usan
`hide_parameters` (los errores no llevan los valores de la sentencia) y las trazas de los logs omiten el `DETAIL` de
PostgreSQL, que puede copiar la fila rechazada: un hash de contraseña o un correo (§5.10). Alembic
aplica el esquema de §5.7; las migraciones están en `project/migrations/` (SQL explícito; `0001` crea la extensión
`vector`, los tipos enumerados, las tablas, los índices y el índice HNSW parcial) y entran en la imagen (§5.9).

**`python -m app.cli migrar`** (tarea `migrate`, paso 2 de `backend.yml`). Es idempotente: se ejecuta en cada
despliegue.
1. Toma un bloqueo consultivo de sesión (`pg_advisory_lock` con la clave `7242031220260001`, la misma en todo el
   proyecto): dos `migrate` a la vez (un despliegue y un validador) se ejecutan en fila. Espera hasta 5 min; si no lo
   consigue, termina con 1 (`migracion_fallida`, motivo `LockNotAvailableError`).
2. `alembic upgrade head`: todas las revisiones pendientes en una sola transacción. El DDL de PostgreSQL es
   transaccional, así que una migración que falla no deja nada a medias.
3. En otra transacción, después de confirmar las migraciones: si no hay **ninguna** fila con rol `admin` (activa o
   no), crea el admin inicial: `ADMIN_INICIAL_CORREO` normalizado (§4.3, «Contraseñas y correo»),
   `ADMIN_INICIAL_PASSWORD` con argon2id y nombre «Administrador». Si ya hay uno, no toca nada: desactivar al admin a
   propósito no lo revive. Si el correo ya es de un usuario `user`, falla (código 1) en lugar de cambiarle el rol; para
   eso está `crear-usuario --rol admin` (BE-1.3). Si este paso falla (1, o 3 porque faltan `ADMIN_INICIAL_*`), la base
   **ya queda** en la revisión nueva; en `backend.yml`, `api` y `worker` siguen con la imagen anterior sobre ese
   esquema hasta un despliegue que pase.

Registra `migracion_iniciada` y `migracion_terminada` (revisión anterior y nueva, si aplicó algo y qué pasó con el admin
inicial); los errores, con los eventos y códigos de salida de §5.9 y §5.10.

**`python -m app.cli verificar-esquema`** (tarea suelta con la definición de `migrate`; la lanza el validador de BE-1.2).
En una transacción de solo lectura toma el mismo bloqueo consultivo en modo compartido (si hay un `migrar` en curso,
espera hasta 5 min a que termine en lugar de leer un esquema a medio migrar; si no termina, sale con 2 y `verificacion_fallida`), lee el catálogo del esquema `public` y lo
compara con `app/db/esquema.py`, la forma comprobable de §5.7. Cada diferencia es un evento `esquema_diferencia` (objeto, aspecto, esperado y encontrado) y el
resultado, `esquema_verificado`. Su código de salida distingue «difiere» (1) de «no se pudo verificar» (2, §5.9).

**Coherencia del esquema.** La migración, los modelos (`app/db/modelos.py`) y `esquema.py` describen lo mismo: las
pruebas aplican la migración y `create_all` de los modelos a bases vacías y comprueban que las dos coinciden exactamente
con `esquema.py`. Cambiar el esquema es una revisión nueva en `migrations/versions/` más esos dos archivos y §5.7, en el
mismo cambio (cómo, abajo, en «Migraciones nuevas»). Los textos de `esquema.py` (restricciones, índices) son los del
catálogo de PostgreSQL 17, la versión de RDS y de CI (riesgo R11; confirmados con 17.9 en `dev` al validar BE-1.2).

**Pruebas con base.** Las marcadas `base` (`tests/base/`, marca de pytest `base`) crean una base nueva por prueba en el
PostgreSQL de `PRUEBAS_DB_URL` y la borran al terminar. La URL es `postgresql://usuario:contraseña@host:puerto/base`,
con `?sslmode=…` opcional para las bases de prueba (por defecto, `disable`); esa `base` solo sirve para crear y borrar
las de prueba, con una conexión que usa el modo TLS por defecto de asyncpg. El usuario necesita permiso para crear
bases, roles (una prueba crea uno sin permiso `CONNECT`) y la extensión `vector`: en CI y en `docker-compose.yml` es el usuario de la imagen
`pgvector/pgvector:pg17`, que es superusuario. En local, con el `db` de `docker compose`:
`postgresql://campus_app:local-solo-desarrollo@localhost:5432/campus_locator` (o el puerto de `DB_PUERTO_LOCAL`). Sin
`PRUEBAS_DB_URL` se omiten; si está y el servidor no responde, fallan. En `backend.yml` el servidor es un servicio
`pgvector/pgvector:pg17` y `PRUEBAS_DB_OBLIGATORIA=1` hace que fallen, en lugar de omitirse, si falta `PRUEBAS_DB_URL`.
El job de pruebas instala también el grupo `ops`, para probar los validadores.

Fixtures de `tests/conftest.py` para las pruebas `base`: `base_vacia` crea una base vacía (`pruebas_<12 hex>`, sin
extensión ni tablas), devuelve los `Settings` que apuntan a ella, con `ADMIN_INICIAL_*` =
`admin.pruebas@campus.edu.co` / `Pruebas-admin-123`, y la borra al terminar (`DROP DATABASE … WITH (FORCE)`);
`base_migrada` es `base_vacia` después de `python -m app.cli migrar` (esquema de §5.7 y ese admin). `logs_json` (de
BE-1.1) captura las líneas JSON de los logs de la prueba (`.lineas`).

**Paso `migrate` de `backend.yml`** (infra §5.9, paso 2). Registra la revisión nueva de `campus-locator-dev-migrate`
junto con las de `api` y `worker` (§4.2), la lanza con `run-task` (Fargate, `SUBREDES_TAREAS`, `SG_MIGRATE`, IP
pública), espera a que pare, imprime su log (`/campus-locator/dev/migrate`, stream `migrate/app/<id de la tarea>`) y
falla si el contenedor `app` no sale con 0; entonces `api` y `worker` no se actualizan (sus revisiones quedan sin usar,
y el siguiente despliegue parte de ellas). Solo usa permisos de `gha-deploy` (infra §5.8): `run-task` sin etiquetas
(que pedirían `ecs:TagResource`), `describe-tasks` y `logs:GetLogEvents` sobre ese log group.

**Para los lotes siguientes: qué ofrece BE-1.2 al código.**

*Conexión* (`app.db.sesion`):
- `crear_motor(ajustes, proceso, *, pool=None, desborde=0)` devuelve un `AsyncEngine` de SQLAlchemy sin conectarse.
  `pool=None` es sin pool (una conexión por uso, para la CLI); con `pool`, usa `pool_pre_ping`. Lanza
  `ConfiguracionIncompleta` (atributos `faltan` e `invalidas`, con nombres de variables) si falta `DB_HOST`,
  `DB_NAME`, `DB_USER` o `DB_PASSWORD`, o si `DB_SSLMODE` no es válido (§5.9); `DB_SSLMODE` se comprueba primero,
  así que, si además faltan variables, solo informa de ella. Cada conexión aparece en `pg_stat_activity` con
  `application_name = campus-locator-<proceso>`.
- `conectar(motor)`: gestor de contexto asíncrono que entrega una `AsyncConnection` y la cierra al salir; cualquier
  fallo al abrirla llega como `BaseNoDisponible`. `comprobar_conexion(motor, timeout_s)` hace `SELECT 1` y lanza
  `BaseNoDisponible` si no puede (lo usa `/v1/health/ready`).
- `es_fallo_de_conexion(exc)` dice si un error con la conexión ya abierta es «base no disponible» (las reglas de
  arriba; sigue `orig` y `raise … from`, no el contexto implícito). Por sí sola no reconoce todos los fallos al abrir
  (credenciales, base inexistente, falta de `CONNECT`…): esos solo cuentan si llegan como `BaseNoDisponible`, así que
  las conexiones se abren con `conectar`. `describir(exc)` da el motivo corto y sin secretos que llevan los eventos:
  `<clase de la causa original>: <primera línea de su mensaje>` (sigue `orig` y `raise … from`), como mucho 300
  caracteres.
- En `api`, el motor está en `app.state.motor` (pool `DB_POOL_API` + `DB_POOL_API_DESBORDE`, §5.10) y se cierra al
  parar; vale `None` si la configuración está incompleta, y entonces `app.state.motivo_sin_motor` dice por qué. El
  `worker` crea el suyo desde BE-2.2 (`crear_motor(ajustes, "worker", pool=DB_POOL_WORKER)`, §4.6; aparece como
  `campus-locator-worker`), y cada comando de la CLI usa uno sin pool.
- Cómo lo usa un router (dependencia `obtener_motor`, `sesion.transaccion` y el `503` de `BaseNoDisponible`): lo añadió
  BE-1.3, en §4.4.

*Modelos, vectores y enumerados*:
- `app.db.modelos` (SQLAlchemy 2 declarativo; `Base.metadata` es §5.7): `Usuario` (`usuarios`), `Lugar` (`lugares`),
  `Alerta` (`alertas`), `Video` (`videos`), `Imagen` (`imagenes`), `Embedding` (`embeddings`), `EventoLocalizacion`
  (`eventos_localizacion`) y `Auditoria` (`auditoria`). `actualizado_en` lo pone el `onupdate` de SQLAlchemy (ORM o
  `update()` de Core); un `UPDATE` escrito como texto tiene que poner `actualizado_en = now()` él mismo.
- `embeddings.vector` usa un tipo de columna propio, `Vector(384)`, sin el paquete `pgvector` (que arrastraría numpy a
  la imagen). Recibe cualquier secuencia de números y devuelve `list[float]`; viaja como texto `[x1,x2,…]`. En SQL
  escrito a mano, el parámetro va como ese texto con `CAST(:v AS vector)`.
- `app.dominio.enumerados`: un `StrEnum` por tipo enumerado de §5.7 (`RolUsuario`, `CategoriaLugar`, `TipoAlerta`,
  `PrioridadAlerta`, `EstadoVideo`, `EstadoImagen`, `CalidadImagen`) y uno por cada columna de texto con valores fijos
  de `eventos_localizacion` (`OrigenLocalizacion`, `ResultadoLocalizacion`, `NivelConfianza`). El nombre de cada
  miembro es su valor. Hoy solo los usan los modelos, y solo los siete de §5.7 (`origen`, `resultado` y `nivel` son
  `text` con `CHECK`); los esquemas Pydantic y la lógica de los lotes siguientes los importan de aquí.

*Contraseñas y correo*:
- `app.seguridad.hash`: `calcular(password)` devuelve el hash argon2id, con sal aleatoria, en formato PHC
  (`$argon2id$v=19$m=65536,t=3,p=4$…`: los parámetros por defecto de argon2-cffi 25.1, 64 MiB, 3 pasadas y 4 hilos).
  `verificar(hash, password)` devuelve `True` o `False`; un hash mal formado da `False` (salvo uno con caracteres no
  ASCII, que lanza `UnicodeEncodeError`; los de `calcular` siempre son ASCII). El hash guarda sus parámetros: si un
  día cambian, los hashes viejos se siguen verificando. Ni la contraseña ni el hash se registran.
- `app.dominio.validaciones.normalizar_correo(correo)`: quita los espacios de alrededor y pasa a minúsculas; no toca
  los espacios internos ni valida el formato. Así se guarda (`usuarios_correo_check`) y así se busca.

*Migraciones nuevas* (un lote que cambie el esquema):
1. Un archivo `migrations/versions/NNNN_<descripcion>.py` con `revision = "NNNN"` (cuatro dígitos, la siguiente) y
   `down_revision` = la anterior. SQL explícito, **una sentencia por `op.execute`** (asyncpg prepara cada sentencia y
   no admite varias juntas), con `upgrade()` y `downgrade()`: las pruebas bajan hasta la base vacía y vuelven a subir.
2. No hay `alembic.ini`: `alembic revision`, `alembic upgrade` y los demás comandos de Alembic no sirven (`env.py`
   exige la conexión que le entrega `migrar` y rechaza el modo *offline*). Se aplica con `python -m app.cli migrar` (en local,
   `docker compose run --rm api python -m app.cli migrar`; en las pruebas, con `base_migrada`).
3. En el mismo cambio: `app/db/modelos.py`, `app/db/esquema.py` y §5.7 (versión menor de este documento, con
   CHANGELOG). En `esquema.py`, restricciones, índices y valores por defecto van con el texto que devuelve el catálogo
   de PostgreSQL 17 (p. ej. `CHECK ((btrim(nombre) <> ''::text))`). La revisión que exige `verificar-esquema` es la
   última de `migrations/versions/`: no se escribe a mano.
4. Las pruebas comprueban que la migración y los modelos dejan exactamente `esquema.py`. Con §5.7 la comparación es
   parcial: las columnas (tipo, nulo y valor por defecto) de sus tablas «Columna | Tipo | Nulo | Por defecto», los
   valores del párrafo de tipos enumerados, que existan las restricciones, índices y secuencias que cita y que aparezca
   el nombre de todo índice. Las definiciones (el texto de un `CHECK`, el `USING`, `WITH` o `WHERE` de un índice) no se
   comparan: se revisan a mano. El formato de §5.7 se conserva.
5. `migrate` corre antes de actualizar `api` y `worker`, y si el despliegue falla después, la imagen anterior sigue
   sobre el esquema nuevo: una migración no quita ni renombra nada que use la imagen anterior (eso va en una migración
   posterior).
6. Una versión de vector nueva lleva su índice parcial, `embeddings_hnsw_<versión con cada carácter que no sea letra
   ni dígito cambiado por _>` (para `dinov2-vits14/pp-v1`, `embeddings_hnsw_dinov2_vits14_pp_v1`), con el `USING` y el
   `WITH` de §5.7 y `WHERE version_vector = '<versión>'`.

### 4.4 BE-1.3 — Autenticación

**Login** (`POST /v1/auth/login`, §5.3; `servicios/autenticacion.py`). Todos los intentos hacen el mismo trabajo, para
que ni la respuesta ni el tiempo revelen qué correos existen (ADR-BE-13):
0. Pydantic rechaza con `422 VALIDACION` un `identificador` o `password` vacío, largo de más o con un carácter NUL o un
   sustituto suelto (`validaciones.motivo_texto_no_admitido`): PostgreSQL rechaza el NUL en `text` (22021) y, sin
   esta regla, el login respondía `500` sin fila de auditoría.
1. Sin `JWT_SECRET`, `500 ERROR_INTERNO` antes de tocar la base (evento `configuracion_incompleta`, proceso `api`).
2. Reserva un puesto en la `ColaHash` de la app: si ya hay `LOGIN_HASH_CONCURRENTES` (2) + `LOGIN_HASH_COLA_MAX` (8)
   intentos dentro, `503 SERVICIO_OCUPADO` con `Retry-After: 5` sin tocar la base.
3. Busca el usuario por correo normalizado (`normalizar_correo`, §4.3) en una transacción corta.
4. Verifica **una** contraseña con argon2id, fuera de la base y en un hilo (`anyio.to_thread`), como mucho
   `LOGIN_HASH_CONCURRENTES` a la vez (cada una usa 64 MiB y la tarea tiene 0,5 GB): la del usuario o, si el correo no
   existe, `hash.hash_ficticio()` (una contraseña aleatoria con los mismos parámetros, calculada al arrancar `api`). Si
   el turno no llega en `LOGIN_HASH_ESPERA_MAX_S` (10 s), también `503 SERVICIO_OCUPADO`. Así un cliente insistente
   no acumula una cola sin fin, nadie espera más de ~10 s más un hash (API Gateway corta a los 30 s) y `api` no hashea
   para peticiones que ya se cortaron.
5. En otra transacción anota el intento en `auditoria` (`usuario.login`, §5.7) y, si entró, fija
   `usuarios.ultimo_acceso_en`. Registra el evento `login` (§5.10).
6. Correo desconocido, contraseña incorrecta o usuario inactivo → `401 CREDENCIALES_INVALIDAS`, mismo cuerpo y mismos
   encabezados; si no, firma el token (§5.2) y responde `200`.

Un rechazo por la cola (pasos 2 y 4) no comprobó ninguna contraseña: no se anota en `auditoria` (solo el evento
`login` con `resultado = rechazado`), para que una avalancha no traslade la carga a la base; §5.3 y §5.7 lo dicen así.

Devuelve el token **también** a usuarios `user`: la app decide no abrir el panel (`LoginViewModel`). Ni la
contraseña ni el identificador escrito se guardan ni se registran (un identificador desconocido puede ser una
contraseña escrita en el campo equivocado). Comprobado en `local` (15 muestras de cada caso, imagen sin límite de
CPU): mediana de 92–94 ms en los cuatro casos (desconocido, contraseña incorrecta, inactivo y correcto). En `dev`, con
0,25 vCPU, 1,1–1,2 s por login visto desde el cliente, una petición a la vez (C2 de `validate13.py`, 2026-10-25:
1168 y 1116 ms); con dos a la vez comparten la CPU (sin medir). No hay límite de intentos por cuenta: R7.

**Autorización** (`seguridad/dependencias.py`, ADR-BE-03, ADR-BE-13). `requiere_admin` es una dependencia de los
routers `/v1/admin` y `/v1/collect` (`app/api/v1/__init__.py`), así que corre antes que cualquier otra cosa de la
ruta, incluida la validación del cuerpo (una petición sin token con un cuerpo no válido da `401`, no `422`; probado).
Rechaza en este orden: sin `Authorization: Bearer <token>` → `401 NO_AUTENTICADO`; token vencido (con firma válida) →
`401 TOKEN_EXPIRADO`; cualquier otro defecto del token → `401 TOKEN_INVALIDO`; después consulta la base: `sub` que no
existe o usuario desactivado → `401 TOKEN_INVALIDO`; rol `admin` que falta en el token **o** en la base → `403
SIN_PERMISOS`. Sin token válido la respuesta no depende de la base (sin base, `401`; con token válido y sin base,
`503`). Los `401` llevan `WWW-Authenticate: Bearer` y cada rechazo registra `autorizacion_rechazada` (§5.10). Los
endpoints reservados (§5.3) ya existen: los públicos responden `501` y `GET /v1/admin/stats/uso` responde `501` solo
después de pasar `requiere_admin`.

**Usuarios por línea de comandos** (`servicios/usuarios.py`, §5.9): `crear-usuario` crea o, si el correo ya existe,
actualiza nombre, contraseña y (solo con `--rol`) rol, y lo reactiva; `desactivar-usuario` lo desactiva (sus tokens
dejan de valer en la siguiente petición). No hay borrado: la fila queda por la auditoría. Ninguno deja la base sin un
admin **activo**: quitar el rol o desactivar a un usuario con rol `admin` exige que quede otro admin activo (si no,
código 1). Sin ninguna fila `admin`, además, `migrar` intentaría crear el admin inicial (§4.3) y, si su correo es el de
ese usuario, fallaría en cada despliegue. Las dos operaciones toman al empezar su transacción el bloqueo consultivo
`7242031220260002` (`pg_advisory_xact_lock`; el de `migrar` es `…0001`): dos a la vez van en fila, así la comprobación
del último admin no tiene carreras y dos `crear-usuario` del mismo correo nuevo dan `creado` y `actualizado` (el
`INSERT` lleva además `ON CONFLICT (correo) DO NOTHING`, por si el correo lo crea otro proceso). Cada cambio deja una
fila en `auditoria` (`usuario.crear`, `usuario.actualizar`, `usuario.desactivar`, §5.7).

**Acceso a la base desde la API** (lo que BE-1.2 dejó para este lote). Cada unidad de trabajo es
`async with sesion.transaccion(motor) as conexion:` (abajo): la conexión solo se tiene durante el bloque, así que lo
lento sin base (el hash, una llamada a embeddings) va fuera y no ocupa el pool (5 + 5). Un fallo de conexión en
cualquier punto sale como `BaseNoDisponible` y el manejador de `errores.py` lo responde `503 BASE_NO_DISPONIBLE` con
el evento `base_no_disponible` (`WARNING`, `motivo`); sin motor (`app.state.motor = None`), igual. La conversión solo
se aplica a errores de SQLAlchemy, de asyncpg o a un `OSError` suelto que no sea `TimeoutError` (`es_fallo_de_base`): un
*timeout* de httpx (embeddings) también lleva un `OSError` en su cadena de causas y no debe salir como «base no
disponible». Por eso tampoco se usa una dependencia con `yield` que tenga la conexión toda la petición: cualquier
excepción del endpoint pasaría por ella.

**Para los lotes siguientes: qué ofrece BE-1.3 al código.**

| Elemento | Qué hace |
|---|---|
| `app.seguridad.dependencias.requiere_admin` → `UsuarioActual` | Dependencia de §5.2 (arriba). `UsuarioActual` es un *dataclass* congelado con `id` (`uuid.UUID`), `nombre`, `correo` y `rol` (`RolUsuario`), leídos de la base en esa petición. Un endpoint que necesite al admin (p. ej. `creado_por`) declara `usuario: UsuarioActual = Depends(requiere_admin)`: FastAPI la evalúa una sola vez por petición aunque el router ya la tenga |
| `app.api.v1.RUTAS_ADMIN`, `RUTAS_COLLECT` | Listas de `APIRouter` que se montan en `/v1/admin` y `/v1/collect` con `requiere_admin` y las respuestas 401/403/503 en el OpenAPI. Un lote añade ahí su router **sin** el prefijo `/admin` o `/collect` (p. ej. `APIRouter(prefix="/videos")`), nunca en `router_v1`. `tests/api/test_auth.py` comprueba, con el OpenAPI, que toda operación de esos prefijos declara el esquema `jwt` y responde 401 sin token (FastAPI 0.143 incluye los routers de forma perezosa: `app.routes` muestra un `_IncludedRouter`, no las rutas) |
| `app.api.dependencias.obtener_motor(request)` → `AsyncEngine` | El motor de `api`; sin motor lanza `BaseNoDisponible` (→ 503). Se llama dentro del endpoint, o como `Depends`, **después** de lo que deba responder antes (p. ej. un 422 o un 500 de configuración) |
| `app.api.dependencias.obtener_ajustes(request)` → `Settings`; `obtener_cola_hash(request)` → `ColaHash` | Los `Settings` de la app; la cola de verificaciones argon2id (`app.state.cola_hash`, renovada en cada arranque). `ColaHash(concurrentes, cola_max, espera_max_s)` (`servicios/autenticacion.py`): `reservar()` (o `Saturado("cola_llena")`), `await verificar(hash, password)` (espera turno como mucho `espera_max_s`, o `Saturado("espera_agotada")`, y libera el puesto) o `liberar()` si no llega a verificar; `dentro` cuenta los puestos ocupados. El router traduce `Saturado` a `503 SERVICIO_OCUPADO` con `Retry-After: 5` |
| `app.db.sesion.transaccion(motor)` | `async with`: abre una conexión con `conectar`, `BEGIN`, `COMMIT` al salir del bloque (o `ROLLBACK` si sale con una excepción) y cierra. Convierte los fallos de conexión en `BaseNoDisponible`; el resto sale tal cual (p. ej. `IntegrityError`, que el servicio traduce a su `ErrorApi`). Lo que deba confirmarse junto (un cambio y su fila de `auditoria`) va en el mismo bloque. Probado: una conexión cortada a mitad de bloque (`pg_terminate_backend`) sale como `BaseNoDisponible` y deshace lo anterior |
| `app.db.sesion.es_fallo_de_base(exc)` | Lo que convierte `transaccion` (arriba) |
| `app.servicios.auditoria.anotar(conexion, *, accion, entidad, entidad_id=None, actor_id=None, detalle=None)` | Inserta una fila de `auditoria` dentro de la transacción del cambio que registra (si el cambio se deshace, la fila también). `entidad_id` se guarda como texto; `detalle`, objeto JSON sin secretos. Las acciones de cada lote están en §5.7 |
| `app.errores.ErrorApi(estado, codigo, mensaje=None, detalle=None, encabezados=None)` | (BE-1.1) El mensaje por defecto de cada código está en `MENSAJE_POR_CODIGO`; BE-1.3 añade `TOKEN_INVALIDO`, `TOKEN_EXPIRADO`, `CREDENCIALES_INVALIDAS` y `SERVICIO_OCUPADO` |
| `app.seguridad.tokens` | `emitir(usuario_id=, rol=, nombre=, ajustes=, ahora=None)` → `TokenEmitido(token, expira_en, jti)`; `decodificar(token, ajustes)` → `Claims(sub, rol, nombre, iat, exp, jti)` o `TokenExpirado` / `TokenInvalido` / `ClaveNoConfigurada`. Firma con PyJWT 2.15 (`pyjwt` en `pyproject.toml`). El módulo no se llama `jwt.py` para no confundirse con el paquete `jwt` |
| `app.seguridad.hash.hash_ficticio()` | Hash argon2id de una contraseña aleatoria, uno por proceso (§4.3 para `calcular` y `verificar`) |
| `app.dominio.validaciones` | `PASSWORD_MIN` (8), `PASSWORD_MAX` (256), `IDENTIFICADOR_MAX` (320), `motivo_texto_no_admitido(texto)` (`None`, o el motivo si lleva un carácter NUL o un sustituto suelto), `tiene_forma_de_correo(correo)` (`algo@algo` sin espacios ni otra `@`, y texto admitido) y `motivo_password_no_valida(password)` (`None` o el motivo, sin el valor). **Todo texto de una petición que llegue a la base pasa por `motivo_texto_no_admitido`** con un `field_validator` del esquema Pydantic que lance `ValueError(motivo)` (→ `422 VALIDACION`; ejemplo en `esquemas/auth.py`): si no, PostgreSQL lo rechaza y la API responde `500` |
| Fixtures de prueba | Las de §4.3; el admin de `base_migrada` (`admin.pruebas@campus.edu.co` / `Pruebas-admin-123`) sirve para el login. Los `Settings` de prueba no traen `JWT_SECRET`: se añade con `model_copy(update={"jwt_secret": SecretStr(…)})` (≥ 32 bytes: con menos, PyJWT avisa con `InsecureKeyLengthWarning`). Ejemplos en `tests/base/test_auth_base.py` |

Trampas: `ruff` marca `S105` en constantes con «password» en el nombre (`# noqa: S105` si es un nombre, no un valor).
Los logs nunca llevan el token: si hace falta correlacionar, `usuario_id` y el `X-Request-Id`.

### 4.5 BE-2.1 — Recolección (subida del dataset)
La app graba sin conexión y sube al terminar (vista 7.5 de la app). Secuencia (contrato en §5.4):
1. `POST /v1/collect/videos` con los metadatos del recorrido y una referencia local (`ref_cliente`, p. ej.
   `rec_0003`). Idempotente por (admin, `ref_cliente`): reintentar devuelve el mismo video, sin cambiarlo.
2. `POST /v1/collect/videos/{id}/images` en lotes de hasta `REC_MAX_LOTE` (50): registra cada foto (orden, coordenada,
   rumbo, hora, tamaño) y devuelve una **URL prefirmada PUT** por foto que siga pendiente. Llamarlo de nuevo regenera
   URLs vencidas (así se retoma una subida interrumpida); a las fotos repetidas que siguen `pendiente_subida` les hace
   antes un `HEAD` en S3 y, si el objeto ya está, las pasa a `subida` y no les da URL.
3. La app hace `PUT` de cada JPEG directo a S3 con **exactamente** el encabezado firmado `Content-Type: image/jpeg`.
4. S3 avisa a la cola `ingesta`; el `worker` continúa (BE-2.2).
5. `POST /v1/collect/videos/{id}/complete` hace `HEAD` de las que siguen pendientes, marca la subida como terminada y
   devuelve el conteo por estado. La app consulta `GET /v1/admin/videos/{id}` para la barra de progreso; ese endpoint
   y `GET /v1/admin/videos` llegan con este lote (el resto de §5.5 sobre videos, con BE-4.1).

**Paso a `subida`** (ADR-BE-14). Una foto pasa de `pendiente_subida` a `subida` cuando el `worker` recibe su evento
de S3 (BE-2.2, antes de procesarla), cuando `complete` comprueba con `HEAD` que el objeto ya está en S3, o cuando
una repetición de `images` la incluye y el `HEAD` la encuentra; lo que ocurra primero. Así el conteo es correcto
aunque el `worker` esté apagado (con `embedding` apagado), y C2 de la validación (repetir no da URL a lo subido) se
cumple sin `worker`. Con el `HEAD` se guardan `imagenes.bytes` (`ContentLength`; nulo si pasa de 2 147 483 647, que
no cabe en `integer`: el `worker` la rechazará por tamaño) y `imagenes.etag` (sin comillas, como llega en el evento
de S3, §5.8). Un `HEAD` que falla por otra causa que «no está» deja la foto pendiente y registra `s3_fallido`
(`WARNING`); la petición responde igual (la app reintenta `complete`).

**`HEAD` sin `s3:ListBucket` (trampa).** El rol `tarea-api` tiene `s3:GetObject` y `s3:PutObject` sobre los objetos,
pero no `s3:ListBucket` (infra §5.8; comprobado en `dev` con `iam get-role-policy`, 2026-10-25): S3 responde **403**,
no 404, al `HEAD` de un objeto que no existe. `AlmacenS3.consultar` toma 404 y 403 como «no está». Consecuencia: si un
día faltara `s3:GetObject`, todas las fotos quedarían `pendiente_subida` sin error visible (solo el conteo).

**Estado del video** (`dominio.recoleccion.estado_video`, ADR-BE-14). Se deriva siempre del conteo de sus fotos y de
`subida_completa_en`, y se guarda en `videos.estado` cada vez que cambia una foto (`recalcular_estado`):
`pendiente` mientras no se haya llamado a `complete` o quede alguna `pendiente_subida`; si no, `procesando` si queda
alguna `subida`; si no, `con_errores` si hay alguna en `error`; si no, `procesado` (también con 0 fotos). Una foto
registrada después de `complete` lo devuelve a `pendiente`. `subida_completa_en` se fija la primera vez que se llama a
`complete` y no cambia después. Un video `eliminado` (BE-4.1) no cambia de estado.

**Concurrencia: orden de bloqueo video → imágenes, siempre.** Toda transacción que cambie fotos de un video bloquea
primero la fila del video con `recoleccion.bloquear_video(conexion, video_id)` (`SELECT … FOR UPDATE`) y solo después
las filas de `imagenes`; así dos lotes del mismo video, un lote y un `complete`, o el `worker` de BE-2.2, van en fila y
no pueden bloquearse entre sí (si una transacción bloqueara una foto y después el video mientras otra hace lo contrario,
PostgreSQL abortaría una por *deadlock*). El `worker` hace lo mismo: bloquea el video, después toca la foto y, en la
misma transacción, llama a `recalcular_estado`. Los `HEAD` y las firmas se hacen fuera de las transacciones: `images` lee qué fotos repetidas siguen pendientes (transacción 1), hace los `HEAD`
(8 a la vez, en hilos), y escribe con el video bloqueado volviendo a leer las filas (transacción 2); al final firma
las URLs en un hilo. `crear_video` es seguro ante dos peticiones a la vez con el mismo `ref_cliente`
(`INSERT … ON CONFLICT (creado_por, ref_cliente) DO NOTHING` y vuelve a leer). `numero` sale de la secuencia
`videos_numero_seq` antes del `INSERT` (para el nombre `video_<numero>`); un `INSERT` que pierde la carrera deja un hueco
en la numeración, que es aceptable (§5.1: «entero creciente», no consecutivo).

**Cliente de S3** (`clientes/s3.py`). `api` crea un `AlmacenS3` al arrancar (en un hilo: crear un cliente de boto3
cuesta CPU) si hay `S3_BUCKET_DATASET`. Sin la variable, `images` y `complete` responden `500 ERROR_INTERNO` con el
evento `configuracion_incompleta` (`faltan = ["S3_BUCKET_DATASET"]`), pero **después** de comprobar el video: un video
inexistente da `404` y uno eliminado `409` aunque falte el bucket (el router pasa `almacen_o_none(request)` y el
servicio lanza `AlmacenNoConfigurado` tras mirar el video, antes de escribir nada). El cliente usa SigV4 y direccionamiento virtual:
las URL quedan `https://<bucket>.s3.amazonaws.com/dataset/…?X-Amz-…` con `X-Amz-SignedHeaders=content-type;host`
(probado con botocore 1.43.110: por eso el `PUT` tiene que llevar exactamente `Content-Type: image/jpeg`). Las
credenciales son las del rol de tarea (temporales): una URL deja de valer al caducar las credenciales con que se
firmó, aunque su `X-Amz-Expires` diga más. **Hipótesis sin comprobar:** botocore renueva esas credenciales unos 15 min
antes de que caduquen, y entonces una URL de 900 s duraría entera. Si no fuera así, una URL firmada cerca del
vencimiento de las credenciales duraría menos que su `expira_en`: la app recibiría `403` de S3 al subir y pediría
otra URL repitiendo `images` (el mismo camino que con una URL vencida, §5.4). `expira_en` se calcula con la hora de antes de firmar, sin fracciones: es una cota inferior del vencimiento
real (como mucho 1 s antes). Ninguna URL prefirmada llega a un log (los motivos de `FalloS3` llevan la clase y el
código de AWS, no la URL).

**Lectura para el panel** (`servicios/videos.py`). Dos consultas por página, en una transacción: el `total`
(`count(*)` con los mismos filtros) y la página (`videos` con el nombre del creador y el conteo por estado, de una
subconsulta agrupada de `imagenes`); los `eliminado` no salen. El detalle hace otras dos: el resumen y sus fotos. `q` busca en `nombre` sin distinguir
mayúsculas (`ILIKE`, con `%`, `_` y `\` escapados: son literales). Los `real` de la base (`distancia_m`, rumbos) se
devuelven con las menos cifras que los representan como float32 (`real_legible`: 340.3 y no 340.29998779296875). Las
URLs de foto y miniatura de `ImagenAdmin` son `null` hasta BE-4.1 (§5.5).

**Limpieza de datos de prueba.** `python -m app.cli limpiar-validacion` (§5.9, `servicios/limpieza.py`) borra de
forma definitiva —filas de `videos` (y en cascada `imagenes` y `embeddings`) y sus objetos de `dataset/{id}/` y
`thumbs/{id}/`— los videos cuyo `nombre` **y** `ref_cliente` empiezan por `validacion-`. Orden: objetos de S3 →
filas → otra pasada por S3 (una miniatura que el `worker` escribiera entretanto). Si S3 falla en la primera
pasada, las filas quedan, el comando termina con 1 y repetirlo termina el trabajo. Si falla en la segunda, las filas
ya no están: el comando **no** falla (sale con 0 y su línea `LIMPIEZA`), pero registra `limpieza_s3_incompleta`
(`WARNING`, con los prefijos) porque pueden quedar objetos huérfanos (miniaturas) que ya ningún comando encuentra; se
borran a mano con un perfil de administración: `aws s3 rm --recursive s3://<bucket>/thumbs/<video_id>/` (y
`dataset/<video_id>/`). Sin `--video` toma todos los de validación; una lista de ids vacía (posible solo desde el
código) no borra nada, nunca «todos». Con `--simular` hace las mismas comprobaciones y la misma negativa, cuenta los
objetos que borraría (`list-objects-v2`) y no borra nada: así un validador puede comprobar la negativa con un video
real sin arriesgarlo. Se ejecuta como tarea suelta con la definición de
`worker`, que es la que puede listar y borrar en S3 (infra §5.8; su `s3:ListBucket` exige `s3:prefix` `dataset/*` o
`thumbs/*`, y `list-objects-v2 --prefix dataset/{id}/` lo cumple). Lo usan los validadores mientras no existe el
borrado de BE-4.1 (§5.11); nunca toca otros videos. Sus logs llevan `proceso = migrate` (como toda la CLI) aunque
corra con la definición de `worker` y su log vaya a `/campus-locator/dev/worker`.

La clave del objeto sigue el formato de infra §5.5 (`dataset/{video_id}/{imagen_id}.jpg`): el `worker` recupera la
fila de la imagen a partir de la clave sin otra consulta (`dominio.recoleccion.ids_de_clave`).

**Para los lotes siguientes: qué ofrece BE-2.1 al código.**

| Elemento | Qué hace |
|---|---|
| `app.dominio.recoleccion` | `clave_dataset(video_id, imagen_id)` y `clave_miniatura(…)` (`dataset/…` y `thumbs/{video_id}/{imagen_id}.jpg`); `prefijos_del_video(video_id)` → `("dataset/{id}/", "thumbs/{id}/")`; `ids_de_clave(clave)` → `(video_id, imagen_id)` o `None` (la clave ya decodificada con `unquote_plus`; exige UUID en minúsculas y `.jpg`): BE-2.2 la usa para los eventos de S3. `Conteo(pendiente_subida, subida, procesada, error)` (*dataclass* congelado; `Conteo.desde({estado: n})`, `.total`, `.como_dict()`); `estado_video(conteo, subida_completa)` → `EstadoVideo` (reglas de arriba); `es_dato_de_validacion(nombre, ref_cliente)`; `PREFIJO_VALIDACION`, `TIPO_JPEG`, `ENCABEZADOS_PUT`; `como_real(x)` (el float32 que guarda una columna `real`) y `real_legible(x)` |
| `app.servicios.recoleccion.bloquear_video(conexion, video_id)` → `EstadoVideo \| None` | `SELECT estado … FOR UPDATE` de la fila del video en la transacción en curso: su estado, o `None` si no existe. No lanza por `eliminado` (quien llama decide: la recolección responde 409; el `worker` descarta el mensaje). **Primer bloqueo de toda transacción que cambie fotos** (orden video → imágenes) |
| `app.servicios.recoleccion.recalcular_estado(conexion, video_id)` → `(EstadoVideo, Conteo)` | Cuenta las fotos por estado, deriva el estado del video y lo guarda si cambió (`eliminado` no cambia; `VideoNoEncontrado` si no existe). Va **dentro** de la transacción que cambió las fotos, que ya llamó a `bloquear_video`. BE-2.2, por cada foto: `async with sesion.transaccion(motor) as c:` → `bloquear_video(c, video_id)` (si `None` o `eliminado`, descarta) → `UPDATE imagenes …` → `recalcular_estado(c, video_id)` |
| `app.servicios.recoleccion` (casos de uso) | `crear_video(motor, usuario_id=, datos=VideoCrear)` → `(VideoResumen, creado)`; `registrar_imagenes(motor, almacen, ajustes, video_id=, imagenes=[ImagenRegistro])` → `ImagenesRegistradas`; `completar_subida(motor, almacen, video_id=)` → `SubidaCompletada`; `validar_lote(imagenes, ajustes)`. `almacen` puede ser `None`: se exige después de comprobar el video. Excepciones: `VideoNoEncontrado`, `VideoEliminado` (de `servicios.videos`), `AlmacenNoConfigurado` (→ `500`), `DatosNoValidos(campos)` (→ `422`, `campos` = `detalle.campos`) y `FalloS3` al firmar |
| `app.servicios.videos` | `listar(motor, q=, orden=, direccion=, pagina=, por_pagina=)` → `Pagina[VideoResumen]`; `detalle(motor, video_id)` → `VideoDetalle` (`VideoNoEncontrado` si no existe o está `eliminado`); `resumen(conexion, video_id)` → `VideoResumen \| None` (también de un eliminado) y `contar(conexion, video_id)` → `Conteo`, dentro de una transacción abierta. BE-4.1 añade aquí renombrar y borrar, y rellena `url`, `url_miniatura` y `url_expira_en` de `ImagenAdmin` en `detalle` |
| `app.servicios.limpieza.limpiar_validacion(motor, almacen, video_ids=None, *, simular=False)` → `ResultadoLimpieza` | Lo que hace `limpiar-validacion` (arriba): `ResultadoLimpieza(videos, objetos, video_ids, simulada, restos_s3, motivo_restos)`. `video_ids=None` = todos los de validación; `[]` = nada. Lanza `LimpiezaRechazada(inexistentes, sin_prefijo)`, `FalloS3` (primera pasada, o el recuento al simular) y los errores de la base. La purga de BE-4.1 puede copiar su orden (S3 → filas → S3) |
| `app.clientes.s3` | `AlmacenS3(bucket, region="us-east-1", cliente=None, reloj=…)` (síncrono): `firmar_put(clave, ttl_s)` → `UrlFirmada(url, expira_en)`; `consultar(clave)` (HEAD) → `ObjetoS3(bytes, etag)` o `None` si 404/403; `borrar_prefijo(prefijo)` → objetos borrados (lista y borra de 1000 en 1000); `contar_prefijo(prefijo)` → objetos bajo el prefijo (solo lista). Todo error → `FalloS3` (mensaje sin URL). Desde código asíncrono: `await firmar_puts(almacen, claves, ttl_s)` → `{clave: UrlFirmada}` (un hilo) y `await consultar_varios(almacen, claves, concurrencia=8)` → `{clave: ObjetoS3 \| FalloS3 \| None}` (nunca lanza por una clave). `crear_cliente(region)` da el cliente de boto3 configurado. Desde BE-2.2, `descargar(clave, max_bytes)` y `escribir(clave, datos, content_type="image/jpeg")` (§4.6; se llama `escribir`, no `subir` como se había previsto, para no chocar con `almacen_falso.subir`). **Falta** (se añade aquí, con su prueba con `Stubber`): para BE-4.1 (URLs GET de 1 h) y, cuando un lote defina la subida de la foto de un lugar (BE-3.1 no la incluye, §4.9), `firmar_get(clave, ttl_s)` |
| `app.api.dependencias.obtener_almacen(request)` → `AlmacenS3`; `almacen_o_none(request)`; `sin_almacen(request)` → `ErrorApi` | El de `app.state.almacen`; sin él, `obtener_almacen` lanza el `500 ERROR_INTERNO` de `sin_almacen` (que registra `configuracion_incompleta`). La recolección usa `almacen_o_none` y traduce `AlmacenNoConfigurado` con `sin_almacen`, para responder antes el 404/409 del video |
| `app.main.crear_app(ajustes=None, *, almacen=None)` | `almacen` sustituye al cliente de S3 (las pruebas pasan un doble); sin él, el ciclo de vida lo crea si hay `S3_BUCKET_DATASET` |
| `app.esquemas.comun` | `FechaUtc` (fecha de **salida**: UTC con `Z` y sin fracciones), `FechaConZona` (de **entrada**: con zona, devuelta en UTC; sin zona, o fuera de los años 1–9999 al pasarla a UTC —p. ej. `0001-01-01T00:00:00+05:00`—, → `422`; sin esa conversión asyncpg lanzaba `OverflowError` al guardarla y la API respondía `500`), `Referencia` (`{id, nombre}`), `Pagina[T]` (`items`, `total`, `pagina`, `por_pagina`; PEP 695: `Pagina[VideoResumen]`) y `texto_admitido(valor)` (la regla de §4.4 en un `field_validator`). BE-3.1 usa `FechaUtc` y `texto_admitido` en `esquemas.lugares` (sus listas no se paginan: `ListaLugares`, §4.9); `Referencia` la usará `AlertaAdmin` (`creado_por`, BE-3.3) |
| `app.esquemas.videos` | Los modelos de §5.4 y §5.5: `VideoCrear`, `InicioRecorrido`, `ImagenRegistro`, `ImagenesRegistrar`, `SubidaPut`, `ImagenRegistrada`, `ImagenesRegistradas`, `ConteoFotos`, `SubidaCompletada`, `VideoResumen`, `ImagenAdmin`, `VideoDetalle`; constantes `NOMBRE_VIDEO_MAX` (40), `REF_CLIENTE_MAX` (40), `DISPOSITIVO_MAX` (200), `APP_VERSION_MAX` (40), `ENTERO_MAX`, `Q_MAX` (100) y `LOTE_TOPE` (50: `ImagenesRegistrar.imagenes` tiene `max_length` fijo, así Pydantic no valida cuerpos enormes; `REC_MAX_LOTE` solo puede bajarlo). Las peticiones ignoran campos de más; las respuestas los prohíben |
| Fixtures de prueba | `almacen_falso` (`tests/conftest.py`): doble de `AlmacenS3` con los objetos en memoria; `subir(clave, n_bytes=1234, datos=None)` simula el `PUT` de la app y devuelve el ETag (`etag0`, `etag1`… distinto en cada subida; con `datos`, guarda esos bytes y `n_bytes = len(datos)`), `fallar_head` y `fallar_firma` provocan `FalloS3`, `contar_prefijo` cuenta, `consultadas` y `firmadas` registran las llamadas y sus URL llevan `FIRMA_FALSA` para comprobar que no llegan a los logs. Desde BE-2.2: `descargar`/`escribir` como los reales, `datos` (bytes por clave), `descargadas`, `escritas`, `fallar_descarga` (claves) y `fallar_escritura`. Para la CLI: `monkeypatch.setattr(cli, "crear_almacen", lambda ajustes: almacen_falso)`. Ejemplos en `tests/base/test_recoleccion_base.py` y `test_limpieza_base.py`; botocore simulado con `Stubber` en `tests/unit/test_s3.py` |

Trampas: un `rumbo` de 359,9999999 pasa `< 360` como `float` pero se guarda como 360,0 en `real` y violaría el
`CHECK`: los esquemas comprueban el rango sobre `como_real(x)`. Un `ImagenRegistro.orden` mayor que 200 lo rechaza el
`CHECK` de §5.7 aunque se suba `REC_MAX_FOTOS_VIDEO`: el servicio usa `min(REC_MAX_FOTOS_VIDEO, 200)`.

### 4.6 BE-2.2 — Worker de ingesta
`python -m app.worker` (`app/worker.py`) consume la cola `ingesta` (`SQS_URL_INGESTA`) y cada lote lo procesa
`servicios.ingesta.procesar_lote` (ADR-BE-15). Probado en local con PostgreSQL real, S3 (`almacen_falso`), SQS y
embeddings simulados (`tests/base/test_ingesta_base.py`, `tests/unit/test_worker.py`), y en `dev` con `validate22.py`
sobre `3b01b68` (2026-10-25; PLAN §3).

**Arranque.** Lee `SQS_URL_INGESTA`, `S3_BUCKET_DATASET`, `EMBEDDING_URL` y `DB_*` (infra §5.4; `worker_iniciado` con
`modo = ingesta`). Si falta alguna (o `DB_SSLMODE` no vale), registra `configuracion_incompleta` (`ERROR`, `faltan`) y
sigue vivo solo con latidos (`modo = sin_consumo`), sin salir: así ECS no lo reinicia en bucle y `docker compose`
local (que no tiene SQS) arranca igual. Crea un motor con pool `DB_POOL_WORKER` (2), un `AlmacenS3` y una `ColaSqs`
(en hilos). SIGTERM termina el bucle tras la recepción en curso (≤ 20 s; ECS espera 30 s) y registra
`worker_detenido`.

**Bucle** (`worker.consumir`):
1. Cada 60 s, `latido` (`modo = ingesta`, `embedding_listo`).
2. `GET {EMBEDDING_URL}/health/ready` (`embedding.esta_listo`, plazo `EMBEDDING_CONNECT_TIMEOUT_S`). Si no responde
   200, **no recibe**: espera `WORKER_ESPERA_EMBEDDING_S` (15 s) y vuelve a mirar. Así, con `embedding` apagado o
   cargando, los mensajes esperan visibles en la cola sin gastar recepciones y no llegan a la DLQ (C3). Registra
   `embedding_listo` / `embedding_no_listo` solo cuando cambia.
3. `ReceiveMessage` con espera larga de 20 s, hasta `WORKER_MAX_MENSAJES` (10).
4. Si tras recibir `embedding` ya no está listo (se apagó durante la espera larga) o el proceso se detiene, devuelve
   los mensajes con visibilidad 0 (`ChangeMessageVisibility`; cuenta una recepción) y registra `mensajes_devueltos`.
5. `procesar_lote` decide por mensaje: lo borra (`DeleteMessage`) si todo lo que nombra terminó (procesado,
   descartado o error permanente) y lo deja si algo falló de forma transitoria: vuelve a ser visible tras la
   visibilidad de la cola (180 s, infra §5.6) y, a la sexta recepción, SQS lo pasa a la DLQ (5 reintentos) y la alarma
   avisa. Registra `lote_ingesta` (`mensajes`, `borrados`, `retenidos`, `duracion_ms`); con algún retenido, espera
   15 s antes de seguir. Un error de SQS (`FalloSqs`) se registra como `cola_fallida` y el bucle sigue.

**Un lote** (`procesar_lote(deps, mensajes)` → `list[Decision]`). Cada mensaje se interpreta con
`dominio.mensajes.interpretar` (§5.8): `s3:TestEvent` → se borra (`mensaje_descartado`, `motivo = prueba_s3`); un
cuerpo que no encaja → se borra (`mensaje_no_reconocido`, `WARNING`); cada `Record` `ObjectCreated:*` es una foto, con
la clave decodificada (`unquote_plus`) y el ETag sin comillas; una clave que no es `dataset/{uuid}/{uuid}.jpg`
(`recoleccion.ids_de_clave`) se descarta (`clave_no_reconocida`). Dos mensajes del lote que nombran la misma foto
comparten el trabajo (se procesa una vez y los dos se borran o se quedan juntos; si una es un evento de S3 y otra
`reprocesar_imagen`, manda la primera que aparece). El lote va **por fases y en serie**, una foto detrás de otra en
cada fase (sin descargas en paralelo: así en memoria solo hay un original decodificado a la vez; de cada foto se
guardan solo la miniatura y la copia reducida, cientos de KB): transacción 1 de todas → descarga + Pillow + miniatura
de las que siguen → embeddings de las que siguen, en grupos → transacción 2 de cada una con vector → transacción de
error de las que quedaron en error permanente. Por foto:
1. **Transacción 1** (orden de bloqueo de §4.5): `recoleccion.bloquear_video`; video inexistente → descartar
   (`video_no_existe`), `eliminado` → descartar (`video_eliminado`: la purga se ocupa del objeto); foto con
   `SELECT … FOR UPDATE` (inexistente → `imagen_no_existe`). Evento de S3 con el mismo ETag que una foto ya `procesada`
   o en `error` → descartar (`duplicado`: idempotencia ante eventos repetidos, C4). Foto `pendiente_subida` → pasa a
   `subida` con `etag` y `bytes` del evento (`bytes` nulo si pasa de 2 147 483 647) y `recalcular_estado` (ADR-BE-14).
   Una foto ya en `subida` (por `complete` o por el `HEAD` de `images`, §4.5) se procesa igual. `reprocesar_imagen`
   lee primero el `video_id` de la foto (sin bloqueo), después bloquea video y foto, y no aplica la regla del ETag.
2. **S3 y Pillow** (fuera de la base): `AlmacenS3.descargar(s3_key, REC_MAX_BYTES_FOTO)`; objeto que no está (404) →
   descartar (`objeto_no_existe`; la foto queda como esté); más grande → error permanente.
   `dominio.imagenes.preparar` (en un hilo): JPEG decodificable (formato `JPEG` o `MPO` según Pillow y `load()` sin
   error; más de ~89,5 MP es «no decodificable»; de un `MPO` —JPEG multi-imagen, abajo— solo se usa la primera
   imagen), orientación EXIF aplicada (`ImageOps.exif_transpose`), lado menor ≥
   `REC_LADO_MIN_PX` (320) y lado mayor ≤ 32 767 (cabe en `smallint`); da `ancho` y `alto` ya orientados, la miniatura
   (lado mayor `MINIATURA_LADO_PX` = 320, calidad `MINIATURA_CALIDAD` = 80, LANCZOS) y una copia reducida en memoria
   (lado mayor `WORKER_LADO_EMBEDDING_PX` = 1024, calidad 90, RGB y **sin EXIF**: embeddings vuelve a aplicar la
   orientación EXIF, §5.3 de su documento, y una copia con la marca la giraría dos veces). Una foto más pequeña no se
   amplía. `AlmacenS3.escribir(thumbs/{video_id}/{imagen_id}.jpg, miniatura)` (`ContentType: image/jpeg`).
3. **Embeddings**: `POST /v1/embed` con grupos de hasta `WORKER_LOTE_EMBEDDING` (4) copias reducidas, `X-Prioridad:
   baja` (`embedding.vectorizar`). Lotes pequeños acotan lo que espera una localización que llega mientras se procesa
   uno (embeddings no interrumpe un lote en curso; 4 imágenes ≈ 331 ms p95 en `dev`, embeddings §5.7). Una imagen
   rechazada (`400 IMAGEN_INVALIDA`, `413`, `415` con `detalle.indice`) queda en error permanente y el grupo se repite
   sin ella. `EmbeddingNoDisponible` (apagado, `503 NO_LISTO`/`SATURADO`, `5xx`, sin respuesta en
   `EMBEDDING_TIMEOUT_S`) o una respuesta que no cumple el contrato → transitorio para lo que falte del lote. Si la
   `version_vector` devuelta no es `EMBEDDING_VERSION_VECTOR`, no guarda nada, registra `version_vector_distinta`
   (`ERROR`, `esperada`, `recibida`) y queda transitorio (el mensaje acaba en la DLQ si no se corrige: es un error de
   configuración, no de la foto). El `worker` compara con la `version_vector` de cada respuesta de `/v1/embed`; no usa
   `GET /v1/info` (la regla «primera llamada y cada 10 min» de §5.10 es la de `api`).
4. **Transacción 2**: `bloquear_video`, foto `FOR UPDATE` (si ya no existen o el video está `eliminado`, descartar),
   `INSERT INTO embeddings … ON CONFLICT (imagen_id, version_vector) DO UPDATE SET vector, creado_en = now()` (una sola
   fila por foto y versión: reprocesar renueva el vector y su `creado_en`, C5), foto `procesada` con `error = NULL`,
   `bytes` (los descargados), `etag` (el del `GetObject`), `ancho`, `alto` e `intentos + 1`, y `recalcular_estado`.
   Evento `imagen_procesada`.

**Errores permanentes** (el mensaje se borra, C2): en una transacción con el mismo orden de bloqueo, la foto pasa a
`error` con el motivo, `intentos + 1`, `bytes` y `etag` si se conocen, `ancho` y `alto` si se decodificó, y se borran
**todos** sus vectores (una foto que se sube de nuevo mal no debe seguir saliendo en la búsqueda con los píxeles
viejos); `recalcular_estado`; evento `imagen_con_error` (`WARNING`). Motivos posibles (`imagenes.error`, el `error` de
`ImagenAdmin`):

| Motivo | Cuándo |
|---|---|
| `no es un JPEG decodificable` | Pillow no lo abre, no es formato `JPEG` ni `MPO` (un PNG, un texto), está truncado o es una bomba de descompresión |
| `demasiado grande: <n> bytes (máximo 4194304)` | El objeto pasa de `REC_MAX_BYTES_FOTO` (no se descarga) |
| `lado menor <n> px (mínimo 320)` | Tras corregir EXIF |
| `lado mayor <n> px (máximo 32767)` | No cabe en `imagenes.ancho`/`alto` (`smallint`) |
| `embeddings la rechazó (<codigo>)` | `IMAGEN_INVALIDA`, `LOTE_DEMASIADO_GRANDE` o `TIPO_NO_SOPORTADO` con índice |

**Errores transitorios** (el mensaje se queda): S3 (`FalloS3`, también un **403** al descargar: el rol `tarea-worker`
tiene `s3:ListBucket` solo con `s3:prefix`, así que un 403 puede ser un permiso que falta y no se toma como «no está»;
qué responde S3 en `dev` al `GetObject` de una clave que no existe, **sin comprobar**), base no disponible
(`BaseNoDisponible`), embeddings, `version_vector` distinta y cualquier excepción imprevista (con la traza en
`excepcion`). Evento `ingesta_transitoria` (`WARNING`; `ERROR` si es imprevista o una respuesta no válida), con
`motivo`, `origen`, `imagen_id` y `video_id`. Lo ya hecho antes del fallo se conserva (el paso a `subida`, una
miniatura escrita): el reintento lo repite sin daño.

`intentos` (§5.7) cuenta las veces que el `worker` terminó una foto (`procesada` o `error`); no cuenta los fallos
transitorios ni los descartes. Una foto en `error` que la app vuelve a subir (otro ETag) se procesa de nuevo y, si
vale, pasa a `procesada` (`error = NULL`). Si el video se borra (`limpiar-validacion` o BE-4.1) mientras el `worker`
procesa, la miniatura puede quedar escrita: `limpiar-validacion` hace una segunda pasada por S3 por eso (§4.5) y la
purga de BE-4.1 también.

**Nombres internos** (para depurar o extender sin abrir el código):
- `servicios/ingesta.py`: `Unidad` (una foto: `imagen_id`, `video_id` —`None` en `reprocesar` hasta la transacción
  1—, `origen` `s3` | `reprocesar`, `etag_evento`, `bytes_evento`, `resultado`, `motivo`, `s3_key`, `datos_bytes`,
  `etag`, `preparada`, `inicio`); `Decision(mensaje, borrar, unidades)`; `Resultado` (`procesada`, `error`,
  `descartado`, `transitorio`); constantes de motivo `VIDEO_NO_EXISTE`, `VIDEO_ELIMINADO`, `IMAGEN_NO_EXISTE`,
  `CLAVE_NO_RECONOCIDA`, `DUPLICADO`, `OBJETO_NO_EXISTE` (los textos de `mensaje_descartado`) y `ENTERO_MAX`
  (2 147 483 647). Fases: `_unidades_de` (mensaje → unidades), `_preparar_en_base` (transacción 1, con
  `_foto_bloqueada`, que bloquea video y foto y descarta si no hay qué procesar), `_descargar_y_preparar` (paso 2),
  `_vectorizar` (paso 3; acota el grupo a 1–8 aunque `WORKER_LOTE_EMBEDDING` diga otra cosa), `_guardar`
  (transacción 2), `_guardar_error` y `_con_errores_controlados` (cualquier excepción de una fase deja esa unidad
  `transitorio` sin tumbar el lote). Sus eventos salen con `logger = app.worker`.
- `worker.py`: `INTERVALO_LATIDO_S` (60), `ESPERA_COLA_S` (20), `MODO_INGESTA`, `MODO_SIN_CONSUMO`;
  `ejecutar(detener, intervalo_s)` es el modo `sin_consumo` (solo latidos); `consumir(…)` el de ingesta;
  `_principal` crea motor, `AlmacenS3` y `ColaSqs` y cierra el motor al salir. Un fallo al devolver un mensaje
  (`mensajes_devueltos`) se ignora en silencio (el mensaje vuelve igual al vencer su visibilidad).
- `dominio/imagenes.py`: `ImagenNoValida(motivo)` (atributo `motivo`), `ImagenPreparada`, `MOTIVO_NO_JPEG`,
  `LADO_MAX_ESQUEMA` (32 767), `CALIDAD_REDUCIDA` (90), `FORMATOS_ADMITIDOS` (`("JPEG", "MPO")`),
  `motivo_demasiado_grande(n, max)`. La miniatura y la copia
  salen de la imagen ya orientada y convertida a RGB; las dos se reducen con `Image.thumbnail` (LANCZOS, proporción
  conservada) solo si su lado mayor pasa del límite.
- `dominio/mensajes.py`: `ObjetoSubido(clave, etag, bytes)` (`etag` sin comillas o `None` si falta o queda vacío;
  `bytes` solo si `size` es un entero ≥ 0, no un booleano), `EventosS3(objetos, ignorados)` (`ignorados` = `Records`
  que no son `ObjectCreated:*` o no traen `s3.object.key`), `Reprocesar(imagen_id: UUID)`, `PruebaS3()`,
  `NoReconocido(motivo)` (motivos cortos: `cuerpo que no es JSON`, `ni Records ni tipo`, `tipo desconocido: …`,
  `versión no admitida de reprocesar_imagen: …`, `reprocesar_imagen sin imagen_id válido`…), `TIPO_REPROCESAR`,
  `VERSIONES_REPROCESAR`.
- `clientes/sqs.py`: `ColaSqs`, `MensajeSqs`, `FalloSqs` (mensaje `<operación>: <clase>: <código de AWS>`, nunca el
  cuerpo), `crear_cliente(region)` (reintentos `standard` × 3, conexión 3 s, lectura 30 s). `recepciones` sale de
  `ApproximateReceiveCount` (1 si no viene).
- `clientes/embedding.py`: `RUTA_PREPARADO` (`/health/ready`), `RUTA_EMBED` (`/v1/embed`), `PRIORIDADES`
  (`alta`, `baja`).

**Para los lotes siguientes: qué ofrece BE-2.2 al código.**

| Elemento | Qué hace |
|---|---|
| `app.clientes.embedding.vectorizar(ajustes, imagenes, *, prioridad="baja", transporte=None, request_id=None)` → `Vectores` | `POST {EMBEDDING_URL}/v1/embed` con cada `bytes` como parte `imagenes` (`image/jpeg`) y `X-Prioridad`; `Vectores(version_vector, dim, vectores, tiempos_ms)` en el orden de las imágenes (comprueba que haya uno por imagen y `dim` componentes). Plazo `EMBEDDING_TIMEOUT_S` (conexión `EMBEDDING_CONNECT_TIMEOUT_S`); un reintento solo si la conexión fue **rechazada** (`ConnectionRefusedError` en la cadena). Excepciones: `EmbeddingNoDisponible` (sin URL, sin conexión, sin respuesta, `5xx`: en `api` corresponde a `503 EMBEDDING_NO_DISPONIBLE`, §5.3), `ImagenRechazada(indice, codigo)` (`400`/`413`/`415` con `detalle.indice`; `api` la responde `400 FOTOS_INVALIDAS` con ese índice desde BE-2.4, §5.5) y `RespuestaNoValida` (otro `4xx` o un `200` mal formado). **BE-2.4** la llama con `prioridad="baja"` (§4.8) y **BE-3.2** con `"alta"` (§4.10); los dos comparan `version_vector` con `EMBEDDING_VERSION_VECTOR` en cada respuesta (BE-2.4 ya lo hace, §4.8; la regla de §5.10 para `api`, «primera llamada y cada 10 min» con `GET /v1/info`, sigue sin código). `transporte` (un `httpx.MockTransport`) es para las pruebas: ejemplos en `tests/unit/test_cliente_embedding.py`. Detalles: cada parte va como `("imagenes", ("<i>.jpg", bytes, "image/jpeg"))`; `request_id` añade `X-Request-Id` (embeddings lo respeta, §5.1 de su documento: `api` debería pasar el de la petición para correlacionar); `ValueError` si `prioridad` no es `alta`/`baja` o la lista está vacía; **no** comprueba el máximo de 8 imágenes ni los 4 MB/16 MB de embeddings (§5.2 de su documento): lo hace quien llama (si no, `413` → `ImagenRechazada` o `RespuestaNoValida`). Abre un `httpx.AsyncClient` por llamada con `trust_env=False` (sin proxies del entorno). `httpx.Timeout(EMBEDDING_TIMEOUT_S, connect=EMBEDDING_CONNECT_TIMEOUT_S)` limita **cada fase** (escritura, lectura, espera del pool), no el total: una respuesta que llega a trozos puede tardar más; para un tope total de la petición (p. ej. los 30 s de API Gateway en BE-3.2), quien llama la envuelve en `anyio.fail_after` |
| `app.clientes.embedding.esta_listo(ajustes, transporte=None)` → `bool` | (BE-1.1) `GET /health/ready` en `EMBEDDING_CONNECT_TIMEOUT_S` |
| `app.clientes.s3.AlmacenS3.descargar(clave, max_bytes)` → `ObjetoDescargado(datos, etag) \| None` | `GetObject`; `None` si 404; `ObjetoDemasiadoGrande(bytes)` si `ContentLength` > `max_bytes` (no lo lee); otro error, también 403 → `FalloS3` |
| `app.clientes.s3.AlmacenS3.escribir(clave, datos, content_type="image/jpeg")` | `PutObject` con `ContentType`. (La foto de un lugar, `lugares/{id}.jpg`, la sube la app con URL prefirmada según infra §5.5, Fase 4: no pasa por aquí; BE-3.1 no la incluye, §4.9) |
| `app.clientes.sqs.ColaSqs(url, region="us-east-1", cliente=None)` | Síncrona (boto3; llamarla con `anyio.to_thread`): `recibir(maximo, espera_s)` → `list[MensajeSqs(id, recibo, cuerpo, recepciones)]` (topes 10 y 20 s; `MessageSystemAttributeNames=["ApproximateReceiveCount"]`), `borrar(recibo)`, `devolver(recibo)` (visibilidad 0). Todo error → `FalloSqs`. `crear_cliente(region)` usa `read_timeout` 30 s (más que la espera larga). Para enviar (`api`: `reprocesar_imagen` de BE-4.1, `purgar_*`) falta `enviar(cuerpo)`; el rol `tarea-api` tiene `sqs:SendMessage` en `ingesta` y `purga` |
| `app.dominio.imagenes.preparar(datos, *, max_bytes, lado_min, lado_miniatura, calidad_miniatura, lado_embedding)` → `ImagenPreparada(ancho, alto, miniatura, reducida)` | Lo de arriba; `ImagenNoValida(motivo)` con los motivos de la tabla. `motivo_demasiado_grande(n, max)`. BE-2.4/BE-3.2 validan las fotos de consulta con otras reglas (`dominio.fotos`, §4.8: tipo, tamaño ≤ `LOC_MAX_BYTES_FOTO` y firma JPEG, sin decodificar) y no necesitan miniatura |
| `app.dominio.mensajes.interpretar(cuerpo)` → `EventosS3(objetos, ignorados) \| Reprocesar(imagen_id) \| PruebaS3() \| NoReconocido(motivo)` | Los mensajes de `ingesta` de §5.8; `ObjetoSubido(clave, etag, bytes)`. `VERSIONES_REPROCESAR = {1}`. BE-4.1 añade aquí los de `purga` (`purgar_video`, `purgar_imagen`) |
| `app.servicios.ingesta.procesar_lote(Dependencias(motor, almacen, ajustes, vectorizar=None), mensajes)` → `list[Decision(mensaje, borrar, unidades)]` | El lote de arriba. `vectorizar` sustituye a `embedding.vectorizar` (las pruebas pasan un doble). `Unidad.resultado` ∈ `Resultado` (`procesada`, `error`, `descartado`, `transitorio`) |
| `app.worker.consumir(detener, ajustes, *, cola, deps, esta_listo=…, espera_cola_s=20)` y `faltan_para_ingesta(ajustes)` | El bucle; las pruebas pasan cola, `esta_listo` y `procesar_lote` falsos (`tests/unit/test_worker.py`). BE-4.1 añade el consumo de `purga` |
| Pruebas con base | `tests/base/test_ingesta_base.py`: la clase `Mundo(ajustes, almacen)` con `video(n_fotos, completa=True)` → `(video_id, [imagen_id…])` (inserta por SQL un video `validacion-22` del primer usuario y sus fotos `pendiente_subida` en `1.0, -100.0`), `subir(video_id, imagen_id, datos=None)` → `MensajeSqs` (el `PUT` en `almacen_falso` y su evento de S3; sin `datos`, un JPEG de 1024×768 hecho con Pillow), `evento(clave, etag, size)`, `mensaje(cuerpo)`, `reprocesar(imagen_id)`, `procesar(mensajes, ajustes=None)` → decisiones (motor con pool 2), `fotos(video_id)`, `vectores(imagen_id)`, `estado_video(video_id)` y `sql(sentencia, **parametros)`. `Embeddings` es el doble de `vectorizar`: `version` (por defecto `dinov2-vits14/pp-v1`), `lotes` (tamaño de cada llamada), `fallos` (excepciones que lanza en las siguientes llamadas) y vectores de 384 con un único 1,0 en la posición `(llamada × 10 + i) mod 384` (no dependen de la imagen: para «la misma foto da el mismo vector», BE-2.4 usa otro doble, `vector_de(bytes)` de `tests/base/test_diagnostico_base.py`, §4.8) |
| Validador falso | `tests/ops/test_validate22.py`: un `Mundo` con la API (`/health/ready` incluido), S3, SQS, ECS (`embedding` y `worker` que arrancan con 60 y 30 s de retraso), Application Auto Scaling, CloudWatch (métrica y alarma), Cloud Map, CloudWatch Logs del `worker` y las tareas `psql` y `limpiar-validacion`, con reloj falso (`dormir` avanza de 5 en 5 s y simula un `worker` que consume `ingesta` cuando `embedding` está en marcha). BE-3.2 puede copiarlo para su validador, que también enciende `embedding` |

**JPEG multi-imagen (MPO).** Algunas cámaras guardan un JPEG con varias imágenes (extensión MPF: la foto más una
previsualización o un mapa de profundidad); empieza por `FF D8` como cualquier JPEG, pero Pillow lo abre como formato
`MPO`, no `JPEG`. `preparar` acepta los dos (`FORMATOS_ADMITIDOS`) y de un `MPO` usa solo la **primera** imagen (la
foto), como un JPEG normal: misma orientación EXIF, mismas reglas de tamaño y lado, y `ancho`/`alto` los de esa imagen.
La miniatura y la copia reducida que va a embeddings salen como JPEG de una sola imagen, así embeddings nunca recibe un
`MPO`. Probado en local con un MPO de 2 imágenes hecho con Pillow 12.3 (1024×768 + 512×384; también con orientación
EXIF 6) en `tests/unit/test_imagenes.py`. Si la app (CameraX) produce esos archivos: **sin comprobar**.

Trampas:
- Pillow lanza `DecompressionBombWarning` (no error) entre ~89,5 y ~179 MP: `preparar` lo convierte en error con
  `warnings.catch_warnings`, que **no es seguro entre hilos**: vale porque el `worker` prepara una foto a la vez; si
  otro lote llama a `preparar` desde varios hilos a la vez, los filtros de avisos pueden mezclarse.
- El `jpeg_sintetico` de los validadores (escala de grises) es válido para el `worker` (prueba en
  `tests/unit/test_imagenes.py`).
- El ETag de un `PUT` simple es el MD5 del contenido: subir los mismos bytes otra vez da el mismo ETag y el evento se
  descarta como duplicado (correcto: no cambió nada).
- En las pruebas del bucle, `worker.consumir` importa `servicios.ingesta.procesar_lote` al llamarse (no al importar
  el módulo): para sustituirlo, `monkeypatch.setattr(ingesta, "procesar_lote", …)` sobre el módulo `ingesta`.
- `Settings(...)` en las pruebas también lee variables del entorno de quien prueba (`pydantic-settings`): una
  `SQS_URL_INGESTA` o `DB_HOST` exportada cambia lo que devuelve `faltan_para_ingesta`.

### 4.7 BE-2.3 — Resumen del panel
`GET /v1/admin/stats` agrega totales en una consulta (fotos procesadas, lugares, alertas activas, último video). Las
«fotos pendientes de subir» del panel salen de la cola local de la app, no del backend. `alertas_activas` cuenta las
filas de `alertas` con `activa` y sin `eliminada_en` (la tabla existe desde BE-1.2): da 0 mientras no exista BE-3.3,
y su comprobación con datos es BE-3.3 C5, no BE-2.3 (decisión de 0.11.0, PLAN §2.2).

### 4.8 BE-2.4 — Diagnóstico de búsqueda
`POST /v1/admin/diagnostico/vecinos` (§5.5) muestra qué devuelve el índice para **una** foto, sin agrupar ni puntuar:
vectoriza la foto con prioridad `baja` (no compite con las localizaciones), busca los `k` vecinos en el índice HNSW de
la versión de vector activa con el mismo `hnsw.ef_search` que `/v1/localize` y **sin** aplicar `LOC_SIM_MIN`, y
devuelve cada vecino con su coordenada, su rumbo y su similitud. Lo usa la herramienta de evaluación de embeddings
(EMB-3.2) para medir *recall* y la distribución de similitudes antes de calibrar BE-3.2; también sirve para
investigar una localización mala. No lo usa la app.

La consulta de vecinos (literal de la versión en el `WHERE` para que se use el índice parcial, §5.7) se escribe aquí
una sola vez y BE-3.2 la reutiliza en el paso 3 de §4.10. Como en la localización, la foto no se guarda en ningún
sitio (ADR-BE-06) y no se registra nada en `eventos_localizacion`.

**Construido (ADR-BE-16).** Probado en local con PostgreSQL 17.11 y pgvector 0.8.7 (`db` del compose) y embeddings
simulado (`tests/base/test_diagnostico_base.py`), y en `dev` con `validate24.py` sobre `50d931d` (2026-10-25; PLAN
§3): cada una de las 3 fotos de prueba (`jpeg_patron`, ya indexadas a partir de la copia reducida JPEG calidad 90 del
`worker`) sale como su propio primer vecino con similitud 0,9991, 0,9992 y 0,9996, así que el cuerpo multipart binario
pasa bien por API Gateway; uno de 1,6 MiB también llega al backend y recibe su `400 FOTOS_INVALIDAS` (C3b). En
esa ejecución el índice tenía solo las 3 fotos de prueba (N = 3: aún no hay dataset real), así que el plan con miles de
vectores sigue a verificar (abajo, R16). Una petición, en este orden (cada paso responde su error de §5.5 y no sigue):
1. `requiere_admin` (router `/v1/admin`, §4.4): `401`/`403`/`503 BASE_NO_DISPONIBLE`.
2. FastAPI valida `k` (`Query(5, ge=1, le=50)`): `422 VALIDACION` con `detalle.campos = [{"campo": "k", …}]` (también
   `k=abc` o `k=5.5`).
3. `foto_de_la_peticion` (router): `api.cuerpo.leer_cuerpo` lee el cuerpo **en memoria** con tope
   `LOC_MAX_BYTES_FOTO + MARGEN_MULTIPART` (1 572 864 + 65 536 = 1 638 400 bytes; si el `Content-Length` declarado o lo
   leído pasa, `400 FOTOS_INVALIDAS` sin leer más); `dominio.multipart.partes_multipart` lo parte (un `Content-Type`
   que no es `multipart/form-data` → `400 FOTOS_INVALIDAS` «falta la parte foto»; multipart mal formado → `400
   SOLICITUD_INVALIDA`); de las partes solo cuenta la que se llama `foto` (las demás se ignoran, como hace embeddings
   con las suyas): ninguna → `indice` 0, dos o más → `indice` 1; `dominio.fotos.motivo_foto_no_valida` exige
   `Content-Type: image/jpeg` (sin mirar parámetros como `; charset=…`), no vacía, ≤ `LOC_MAX_BYTES_FOTO` y que empiece
   por `FF D8 FF`. No decodifica: lo hace embeddings.
4. `servicios.diagnostico.vecinos_de_foto`: `embedding.vectorizar([foto], prioridad="baja", request_id=<X-Request-Id
   de la petición>)` dentro de `anyio.fail_after(TOPE_EMBEDDING_S)` (20 s: los plazos de httpx son por fase). Errores:
   `EmbeddingNoDisponible` (apagado, saturado, `5xx`, sin respuesta) y `RespuestaNoValida` → `503
   EMBEDDING_NO_DISPONIBLE` con el evento `embedding_no_disponible` (`WARNING` y `ERROR`); `ImagenRechazada` → `400
   FOTOS_INVALIDAS` «embeddings la rechazó (<código>)»; `version_vector` de la respuesta distinta de
   `EMBEDDING_VERSION_VECTOR` → `503 EMBEDDING_NO_DISPONIBLE` con `version_vector_distinta` (no se busca con un vector
   incomparable). Sin `GET /v1/info`: la versión viene en cada respuesta de `/v1/embed`.
5. En **una** transacción corta (`sesion.transaccion`), `db.consultas.buscar_vecinos` con `k`, `LOC_EF_SEARCH` y
   `EMBEDDING_VERSION_VECTOR`. Un fallo de la base → `503 BASE_NO_DISPONIBLE` (§4.4). Nada se escribe.
6. Respuesta: `similitud` redondeada a 6 decimales (el orden lo da la distancia sin redondear), `rumbo` con
   `real_legible` (§4.5), `latencia_ms` = desde que empieza el endpoint (ya pasados los pasos 1 y 2) hasta antes de
   serializar. Evento `vecinos_consultados` (§5.10), sin ids ni bytes de la foto.

**La consulta** (`db.consultas.sql_vecinos`, la única del proyecto para vecinos):
```sql
SELECT i.id, i.video_id, i.lat, i.lng, i.rumbo, i.lugar_id, c.distancia
FROM (SELECT e.imagen_id, e.vector <=> CAST(:vector AS vector) AS distancia
      FROM embeddings e WHERE e.version_vector = '<EMBEDDING_VERSION_VECTOR>'
      ORDER BY e.vector <=> CAST(:vector AS vector) LIMIT :k) AS c
JOIN imagenes i ON i.id = c.imagen_id
ORDER BY c.distancia, i.id
```
precedida, en la misma transacción, de `SELECT set_config('hnsw.ef_search', '<max(LOC_EF_SEARCH, k)>', true)` (=
`SET LOCAL`: no sale de la transacción; comprobado). La subconsulta ordena por la expresión del índice con `LIMIT`
(lo que pgvector necesita para usar HNSW) y la unión con `imagenes` va fuera. `ef_search` es el de `/v1/localize`
(64) salvo si `k` lo supera (HNSW devolvería como mucho `ef_search` filas); con `k` ≤ 50, siempre 64. Similitud =
`1 − distancia coseno`, acotada a [−1, 1]. Solo entran imágenes con vector de la versión activa; una imagen de otra
versión no sale (probado). No mira `imagenes.estado` ni el video: los vectores solo existen para fotos `procesada`
(el `worker` los borra en `error`, §4.6) y BE-4.1 los borra al borrar un video (ADR-BE-07).

**Plan de PostgreSQL (trampa).** Con el índice parcial disponible, el planificador decide por costo: en local, con 10
vectores y `enable_seqscan = off`, el plan usa `embeddings_hnsw_dinov2_vits14_pp_v1` (prueba
`test_la_consulta_usa_el_indice_parcial_y_ef_search_solo_en_la_transaccion`); con la tabla vacía y sin estadísticas
prefiere `embeddings_pkey` (`version_vector` es la segunda columna de la PK) más un `Sort` exacto. Los dos dan los
mismos vecinos (el exacto, incluso mejores); con miles de vectores el `Sort` de todos cuesta más que HNSW. **A
verificar** con `EXPLAIN` en `dev` cuando haya un dataset real (FE-2.1): si no usara el índice, BE-3.2 lo notaría en
la latencia (C3).

**Por qué el multipart se parte a mano** (ADR-BE-16): `request.form()` de Starlette exige `python-multipart` (no está
en la imagen) y pasa a un archivo temporal **en disco** toda parte de más de 1 MB: una foto de consulta tocaría el disco
(ADR-BE-06; BE-3.2 C4 lo comprueba con ECS Exec). `dominio.multipart` sigue RFC 7578/2046 (preámbulo y epílogo,
`boundary` de 1 a 70 caracteres, `name*=` de RFC 2231) y está probado con lo que manda httpx (el cliente de la
herramienta de evaluación de embeddings y de los validadores), con bytes binarios que contienen `\r\n--` en medio.

**Para los lotes siguientes: qué ofrece BE-2.4 al código** (BE-3.2 reutiliza todo menos el router; BE-4.1 C1 usa el
endpoint).

| Elemento | Qué hace |
|---|---|
| `app.db.consultas.buscar_vecinos(conexion, vectores, *, k, version_vector, ef_search)` → `list[list[Vecino]]` | Dentro de una transacción abierta: `fijar_ef_search(conexion, max(ef_search, k))` y una sentencia `sql_vecinos` por vector; una lista por vector, en el mismo orden, de mayor a menor similitud (a igualdad, `imagen_id`). `ValueError` si `k` < 1, la versión no tiene formato de versión o un vector está vacío o no es finito. **BE-3.2**: `async with sesion.transaccion(motor) as c: vecinos = await buscar_vecinos(c, vectores.vectores, k=LOC_TOP_K, version_vector=EMBEDDING_VERSION_VECTOR, ef_search=LOC_EF_SEARCH)` (una transacción para las 1–5 fotos) y después descarta `similitud < LOC_SIM_MIN` (aquí no se filtra) |
| `app.db.consultas.Vecino` | *Dataclass* congelado: `imagen_id`, `video_id` (`uuid.UUID`), `lat`, `lng` (`float`), `rumbo` (`float \| None`, el `real` crudo: pasarlo por `real_legible` para la API), `lugar_id` (`uuid.UUID \| None`), `distancia` y `similitud` (`float`, sin redondear) |
| `app.db.consultas.sql_vecinos(version)`, `literal_version(version)`, `texto_vector(vector)`, `fijar_ef_search(conexion, n)` | La sentencia (parámetros `:vector` y `:k`); la versión citada como literal (`'…'`; exige `[A-Za-z0-9._/-]{1,100}`, si no `ValueError`); el vector como texto de pgvector (`[x1,x2,…]` con `repr` de cada `float`); `set_config('hnsw.ef_search', n, true)` |
| `app.servicios.diagnostico.vecinos_de_foto(motor, ajustes, foto, *, k, request_id=None, vectorizar=None)` → `ResultadoVecinos(version_vector, k, vecinos, embedding_ms, busqueda_ms)` | Pasos 4 y 5 de arriba. `vectorizar(imagenes)` sustituye la llamada a embeddings; sin él usa `embedding.vectorizar(ajustes, imagenes, prioridad="baja", request_id=…)` (buscado en el módulo al llamar: las pruebas lo cambian con `monkeypatch.setattr(embedding, "vectorizar", doble)`). Excepciones: las de `clientes.embedding`, `VersionVectorDistinta(esperada, recibida)` y `BaseNoDisponible`. Constante `TOPE_EMBEDDING_S` (20). BE-3.2 escribe su propio servicio (prioridad `alta`, varias fotos) con las mismas piezas |
| `app.dominio.multipart.partes_multipart(content_type, cuerpo)` → `list[Parte(nombre, archivo, tipo, datos)]` | Partes en orden de llegada; `tipo` en minúsculas sin parámetros (`text/plain` si la parte no trae); `NoEsMultipart` (otro `Content-Type` o ninguno) y `MultipartInvalido(motivo)` (sin `boundary`, sin delimitador final, cabeceras sin `:` o sin fin, parte sin `Content-Disposition: form-data; name=…`). `boundary_de(content_type)`, `BOUNDARY_MAX` (70). Sin dependencias (stdlib `email.message` para los parámetros de las cabeceras) |
| `app.dominio.fotos.motivo_foto_no_valida(tipo, datos, max_bytes)` → `str \| None` | Reglas de §5.5 para una foto (en este orden: tipo `image/jpeg`, no vacía, tamaño, firma `FF D8 FF`); los motivos (`tipo image/png: se espera image/jpeg`, `la foto está vacía`, `la foto pesa N bytes (máximo M)`, `no es un JPEG (no empieza por FF D8 FF)`) van en `detalle.motivo`. `TIPO_JPEG`, `FIRMA_JPEG`. **BE-3.2** la aplica a cada foto con su índice |
| `app.api.cuerpo.leer_cuerpo(request, max_bytes)` → `bytes`; `CuerpoDemasiadoGrande(max_bytes)` | Lectura acotada del cuerpo (`Content-Length` y lo leído). BE-3.2 usa como tope `LOC_MAX_FOTOS × LOC_MAX_BYTES_FOTO` + margen |
| `app.api.v1.admin_diagnostico.foto_de_la_peticion(request, max_bytes)` → `bytes`; `PARTE_FOTO` (`foto`), `MARGEN_MULTIPART` (65 536) | El paso 3 con sus `ErrorApi`. El router `admin_diagnostico.router` (`/diagnostico`) va en `RUTAS_ADMIN` |
| `app.esquemas.diagnostico` | `VecinoDiagnostico`, `VecinosRespuesta` (§5.5; prohíben campos de más), `K_MIN` (1), `K_MAX` (50), `K_POR_DEFECTO` (5), `DECIMALES_SIMILITUD` (6). La petición no tiene modelo: el OpenAPI la declara con `openapi_extra` (`multipart/form-data`, `foto` binaria) |
| Pruebas con base | `tests/base/test_diagnostico_base.py`: `vector_de(bytes)` (vector unitario de 384 sacado del SHA-256 de los bytes: la misma foto da el mismo vector; dos distintas, similitud ~0), `Embeddings` (doble de `embedding.vectorizar` con `version`, `llamadas` —`n`, `prioridad`, `request_id`— y `fallo`), `indexar(ajustes, fotos, version=…, rumbo=340.3)` → `{"video_id", "imagenes"}` (un video `validacion-24` con una imagen `procesada` y su vector por foto, en `1.0 + orden·0,0001, −100.0`), `jpeg(semilla)`, `consultar(api, foto, k, tipo=, parte=)` y la fixture `api` (admin con sesión). BE-3.2 puede partir de ahí |
| Ejemplo de doble de embeddings en la API | `monkeypatch.setattr(app.clientes.embedding, "vectorizar", doble)` con la firma `(ajustes, imagenes, *, prioridad, transporte=None, request_id=None)` |

**Guía para BE-3.2** (`POST /v1/localize`, §5.3; el algoritmo es §4.10, que este lote no toca). Aplicada tal cual
en BE-3.2 (0.12.0); lo construido y sus detalles están en §4.10. Con las piezas de arriba, sin abrir `project/`:
1. Cuerpo: `leer_cuerpo(request, LOC_MAX_FOTOS × LOC_MAX_BYTES_FOTO + MARGEN_MULTIPART)`; si pasa,
   `400 FOTOS_INVALIDAS`. `partes_multipart(request.headers.get("content-type"), cuerpo)` (`NoEsMultipart` →
   `400 FOTOS_INVALIDAS`; `MultipartInvalido` → `400 SOLICITUD_INVALIDA`, como aquí).
2. Fotos: las partes `fotos`, **en el orden en que llegan** (ese orden es el `indice` de `detalle.indice` y el de
   `rumbos`); de 1 a `LOC_MAX_FOTOS` (si no, `400 FOTOS_INVALIDAS` con el índice de la primera que sobra, o 0 si no hay
   ninguna); `motivo_foto_no_valida(parte.tipo, parte.datos, LOC_MAX_BYTES_FOTO)` en cada una, con su índice.
3. Metadatos: la parte `metadatos` es texto (`Parte.tipo` = `text/plain` si no declara otro): `parte.datos` en UTF-8
   → JSON → su modelo Pydantic (`rumbos` del mismo largo que las fotos; si no, `400 FOTOS_INVALIDAS`, §5.3).
4. Embeddings: **una** llamada `embedding.vectorizar(ajustes, fotos, prioridad="alta", request_id=…)` (5 × 1,5 MB
   cabe en los límites de embeddings: 8 imágenes, 4 MB cada una, 16 MB en total) dentro de `anyio.fail_after` con un
   tope por debajo de los 30 s de API Gateway (aquí, `TOPE_EMBEDDING_S` = 20 s, importable de
   `servicios.diagnostico`). Misma traducción y mismos eventos que el paso 4 de arriba: `ImagenRechazada.indice` es ya
   el índice de la foto (`400 FOTOS_INVALIDAS`); `EmbeddingNoDisponible`, `RespuestaNoValida` y otra `version_vector`
   (`servicios.diagnostico.VersionVectorDistinta` sirve también) → `503 EMBEDDING_NO_DISPONIBLE` con
   `embedding_no_disponible` o `version_vector_distinta`.
5. Búsqueda: una transacción con `buscar_vecinos(c, vectores.vectores, k=LOC_TOP_K, version_vector=…,
   ef_search=LOC_EF_SEARCH)`; después, BE-3.2 descarta `similitud < LOC_SIM_MIN` (aquí no se filtra) y agrupa con
   `Vecino.lat`, `Vecino.lng`, `Vecino.similitud` y `Vecino.rumbo` (`None` si la foto del dataset no tenía rumbo: no
   entra en la corrección de rumbo). Usa los valores crudos de `Vecino`; `real_legible` y el redondeo son solo para
   la salida de la API.
6. A diferencia de BE-2.4, BE-3.2 sí escribe la fila de `eventos_localizacion` (§4.10 paso 10, §5.7).
7. Pruebas: el doble `Embeddings`/`vector_de` y `indexar` de `tests/base/test_diagnostico_base.py` sirven para tener
   un índice sin `embedding`; `indexar` pone todas las fotos en `1.0 + orden·0,0001, −100.0`, así que para probar la
   agrupación geográfica hace falta una variante con coordenadas propias.

Trampas:
- `request.form()` y los parámetros `File`/`UploadFile` de FastAPI **no** se usan en estas rutas (disco y
  `python-multipart`, arriba). Una ruta nueva que reciba fotos usa `leer_cuerpo` + `partes_multipart`.
- `leer_cuerpo` consume `request.stream()`: después, `await request.body()` ya no devuelve el cuerpo.
- El `Content-Type` de la parte manda: un JPEG enviado como `image/png` es `400` aunque los bytes sean JPEG (y un PNG
  enviado como `image/jpeg`, `400` por la firma). `image/jpeg; charset=binary` vale.
- HNSW es aproximado (R16): con muchos vectores, algún vecino exacto puede faltar; la herramienta de evaluación de
  embeddings lo compara con fuerza bruta (`SERVICE_EMBEDDING/docs/ARCHITECTURE.md` §4.5).
- `embeddings.vector` es `vector(384)`: un vector de otra dimensión hace fallar la sentencia en PostgreSQL (no es «base
  no disponible»: saldría como `500`). Comparar antes la `version_vector` (paso 4) lo evita, porque una versión con
  otra dimensión trae otro nombre.
- La herramienta de evaluación de embeddings y `validate24.py` mandan la foto como `consulta.jpg` con `image/jpeg`
  (`comun.pedir_vecinos`); el nombre de archivo no se mira.

### 4.9 BE-3.1 — Lugares (las alertas pasaron a BE-3.3, sin implementar)
`GET /v1/places` (público) da todos los lugares, con la distancia a una posición si se envía; `/v1/admin/places`
(admin) los crea, reemplaza, borra y lista para el panel (contratos en §5.3 y §5.5). Los usan la app (Selección de
destino 6.4 y lugares de administración 7.6–7.7: FE-3.1 y FE-3.4) y BE-3.2 (lugar cercano y referencias, §4.10 paso 9).

**Construido (ADR-BE-17).** Probado en local con PostgreSQL 17.11 y pgvector 0.8.7 (`db` del compose):
`tests/base/test_lugares_base.py` (endpoints contra la base), `tests/unit/test_lugares.py` (nombre normalizado,
geometría, `LugarEntrada`), `tests/contrato/test_contrato_lugares.py` (ejemplos de §5 contra los esquemas) y
`validate31.py --entorno local` contra el compose (validation-3-1 §5); en `dev`, `validate31.py` con código 0 sobre
`86fc024` (2026-10-25, informe `BE-3.1-20261026-030207.json`: C1a–C4b en verde, 3 lugares de prueba borrados). Sin
migración: la tabla `lugares` y sus restricciones existen desde `0001` (§5.7).

**Lectura pública** (`GET /v1/places`, router `api/v1/lugares.router_publico`, sin `requiere_admin`: ignora
`Authorization`, también un token no válido):
1. FastAPI valida `lat` ([−90, 90]), `lng` ([−180, 180]), sin `NaN` ni infinitos, y `categoria` (`CategoriaLugar`):
   si no, `422 VALIDACION` con `detalle.campos`.
2. Si llega uno de `lat`/`lng` sin el otro: `422 VALIDACION` con el campo que falta (`lat y lng van juntos: falta
   este.`).
3. `servicios.lugares.listar_publico`: una transacción corta lee todas las filas de `lugares` (con `WHERE categoria`
   si se pide). Son decenas: no hay paginación ni índice por posición.
4. En Python: sin posición, orden por `nombre_normalizado` y, a igualdad, `id`; con posición, `distancia_m =
   geo.distancia_m(lat, lng, lugar)` (haversine, radio medio 6 371 008,8 m) y orden por esa distancia **sin
   redondear**, después `nombre_normalizado` e `id`. La distancia se devuelve redondeada a 1 decimal. El orden de los
   nombres es el de los puntos de código (como `COLLATE "C"`), no el de la intercalación de la base, por eso se ordena
   en Python.
5. `{"items": […], "total": len(items)}`. `imagen_url` es siempre `null` (abajo, «Foto del lugar»).

**Panel** (`GET /v1/admin/places`, `listar_admin`): `q` (≤ 100 caracteres, sin NUL) se normaliza como un nombre y se
busca contenido en `nombre_normalizado` con `LIKE` (`%`, `_` y `\` escapados: son literales); vacío o solo espacios
= sin filtro. No busca en `alias`. `total_fotos` sale de una subconsulta agrupada: imágenes con ese `lugar_id` cuyo
video no está `eliminado`, en cualquier estado. Mismo orden por nombre.

**Escrituras** (`crear`, `reemplazar`, `borrar`; el admin es el `UsuarioActual` de `requiere_admin`, §4.4). Cada
cambio va en una transacción con su fila de `auditoria` (§5.7, «filas de BE-3.1») y, tras confirmar, su evento
(`lugar_guardado` o `lugar_eliminado`, §5.10; sin el nombre):
- **Crear**: `INSERT … ON CONFLICT ON CONSTRAINT lugares_nombre_normalizado_key DO NOTHING RETURNING …`; sin fila
  devuelta → `409 NOMBRE_DUPLICADO` (nada escrito). `creado_en` = `actualizado_en` = `now()` de la transacción;
  `creado_por` = el admin.
- **Reemplazar** (`PUT`, todos los campos de `LugarEntrada`: lo que no se envía vuelve a su valor por defecto):
  `SELECT … FOR NO KEY UPDATE` del lugar (no existe → `404`); compara campo a campo (`CAMPOS`); **sin cambios no
  escribe** (ni `actualizado_en`, ni auditoría, ni evento) y devuelve el lugar como está; si el nombre normalizado
  cambia y otro lugar ya lo tiene → `409`; si no, `UPDATE` con `actualizado_en = now()`. El mismo nombre con otras
  mayúsculas o tildes no es un duplicado de sí mismo. Si dos `PUT` a la vez ponen el mismo nombre, la comprobación
  previa no ve al otro y gana la restricción única: el `IntegrityError` de `lugares_nombre_normalizado_key` también
  se responde `409` (`_es_nombre_duplicado`, que mira `constraint_name` en la cadena de causas de asyncpg).
- **Borrar**: orden de bloqueo **videos de sus fotos (por id) → lugar → fotos**: lee sin bloqueo los `video_id` de
  las imágenes del lugar, los bloquea con `recoleccion.bloquear_video` en orden, bloquea el lugar `FOR UPDATE`, pone
  `lugar_id = NULL` y `actualizado_en = now()` en sus imágenes (la FK `ON DELETE SET NULL` haría lo primero, pero no
  lo segundo ni el recuento) y borra la fila. Un id que no existe da `204` sin auditoría (evento con `existia =
  false`): el `DELETE` es idempotente, así un reintento tras perder la respuesta no da error (ADR-BE-17).

**Nombre normalizado** (`dominio.lugares.normalizar_nombre`, ADR-BE-17): Unicode NFKD, sin marcas combinantes
(tildes, diéresis y la virgulilla de la ñ), `casefold()` y los espacios de cualquier clase reducidos a uno, sin
espacios alrededor. «Café  Norte», «CAFE NORTE» y «cafe norte» → `cafe norte`; «Baño» → `bano`; «Straße» →
`strasse`; «ﬁ» → `fi`. Es lo que guarda `lugares.nombre_normalizado` (único) y lo que se compara con `q`. `nombre` se
guarda como llega, recortado (sin tocar los espacios internos). Un nombre que queda vacío al normalizar (solo marcas
combinantes) es `422`.

**Foto del lugar: fuera de BE-3.1.** §5.5 no tiene un endpoint para subirla, así que `lugares.imagen_key` queda
siempre nulo e `imagen_url` es siempre `null` (como `ImagenAdmin.url` hasta BE-4.1); la app ya muestra el ícono de la
categoría sin foto (FE-3.1). Infra reserva el prefijo `lugares/{lugar_id}.jpg` para la Fase 4, subido por la app con
URL prefirmada (infra §5.5), y da a `tarea-api` `s3:PutObject` y `s3:GetObject` en `lugares/*` (infra §5.8; sin
comprobar en `dev`). El lote que la añada (sin asignar en PLAN) define primero el endpoint en §5.5 y usa
`AlmacenS3.firmar_put` y un `firmar_get` que falta (§4.5).

**Para los lotes siguientes: qué ofrece BE-3.1 al código.**

| Elemento | Qué hace |
|---|---|
| `app.dominio.lugares` | `normalizar_nombre(texto)` (arriba; puede dar `""`); límites de `LugarEntrada`: `NOMBRE_MIN` (2), `NOMBRE_MAX` (80), `ALIAS_MAX_ELEMENTOS` (20), `ALIAS_MAX` (60), `DESCRIPCION_MAX` (300, también `referencias`), `Q_MAX` (100) y `DECIMALES_DISTANCIA` (1) |
| `app.dominio.geo` | `distancia_m(lat1, lng1, lat2, lng2)` (haversine, `RADIO_TIERRA_M` = 6 371 008,8; a cientos de metros, < 0,5 % de error frente al elipsoide) y `rumbo_grados(lat1, lng1, lat2, lng2)` (rumbo inicial del 1 al 2 en [0, 360), 0 = norte verdadero, horario; 0 entre puntos iguales). Python puro. BE-3.2 los usa para `lugar_cercano.distancia_m` y `referencias[].rumbo_grados` (§4.10 paso 9) |
| `app.esquemas.lugares` | `LugarEntrada` (ignora campos de más; recorta textos; `alias` ausente o `null` → `[]`; `descripcion`/`referencias` vacías → `null`; todo texto por `texto_admitido`), `LugarPublico`, `LugarAdmin` (prohíben campos de más) y `ListaLugares[T]` (`items`, `total`) |
| `app.servicios.lugares` | `listar_publico(motor, *, lat=None, lng=None, categoria=None)` → `list[LugarPublico]`; `listar_admin(motor, *, q=None, categoria=None)` → `list[LugarAdmin]`; `crear(motor, *, usuario_id, datos)` → `LugarAdmin`; `reemplazar(motor, *, usuario_id, lugar_id, datos)` → `LugarAdmin`; `borrar(motor, *, usuario_id, lugar_id)` → `Borrado(existia, fotos_sin_lugar)`. Excepciones `NombreDuplicado` y `LugarNoEncontrado`. `leer_todos(conexion, categoria=None)` → `list[LugarRef(id, nombre, categoria, lat, lng)]` por nombre normalizado, **dentro de una transacción abierta** (para BE-3.2). `RESTRICCION_NOMBRE` (`lugares_nombre_normalizado_key`), `CAMPOS` (los 7 de `LugarEntrada` que guarda la tabla) |
| `app.api.v1.lugares` | `router_publico` (`/places`, montado en `router_v1`) y `router_admin` (`/places`, en `RUTAS_ADMIN`) |
| `app.errores.MENSAJE_POR_CODIGO["NOMBRE_DUPLICADO"]` | «Ya existe un lugar con ese nombre (sin distinguir mayúsculas ni tildes).» |
| Pruebas con base | `tests/base/test_lugares_base.py`: `entrada(nombre, **cambios)` (un `LugarEntrada` completo), `crear(api, nombre, **cambios)` → `LugarAdmin` (exige 201), `foto_con_lugar(ajustes, lugar_id, eliminado=False)` → `imagen_id` (inserta por SQL un video `validacion-31` y una foto con ese `lugar_id`: lo que hará `PATCH` de BE-4.1), `auditoria(ajustes, accion)`, `sql(ajustes, sentencia, **parametros)` y la fixture `api` (admin con sesión, sin S3) |

**Guía para BE-3.2** (paso 9 de §4.10, que este lote no toca; aplicada en BE-3.2, 0.12.0, con `leer_todos` en la
misma transacción de la búsqueda y `DECIMALES_DISTANCIA` en las dos distancias, §4.10): en la transacción de la búsqueda (o en otra corta),
`await lugares.leer_todos(conexion)`; con la posición calculada, `geo.distancia_m` a cada lugar para el más cercano a
≤ `LOC_LUGAR_CERCANO_M` y las referencias a ≤ `LOC_REFERENCIAS_M`, y `geo.rumbo_grados(posición → lugar)` para
`referencias[].rumbo_grados`. Para probarlo sin dataset real, `crear` de las pruebas de arriba (coordenadas propias).
Detalles (0.11.1):
- Importes: `from app.servicios import lugares` (`lugares.leer_todos`, `lugares.LugarRef`) y `from app.dominio import
  geo`. `leer_todos` solo trae `id`, `nombre`, `categoria`, `lat` y `lng` (no `alias` ni textos) y lee la tabla entera
  (decenas de filas); `geo.*` reciben y devuelven `float` crudos (grados y metros, sin redondear).
- Redondeo: `GET /v1/places` da `distancia_m` con `dominio.lugares.DECIMALES_DISTANCIA` (1); usar la misma constante
  para `lugar_cercano.distancia_m` y `referencias[].distancia_m` deja las dos rutas coherentes (el ejemplo de §5.3 ya
  va con 1 decimal). Cómo redondear `rumbo_grados` lo decide BE-3.2 (un `round` puede dar 360.0: normalizar a
  [0, 360)).
- Pruebas con base: `entrada`, `crear`, `sql` y la fixture `api` son funciones de un **módulo de pruebas**
  (`tests/base/test_lugares_base.py`), no de un paquete. Para reutilizarlas, cargarlo con `importlib.util`
  (`spec_from_file_location` + `exec_module`, como `tests/ops/test_validate24.py` con `test_validate22.py`) o crear
  los lugares con la API (`POST /v1/admin/places` con un admin, como `crear`) o por SQL: `INSERT INTO lugares (nombre,
  nombre_normalizado, categoria, lat, lng, creado_por) SELECT :nombre, :normalizado, 'bloque', :lat, :lng, id FROM
  usuarios LIMIT 1`, con `normalizado = normalizar_nombre(nombre)` (único: dos nombres iguales al normalizar violan
  `lugares_nombre_normalizado_key`).
- Validador de BE-3.2 en `dev`: desde 0.12.0, P3 de `validation-3-2.md` solo exige `GET /v1/places` → `200` (anota el
  `total`; antes pedía `total` ≥ 1, que no dependía de ningún lote) y no crea lugares: ningún criterio de BE-3.2 mira
  el contexto, que cubren las pruebas con base (§4.10). Si un lote futuro necesita lugares propios en `dev`, los crea
  con `POST /v1/admin/places` y nombre `validacion-<lote>-<ts> …`, los borra con `comun.borrar_lugares` y barre restos
  con `comun.borrar_lugares_restos` en su `preparacion` (§5.11, ayudas de BE-3.1); nunca toca lugares reales.

**Guía para BE-4.1** (imágenes con lugar): un `PATCH` de imagen con `lugar_id` bloquea video → imagen (§4.5) y la FK
toma `KEY SHARE` del lugar al escribir: compatible con el orden de `borrar` de arriba y con el `FOR NO KEY UPDATE` de
`reemplazar`. Un `lugar_id` que no existe (o que se borra a la vez) llega como violación de FK (23503) y hay que
traducirlo; `total_fotos` de `LugarAdmin` ya cuenta esas fotos.

Trampas:
- La normalización junta la ñ con la n («Año» = «Ano») y la ß con «ss»: es a propósito (quien busca escribe sin
  tildes), pero dos lugares reales que solo se distingan así darían `409`.
- `GET /v1/admin/places?q=` no busca en `alias` ni en `descripcion`.
- `DELETE` de un id que no existe da `204`: un id equivocado no da error (comprobar con `GET` si hace falta).
- `GET /v1/places` lee la tabla entera en cada llamada: con decenas de lugares no importa; si llegaran a miles,
  habría que paginar o filtrar en SQL (cambio de §5.3).
- Con el `TestClient` de las pruebas, `GET /v1/places?lat=nan` también es `422` (`allow_inf_nan=False` en `Query`).

**Alertas (BE-3.3, sin implementar).** Decisión del usuario (2026-10-25): las alertas salen del núcleo y de BE-3.1
a un lote propio, BE-3.3 (PLAN §2.2). Su contrato de §5.3 y §5.5 queda documentado y marcado «sin implementar
(BE-3.3)»; hoy esas rutas no existen y responden `404 NO_ENCONTRADO` (ruta inexistente, §5.6), también
`/v1/admin/alerts/*` sin token (no hay ruta que proteger). La tabla `alertas` existe desde `0001` (§5.7) y
`GET /v1/admin/stats` (BE-2.3) la cuenta. Diseño para BE-3.3 (ADR-BE-10):
- `GET /v1/alerts` alimenta la caché local de la app, que debe funcionar sin conexión: sin `desde` entrega la foto
  completa de alertas activas (incluidas las de vigencia futura, para que lleguen antes de empezar; la app filtra por
  vigencia al anunciar); con `desde` entrega solo lo cambiado y los identificadores borrados (*tombstones*, 90 días,
  `ALERTAS_TOMBSTONE_DIAS`, con su limpieza diaria desde `api`). La app guarda `generado_en` y lo envía como `desde`
  la próxima vez.
- El editor de la app trabaja local primero y genera los UUID. `PUT /v1/admin/alerts/{id}` crea o reemplaza
  (idempotente); `DELETE` de un id desconocido responde `204` (así, una alerta creada y borrada antes de sincronizar
  no da error). `POST /v1/admin/alerts/sincronizar` aplica una lista de cambios independientes y devuelve el resultado
  de cada uno: la app quita de «pendientes» solo los que salieron `ok`. Control de concurrencia opcional con
  `If-Match: <version>` (`409 CONFLICTO_VERSION`).

### 4.10 BE-3.2 — Localización (`POST /v1/localize`)
`POST /v1/localize` (§5.3, público) recibe 1–5 fotos de una vuelta de 360° y sus rumbos, y devuelve la posición, la
confianza, la corrección de la brújula y el lugar cercano con sus referencias. Lo usa la app (Escaneo 360° →
Resultado, 6.2–6.3, FE-3.2). Algoritmo v1 por vecinos más cercanos y agrupación geográfica (ADR-BE-08), con los
detalles que fija ADR-BE-18 y los parámetros `LOC_*` de §5.10.

**Estado (0.12.0): construido, sin validar en `dev`.** Probado en local con PostgreSQL 17.11 y pgvector 0.8.7 (`db`
del compose) y embeddings simulado: `tests/unit/test_localizacion.py` (el algoritmo, sin base),
`tests/base/test_localizacion_base.py` (el endpoint contra la base, con vectores elegidos a mano),
`tests/contrato/test_contrato_localizacion.py` (§5.3, §5.6 y §5.10 contra los esquemas, `Settings` y el OpenAPI) y
`tests/ops/test_validate32.py` (el validador contra un mundo falso). **Falta**, porque depende de otros lotes: el
dataset real indexado (FE-2.1 + BE-2.2), el conjunto de consulta y el informe de EMB-3.2, la calibración de
`LOC_SIM_MIN`, `LOC_SIM_ALTA` y los cortes de nivel (abajo, «Calibración») y `validate32.py` con código 0 en `dev`
(PLAN §3). Hasta entonces los umbrales son los iniciales de §5.10 y ningún número de precisión está medido.

**Una petición**, en este orden (cada paso responde su error de §5.3 y no sigue):
1. Router `api/v1/localizar.localizar` (en `router_v1`, sin `requiere_admin`: ignora `Authorization`). Toma
   `inicio = time.perf_counter()` (de ahí sale `latencia_ms`).
2. `partes_de_la_peticion`: `leer_cuerpo(request, LOC_MAX_FOTOS × LOC_MAX_BYTES_FOTO + MARGEN_MULTIPART)`
   (5 × 1 572 864 + 65 536 = 7 929 856 bytes, por debajo de los 10 MB de API Gateway; si pasa, `400 FOTOS_INVALIDAS`
   con `indice` 0) y `partes_multipart` (`NoEsMultipart` → `400 FOTOS_INVALIDAS` «falta la parte fotos»;
   `MultipartInvalido` → `400 SOLICITUD_INVALIDA`). Las partes que no se llaman `fotos` ni `metadatos` se ignoran.
3. `fotos_de`: las partes `fotos` **en el orden en que llegan** (aunque haya otras partes en medio): ninguna →
   `indice` 0; más de `LOC_MAX_FOTOS` → `indice` = `LOC_MAX_FOTOS` (la primera que sobra); después
   `dominio.fotos.motivo_foto_no_valida` en cada una con su índice (tipo `image/jpeg` sin mirar parámetros, no vacía,
   ≤ `LOC_MAX_BYTES_FOTO`, firma `FF D8 FF`). No decodifica: lo hace embeddings.
4. `metadatos_de`: una sola parte `metadatos` (falta o repetida → `422 VALIDACION`, campo `metadatos`), como mucho
   `METADATOS_MAX_BYTES` (16 384; si no, `422`), JSON en UTF-8 sin mirar su `Content-Type` (si no se puede leer,
   también por anidamiento excesivo, `400 SOLICITUD_INVALIDA`), validado con `esquemas.localizacion.MetadatosLocalizacion`
   (`422 VALIDACION` con `detalle.campos` = `metadatos.<campo>`, p. ej. `metadatos.rumbos.1`; un JSON que no es objeto,
   campo `metadatos`). `rumbos` con otro largo que las fotos → `400 FOTOS_INVALIDAS` con
   `indice = min(len(rumbos), fotos)` (la primera foto sin rumbo, o el primer rumbo sin foto).
5. `obtener_motor(request)`: sin motor, `503 BASE_NO_DISPONIBLE`. Va después de validar, como en BE-2.4.
6. `servicios.localizar.localizar(motor, ajustes, fotos, rumbos, origen=, app_version=, inicio=, request_id=)`:
   **una** llamada `embedding.vectorizar(ajustes, fotos, prioridad="alta", request_id=<X-Request-Id>)` dentro de
   `anyio.fail_after(TOPE_EMBEDDING_S)` (20 s, de `servicios.diagnostico`); `version_vector` distinta de
   `EMBEDDING_VERSION_VECTOR` → `VersionVectorDistinta` sin buscar. Después, **una** transacción
   (`sesion.transaccion`): `buscar_vecinos(c, vectores, k=LOC_TOP_K, version_vector=…, ef_search=LOC_EF_SEARCH)` (un
   vector por foto), el algoritmo (`dominio.localizacion.localizar`, Python puro, microsegundos con la
   conexión abierta), `lugares.leer_todos(c)` y `localizacion.contexto` solo si hay posición, y el `INSERT` en
   `eventos_localizacion` (paso 10). `latencia_ms` se mide justo antes del `INSERT`. Si el `INSERT` o el `COMMIT`
   fallan por la base, `503 BASE_NO_DISPONIBLE`: la respuesta y la tabla nunca se contradicen.
7. Traducción de errores (la misma que BE-2.4, §4.8): `ImagenRechazada(indice, codigo)` → `400 FOTOS_INVALIDAS` con ese
   `indice` y `motivo` «embeddings la rechazó (<codigo>)»; `EmbeddingNoDisponible` (también el tope de 20 s) y
   `RespuestaNoValida` → `503 EMBEDDING_NO_DISPONIBLE` con el evento `embedding_no_disponible` (`WARNING`; `ERROR` si
   la respuesta no cumple el contrato); `VersionVectorDistinta` → `503` con `version_vector_distinta`. Ningún error
   escribe en `eventos_localizacion`.
8. `respuesta_de`: redondeo para la salida (abajo) y evento `localizacion_calculada` (§5.10: cifras de la consulta, sin
   posición, ids ni nada de las fotos salvo el total de bytes).

**El algoritmo** (`dominio/localizacion.py`; los pasos de ADR-BE-08 con los detalles de ADR-BE-18). Entrada: la lista de
vecinos de cada foto (`db.consultas.Vecino`, valores crudos: similitud sin redondear, `rumbo` `real` sin
`real_legible`) y los `rumbos` de la consulta; salida: `Localizacion` (valores sin redondear salvo `confianza`).
3. **Filtro y orden** (`coincidencias`): los vecinos con `similitud ≥ LOC_SIM_MIN` (iguales al umbral, dentro), de
   mayor a menor similitud; a igualdad, el orden de llegada (foto 0, 1… y, dentro de cada foto, el de
   `buscar_vecinos`: distancia e `imagen_id`). Una misma imagen del dataset que sale para dos fotos cuenta dos veces
   (una por foto). Sin ninguna → `sin_coincidencias`.
4. **Agrupar** (`agrupar`): cada coincidencia entra en el **primer** grupo, por orden de creación, cuyo centroide esté
   a **menos** de `LOC_RADIO_GRUPO_M` (`geo.distancia_m`, estrictamente menor), aunque otro esté más cerca; si
   ninguno, abre uno. **Centroide = media sin ponderar** de la latitud y de la longitud de sus miembros, recalculada al
   añadir cada uno (decisión del maestro, a confirmar por el usuario; ADR-BE-18).
5. **Puntuar** (`Grupo.puntuacion`): suma, por cada foto de la consulta, de la mejor similitud que esa foto aporta al
   grupo. Mejor grupo (`mejor_grupo`) = mayor puntuación; a igualdad, el creado antes.
6. **Posición** (`posicion`): media de latitud y longitud de **todos** los miembros del mejor grupo ponderada por
   `similitud ^ LOC_PESO_EXPONENTE`. Radio = `√(Σ wᵢ·dᵢ² / Σ wᵢ)` con los mismos pesos y `dᵢ` = distancia del miembro a
   la posición; como mínimo `LOC_RADIO_MIN_M` (un grupo de un miembro da exactamente ese mínimo).
7. **Confianza** = `0,5·s + 0,3·c + 0,2·m`, con `s` = (similitud máxima del grupo − `LOC_SIM_MIN`) / (`LOC_SIM_ALTA` −
   `LOC_SIM_MIN`) acotada a [0, 1] (1 si `LOC_SIM_ALTA` ≤ `LOC_SIM_MIN`), `c` = fotos con alguna coincidencia en el
   grupo / fotos de la consulta (cuentan también las que no tienen ningún vecino) y **`m` = (p₁ − p₂) / p₁**, con p₁ y p₂
   las puntuaciones del mejor y del segundo grupo; 1 con un solo grupo (decisión del maestro, a confirmar por el
   usuario; ADR-BE-18). Se **trunca** a 2 decimales (`truncar_confianza`: `floor(round(x·100, 6)) / 100`, en [0, 1]) y
   el **nivel se decide con el valor truncado**: `alta` si ≥ `LOC_NIVEL_ALTA_MIN`, `media` si ≥ `LOC_NIVEL_MEDIA_MIN`,
   si no `baja`.
8. **Corrección de rumbo** (`correccion_rumbo`): por cada foto con rumbo informado y alguna coincidencia **con rumbo** en
   el mejor grupo, la de mayor similitud da `diferencia_angular(rumbo del dataset, rumbo del teléfono)` en (−180, 180]
   (la app la suma a su brújula: teléfono + corrección = dataset). Con ≥ 2 diferencias y desviación estándar circular
   `√(−2·ln R)` ≤ `LOC_DISPERSION_RUMBO_MAX` (R = longitud del resultante medio de las diferencias), la corrección es
   su media circular (`atan2`); si no, `None`. Las fotos que solo coinciden con otros grupos no cuentan.
9. **Contexto** (`contexto`): distancia (`geo.distancia_m`) y rumbo inicial (`geo.rumbo_grados`) desde la posición a
   cada lugar de `leer_todos`, ordenados por distancia (a igualdad, el orden de `leer_todos`: nombre normalizado e id).
   `lugar_cercano` = el primero si está a ≤ `LOC_LUGAR_CERCANO_M`; `referencias` = los siguientes a ≤
   `LOC_REFERENCIAS_M`, **sin repetir el lugar cercano**, como mucho `LOC_REFERENCIAS_MAX`.
10. **Evento** (servicio): una fila de `eventos_localizacion` por cada `200` (§5.7, «filas de BE-3.2»).

Ejemplo (el de `test_ok_con_posicion_confianza_correccion_y_contexto`): 3 fotos; grupo A con 0,92 (foto 0), 0,85 (foto
1) y 0,80 (foto 2) en 7 m; grupo B a 200 m con 0,60 (foto 0); una imagen con 0,40 no pasa el umbral. p₁ = 2,57, p₂ =
0,60, s = 1, c = 3/3, m = 0,7665 → 0,9533 → **0,95**, `alta`. Rumbos del teléfono 90 y 180 frente a 84 y 176 en el
dataset → corrección −5,0.

**Salida** (`respuesta_de`; el cálculo usa los valores sin redondear): `posicion.lat`/`lng` con 6 decimales
(`DECIMALES_COORDENADA`), `radio_m` con 1 (`DECIMALES_RADIO`), `confianza` truncada a 2, `correccion_rumbo_grados` con
1 y en (−180, 180] (−180,0 sale como 180,0), las dos distancias con `dominio.lugares.DECIMALES_DISTANCIA` (1, como
`GET /v1/places`) y `rumbo_grados` con 1 y en [0, 360) (359,96 sale como 0,0). `fotos_con_coincidencia` = fotos con
coincidencia en el **mejor grupo** (`c × fotos_usadas`).

**Nombres internos** (para depurar o extender sin abrir el código):
- `dominio/localizacion.py`: `Parametros` (los `LOC_*` que usa; por defecto, los valores de §5.10), `Coincidencia(foto,
  lat, lng, similitud, rumbo)`, `Grupo` (`miembros`, `lat`/`lng` = centroide, `anadir`, `puntuacion`, `fotos`,
  `similitud_max`, `mejor_por_foto`), `Posicion(lat, lng, radio_m)`, `Localizacion(resultado, posicion, confianza,
  nivel, correccion_rumbo_grados, fotos_usadas, fotos_con_coincidencia, coincidencias, grupos, similitud_max, s, c,
  m)`, `LugarContexto(lugar, distancia_m, rumbo_grados)` (`lugar` es el `LugarRef` tal cual), `DECIMALES_CONFIANZA`
  (2); funciones `coincidencias`, `agrupar`, `mejor_grupo`, `posicion`, `truncar_confianza`, `nivel_de`,
  `diferencia_angular`, `correccion_rumbo`, `localizar(vecinos_por_foto, rumbos, parametros)` y `contexto(posicion,
  lugares, parametros)`. Los vecinos y los lugares se leen por atributos (protocolos `VecinoBuscado`: `lat`, `lng`,
  `similitud`, `rumbo`; `LugarConPosicion`: `lat`, `lng`): no importa `db` ni `servicios`.
- `servicios/localizar.py`: `localizar(…)` → `ResultadoLocalizar(localizacion, lugar_cercano, referencias,
  version_vector, embedding_ms, busqueda_ms, latencia_ms)`; `parametros_de(ajustes)` → `Parametros`; reexporta
  `VersionVectorDistinta`. `vectorizar=` sustituye la llamada a embeddings (si no, `embedding.vectorizar`, buscado en
  el módulo al llamar: las pruebas lo cambian con `monkeypatch.setattr(embedding, "vectorizar", doble)`).
- `esquemas/localizacion.py`: `MetadatosLocalizacion` (`rumbos: list[float en [0, 360) | None]`, `origen:
  Literal["escaneo"]`, `app_version` recortada, vacía → `None`, ≤ `APP_VERSION_MAX` (40), sin NUL; campos de más
  ignorados), `PosicionRespuesta`, `LugarCercano`, `ReferenciaLugar`, `LocalizacionRespuesta` (prohíben campos de
  más); constantes `PARTE_FOTOS`, `PARTE_METADATOS`, `METADATOS_MAX_BYTES`, `DECIMALES_COORDENADA` (6),
  `DECIMALES_RADIO` (1), `DECIMALES_RUMBO` (1), `DECIMALES_EVENTO` (5).
- `api/v1/localizar.py`: `router`, `partes_de_la_peticion`, `fotos_de`, `metadatos_de`, `respuesta_de`; reutiliza
  `MARGEN_MULTIPART` de `admin_diagnostico`.

**Para los lotes siguientes: qué ofrece BE-3.2 al código** (BE-5.1 `/v1/localize/frame` restringe la búsqueda a un
radio y reutiliza el resto; BE-5.2 lee `eventos_localizacion`).

| Elemento | Qué hace |
|---|---|
| `app.dominio.localizacion.localizar(vecinos_por_foto, rumbos, parametros)` → `Localizacion` | Pasos 3–8. Python puro: se prueba sin base (`tests/unit/test_localizacion.py`). Para BE-5.1 (una foto y una posición previa) basta con filtrar los vecinos por distancia a esa posición antes de llamarlo |
| `app.dominio.localizacion.contexto(posicion, lugares, parametros)` → `(LugarContexto \| None, [LugarContexto])` | Paso 9 con cualquier lista de objetos con `lat`/`lng` (en el orden de desempate que se quiera) |
| `app.servicios.localizar.localizar(motor, ajustes, fotos, rumbos, *, origen, app_version, inicio, request_id=None, vectorizar=None)` | Pasos 2–10 (embeddings, búsqueda, algoritmo, contexto y evento en una transacción). `origen` va tal cual a `eventos_localizacion.origen` (`escaneo`; BE-5.1, `frame`) |
| `app.servicios.localizar.parametros_de(ajustes)` | Los `LOC_*` de `Settings` como `Parametros` |
| `app.api.v1.localizar.fotos_de(partes, ajustes)`, `metadatos_de(partes, n_fotos)`, `partes_de_la_peticion(request, ajustes)` | La validación de la petición con sus `ErrorApi` (pasos 2–4) |
| Pruebas con base | `tests/base/test_localizacion_base.py`: `eje(i)` (vector unitario de la foto `i` de la consulta), `con_similitud(i, s)` (vector con similitud coseno `s` con `eje(i)` y 0 con los ejes 0–9; usa ejes libres del 100 al 383), `EmbeddingsFijos` (doble de `vectorizar`: `registrar(fotos)` asigna `eje(i)` a `fotos[i]` por sus bytes; una foto no registrada da un eje sin dataset; `llamadas`, `fallo`, `version`), `indexar_en(ajustes, [(vector, lat, lng, rumbo)])` (un video `validacion-32` con imágenes `procesada` y sus vectores en coordenadas propias: lo que pedía la guía de §4.8), `crear_lugar(ajustes, nombre, lat, lng)`, `eventos(ajustes)` (las filas de `eventos_localizacion`), `norte(m)`/`este(m)`, `localizar(api, fotos, rumbos, metadatos=…, extra=…)` y `_escena` (grupos A y B y tres lugares). Son de un módulo de pruebas: para reutilizarlas, `importlib` (como `test_validate24.py`) |

**Calibración (pendiente de EMB-3.2; C6).** Cuando EMB-3.2 entregue su informe (`recomendado`: `LOC_SIM_MIN`,
`LOC_SIM_ALTA`, `corte_alta`, `corte_media`, embeddings §5.9) y la persona lo revise, en **un** commit: (1) los valores
por defecto de `project/src/app/config.py` (`loc_sim_min`, `loc_sim_alta`, `loc_nivel_alta_min`, `loc_nivel_media_min`);
(2) las filas de §5.10, sin la palabra «Iniciales» y con el informe que las respalda (`tests/contrato/
test_contrato_localizacion.py` compara §5.10 con `Settings`: si solo cambia uno de los dos, falla); (3) una entrada
menor del CHANGELOG con «Lote que la motivó: BE-3.2 (calibración …)» (C6 la busca: versión posterior a 0.12.0, BE-3.2 y
«calibr»); (4) avisar al maestro para que SERVICE_EMBEDDING actualice su copia de los parámetros en
`tools/evaluacion/metricas.py` (embeddings §5.9: `LOC_SIM_MIN_ACTUAL`…), que este documento no toca. Cambiarlos solo en
`dev` con una variable de entorno del mismo nombre es posible (§5.9), pero antes hay que añadirla a infra §5.4.

**Trampas**:
- Un campo de log llamado `nivel` choca con el parámetro `nivel` de `logs.registrar` (y con el campo fijo `nivel` de
  §5.10): el nivel de confianza va como `nivel_confianza` en `localizacion_calculada`.
- pgvector guarda `float32`: la similitud de un vector consigo mismo es 1 ± 1e-7 y la de los vectores de prueba difiere
  del valor pedido en ~1e-7. Las pruebas comparan con margen.
- EMB-3.2 simula los pasos 3–7 con las similitudes de `vecinos`, redondeadas a 6 decimales, y compara la confianza **sin
  truncar** con los cortes; aquí se usan las similitudes crudas y la confianza truncada. Solo cambia el nivel de una
  confianza a menos de 5·10⁻⁷ por debajo de un corte (por el `round(…, 6)` de `truncar_confianza`). Sin documentar en
  EMB: cómo desempata a igual similitud (aquí, orden de llegada).
- El `INSERT` del evento va en la transacción de la búsqueda: si la base cae justo ahí, la localización calculada se
  pierde y la respuesta es `503` (a propósito: no hay respuestas sin su fila).
- `leer_cuerpo` consume `request.stream()` (§4.8): después `request.body()` está vacío.
- `origen` solo admite `escaneo`: `frame` es de BE-5.1, que tiene su propia ruta.
- El índice HNSW es aproximado (R16) y con pocos vectores PostgreSQL puede no usarlo (§4.8); el plan con el dataset
  real sigue a verificar con `EXPLAIN` en `dev`.

Presupuesto de tiempo: embedding ≤ `EMBEDDING_TIMEOUT_S` por fase (5 s; tope total 20 s; en `dev` se esperan ≤ 800 ms
para 5 fotos, embeddings §5.7: EMB-3.1 midió 413 ms de p95 para un lote de 5), búsquedas < 100 ms; objetivo p95 en el
servidor ≤ 1 s con `embedding` encendido (infra §5.10, C3). Sin medir en `dev`.

### 4.11 BE-4.1 — Administración de videos e imágenes, y purga
- Listado, detalle (con URLs prefirmadas GET de 1 h para foto y miniatura), renombrar, re-procesar y edición de
  imágenes (coordenada, lugar, calidad, notas). Corregir la coordenada **no** exige recalcular el vector: el vector
  solo depende de los píxeles.
- **Borrar un video** (ADR-BE-07): en una sola transacción, el video pasa a `eliminado`, se borran los vectores de sus
  imágenes (salen de la búsqueda **de inmediato**) y se escribe la auditoría; después se encola `purgar_video`. El
  `worker` borra los objetos de `dataset/` y `thumbs/` y las filas de `imagenes`, y marca `purgado_en`. El video
  queda como registro histórico. Cualquier admin puede borrar cualquier video; queda quién y cuándo.
- **Borrar una imagen**: mismo patrón (`purgar_imagen`).
- **Reconciliador** en `api`: cada 10 min re-encola las purgas de videos borrados hace más de 10 min sin `purgado_en`
  (cubre un fallo al enviar a SQS justo después del commit).

### 4.12 Lotes diferidos (Fase 5)
- **BE-5.1** `POST /v1/localize/frame`: una foto + posición previa; restringe la búsqueda a un radio alrededor de esa
  posición. Hoy responde `501`.
- **BE-5.2** `POST /v1/eventos` y `GET /v1/admin/stats/uso`: eventos anónimos de uso (rutas iniciadas y completadas,
  destinos buscados, alertas anunciadas) para la vista 7.15. Hoy `501`.
- **BE-5.3** `GET /v1/route`: grafo de caminos y ruta más corta (decisión abierta 2 del frontend). Hoy `501`.

---

## 5. Interfaces (contratos)

> **Única fuente de verdad** de lo que expone el backend. Cambiar algo aquí sube la versión de este documento y exige
> entrada en `CHANGELOG.md`; la app y los demás servicios se adaptan en un lote de su `PLAN.md`.

### 5.1 Convenciones generales

| Tema | Regla |
|---|---|
| URL base | `{api_base_url}/v1` (`api_base_url`: output de infra §5.2). En la app, `ApiConfig.kt` |
| Barra final | Las rutas no llevan barra final y no se redirige: `/v1/health/` responde `404 NO_ENCONTRADO` |
| Formato | JSON UTF-8, nombres en español y `snake_case`. Valores enumerados en minúsculas (`admin`, `alta`, `biblioteca`) |
| Fechas | ISO-8601 en UTC con `Z`: `2026-10-23T15:04:05Z` |
| Coordenadas | WGS84 en grados decimales: `lat` ∈ [−90, 90], `lng` ∈ [−180, 180] |
| **Rumbo** | Grados en **[0, 360)**, 0 = **norte verdadero** (geográfico), sentido horario. `null` si se desconoce (ADR-BE-12) |
| Distancias / radios | Metros (`distancia_m`, `radio_m`) |
| Identificadores | UUID v4 en minúsculas. Los videos tienen además `numero` (entero creciente) |
| Autenticación | `Authorization: Bearer <jwt>` en `/v1/admin/*` y `/v1/collect/*` (§5.2). Los endpoints públicos no la requieren y la ignoran |
| Correlación | Encabezado `X-Request-Id` en todas las respuestas, también en los `500`. Si la petición lo trae con 1 a 128 caracteres `[A-Za-z0-9._:-]`, se reutiliza; si no lo trae o no cumple, se genera un UUID v4 |
| Errores | `{"error": {"codigo": "TEXTO_FIJO", "mensaje": "texto para humanos", "detalle": {…} \| null}}` (códigos en §5.6). El cuerpo solo tiene la clave `error` |
| Paginación | `?pagina=1&por_pagina=24` (máx. 100) → `{"items": […], "total": 123, "pagina": 1, "por_pagina": 24}` |
| Tamaño | Cuerpo ≤ 10 MB y respuesta en ≤ 30 s (límites de API Gateway). Respuestas generadas por API Gateway (429, 413, 503/504 de *timeout*) llegan con cuerpo `{"message": "…"}`, **no** con el formato de error de arriba: la app debe tratarlas por código HTTP |

### 5.2 JWT

- Algoritmo `HS256`, clave `JWT_SECRET` (infra §5.4) usada **como texto**: los bytes UTF-8 de la cadena base64, sin
  decodificarla. Cabecera `{"alg": "HS256", "typ": "JWT"}`. Emisor `iss = "campus-locator-api"`.
- Claims (todos y solo estos): `iss`, `sub`, `rol`, `nombre`, `iat`, `exp`, `jti`. `sub` = id del usuario (UUID en
  texto); `rol` ∈ {`admin`, `user`}; `nombre` = el del usuario al iniciar sesión; `iat` y `exp` en segundos Unix
  (enteros), `exp` = `iat` + `JWT_TTL_MIN` · 60; `jti` = UUID v4 nuevo en cada token. `expira_en` del login es `exp`.
- Sin *refresh token*: al vencer, la app vuelve a Login (la app ya borra la sesión en cada arranque en frío).
- Rechazos, en este orden (el primero que aplica):
  1. Sin encabezado `Authorization`, con otro esquema que `Bearer` o sin token → `401 NO_AUTENTICADO`.
  2. Firma correcta, con todos los claims, y `exp` pasado (sin margen) → `401 TOKEN_EXPIRADO`.
  3. Cualquier otro defecto del token (formato, firma, otro algoritmo, `iss` distinto, falta un claim o tiene un valor
     no válido) → `401 TOKEN_INVALIDO`.
  4. `sub` que no es un usuario, o usuario desactivado (se mira en la base en cada petición) → `401 TOKEN_INVALIDO`.
  5. Rol distinto de `admin` en el token o, ahora, en la base → `403 SIN_PERMISOS`.

  Así, un `user` desactivado recibe `401`, no `403`. Los `401` llevan el encabezado `WWW-Authenticate: Bearer`.
  Sin `JWT_SECRET` en `api`, las rutas protegidas y el login responden `500 ERROR_INTERNO`.
- Consecuencias: reactivar a un usuario (`crear-usuario`, §5.9) devuelve la validez a sus tokens sin vencer; cambiar
  la contraseña no invalida los tokens emitidos (solo desactivar).

### 5.3 Endpoints públicos

| Método y ruta | Uso en la app | Lote que lo entrega |
|---|---|---|
| `GET /v1/health` | Indicador de conexión de Inicio (6.1) | BE-1.1 |
| `GET /v1/health/ready` | Diagnóstico | BE-1.1 |
| `GET /v1/openapi.json`, `GET /v1/docs` | No los usa la app: revisión del contrato (ADR-BE-01). Solo si `APP_ENV` ≠ `prod` | BE-1.1 |
| `POST /v1/auth/login` | Login (7.1) | BE-1.3 |
| `POST /v1/localize` | Escaneo 360° → Resultado (6.2, 6.3) | BE-3.2 |
| `GET /v1/places` | Selección de destino (6.4) | BE-3.1 |
| `GET /v1/alerts` | Caché local de alertas (2.5, 6.3, 6.5) | BE-3.3 — **sin implementar** (hoy `404`, §4.9) |
| `POST /v1/localize/frame` | Corrección visual en navegación (6.5) | BE-5.1 (hasta entonces `501`) |
| `GET /v1/route` | Ruta a un destino (6.5) | BE-5.3 (hasta entonces `501`) |
| `POST /v1/eventos` | Estadísticas de uso (7.15) | BE-5.2 (hasta entonces `501`) |

#### `GET /v1/health`
`200` → `{"estado": "ok", "version": "0.1.0", "commit": "<sha corto>"}`. No consulta la base ni embeddings.
- `version`: versión del backend (`app.__version__`, la misma de `project/pyproject.toml`), no la de este documento.
- `commit`: los 7 primeros caracteres de `APP_COMMIT` (§5.9). Si el valor no es un SHA (p. ej. `local` en
  `docker compose`), se devuelve tal cual.

#### `GET /v1/health/ready`
`200` → `{"estado": "ok", "db": "ok", "embedding": "ok" | "no_disponible"}`. Si la base no responde a `SELECT 1` en
`DB_CONNECT_TIMEOUT_S` (§5.10), o faltan las variables `DB_*`, `503 BASE_NO_DISPONIBLE` con el formato de §5.1 (desde
BE-1.2 ya no existe `db = no_configurada`). Que `embedding` esté apagado (se enciende a mano, infra §3.4) **no** produce
`503`. Las dos comprobaciones se hacen en paralelo.
- `embedding = ok` si `GET {EMBEDDING_URL}/health/ready` responde `200` dentro de `EMBEDDING_CONNECT_TIMEOUT_S`;
  cualquier otro resultado (apagado, el nombre DNS sin registros, error o lentitud) es `no_disponible`.

#### `GET /v1/openapi.json` y `GET /v1/docs`
OpenAPI generado de los esquemas Pydantic (ADR-BE-01) y su vista Swagger, para revisar el contrato. Se publican solo
si `APP_ENV` ≠ `prod` (en `prod` responden `404`). No reemplazan este §5, que sigue siendo la fuente de verdad.

#### `POST /v1/auth/login`
Petición:
```json
{ "identificador": "admin@campus.edu.co", "password": "••••••" }
```
- `identificador`: texto de 1 a 320 caracteres, el correo. Se compara sin espacios alrededor y en minúsculas.
- `password`: texto de 1 a 256 caracteres; no se recorta.
- Ninguno de los dos puede llevar el carácter NUL (`\u0000`) ni un sustituto suelto (p. ej. `\ud800`).
- Otros campos se ignoran.

`200`:
```json
{
  "token": "eyJhbGciOi…",
  "expira_en": "2026-10-24T03:04:05Z",
  "usuario": { "id": "7c1e…", "nombre": "Alejandro Gómez", "correo": "admin@campus.edu.co", "rol": "admin" }
}
```
- `token`: JWT de §5.2; `expira_en` = su `exp`. `usuario.correo` es el guardado (sin espacios y en minúsculas).
- Se entrega también a usuarios `user`: la app decide qué abrir.
- Cada intento en el que se comprueba la contraseña, correcto o no, queda en `auditoria` (`usuario.login`, §5.7). Los
  rechazados antes (`422`, `400`, `503`, `500`) no.

Errores:
- `401 CREDENCIALES_INVALIDAS` si el correo no existe, la contraseña no corresponde o el usuario está inactivo, sin
  distinguir: el cuerpo es siempre
  `{"error": {"codigo": "CREDENCIALES_INVALIDAS", "mensaje": "Correo o contraseña incorrectos.", "detalle": null}}`,
  con los mismos encabezados y el mismo trabajo (§4.4).
- `422 VALIDACION` (campos que faltan, fuera de rango o con un carácter no admitido, `detalle.campos`),
  `400 SOLICITUD_INVALIDA` (JSON roto).
- `503 SERVICIO_OCUPADO` con `Retry-After: 5` (segundos): hay demasiados inicios de sesión esperando su turno, o el
  turno no llegó en `LOGIN_HASH_ESPERA_MAX_S` (§4.4, §5.10). No dice nada de la cuenta; se puede reintentar.
- `503 BASE_NO_DISPONIBLE`; `500 ERROR_INTERNO` si falta `JWT_SECRET`.
- `429` de API Gateway (*throttling* de esta ruta, infra §5.10; cuerpo `{"message": …}`, §5.1). El backend no limita
  intentos por cuenta (R7).

#### `POST /v1/localize`
`multipart/form-data` con:
- `fotos`: 1 a 5 partes `image/jpeg`, cada una ≤ 1,5 MB. Recomendado: lado mayor 1024 px, calidad 85.
- `metadatos`: una parte de texto con JSON:
```json
{ "rumbos": [12.0, 84.5, 156.0, 228.3, 300.1], "origen": "escaneo", "app_version": "0.9.0" }
```
`rumbos[i]` es el rumbo (norte verdadero, [0, 360)) de `fotos[i]`, o `null`. `origen` ∈ {`escaneo`}.

`200`:
```json
{
  "resultado": "ok",
  "posicion": { "lat": 6.200104, "lng": -75.578612, "radio_m": 8.5 },
  "confianza": 0.78,
  "nivel": "alta",
  "correccion_rumbo_grados": -6.0,
  "lugar_cercano": { "id": "3f2a…", "nombre": "Biblioteca Central", "distancia_m": 12.4 },
  "referencias": [
    { "id": "9b0c…", "nombre": "Bloque de los Trillizos", "distancia_m": 35.2, "rumbo_grados": 95.0 }
  ],
  "fotos_usadas": 5,
  "fotos_con_coincidencia": 4,
  "version_vector": "dinov2-vits14/pp-v1",
  "latencia_ms": 640
}
```
- `resultado` ∈ {`ok`, `sin_coincidencias`}. Con `sin_coincidencias`: `posicion`, `nivel`, `correccion_rumbo_grados`
  y `lugar_cercano` son `null`, `confianza` es `0` y `referencias` está vacía.
- `nivel` ∈ {`alta`, `media`, `baja`}. La app decide qué decir; con `baja` debería sugerir repetir la vuelta (6.3).
- `referencias[].rumbo_grados`: rumbo absoluto desde `posicion` hacia el lugar.

En detalle (desde BE-3.2, ARCHITECTURE 0.12.0; el cálculo, en §4.10):
- **Petición.** Público: no pide token e ignora `Authorization` (también uno no válido). Las partes `fotos` cuentan
  **en el orden en que llegan** (aunque haya otras partes entre ellas): ese orden es el de `rumbos` y el de
  `detalle.indice`. Cada una declara `Content-Type: image/jpeg` (se ignoran parámetros como `; charset=…`), no está
  vacía, pesa como mucho `LOC_MAX_BYTES_FOTO` (1 572 864 bytes) y empieza por `FF D8 FF`; el nombre de archivo da
  igual. El cuerpo entero, como mucho `LOC_MAX_FOTOS` × `LOC_MAX_BYTES_FOTO` + 64 KiB. Las partes con otro nombre se
  ignoran.
- **`metadatos`**: exactamente una parte, de como mucho 16 384 bytes, con un objeto JSON en UTF-8 (su `Content-Type` no
  se mira). `rumbos` (obligatorio): lista con un elemento por foto, cada uno un número en [0, 360) o `null`. `origen`
  (obligatorio): `"escaneo"`. `app_version` (opcional): texto de hasta 40 caracteres tras recortar (vacío = `null`), sin
  NUL. Los demás campos se ignoran; `NaN` o infinitos no valen.
- **`posicion`**: `lat`/`lng` con 6 decimales; `radio_m` (m, 1 decimal, mínimo `LOC_RADIO_MIN_M`) es la dispersión de
  las coincidencias del grupo elegido alrededor de la posición.
- **`confianza`** ∈ [0, 1], **truncada** a 2 decimales; `nivel` se decide con ese mismo valor (cortes de §5.10): una
  `confianza` de 0,70 nunca llega con `media` si el corte de `alta` es 0,70.
- **`correccion_rumbo_grados`**: grados en (−180, 180], 1 decimal, o `null` (menos de 2 fotos con rumbo que coincidan
  con el grupo elegido, o diferencias demasiado dispersas: `LOC_DISPERSION_RUMBO_MAX`). La app la **suma** a su
  brújula.
- **`lugar_cercano`**: el lugar más cercano a la posición si está a ≤ `LOC_LUGAR_CERCANO_M` (60 m); si no, `null`.
  **`referencias`**: los siguientes lugares más cercanos a ≤ `LOC_REFERENCIAS_M` (150 m), sin repetir `lugar_cercano`,
  como mucho `LOC_REFERENCIAS_MAX` (3), de más cerca a más lejos (a igualdad, por nombre). `distancia_m` con 1 decimal
  (haversine, como `GET /v1/places`); `rumbo_grados` en [0, 360) con 1 decimal (0 = norte verdadero).
- **`fotos_usadas`** = fotos de la petición; **`fotos_con_coincidencia`** = las que tienen alguna coincidencia en el
  grupo elegido (0 con `sin_coincidencias`). `version_vector` = `EMBEDDING_VERSION_VECTOR`. `latencia_ms`: lo que
  tardó el servidor desde que empezó el endpoint hasta antes de guardar el evento (embeddings y búsqueda incluidos).
- Cada `200` deja una fila anónima en `eventos_localizacion` (§5.7, «filas de BE-3.2»); un error no deja ninguna. Las
  fotos no se guardan en ningún sitio: ni S3, ni disco, ni logs (ADR-BE-06).

Errores, en este orden (el primero que aplica):
1. `400 FOTOS_INVALIDAS` con `detalle = {"indice": i, "motivo": "…"}` (`motivo`, texto corto para humanos): el cuerpo
   pasa del tope o no es `multipart/form-data` (`indice` 0), no hay ninguna parte `fotos` (0), hay más de
   `LOC_MAX_FOTOS` (`indice` = `LOC_MAX_FOTOS`, la primera que sobra) o una foto no vale (su índice).
   `400 SOLICITUD_INVALIDA` si el multipart está mal formado.
2. `422 VALIDACION` (`detalle.campos` con `metadatos` o `metadatos.<campo>`, p. ej. `metadatos.rumbos.1`) si falta la
   parte `metadatos`, está repetida, pesa de más o un campo no vale; `400 SOLICITUD_INVALIDA` si no es JSON en UTF-8;
   `400 FOTOS_INVALIDAS` si `rumbos` no tiene un elemento por foto (`indice` = el menor de los dos largos).
3. `503 EMBEDDING_NO_DISPONIBLE` (apagado, caído, saturado, sin respuesta en `EMBEDDING_TIMEOUT_S` o en 20 s en total,
   respuesta fuera de contrato o con otra `version_vector`), o `400 FOTOS_INVALIDAS` (`indice` de la foto, `motivo`
   «embeddings la rechazó (IMAGEN_INVALIDA)») si embeddings no pudo decodificar una foto.
4. `503 BASE_NO_DISPONIBLE` (sin base, durante la búsqueda o al guardar el evento).

#### `GET /v1/places`
Público: no pide token e ignora `Authorization` (también uno no válido). Parámetros opcionales: `lat`, `lng` (ambos o
ninguno), `categoria`.

`200` → `{"items": [LugarPublico…], "total": 6}`, ordenado por `distancia_m` si se envió posición; si no, por nombre.
Desde BE-3.1 (ARCHITECTURE 0.11.0):
- `lat` ∈ [−90, 90] y `lng` ∈ [−180, 180] (números, sin `NaN`); `categoria`, uno de los valores de abajo (filtra).
- Todos los lugares que cumplen el filtro, sin paginar; `total` = número de `items`.
- «Por nombre» = por el nombre normalizado (sin tildes ni mayúsculas, §5.5 `LugarEntrada`) en orden de puntos de
  código, y a igualdad por `id`. Con posición, por la distancia sin redondear y, a igualdad, por nombre.
- `distancia_m`: distancia de círculo máximo (haversine, radio medio de la Tierra 6 371 008,8 m) desde (`lat`, `lng`)
  hasta el lugar, en metros con 1 decimal.
- Errores: `422 VALIDACION` (`detalle.campos` con `lat`, `lng` o `categoria`; con uno de `lat`/`lng` sin el otro,
  el campo que falta) y `503 BASE_NO_DISPONIBLE`.

`LugarPublico`:
```json
{
  "id": "3f2a…", "nombre": "Biblioteca Central", "categoria": "biblioteca",
  "lat": 6.2009, "lng": -75.5783, "alias": ["biblioteca", "la biblioteca"],
  "descripcion": "Edificio de tres pisos…", "referencias": "Frente al lago…",
  "imagen_url": null, "distancia_m": 85.0
}
```
`categoria` ∈ {`biblioteca`, `cafeteria`, `bano`, `bloque`, `auditorio`, `deportes`, `administracion`, `entrada`}
(los mismos valores que `CategoriaLugar` de la app, en minúsculas). `distancia_m` es `null` sin posición.
`imagen_url` es una URL prefirmada de 1 h o `null`; **hoy siempre `null`**: ningún endpoint sube todavía la foto de un
lugar (§4.9, «Foto del lugar»). `alias` es siempre una lista (vacía si no hay); `descripcion` y `referencias` pueden
ser `null`.

#### `GET /v1/alerts`
> **Sin implementar (BE-3.3).** Las alertas salieron del núcleo (decisión del usuario, 2026-10-25; §4.9): este
> contrato se conserva para BE-3.3, pero hoy la ruta no existe y responde `404 NO_ENCONTRADO`.

Parámetro opcional: `desde` (fecha ISO-8601 tomada de un `generado_en` anterior).

`200`:
```json
{
  "generado_en": "2026-10-23T15:04:05Z",
  "completo": true,
  "alertas": [ Alerta… ],
  "eliminadas": []
}
```
- Sin `desde`, o con un `desde` anterior a 90 días: `completo = true`, `alertas` = todas las activas (también las de
  vigencia pasada o futura), `eliminadas` vacía. La app **reemplaza** su caché.
- Con `desde`: `completo = false`, `alertas` = todas las modificadas después de `desde` (activas o no),
  `eliminadas` = ids borrados después de `desde`. La app actualiza su caché (quita las que llegan con `activa = false`
  y las de `eliminadas`); la vigencia la evalúa al anunciar (abajo).

`Alerta`:
```json
{
  "id": "1d6e…", "lat": 6.2011, "lng": -75.5790,
  "mensaje": "Ten cuidado, hay un lago alrededor de la biblioteca",
  "tipo": "agua", "prioridad": "alta", "radio_m": 15, "activa": true,
  "vigencia_desde": null, "vigencia_hasta": null,
  "actualizado_en": "2026-10-22T20:11:00Z", "version": 3
}
```
`tipo` ∈ {`agua`, `mobiliario`, `escalones`, `obra`, `vehiculos`, `otro`}; `prioridad` ∈ {`normal`, `alta`};
`radio_m` entero en [5, 100]. Vigente = `vigencia_desde` nula o pasada, y `vigencia_hasta` nula o futura. **La vigencia
la evalúa la app** en el momento de anunciar, porque una alerta puede empezar a regir sin que nada cambie en el
servidor.

#### Endpoints reservados
`POST /v1/localize/frame`, `GET /v1/route` y `POST /v1/eventos` responden hoy `501 NO_IMPLEMENTADO`, sin mirar el
cuerpo ni los parámetros. Su contrato se definirá aquí antes de implementarlos (Fase 5). El reservado de
administración, `GET /v1/admin/stats/uso` (§5.5), exige primero el token de admin (`401`/`403`, §5.2) y después
responde `501`. Existen desde BE-1.3 (antes daban `404`). Un `501` es un 5xx para la métrica de API Gateway y su
alarma (infra §5.10: más de 5 en 5 min; sin comprobar en `dev`): `validate13.py` provoca uno por ejecución.

### 5.4 Endpoints de recolección (requieren `admin`)

#### `POST /v1/collect/videos`
```json
{
  "ref_cliente": "rec_0003",
  "nombre": "video_3",
  "iniciado_en": "2026-10-20T14:00:00Z", "finalizado_en": "2026-10-20T14:08:32Z",
  "duracion_s": 512, "distancia_m": 340.5, "pasos": 470,
  "inicio": { "lat": 6.2001, "lng": -75.5786, "rumbo": 90.0 },
  "total_fotos": 120,
  "dispositivo": "Xiaomi 23028RA60L / Android 14", "app_version": "0.9.0"
}
```
- `ref_cliente` es obligatorio: 1–40 caracteres tras recortar los espacios de alrededor (se guarda recortado).
  `nombre` opcional: 1–40 tras recortar; vacío, solo espacios, `null` o ausente → `video_<numero>`.
- El resto es opcional (ausente = `null`): `iniciado_en` y `finalizado_en` (ISO-8601 **con zona**, `Z` o `±hh:mm`; sin
  zona, o fuera de los años 1–9999 al pasarla a UTC, → `422`; si están las dos, `finalizado_en` ≥ `iniciado_en`), `duracion_s` y `pasos` (enteros en
  [0, 2 147 483 647]), `distancia_m` (número en [0, 1 000 000]), `inicio` (`lat` y `lng` obligatorios dentro del
  objeto, WGS84; `rumbo` en [0, 360) o `null`, §5.1), `total_fotos` (entero en [0, 200], por defecto 0; solo informa:
  no limita las fotos), `dispositivo` (≤ 200 tras recortar) y `app_version` (≤ 40 tras recortar).
- Ningún texto puede llevar el carácter NUL ni un sustituto suelto (§4.4). Los campos de más se ignoran (también dentro
  de `inicio`). Los números no admiten `NaN` ni infinitos.
- `201` → `VideoResumen` (§5.5) con `estado = "pendiente"`. Si ya existe un video del mismo admin con ese
  `ref_cliente`: `200` con ese video **tal como está** (idempotente: el cuerpo nuevo no lo cambia). Otro admin con el
  mismo `ref_cliente` crea su propio video.
- Errores: `422 VALIDACION` (`detalle.campos`, p. ej. `inicio.rumbo`), `400 SOLICITUD_INVALIDA` (JSON roto),
  `409 VIDEO_ELIMINADO` si el video de ese admin con ese `ref_cliente` está eliminado (BE-4.1; la app usa otro
  `ref_cliente`), `503 BASE_NO_DISPONIBLE` y los de §5.2.

#### `POST /v1/collect/videos/{video_id}/images`
```json
{
  "imagenes": [
    { "orden": 1, "lat": 6.2001, "lng": -75.5786, "rumbo": 90.0, "capturada_en": "2026-10-20T14:00:05Z", "bytes": 345678 }
  ]
}
```
- 1 a `REC_MAX_LOTE` (50) elementos (más de 50 se rechaza siempre, aunque se suba el parámetro: el esquema tiene ese
  tope fijo); `orden` ∈ [1, `REC_MAX_FOTOS_VIDEO`] (200; nunca más de 200, el `CHECK` de §5.7)
  y sin repetir dentro de la petición; `lat` y `lng` WGS84; `rumbo` en [0, 360) o `null`; `capturada_en` ISO-8601 con
  zona; `bytes` (tamaño del JPEG que se va a subir) en [1, `REC_MAX_BYTES_FOTO`] (4 194 304). Los máximos son
  parámetros de §5.10. Campos de más, ignorados.
- `200` (los elementos en el **mismo orden** que la petición):
```json
{
  "imagenes": [
    {
      "orden": 1, "id": "a91f…", "estado": "pendiente_subida",
      "subida": {
        "metodo": "PUT",
        "url": "https://campus-locator-dev-dataset-648617469176.s3.amazonaws.com/dataset/…?X-Amz-…",
        "encabezados": { "Content-Type": "image/jpeg" },
        "expira_en": "2026-10-23T15:19:05Z"
      }
    }
  ]
}
```
- `id` lo genera el backend la primera vez; la clave del objeto es `dataset/{video_id}/{id}.jpg` (infra §5.5).
  `estado` es el de la foto **después** de la llamada.
- Idempotente por (`video_id`, `orden`): una foto repetida que sigue `pendiente_subida` se comprueba antes con `HEAD`
  en S3 (§4.5): si el objeto ya está, pasa a `subida` (sin tocar sus metadatos) y `subida` es `null`; si no, se
  actualizan sus metadatos y recibe una URL nueva. Si la foto ya estaba `subida`, `procesada` o `error`, no cambia y
  `subida` es `null`. Una foto nueva siempre recibe URL. Registrar una foto devuelve el video a `pendiente` (§5.5).
- `subida.expira_en` = hora de la firma + `PRESIGN_PUT_TTL_S` (900 s), sin fracciones (como mucho 1 s antes del
  vencimiento real).
- La app sube con `PUT` a `url`, enviando **exactamente** los `encabezados` indicados (`Content-Type` forma parte de
  la firma) y el JPEG como cuerpo. S3 responde `200`; repetir el mismo `PUT` sobrescribe el mismo objeto. Una URL
  vencida da `403` de S3 (`<Code>AccessDenied</Code>`, `Request has expired`) → pedir URLs de nuevo. Una URL `PUT` no
  limita el tamaño: lo valida el `worker` (R4).
- Errores, en este orden: `422 VALIDACION` (cuerpo; también `video_id` que no es un UUID), `404 NO_ENCONTRADO` (video
  inexistente), `409 VIDEO_ELIMINADO`, `500 ERROR_INTERNO` (falta `S3_BUCKET_DATASET` en `api`, sin registrar nada; o
  no se pudo firmar, evento `s3_fallido`: las fotos ya quedaron registradas y repetir es seguro), `503
  BASE_NO_DISPONIBLE` y los de §5.2.

#### `POST /v1/collect/videos/{video_id}/complete`
Sin cuerpo (si llega, se ignora). Antes de responder hace `HEAD` en S3 de las fotos que siguen `pendiente_subida` y
pasa a `subida` las que ya existen (§4.5). `200` →
```json
{ "id": "…", "estado": "procesando", "conteo": { "pendiente_subida": 0, "subida": 37, "procesada": 83, "error": 0 } }
```
- Marca la subida como terminada (`videos.subida_completa_en`, la primera vez) y devuelve el `estado` del video
  (§5.5: `pendiente` si queda alguna foto sin subir) y el `conteo` (siempre las cuatro claves).
- Repetirlo es seguro: solo vuelve a consultar en S3 las que sigan pendientes. Un `HEAD` que falla por otra causa que
  «no está» deja esa foto pendiente (evento `s3_fallido`) y la respuesta sigue siendo `200`.
- Errores: `404 NO_ENCONTRADO`, `409 VIDEO_ELIMINADO`, `422 VALIDACION` (`video_id` no es un UUID), `500 ERROR_INTERNO`
  (falta `S3_BUCKET_DATASET`; después de comprobar el video, así un video inexistente da `404` igual), `503
  BASE_NO_DISPONIBLE` y los de §5.2.

### 5.5 Endpoints de administración (requieren `admin`)

**Objetos comunes**

`VideoResumen`:
```json
{
  "id": "…", "numero": 12, "nombre": "Entrada norte", "ref_cliente": "rec_0003", "estado": "procesado",
  "creado_en": "…", "iniciado_en": "…", "finalizado_en": "…",
  "duracion_s": 512, "distancia_m": 340.5, "pasos": 470,
  "inicio": { "lat": 6.2001, "lng": -75.5786, "rumbo": 90.0 },
  "total_fotos": 120,
  "conteo": { "pendiente_subida": 0, "subida": 0, "procesada": 118, "error": 2 },
  "creado_por": { "id": "…", "nombre": "Alejandro Gómez" }
}
```
`estado` del video ∈ {`pendiente` (faltan fotos por subir), `procesando`, `procesado` (todas procesadas),
`con_errores` (ninguna pendiente y al menos una en error), `eliminado`}. Los videos `eliminado` no aparecen en los
listados. El estado se deriva del `conteo` y de si la app ya llamó a `complete` (ADR-BE-14): `pendiente` mientras no
lo haya llamado o quede alguna foto `pendiente_subida`; si no, `procesando` si queda alguna `subida`; si no,
`con_errores` si hay alguna en `error`; si no, `procesado` (también un video sin fotos).
- `inicio` es `null` si la app no lo envió; `iniciado_en`, `finalizado_en`, `duracion_s`, `distancia_m` y `pasos`, `null`
  si no se enviaron. `total_fotos` es el que declaró la app al crear el video (no el número de fotos registradas: ese
  es la suma del `conteo`). `creado_por` es el admin que lo creó. `ref_cliente` es la referencia local con que la app
  lo creó (recortada, §5.4): la app la usa para casar sus grabaciones con los videos del servidor y los validadores para
  reconocer sus datos (`validacion-` en `nombre` **y** `ref_cliente`).
- `conteo` lleva siempre las cuatro claves. Las fechas, en UTC con `Z` y sin fracciones (§5.1).

`ImagenAdmin`:
```json
{
  "id": "…", "video_id": "…", "orden": 7,
  "lat": 6.2003, "lng": -75.5788, "rumbo": 182.0, "capturada_en": "…",
  "estado": "procesada", "error": null, "calidad": "normal",
  "lugar": { "id": "…", "nombre": "Biblioteca Central" },
  "notas": null,
  "url": "https://…", "url_miniatura": "https://…", "url_expira_en": "…"
}
```
`estado` de la imagen ∈ {`pendiente_subida`, `subida`, `procesada`, `error`}; `calidad` ∈ {`alta`, `normal`, `baja`};
`url` y `url_miniatura` son prefirmadas GET de 1 h (`null` mientras no existan). **Hasta BE-4.1, `url`,
`url_miniatura` y `url_expira_en` son siempre `null`** (BE-2.1 entrega el detalle para la barra de progreso; las URLs
GET llegan con BE-4.1, PLAN §2.2). `error` es el motivo cuando `estado = "error"` (si no, `null`); `lugar` es `null`
si la foto no tiene lugar asignado.

`LugarAdmin` = `LugarPublico` sin `distancia_m`, más `creado_en`, `actualizado_en` y `total_fotos`.

`AlertaAdmin` = `Alerta` más `creado_en`, `creado_por` y `actualizado_por` (`{id, nombre}`). **Sin implementar
(BE-3.3).**

Lote que entrega cada grupo: `GET /v1/admin/videos` y `GET /v1/admin/videos/{id}`, BE-2.1; `GET /v1/admin/stats`,
BE-2.3; diagnóstico, BE-2.4; lugares, BE-3.1; alertas, BE-3.3 (**sin implementar**: hoy esas rutas no existen y
responden `404 NO_ENCONTRADO`, §4.9); el resto de videos y todas las de imágenes, BE-4.1.

| Método y ruta | Petición | Respuesta |
|---|---|---|
| `GET /v1/admin/stats` | — | `200` `{"total_fotos": 2842, "total_lugares": 48, "alertas_activas": 3, "ultimo_video": {"numero": 12, "creado_en": "…"} \| null}`. `total_fotos` = imágenes `procesada` de videos no eliminados; `alertas_activas` = alertas `activa` sin borrar (0 mientras BE-3.3 no exista, §4.7) |
| `GET /v1/admin/videos` | `?q=&orden=fecha\|nombre\|fotos&dir=desc\|asc&pagina&por_pagina` | Página de `VideoResumen` (detalle abajo) |
| `GET /v1/admin/videos/{id}` | — | `VideoResumen` + `"fotos": [ImagenAdmin…]` en orden (detalle abajo) |
| `PATCH /v1/admin/videos/{id}` | `{"nombre": "Entrada norte"}` (1–40 tras recortar) | `200` `VideoResumen` |
| `DELETE /v1/admin/videos/{id}` | — | `202` `{"id": "…", "estado": "eliminado", "fotos_retiradas": 120, "purga": "programada"}`. Repetir da la misma respuesta |
| `GET /v1/admin/images` | `?video_id&lugar_id&estado&calidad&q&pagina&por_pagina` | Página de `ImagenAdmin`, por video (más reciente primero) y `orden` |
| `GET /v1/admin/images/{id}` | — | `ImagenAdmin` + `"video": {id, numero, nombre}` + `"vector": {"version_vector", "creado_en"} \| null` |
| `PATCH /v1/admin/images/{id}` | Cualquiera de: `lat`+`lng` (juntos), `lugar_id` (o `null`), `calidad`, `notas` (≤ 500) | `200` `ImagenAdmin` |
| `DELETE /v1/admin/images/{id}` | — | `204`. Retira el vector al instante y encola `purgar_imagen` |
| `POST /v1/admin/images/lote` | `{"accion": "eliminar" \| "reasignar", "ids": [≤ 200], "lugar_id": "…" \| null}` | `200` `{"procesadas": 10, "fallidas": [{"id": "…", "codigo": "NO_ENCONTRADO"}]}` |
| `POST /v1/admin/images/{id}/reprocesar` | — | `202`; la imagen vuelve a `subida` y se encola `reprocesar_imagen` |
| `GET /v1/admin/places` | `?q=&categoria=` | `{"items": [LugarAdmin…], "total": n}` (detalle abajo) |
| `POST /v1/admin/places` | `LugarEntrada` | `201` `LugarAdmin` |
| `PUT /v1/admin/places/{id}` | `LugarEntrada` | `200` `LugarAdmin` |
| `DELETE /v1/admin/places/{id}` | — | `204`; sus imágenes quedan con `lugar = null`. También `204` si no existe |
| `GET /v1/admin/alerts` (BE-3.3, sin implementar) | `?q=&tipo=&prioridad=&activa=` | `{"items": [AlertaAdmin…], "total": n}` (sin borradas) |
| `PUT /v1/admin/alerts/{id}` (BE-3.3, sin implementar) | `AlertaEntrada`; opcional `If-Match: <version>` | `201` si se creó, `200` si se reemplazó; cuerpo `AlertaAdmin` |
| `DELETE /v1/admin/alerts/{id}` (BE-3.3, sin implementar) | — | `204`, también si no existe |
| `POST /v1/admin/alerts/sincronizar` (BE-3.3, sin implementar) | `{"cambios": [{"op": "upsert", "alerta": {"id": "…", …AlertaEntrada}}, {"op": "eliminar", "id": "…"}]}` (≤ 100) | `200` `{"generado_en": "…", "resultados": [{"id": "…", "op": "upsert", "estado": "ok" \| "error", "codigo": null \| "VALIDACION"}]}` |
| `GET /v1/admin/stats/uso` | — | BE-5.2 (hasta entonces `501`) |
| `POST /v1/admin/diagnostico/vecinos` | `multipart/form-data` con una foto; `?k=` | Ver abajo (BE-2.4) |

`LugarEntrada`: `nombre` (2–80), `categoria`, `lat`, `lng`, `alias` (≤ 20 textos de ≤ 60), `descripcion` (≤ 300),
`referencias` (≤ 300). Nombre único sin distinguir mayúsculas ni tildes → `409 NOMBRE_DUPLICADO`. En detalle (desde
BE-3.1, ARCHITECTURE 0.11.0):
- Obligatorios: `nombre`, `categoria` (valores de `LugarPublico`), `lat` y `lng` (WGS84, números sin `NaN`).
- Las longitudes son en caracteres **tras recortar** los espacios de alrededor, y así se guardan. `alias` ausente o
  `null` = `[]`; cada alias, de 1 a 60 tras recortar (uno vacío es `422`). `descripcion` y `referencias` vacías o
  solo espacios = `null`. Ningún texto admite el carácter NUL ni un sustituto suelto (§4.4). Los campos de más se
  ignoran (también `id`, `imagen_url`, `distancia_m`…).
- «Sin distinguir mayúsculas ni tildes»: dos nombres son el mismo si coinciden tras descomponer Unicode (NFKD), quitar
  las marcas (tildes, diéresis, la virgulilla de la ñ), pasar a minúsculas (`casefold`) y reducir los espacios
  internos a uno. «Café  Norte» = «CAFE NORTE» = «cafe norte»; «Baño» = «Bano» (ADR-BE-17). Un nombre que queda vacío
  así es `422`.
- `409 NOMBRE_DUPLICADO` lleva `detalle: null`.

`AlertaEntrada` (**sin implementar, BE-3.3**): `lat`, `lng`, `mensaje` (1–200 tras recortar), `tipo` (por defecto `otro`), `prioridad` (por defecto
`normal`), `radio_m`
(5–100, por defecto 15), `activa` (por defecto `true`), `vigencia_desde`, `vigencia_hasta` (si ambas,
`hasta > desde`). En `sincronizar`, cada cambio es independiente: un error no revierte los demás.

#### `GET /v1/admin/videos` (BE-2.1)
Parámetros, todos opcionales:
- `q`: texto (≤ 100 caracteres, sin NUL) contenido en `nombre`, sin distinguir mayúsculas; `%`, `_` y `\` se buscan
  literalmente. Vacío o solo espacios = sin filtro.
- `orden`: `fecha` (por defecto; `creado_en`), `nombre` (en minúsculas) o `fotos` (fotos registradas, la suma del
  `conteo`); `dir`: `desc` (por defecto) o `asc`. A igualdad, desempata `numero` en la misma dirección.
- `pagina` ≥ 1 (por defecto 1, como mucho 100 000); `por_pagina` en [1, `PAGINA_MAX`] (100; por defecto
  `PAGINA_POR_DEFECTO`, 24).

`200` → `{"items": [VideoResumen…], "total": n, "pagina": 1, "por_pagina": 24}` (§5.1), sin los videos `eliminado`;
`total` cuenta todos los que cumplen `q`. Una página más allá del final da `items` vacío. Errores: `422 VALIDACION`
(parámetro fuera de rango o valor no admitido, `detalle.campos` con `q`, `orden`, `dir`, `pagina` o `por_pagina`),
`503 BASE_NO_DISPONIBLE` y los de §5.2.

#### `GET /v1/admin/videos/{id}` (BE-2.1)
`200` → `VideoResumen` + `"fotos": [ImagenAdmin…]` ordenadas por `orden` (todas, sin paginar: como mucho 200). Su
`conteo` es el mismo que devolvería `complete` en ese momento. Errores: `404 NO_ENCONTRADO` (no existe o está
`eliminado`), `422 VALIDACION` (`id` no es un UUID), `503 BASE_NO_DISPONIBLE` y los de §5.2.

#### Lugares: `/v1/admin/places` (BE-3.1)
`POST /v1/admin/places` (y `PUT /v1/admin/places/{id}`, con el mismo cuerpo) recibe un `LugarEntrada`:
```json
{
  "nombre": "Biblioteca Central", "categoria": "biblioteca", "lat": 6.2009, "lng": -75.5783,
  "alias": ["biblioteca", "la biblioteca"], "descripcion": "Edificio de tres pisos…", "referencias": "Frente al lago…"
}
```
y responde un `LugarAdmin`:
```json
{
  "id": "3f2a…", "nombre": "Biblioteca Central", "categoria": "biblioteca",
  "lat": 6.2009, "lng": -75.5783, "alias": ["biblioteca", "la biblioteca"],
  "descripcion": "Edificio de tres pisos…", "referencias": "Frente al lago…",
  "imagen_url": null, "creado_en": "2026-10-25T20:11:00Z", "actualizado_en": "2026-10-25T20:11:00Z", "total_fotos": 0
}
```
- `POST`: `201`. `creado_en` = `actualizado_en`. Errores, en este orden: los de §5.2, `422 VALIDACION`
  (`detalle.campos`), `409 NOMBRE_DUPLICADO`, `503 BASE_NO_DISPONIBLE`. Un `409` no escribe nada.
- `PUT`: reemplaza **todos** los campos de `LugarEntrada` (lo que no se envía toma su valor por defecto: `alias` = `[]`,
  `descripcion` y `referencias` = `null`); no cambia `id`, `creado_en`, `imagen_url` ni las fotos. `200` con el lugar
  guardado. Si nada cambia, no escribe: `actualizado_en` sigue igual. El mismo nombre con otras mayúsculas, tildes o
  espacios no es un duplicado de sí mismo. Errores, en este orden: los de §5.2, `422 VALIDACION` (cuerpo, o `id` que no
  es un UUID), `404 NO_ENCONTRADO`, `409 NOMBRE_DUPLICADO` (otro lugar tiene ese nombre), `503`.
- `DELETE`: `204` sin cuerpo; las imágenes del lugar quedan con `lugar = null` (y su `actualizado_en` cambia). Un id
  que no existe también da `204` (idempotente). `422` si el id no es un UUID.
- `GET /v1/admin/places`: `q` (opcional, ≤ 100 caracteres, sin NUL) se compara sin tildes, mayúsculas ni espacios de
  más (la regla de `LugarEntrada`) y se busca **contenido** en el nombre; `%`, `_` y `\` son literales; vacío o solo
  espacios = sin filtro. `categoria` filtra. Orden por nombre (como `GET /v1/places`), sin paginar; `total` = número de
  `items`. `total_fotos` = imágenes con ese lugar de videos no eliminados, en cualquier estado (hasta BE-4.1, que
  asigna lugares a las fotos, es 0). Errores: `422` (`q` o `categoria`), `503` y los de §5.2.
- Cada cambio queda en `auditoria` (`lugar.crear`, `lugar.editar`, `lugar.eliminar`, §5.7).

#### `POST /v1/admin/diagnostico/vecinos`
`multipart/form-data` con una sola parte `foto` (`image/jpeg`, ≤ `LOC_MAX_BYTES_FOTO`, las mismas reglas que una foto
de `/v1/localize`). Parámetro `k` en la URL: entero de 1 a 50, por defecto 5. Desde BE-2.4 (ARCHITECTURE 0.10.0):
- La parte `foto` debe declarar `Content-Type: image/jpeg` (se ignoran parámetros como `; charset=…`), no estar vacía,
  pesar como mucho `LOC_MAX_BYTES_FOTO` (1 572 864 bytes) y empezar por `FF D8 FF`. El nombre de archivo da igual. Las
  partes con otro nombre se ignoran.
- La foto se vectoriza con prioridad `baja` (no compite con `/v1/localize`) y no se guarda en ningún sitio: ni S3, ni
  disco, ni logs, ni `eventos_localizacion` (ADR-BE-06, ADR-BE-16).

`200`:
```json
{
  "version_vector": "dinov2-vits14/pp-v1",
  "k": 5,
  "vecinos": [
    { "imagen_id": "…", "video_id": "…", "lat": 6.2003, "lng": -75.5788, "rumbo": 182.0,
      "lugar_id": "3f2a…", "similitud": 0.83 }
  ],
  "latencia_ms": 180
}
```
- `vecinos` va de mayor a menor `similitud` (`1 − distancia coseno`) y tiene `k` elementos, o menos si el índice tiene
  menos vectores (vacío si no hay dataset). Solo incluye imágenes con vector de la versión activa; `lugar_id` puede ser
  `null`.
- No aplica `LOC_SIM_MIN` ni agrupa: es la salida cruda del paso 3 de §4.10 para una foto.
- `version_vector` es `EMBEDDING_VERSION_VECTOR` (§5.10), la misma que devolvió embeddings para la foto; `k`, el
  pedido. `similitud` va con 6 decimales como mucho (a igualdad, el orden lo da `imagen_id`); `rumbo` es el del
  dataset (norte verdadero) o `null`. `latencia_ms`: lo que tardó el servidor desde que empezó el endpoint
  (autenticación y `k` ya validados), embeddings y búsqueda incluidos.

Errores, en este orden (el primero que aplica):
1. Los de §5.2 (`401`, `403 SIN_PERMISOS`) y `503 BASE_NO_DISPONIBLE`.
2. `422 VALIDACION` si `k` no es un entero de 1 a 50 (`detalle.campos` nombra `k`).
3. `400 FOTOS_INVALIDAS` con `detalle = {"indice": 0, "motivo": "…"}`: falta la parte `foto` (o el cuerpo no es
   `multipart/form-data`), tipo, foto vacía, tamaño (también si el cuerpo pasa de `LOC_MAX_BYTES_FOTO` + 64 KiB) o no
   empieza por `FF D8 FF`. Con dos o más partes `foto`, `indice = 1`. `motivo` es un texto corto para humanos (no un
   código). `400 SOLICITUD_INVALIDA` si el multipart está mal formado.
4. `503 EMBEDDING_NO_DISPONIBLE` (apagado, caído, saturado, sin respuesta en `EMBEDDING_TIMEOUT_S` o con otra
   `version_vector`), o `400 FOTOS_INVALIDAS` (`indice` 0, `motivo` «embeddings la rechazó (IMAGEN_INVALIDA)») si
   embeddings no pudo decodificar la foto.
5. `503 BASE_NO_DISPONIBLE` durante la búsqueda.

### 5.6 Códigos de error

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `SOLICITUD_INVALIDA` | Cuerpo mal formado (JSON inválido, multipart roto) |
| 400 | `FOTOS_INVALIDAS` | `/v1/localize` y `/v1/admin/diagnostico/vecinos`: cantidad, tipo o tamaño de fotos, o `rumbos` incoherente; `detalle.indice` señala la foto y `detalle.motivo` dice por qué (en `vecinos` desde BE-2.4, en `localize` desde BE-3.2) |
| 401 | `NO_AUTENTICADO` · `TOKEN_INVALIDO` · `TOKEN_EXPIRADO` | §5.2 (con `WWW-Authenticate: Bearer`) |
| 401 | `CREDENCIALES_INVALIDAS` | Login fallido (cuerpo fijo, §5.3) |
| 403 | `SIN_PERMISOS` | Token válido de un usuario activo sin rol `admin` (§5.2) |
| 404 | `NO_ENCONTRADO` | Recurso inexistente (o video eliminado en rutas de lectura); también una ruta que no existe |
| 405 | `SOLICITUD_INVALIDA` | Método no permitido en una ruta que existe; `detalle.metodos_permitidos` (p. ej. `["GET"]`) y encabezado `Allow` |
| 409 | `NOMBRE_DUPLICADO` · `VIDEO_ELIMINADO` · `CONFLICTO_VERSION` | Lugar repetido al crear o editar (BE-3.1, §5.5; `detalle: null`) · registrar fotos, completar la subida o volver a crear (mismo `ref_cliente`) un video borrado (§5.4) · `If-Match` no coincide (alertas, BE-3.3: sin implementar) |
| 422 | `VALIDACION` | Campos fuera de rango; `detalle.campos` = `[{"campo": "radio_m", "motivo": "…"}]`. En `/v1/localize` (BE-3.2), la parte `metadatos`: `campo` = `metadatos` o `metadatos.<campo>` |
| 500 | `ERROR_INTERNO` | Fallo no previsto (el `X-Request-Id` permite encontrarlo en los logs); también configuración que falta en `api` (`JWT_SECRET`, §5.2; `S3_BUCKET_DATASET` en las rutas de §5.4 que usan S3) |
| 501 | `NO_IMPLEMENTADO` | Endpoints reservados |
| 503 | `EMBEDDING_NO_DISPONIBLE` · `BASE_NO_DISPONIBLE` | Dependencia caída, apagada o lenta. `BASE_NO_DISPONIBLE`, en cualquier endpoint que use la base (desde BE-1.3, §4.4) |
| 503 | `SERVICIO_OCUPADO` | `POST /v1/auth/login` con la cola de verificaciones llena o sin turno a tiempo (§5.3); lleva `Retry-After` |

Si el framework genera otro estado que no está en la tabla, se responde con el mismo formato: `SOLICITUD_INVALIDA`
para un 4xx y `ERROR_INTERNO` para un 5xx. Las respuestas que genera API Gateway no siguen este formato (§5.1).

### 5.7 Esquema de la base de datos

PostgreSQL 17 con la extensión `vector` (pgvector 0.8.x), en el esquema `public`. `python -m app.cli verificar-esquema`
(§5.9) compara la base con **exactamente** lo que dice esta sección: tipos enumerados, tablas, columnas (tipo, nulo y
valor por defecto), restricciones e índices con sus nombres, secuencias y la revisión de Alembic; un objeto de más
(tabla, columna, índice, vista, función, *trigger*, tipo) también es una diferencia. La forma comprobable está en
`project/src/app/db/esquema.py`, con los textos del catálogo de PostgreSQL 17; la migración `0001` y los modelos
(`app/db/modelos.py`) dejan exactamente eso (§4.3).

**Convenciones**
- Columnas `NOT NULL` salvo las marcadas «sí» en *Nulo*: lo que la app puede no informar, lo que se completa en un paso
  posterior (tamaño real, dimensiones, error) y las marcas de borrado. Todas las fechas son `timestamptz`.
- `id uuid` con `DEFAULT gen_random_uuid()` (nativo de PostgreSQL); `creado_en` y `actualizado_en` con `DEFAULT now()`.
  `actualizado_en` lo actualiza la aplicación en cada cambio: no hay *triggers*.
- Los `CHECK` fijan los rangos y longitudes de esta sección y algunos invariantes baratos. Un `CHECK` deja pasar el nulo
  de una columna nula. Los límites que son parámetros de §5.10 (`REC_MAX_BYTES_FOTO`, `LOC_MAX_FOTOS`…) los valida la
  aplicación, para que cambiar el parámetro no exija una migración.
- «WGS84»: `lat` ∈ [−90, 90] y `lng` ∈ [−180, 180] (§5.1). «Rumbo»: [0, 360) (ADR-BE-12). Longitudes en caracteres.
- Nombres de restricciones e índices como los pone PostgreSQL: `<tabla>_pkey`, `<tabla>_<columnas>_key` (únicos),
  `<tabla>_<columna>_fkey`, `<tabla>_<columna>_idx` y `<tabla>_<regla>_check` (`<regla>` = la columna o el nombre que
  indica la tabla).
- Las FK hacia `usuarios` no tienen `ON DELETE`: los usuarios no se borran (§4.4). Las demás llevan la acción indicada.
- Además existe `alembic_version` (de Alembic), con la revisión aplicada: `verificar-esquema` exige la última de las
  migraciones de la imagen.

**Tipos enumerados** (los valores, en este orden)
`rol_usuario` (`user`, `admin`) · `categoria_lugar` (`biblioteca`, `cafeteria`, `bano`, `bloque`, `auditorio`,
`deportes`, `administracion`, `entrada`) · `tipo_alerta` (`agua`, `mobiliario`, `escalones`, `obra`, `vehiculos`,
`otro`) · `prioridad_alerta` (`normal`, `alta`) · `estado_video` (`pendiente`, `procesando`, `procesado`, `con_errores`,
`eliminado`) · `estado_imagen` (`pendiente_subida`, `subida`, `procesada`, `error`) · `calidad_imagen` (`alta`,
`normal`, `baja`). En el código: `app/dominio/enumerados.py`.

**`usuarios`**

| Columna | Tipo | Nulo | Por defecto | Reglas |
|---|---|---|---|---|
| `id` | `uuid` | | `gen_random_uuid()` | PK |
| `correo` | `text` | | | único (`usuarios_correo_key`); guardado sin espacios alrededor y en minúsculas: `correo = lower(btrim(correo))` y no vacío (`usuarios_correo_check`) |
| `nombre` | `text` | | | no vacío ni solo espacios: `btrim(nombre) <> ''` (`usuarios_nombre_check`) |
| `rol` | `rol_usuario` | | `user` | |
| `hash_password` | `text` | | | argon2id (§4.3) |
| `activo` | `boolean` | | `true` | `false` = no puede iniciar sesión y sus tokens no valen (§5.2) |
| `creado_en` | `timestamptz` | | `now()` | |
| `ultimo_acceso_en` | `timestamptz` | sí | | último login correcto (BE-1.3) |

**`lugares`**

| Columna | Tipo | Nulo | Por defecto | Reglas |
|---|---|---|---|---|
| `id` | `uuid` | | `gen_random_uuid()` | PK |
| `nombre` | `text` | | | 2–80 |
| `nombre_normalizado` | `text` | | | único; minúsculas y sin tildes (lo calcula la aplicación) |
| `categoria` | `categoria_lugar` | | | |
| `lat`, `lng` | `double precision` | | | WGS84 |
| `alias` | `text[]` | | `'{}'` | hasta 20 textos de ≤ 60 (lo valida la API, §5.5) |
| `descripcion`, `referencias` | `text` | sí | | ≤ 300 |
| `imagen_key` | `text` | sí | | exactamente `lugares/{id}.jpg` (infra §5.5) |
| `creado_en`, `actualizado_en` | `timestamptz` | | `now()` | |
| `creado_por` | `uuid` | | | FK `usuarios` |

**`alertas`**

| Columna | Tipo | Nulo | Por defecto | Reglas |
|---|---|---|---|---|
| `id` | `uuid` | | `gen_random_uuid()` | PK; lo puede generar la app (ADR-BE-10) |
| `lat`, `lng` | `double precision` | | | WGS84 |
| `mensaje` | `text` | | | 1–200 |
| `tipo` | `tipo_alerta` | | `otro` | |
| `prioridad` | `prioridad_alerta` | | `normal` | |
| `radio_m` | `smallint` | | `15` | 5–100 |
| `activa` | `boolean` | | `true` | |
| `vigencia_desde`, `vigencia_hasta` | `timestamptz` | sí | | si están las dos, `hasta > desde` (`alertas_vigencia_check`) |
| `version` | `integer` | | `1` | ≥ 1; +1 en cada cambio |
| `creado_en`, `actualizado_en` | `timestamptz` | | `now()` | índice `alertas_actualizado_en_idx` |
| `creado_por`, `actualizado_por` | `uuid` | | | FK `usuarios` |
| `eliminada_en` | `timestamptz` | sí | | *tombstone*: borrar fija `eliminada_en` y `actualizado_en`, así `GET /v1/alerts?desde=` usa el mismo índice; las borradas hace más de 90 días se eliminan físicamente (BE-3.3: hasta entonces nadie escribe en `alertas`) |

**`videos`**

| Columna | Tipo | Nulo | Por defecto | Reglas |
|---|---|---|---|---|
| `id` | `uuid` | | `gen_random_uuid()` | PK |
| `numero` | `integer` | | `nextval('videos_numero_seq')` | único (`videos_numero_key`); la secuencia (`integer`) pertenece a la columna |
| `nombre` | `text` | | | 1–40 |
| `ref_cliente` | `text` | | | 1–40; único junto con `creado_por` (`videos_creado_por_ref_cliente_key`) |
| `estado` | `estado_video` | | `pendiente` | |
| `iniciado_en`, `finalizado_en` | `timestamptz` | sí | | informados por la app |
| `duracion_s`, `pasos` | `integer` | sí | | ≥ 0 |
| `distancia_m` | `real` | sí | | ≥ 0 |
| `inicio_lat`, `inicio_lng` | `double precision` | sí | | WGS84; las dos o ninguna (`videos_inicio_check`) |
| `inicio_rumbo` | `real` | sí | | rumbo |
| `total_fotos_declaradas` | `smallint` | | `0` | 0–200 |
| `dispositivo`, `app_version` | `text` | sí | | |
| `subida_completa_en` | `timestamptz` | sí | | la primera llamada a `complete` (§5.4); entra en el estado del video (ADR-BE-14) |
| `creado_por` | `uuid` | | | FK `usuarios` |
| `creado_en`, `actualizado_en` | `timestamptz` | | `now()` | |
| `eliminado_en`, `purgado_en` | `timestamptz` | sí | | borrado lógico y purga (ADR-BE-07): `estado = 'eliminado'` si y solo si `eliminado_en` no es nulo, y `eliminado_en` y `eliminado_por` van juntos (`videos_eliminado_check`); `purgado_en` solo con `eliminado_en` (`videos_purgado_en_check`) |
| `eliminado_por` | `uuid` | sí | | FK `usuarios` |

**`imagenes`**

| Columna | Tipo | Nulo | Por defecto | Reglas |
|---|---|---|---|---|
| `id` | `uuid` | | `gen_random_uuid()` | PK |
| `video_id` | `uuid` | | | FK `videos` (`ON DELETE CASCADE`) |
| `orden` | `smallint` | | | 1–200; único junto con `video_id` (`imagenes_video_id_orden_key`) |
| `s3_key` | `text` | | | único; exactamente `dataset/{video_id}/{id}.jpg` (infra §5.5; `imagenes_s3_key_check`) |
| `lat`, `lng` | `double precision` | | | WGS84 |
| `rumbo` | `real` | sí | | rumbo |
| `capturada_en` | `timestamptz` | | | informada por la app |
| `bytes_declarados` | `integer` | | | > 0 (el máximo, `REC_MAX_BYTES_FOTO`, lo valida la API) |
| `bytes` | `integer` | sí | | ≥ 0; tamaño real en S3 (del `HEAD` de la recolección o del `worker`, §4.5) |
| `etag` | `text` | sí | | sin comillas, como el `eTag` de los eventos de S3 (§5.8) |
| `ancho`, `alto` | `smallint` | sí | | > 0; tras corregir EXIF |
| `estado` | `estado_imagen` | | `pendiente_subida` | índice `imagenes_estado_idx` |
| `error` | `text` | sí | | motivo legible; no nulo si y solo si `estado = 'error'` (`imagenes_error_check`) |
| `intentos` | `smallint` | | `0` | ≥ 0; veces que el `worker` terminó la foto (`procesada` o `error`), §4.6 |
| `calidad` | `calidad_imagen` | | `normal` | |
| `lugar_id` | `uuid` | sí | | FK `lugares` (`ON DELETE SET NULL`); índice `imagenes_lugar_id_idx` |
| `notas` | `text` | sí | | ≤ 500 |
| `creado_en`, `actualizado_en` | `timestamptz` | | `now()` | |

**`embeddings`**

| Columna | Tipo | Nulo | Por defecto | Reglas |
|---|---|---|---|---|
| `imagen_id` | `uuid` | | | FK `imagenes` (`ON DELETE CASCADE`) |
| `version_vector` | `text` | | | p. ej. `dinov2-vits14/pp-v1` (definido por embeddings, §5.3 de su documento) |
| `vector` | `vector(384)` | | | normalizado L2 (lo garantiza embeddings; sin `CHECK`) |
| `creado_en` | `timestamptz` | | `now()` | |
| PK | (`imagen_id`, `version_vector`) | | | |

Índice por versión activa (parcial):
```sql
CREATE INDEX embeddings_hnsw_dinov2_vits14_pp_v1 ON embeddings
  USING hnsw (vector vector_cosine_ops) WITH (m = 16, ef_construction = 64)
  WHERE version_vector = 'dinov2-vits14/pp-v1';
```
Toda consulta vectorial filtra por la misma `version_vector` para usar el índice. El valor se escribe **como literal**
en la consulta (sale de `EMBEDDING_VERSION_VECTOR`, nunca de la petición): con un parámetro, las sentencias preparadas
de `asyncpg` pueden pasar a un plan genérico que ignora el índice parcial. Una versión nueva del modelo llega con su
propia migración (índice parcial nuevo) y se activa cambiando `EMBEDDING_VERSION_VECTOR` (§5.10).

**`eventos_localizacion`** (anónimo, retención 180 días; sin IP, sin identificador de dispositivo, sin fotos)

| Columna | Tipo | Nulo | Por defecto | Reglas |
|---|---|---|---|---|
| `id` | `bigint` | | `nextval('eventos_localizacion_id_seq')` | PK (`bigserial`) |
| `creado_en` | `timestamptz` | | `now()` | índice `eventos_localizacion_creado_en_idx` (retención y estadísticas) |
| `origen` | `text` | | | `escaneo` o `frame` (`CHECK`, no tipo enumerado) |
| `resultado` | `text` | | | `ok`, `sin_coincidencias` o `error` |
| `nivel` | `text` | sí | | `alta`, `media` o `baja` |
| `confianza` | `real` | sí | | [0, 1] |
| `lat`, `lng` | `double precision` | sí | | WGS84, redondeadas a 5 decimales (~1 m) por la aplicación; las dos o ninguna (`eventos_localizacion_posicion_check`) |
| `fotos_usadas`, `fotos_con_coincidencia` | `smallint` | | | 0 ≤ `fotos_con_coincidencia` ≤ `fotos_usadas` (`eventos_localizacion_fotos_check`) |
| `latencia_ms` | `integer` | | | ≥ 0 |
| `version_vector` | `text` | | | |
| `app_version` | `text` | sí | | |

**`eventos_localizacion`: filas de BE-3.2** (una por cada `POST /v1/localize` con `200`, en la misma transacción que la
búsqueda; un error no deja fila; §4.10):

| Columna | Valor |
|---|---|
| `origen` | `escaneo` (el de `metadatos`; `frame` queda para BE-5.1) |
| `resultado` | `ok` o `sin_coincidencias` (`error` no lo escribe BE-3.2) |
| `nivel`, `confianza` | los de la respuesta (`confianza` ya truncada; `0` y `nivel` nulo con `sin_coincidencias`) |
| `lat`, `lng` | la posición de la respuesta redondeada a 5 decimales; nulas con `sin_coincidencias` |
| `fotos_usadas`, `fotos_con_coincidencia`, `latencia_ms`, `version_vector` | los de la respuesta |
| `app_version` | la de `metadatos` (recortada; nula si no viene o queda vacía). Los validadores envían `validacion-32` |

**`auditoria`**

| Columna | Tipo | Nulo | Por defecto | Reglas |
|---|---|---|---|---|
| `id` | `bigint` | | `nextval('auditoria_id_seq')` | PK (`bigserial`) |
| `creado_en` | `timestamptz` | | `now()` | |
| `actor_id` | `uuid` | sí | | FK `usuarios`; nulo en logins fallidos y en los cambios hechos por la CLI |
| `accion` | `text` | | | `usuario.login`, `usuario.crear`, `usuario.actualizar`, `usuario.desactivar`, `video.renombrar`, `video.eliminar`, `imagen.editar`, `imagen.eliminar`, `imagen.reprocesar`, `lugar.crear`, `lugar.editar`, `lugar.eliminar`, `alerta.upsert`, `alerta.eliminar`. Sin `CHECK`: el catálogo crece con los lotes |
| `entidad` | `text` | | | tipo de la entidad (`usuario`, `video`, `imagen`, `lugar`, `alerta`) |
| `entidad_id` | `text` | sí | | |
| `detalle` | `jsonb` | | `'{}'` | un objeto JSON (`auditoria_detalle_check`), sin secretos |

**`auditoria`: filas de BE-1.3** (`entidad = 'usuario'`; nunca la contraseña, su hash, el token ni el identificador
escrito):

| `accion` | `actor_id` | `entidad_id` | `detalle` |
|---|---|---|---|
| `usuario.login` (cada intento en el que se comprobó la contraseña; no los rechazados antes, p. ej. `503 SERVICIO_OCUPADO`) | el usuario si entró; si no, nulo | el usuario si el correo existe; si no, nulo | `{"resultado": "exito"}` o `{"resultado": "fallo", "motivo": "correo_desconocido" \| "password_incorrecta" \| "usuario_inactivo"}` |
| `usuario.crear`, `usuario.actualizar` (`crear-usuario`) | nulo | el usuario | `{"origen": "cli", "rol": …, "reactivado": true \| false}`, y `"rol_anterior"` al actualizar |
| `usuario.desactivar` (`desactivar-usuario`) | nulo | el usuario | `{"origen": "cli", "ya_estaba_inactivo": true \| false}` |

**`auditoria`: filas de BE-3.1** (`entidad = 'lugar'`, `actor_id` = el admin del token, `entidad_id` = el id del
lugar; en la misma transacción que el cambio):

| `accion` | Cuándo | `detalle` |
|---|---|---|
| `lugar.crear` | `POST /v1/admin/places` con `201` | `{"nombre": "<nombre guardado>", "categoria": "<categoria>"}` |
| `lugar.editar` | `PUT /v1/admin/places/{id}` que cambió algo (sin cambios no hay fila) | `{"cambios": [<campos que cambiaron, en el orden nombre, categoria, lat, lng, alias, descripcion, referencias>]}` |
| `lugar.eliminar` | `DELETE /v1/admin/places/{id}` de un lugar que existía (un id desconocido no deja fila) | `{"nombre": "<nombre>", "fotos_sin_lugar": <imágenes que quedaron sin lugar>}` |

### 5.8 Mensajes de las colas

Entrega «al menos una vez»: todo consumidor es idempotente. Colas, visibilidad y DLQ: infra §5.6.

**Cola `ingesta`** — dos tipos de mensaje:

1. **Evento de S3** (lo genera S3; formato estándar de notificaciones de S3, versión 2.x):
```json
{ "Records": [ { "eventName": "ObjectCreated:Put",
  "s3": { "bucket": { "name": "campus-locator-dev-dataset-648617469176" },
          "object": { "key": "dataset/9c1d…/a91f….jpg", "size": 345678, "eTag": "…" } } } ] }
```
   - La clave viene codificada como URL: decodificar (`unquote_plus`) antes de usarla.
   - Un mensaje puede traer varios `Records`; se procesan uno a uno.
   - Al configurar la notificación S3 envía `{"Service": "Amazon S3", "Event": "s3:TestEvent", …}`: se borra sin hacer
     nada.
2. **Re-procesado** (lo envía `api`):
```json
{ "tipo": "reprocesar_imagen", "version": 1, "imagen_id": "a91f…",
  "solicitado_por": "7c1e…", "solicitado_en": "2026-10-23T15:04:05Z" }
```

El `worker` distingue por la presencia de `Records` o de `tipo`. Un mensaje que no encaja en ninguno se registra y se
borra (`mensaje_no_reconocido`). Desde BE-2.2 (§4.6): de un evento de S3 solo cuentan los `Record` con `eventName`
`ObjectCreated:*` y `s3.object.key`; `eTag` y `size` son opcionales (sin ellos, no hay regla de duplicado ni `bytes`
del evento); una clave que no es `dataset/{video_id}/{imagen_id}.jpg` (UUID en minúsculas) se descarta.
`reprocesar_imagen` solo exige `tipo`, `version` = 1 (entero) e `imagen_id` (UUID); `solicitado_por` y
`solicitado_en` son informativos. Un evento repetido de una foto ya `procesada` o en `error` con el mismo ETag se borra
sin hacer nada.

**Cola `purga`** (la llena `api`):
```json
{ "tipo": "purgar_video", "version": 1, "video_id": "9c1d…",
  "solicitado_por": "7c1e…", "solicitado_en": "2026-10-23T15:04:05Z" }
```
```json
{ "tipo": "purgar_imagen", "version": 1, "imagen_id": "a91f…", "video_id": "9c1d…",
  "s3_keys": ["dataset/9c1d…/a91f….jpg", "thumbs/9c1d…/a91f….jpg"],
  "solicitado_por": "7c1e…", "solicitado_en": "2026-10-23T15:04:05Z" }
```
- `purgar_video`: borra todos los objetos bajo `dataset/{video_id}/` y `thumbs/{video_id}/`, borra las filas de
  `imagenes` del video y fija `videos.purgado_en`. Repetirlo no hace daño.
- `purgar_imagen`: borra los objetos listados (la fila ya se borró en la petición).
- Un cambio incompatible en un mensaje sube `version`; el `worker` acepta la versión actual y la anterior durante un
  despliegue.

### 5.9 Procesos de la imagen

Una sola imagen (`campus-locator/backend`, `project/Dockerfile`, Python 3.12, usuario sin privilegios). Contiene solo
`src/app/` (copiado como paquete `app`, en `/srv/app`) y `migrations/` (en `/srv/migrations`, desde BE-1.2); `src/ops/`
y `tests/` quedan fuera. El contenedor se llama `app` (infra §5.1).

| Imagen | Valor |
|---|---|
| Base | `python:3.12-slim-bookworm`; dependencias instaladas con `uv sync --frozen --no-dev` desde `uv.lock` en `/opt/venv` |
| Código | `/srv/app` (`PYTHONPATH=/srv`, directorio de trabajo `/srv`) |
| Usuario | `app` (uid y gid 10001), sin *shell* ni directorio personal |
| Variables fijadas en el `Dockerfile` | `APP_COMMIT` ← `--build-arg GIT_COMMIT` (SHA completo del commit; `backend.yml` pasa `${GITHUB_SHA}`; por defecto `desconocido`), `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1` |

| Proceso | Comando | Puerto | Salud |
|---|---|---|---|
| `api` (por defecto, `CMD` de la imagen) | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-server-header` | 8000 | `GET /v1/health` |
| `worker` | `python -m app.worker` | — | proceso vivo; registra un latido cada 60 s. Desde BE-2.2 consume `ingesta` (§4.6); sin `SQS_URL_INGESTA`, `S3_BUCKET_DATASET`, `EMBEDDING_URL` o `DB_*`, solo latidos (`modo = sin_consumo`) y `configuracion_incompleta`, sin salir |
| `migrate` | `python -m app.cli migrar` (§4.3) | — | código de salida 0 = migrado y admin inicial en orden; 1 = falló una migración o el admin inicial, o esperó más de 5 min a otro `migrar`; 2 y 3, abajo |
| Verificación de esquema (tarea suelta con la definición de `migrate`) | `python -m app.cli verificar-esquema` (compara la base con §5.7 en una transacción de solo lectura) | — | código de salida 0 = coincide; 1 = difiere (un evento `esquema_diferencia` por diferencia); 2 = no se pudo verificar (base no disponible o error al leer el catálogo); 3, abajo |
| Usuarios (tarea suelta con la definición de `migrate`; BE-1.3) | `python -m app.cli crear-usuario --correo X --nombre Y [--rol admin\|user]`. Si el correo existe, actualiza nombre, contraseña y, si se pasa `--rol`, rol (sin `--rol` conserva el suyo), y lo reactiva; un usuario nuevo sin `--rol` es `user`. Resultado: evento `usuario_guardado` (`resultado` = `creado` \| `actualizado`) | — | 0 = hecho; 1 = dejaría sin ningún admin activo (`usuario_rechazado`) u otro error de la base (`comando_fallido`); 2 y 3, abajo |
| | `python -m app.cli desactivar-usuario --correo X`. Resultado: evento `usuario_desactivado` | — | 0 = desactivado (también si ya lo estaba); 1 = no existe (`usuario_no_encontrado`), dejaría sin ningún admin activo (`usuario_rechazado`) u otro error (`comando_fallido`); 2 y 3, abajo |
| Limpieza de pruebas (tarea suelta con la definición de `worker`; BE-2.1) | `python -m app.cli limpiar-validacion [--video ID …] [--simular]` (§4.5): sin `--video`, todos los videos cuyo `nombre` **y** `ref_cliente` empiezan por `validacion-`; con `--video` (uno o varios UUID, `--video A B` o `--video A --video B`), solo esos, y se niega entera (nada se borra) si alguno no existe o no lleva el prefijo. Borra filas (`videos` y en cascada `imagenes` y `embeddings`) y objetos de `dataset/{id}/` y `thumbs/{id}/`. Resultado: evento `limpieza_validacion` (`videos`, `objetos`, `video_ids`) y, después, la línea de texto `LIMPIEZA {"videos": n, "objetos": m}` por la salida estándar (`n` = videos borrados, `m` = objetos borrados). Si S3 falla en la segunda pasada (tras borrar las filas), antes registra `limpieza_s3_incompleta` (`WARNING`, `prefijos`, `motivo`) y sale igual con 0: pueden quedar objetos huérfanos que se borran a mano (§4.5). Con `--simular`: las mismas comprobaciones y la misma negativa, sin borrar nada; cuenta los objetos (`list-objects-v2`) y su resultado es el evento `limpieza_simulada` (`videos`, `objetos`, `video_ids`) y la línea `SIMULACION {"videos": n, "objetos": m}` (lo que borraría) | — | 0 = hecho (también con 0 videos; con `--simular`, «lo borraría»); 1 = negativa (`limpieza_rechazada`: `inexistentes`, `sin_prefijo`; también con `--simular`), error de S3 (`s3_fallido`, operación `borrar` —las filas quedan— o `listar` con `--simular`) u otro error (`comando_fallido`); 2 y 3, abajo (3 también si falta `S3_BUCKET_DATASET`, o un `--video` que no es un UUID) |

**`crear-usuario` y `desactivar-usuario` en detalle** (BE-1.3, §4.4):
- `--correo` se normaliza (sin espacios alrededor y en minúsculas) y tiene que tener la forma `algo@algo` (sin
  espacios ni una segunda `@`); `--nombre` se recorta y no puede quedar vacío; ninguno admite el carácter NUL ni un
  sustituto suelto. Si no, código 3 por stderr.
- La contraseña de `crear-usuario` nunca va como argumento: se lee de `CREAR_USUARIO_PASSWORD` (si está y no está
  vacía) o, si no y hay terminal, se pide dos veces (tienen que coincidir). Debe tener de 8 a 256 caracteres. Sin
  variable ni terminal, con las dos escritas distintas o fuera de rango: código 3 con `configuracion_incompleta`
  (`faltan` o `invalidas`, sin el valor). Se comprueba antes que `DB_*`.
- Ninguno de los dos deja la base sin un admin activo: quitar el rol (`crear-usuario --rol user`) o desactivar a un
  usuario con rol `admin` exige que quede otro admin **activo**; si no, código 1 con `usuario_rechazado` y nada
  cambia. Los dos toman el bloqueo consultivo de transacción `7242031220260002` (distinto del de `migrar`): dos
  ejecuciones a la vez van en fila, y dos `crear-usuario` del mismo correo nuevo dan `creado` y `actualizado`
  (§4.4; probado).
- Cada cambio deja su fila en `auditoria` (§5.7). Solo necesitan `DB_*`, no `ADMIN_INICIAL_*`.
- En `dev`: `aws ecs run-task` con la última revisión de `campus-locator-dev-migrate`, red `subredes_tareas` +
  `sg_migrate` con IP pública, y `containerOverrides` con `command` y, para la contraseña, `environment`
  (`CREAR_USUARIO_PASSWORD`). Ese valor queda visible en `describe-tasks` para quien tenga acceso a la cuenta: para el
  admin real, mejor una contraseña temporal que se cambia después con otra ejecución. En `local`:
  `docker compose run --rm -T -e CREAR_USUARIO_PASSWORD api python -m app.cli crear-usuario …` con la variable
  exportada (así lo hace `validate13.py`), o sin `-T` ni `-e` para que la pida por la terminal (sin comprobar).

**`limpiar-validacion` en `dev`** (BE-2.1): `aws ecs run-task` con la última revisión de `campus-locator-dev-worker`
(tiene `DB_*`, `S3_BUCKET_DATASET` y el rol `tarea-worker`), la misma red que `migrate` (`subredes_tareas` +
`sg_migrate`, IP pública) y `containerOverrides` con `command`. Su log va a `/campus-locator/dev/worker`, stream
`worker/app/<id de la tarea>`. Así lo lanza `EntornoBackend.cli(…, familia=FAMILIA_WORKER)` (§5.11). En `local` no hay
S3: sin `S3_BUCKET_DATASET` termina con 3.

**Códigos de salida de `python -m app.cli`**, comunes a todos los comandos. Sus logs son líneas JSON de §5.10 con
`proceso = migrate` (también `limpiar-validacion`, aunque corra con la definición de `worker`); todos informan su
resultado solo como eventos de log (desde BE-1.3, también `crear-usuario`), salvo `limpiar-validacion`, que además
imprime la línea `LIMPIEZA {…}` (texto, no JSON de §5.10). La otra excepción es un error en los argumentos: argparse
escribe el uso y el error en texto por stderr, sin evento.

| Código | Significado |
|---|---|
| 0 | Hecho (en `verificar-esquema`, la base coincide) |
| 1 | Resultado negativo: el que diga cada comando arriba (difiere, falló, no existe) |
| 2 | No se pudo trabajar con la base: no se pudo abrir la conexión (red, DNS, TLS, credenciales, permiso `CONNECT`, base inexistente, tiempo agotado) o se perdió después (evento `base_no_disponible`). En `verificar-esquema`, también un error que impide comparar sin ser de conexión: al leer el catálogo, al cargar las migraciones o al esperar más de 5 min a un `migrar` en curso (evento `verificacion_fallida`) |
| 3 | Uso o configuración: argumentos (argparse daría 2; aquí es 3; escribe el uso y el error en texto por stderr, sin evento), una variable con un valor no válido (p. ej. `DB_PORT=abc`), `DB_*` que faltan, `ADMIN_INICIAL_*` cuando hay que crear el admin, la contraseña de `crear-usuario` o `S3_BUCKET_DATASET` en `limpiar-validacion` (evento `configuracion_incompleta`) |

Variables que lee: las de infra §5.4 para `api`, `worker` y `migrate`, `APP_COMMIT`, que fija la imagen, y
`CREAR_USUARIO_PASSWORD` (solo `crear-usuario`). `api` necesita `JWT_SECRET` (infra §5.4) para el login y las rutas
protegidas: sin ella arranca, pero esas rutas responden `500` (§5.2); con menos de 32 bytes, PyJWT avisa
(`InsecureKeyLengthWarning`, en texto por stderr). Desde BE-2.1, `api` usa `S3_BUCKET_DATASET` y `AWS_REGION` para el
cliente de S3 (sin el bucket arranca, pero `images` y `complete` responden `500`, §5.4) y `limpiar-validacion` los
mismos (sin el bucket, código 3). Las credenciales de AWS son las del rol de tarea (infra §5.8): no hay variables de
llaves. boto3 está en la imagen desde BE-2.1 (dependencias de `pyproject.toml`; antes solo en el grupo `ops`). Desde
BE-2.2, `worker` usa `SQS_URL_INGESTA`, `S3_BUCKET_DATASET`, `EMBEDDING_URL`, `AWS_REGION` y `DB_*` (§4.6), y la imagen
lleva Pillow (12.3; comprobado: `import PIL` en la imagen construida en local). Ningún otro valor es obligatorio; los parámetros de §5.10 tienen valor por defecto en `config.py` y pueden sobrescribirse con
una variable del mismo nombre (si se vuelve necesario, se añade antes a infra §5.4). Ninguna variable es obligatoria
para arrancar: cada lote exige las suyas al usarlas (por ejemplo, `DB_*` desde BE-1.2). De las `DB_*` de conexión
(infra §5.4), tienen valor por defecto `DB_PORT` (5432) y `DB_SSLMODE` (`require`). `DB_SSLMODE` admite `disable`, `allow`, `prefer`, `require`,
`verify-ca` y `verify-full` (sin distinguir mayúsculas ni espacios alrededor); con otro valor, la CLI termina con 3 y
`api` no crea el motor (`/v1/health/ready` responde `503 BASE_NO_DISPONIBLE`). Una variable de `config.py` con un valor
que no se puede leer (p. ej. `DB_PORT=abc`) hace que la CLI termine con 3 y que `api` no arranque.

### 5.10 Parámetros operativos

| Parámetro (`config.py`) | Valor inicial | Notas |
|---|---|---|
| `JWT_TTL_MIN` | 720 (12 h) | `exp − iat` del token (§5.2) |
| `LOGIN_HASH_CONCURRENTES` | 2 | Verificaciones argon2id a la vez en `api` (cada una usa 64 MiB; la tarea tiene 0,5 GB). Las demás esperan su turno sin conexión a la base (§4.4) |
| `LOGIN_HASH_COLA_MAX` | 8 | Logins que pueden esperar turno además de los que verifican; el siguiente recibe `503 SERVICIO_OCUPADO` sin tocar la base |
| `LOGIN_HASH_ESPERA_MAX_S` | 10 | Espera máxima por el turno; después, `503 SERVICIO_OCUPADO`. Muy por debajo de los 30 s de API Gateway |
| `EMBEDDING_VERSION_VECTOR` | `dinov2-vits14/pp-v1` | Debe coincidir con `GET /v1/info` de embeddings. Se comprueba en la primera llamada tras cada arranque del servicio y cada 10 min (no al arrancar `api`, porque embeddings puede estar apagado); si no coincide, no se usa el servicio y `/v1/health/ready` lo informa (esa regla aún no tiene código). Hoy se compara con la `version_vector` de cada respuesta de `/v1/embed`: el `worker` (BE-2.2) no guarda el vector y `vecinos` (BE-2.4) responde `503 EMBEDDING_NO_DISPONIBLE` sin buscar. Es también el literal del `WHERE` de la búsqueda (§4.8, §5.7) |
| `EMBEDDING_TIMEOUT_S` / `EMBEDDING_CONNECT_TIMEOUT_S` | 5 / 3 | Un reintento solo si la conexión fue rechazada. 5 s deja margen sobre los ≤ 800 ms esperados para 5 fotos en `dev` (embeddings §5.7); si hace falta, se sube con la variable del mismo nombre |
| `LOC_MAX_FOTOS` / `LOC_MAX_BYTES_FOTO` | 5 / 1 572 864 (1,5 MB) | Fotos por localización y tope de cada foto (`localize` desde BE-3.2; `LOC_MAX_BYTES_FOTO` también `vecinos`, desde BE-2.4). Tope del cuerpo: `vecinos`, una foto + 64 KiB; `localize`, `LOC_MAX_FOTOS` × `LOC_MAX_BYTES_FOTO` + 64 KiB (§4.8, §4.10) |
| `LOC_TOP_K` / `LOC_EF_SEARCH` | 10 / 64 | Por foto. `localize` (BE-3.2) busca `LOC_TOP_K` vecinos por foto y `vecinos` (BE-2.4) los `k` pedidos, los dos con `hnsw.ef_search = max(LOC_EF_SEARCH, k)` (§4.8); `LOC_TOP_K` es el `k` con que la herramienta de evaluación de embeddings llama a `vecinos` |
| `LOC_SIM_MIN` / `LOC_SIM_ALTA` | 0,55 / 0,80 | **Iniciales: se calibran en BE-3.2 con el conjunto de evaluación de EMB-3.2** (cómo y dónde, §4.10 «Calibración»; C6 de `validation-3-2.md` falla mientras digan «Iniciales»). Umbral de las coincidencias (≥) y similitud a la que `s` vale 1 (§4.10, pasos 3 y 7) |
| `LOC_RADIO_GRUPO_M` / `LOC_PESO_EXPONENTE` / `LOC_RADIO_MIN_M` | 20 / 4 / 5 | Distancia (m, estrictamente menor) al centroide sin ponderar para entrar en un grupo; exponente de los pesos de la posición; radio mínimo (m) (§4.10, pasos 4 y 6) |
| `LOC_NIVEL_ALTA_MIN` / `LOC_NIVEL_MEDIA_MIN` (cortes de nivel) | 0,70 / 0,45 | `alta` ≥ 0,70 · `media` ≥ 0,45 · `baja` < 0,45, sobre la confianza truncada a 2 decimales (§4.10, paso 7). Iniciales: se calibran con EMB-3.2 como `LOC_SIM_MIN` |
| `LOC_DISPERSION_RUMBO_MAX` | 30° | Desviación estándar circular máxima de las diferencias de rumbo para devolver `correccion_rumbo_grados` (§4.10, paso 8) |
| `LOC_LUGAR_CERCANO_M` / `LOC_REFERENCIAS_M` / `LOC_REFERENCIAS_MAX` | 60 / 150 / 3 | `lugar_cercano` a ≤ 60 m; hasta 3 `referencias` a ≤ 150 m sin repetirlo (§4.10, paso 9) |
| `REC_MAX_FOTOS_VIDEO` / `REC_MAX_LOTE` | 200 / 50 | 200 coincide con `MAX_FOTOS_VIDEO` de la app. `images` (BE-2.1) rechaza con `422` un `orden` > `min(REC_MAX_FOTOS_VIDEO, 200)` (200 es el `CHECK` de §5.7) y un lote de más de `REC_MAX_LOTE` |
| `REC_MAX_BYTES_FOTO` / `REC_LADO_MIN_PX` | 4 194 304 (4 MB) / 320 | `images` rechaza un `bytes` declarado mayor (`422`); el tamaño real (sin descargar lo que pasa del máximo) y el lado menor tras EXIF los valida el `worker` (BE-2.2, §4.6; una URL PUT no limita tamaño) |
| `PRESIGN_PUT_TTL_S` / `PRESIGN_GET_TTL_S` | 900 / 3600 | Vida de las URL `PUT` de `images` (BE-2.1) y de las GET (BE-4.1). C3a de la validación espera 900 s + 10 s |
| `MINIATURA_LADO_PX` / `MINIATURA_CALIDAD` | 320 / 80 | Lado mayor y calidad JPEG de `thumbs/…` (BE-2.2, §4.6) |
| `WORKER_MAX_MENSAJES` / `WORKER_LOTE_EMBEDDING` | 10 / 4 | Mensajes por `ReceiveMessage` (máx. de SQS: 10) e imágenes por `POST /v1/embed`. Embeddings admite hasta 8; se usan 4 para no retrasar la localización (el código acota a 1–8) |
| `WORKER_LADO_EMBEDDING_PX` | 1024 | Copia reducida que se envía al modelo (el original y la miniatura no cambian) |
| `WORKER_ESPERA_EMBEDDING_S` | 15 | Pausa entre comprobaciones de `/health/ready` con `embedding` no listo, tras un error de SQS y tras un lote con mensajes retenidos |
| `RECONCILIADOR_CADA_MIN` | 10 | Purgas pendientes |
| `ALERTAS_TOMBSTONE_DIAS` / `EVENTOS_RETENCION_DIAS` | 90 / 180 | Limpieza diaria desde `api` (sin código todavía; la de *tombstones* es de BE-3.3, §4.9; BE-3.2 escribe `eventos_localizacion` pero no la limpia) |
| `PAGINA_POR_DEFECTO` / `PAGINA_MAX` | 24 / 100 | 24 coincide con `FOTOS_POR_PAGINA` de la Galería. Los usa `GET /v1/admin/videos` desde BE-2.1 |
| `DB_POOL_API` / `DB_POOL_API_DESBORDE` / `DB_POOL_WORKER` | 5 / 5 / 2 | `db.t4g.micro` admite ~100 conexiones |
| `DB_CONNECT_TIMEOUT_S` | 5 | Tiempo máximo para abrir una conexión (asyncpg espera 60 s por defecto) y para el `SELECT 1` de `/v1/health/ready` |
| Formato de log | JSON por línea: `ts`, `nivel`, `proceso`, `request_id`, `evento`, campos propios | Sin secretos ni URLs firmadas. Detalle abajo |

**Formato de log en detalle.** `ts` en UTC con milisegundos y `Z` (`2026-10-23T15:04:05.123Z`); `nivel` = `DEBUG`,
`INFO`, `WARNING`, `ERROR` o `CRITICAL`; `proceso` = `api`, `worker` o `migrate`; `request_id` = el de la petición en
curso o `null` fuera de una petición. Después van los campos propios del evento y, si aplica, `mensaje` (cuando el
texto difiere del evento), `logger` y `excepcion` (la traza completa, en la misma línea, con el `DETAIL` de los errores
de PostgreSQL sustituido por `(omitido)`, porque puede copiar los valores de la fila rechazada). Los mensajes de librerías
(uvicorn, por ejemplo) salen con `evento = "log"` y su texto en `mensaje`. Un campo propio nunca reemplaza a uno fijo.

**Eventos de log** (cada lote añade los suyos aquí):

| Evento | Proceso | Campos propios | Cuándo |
|---|---|---|---|
| `peticion` | `api` | `metodo`, `ruta` (sin *query string*), `estado`, `duracion_ms` | Cada solicitud HTTP. En `DEBUG` si es `/v1/health` con estado < 400; si no, en `INFO`. Es lo que busca la validación de BE-1.1 (C2b) |
| `error_no_controlado` | `api` | `metodo`, `ruta` (y la traza en `excepcion`) | Excepción que llega al middleware (`ERROR`); la respuesta es `500 ERROR_INTERNO` |
| `error_api` | `api` | `estado`, `codigo` | Un error de §5.6 con estado ≥ 500 (`ERROR`) |
| `api_iniciada` / `api_detenida` | `api` | `version`, `commit`, `entorno` (solo al iniciar) | Arranque y parada de la aplicación |
| `worker_iniciado` / `latido` / `worker_detenido` | `worker` | Al iniciar: `version`, `commit`, `entorno`, `modo`; en cada latido: `modo` y, en `ingesta`, `embedding_listo` (`null` antes de la primera comprobación) | Arranque, cada 60 s y parada. `modo` = `ingesta` desde BE-2.2, o `sin_consumo` si falta configuración (§4.6) |
| `embedding_listo` / `embedding_no_listo` | `worker` | — | `GET /health/ready` de embeddings pasa a responder 200 / deja de hacerlo (solo al cambiar). Sin `embedding`, el `worker` no recibe mensajes (BE-2.2) |
| `lote_ingesta` | `worker` | `mensajes`, `borrados`, `retenidos`, `duracion_ms` | Tras procesar cada recepción con mensajes (BE-2.2) |
| `mensajes_devueltos` | `worker` | `mensajes` | `embedding` dejó de estar listo durante la espera larga (o el proceso se detiene): devueltos con visibilidad 0 |
| `imagen_procesada` | `worker` | `origen` (`s3` \| `reprocesar`), `imagen_id`, `video_id`, `version_vector`, `ancho`, `alto`, `bytes`, `duracion_ms` | Foto `procesada` con su vector (BE-2.2) |
| `imagen_con_error` | `worker` | `origen`, `imagen_id`, `video_id`, `motivo` (los de §4.6) | Error permanente: foto en `error`, mensaje borrado (`WARNING`) |
| `mensaje_descartado` | `worker` | `motivo` (`prueba_s3`, `clave_no_reconocida`, `video_no_existe`, `video_eliminado`, `imagen_no_existe`, `duplicado`, `objeto_no_existe`), `origen`, `imagen_id`, `video_id` (o `mensaje_id` en los dos primeros) | Nada que procesar; el mensaje se borra (`INFO`) |
| `mensaje_no_reconocido` | `worker` | `motivo`, `mensaje_id` | Cuerpo que no es ninguno de §5.8; se borra (`WARNING`) |
| `ingesta_transitoria` | `worker` | `motivo` (`s3: …`, `base: …`, `embedding: …`, `version_vector distinta…`, `imprevisto: …`), `origen`, `imagen_id`, `video_id` (y la traza en `excepcion` si es imprevista) | Fallo transitorio: el mensaje se queda (`WARNING`; `ERROR` si es imprevisto o una respuesta no válida de embeddings) |
| `version_vector_distinta` | `worker`, `api` | `esperada`, `recibida` | `/v1/embed` devolvió otra `version_vector` que `EMBEDDING_VERSION_VECTOR`: el `worker` no guarda nada; en `api` (`vecinos` desde BE-2.4, `localize` desde BE-3.2), `503 EMBEDDING_NO_DISPONIBLE` sin buscar (`ERROR`) |
| `cola_fallida` | `worker` | `operacion` (`recibir` \| `borrar`), `motivo` | Error de SQS; el bucle sigue (`WARNING`) |
| `vecinos_consultados` | `api` | `k`, `devueltos`, `similitud_max` (`null` sin vecinos), `bytes` (de la foto), `embedding_ms`, `busqueda_ms`, `latencia_ms` | `POST /v1/admin/diagnostico/vecinos` con `200` (BE-2.4, `INFO`). Nunca ids, bytes ni nada de la foto salvo su tamaño |
| `embedding_no_disponible` | `api` | `motivo` (p. ej. `sin EMBEDDING_URL`, `sin respuesta en 5 s`, `503 SATURADO`, `respuesta no válida: …`) | Una llamada de `api` a `/v1/embed` falló: `vecinos` (BE-2.4) y `localize` (BE-3.2) responden `503 EMBEDDING_NO_DISPONIBLE` (`WARNING`; `ERROR` si la respuesta no cumple el contrato). Va seguido de `error_api` |
| `localizacion_calculada` | `api` | `resultado`, `nivel_confianza` (`null` con `sin_coincidencias`), `confianza`, `fotos_usadas`, `fotos_con_coincidencia`, `coincidencias` (vecinos sobre `LOC_SIM_MIN`), `grupos`, `similitud_max` (6 decimales o `null`), `bytes` (de todas las fotos), `embedding_ms`, `busqueda_ms`, `latencia_ms` | `POST /v1/localize` con `200` (BE-3.2, `INFO`). Nunca la posición, ids, rumbos ni nada de las fotos salvo su tamaño total |
| `base_no_disponible` | `api`, `migrate` | `motivo` (clase y mensaje del error, sin secretos) | La base no respondió. En `api`, en `/v1/health/ready` y, desde BE-1.3, en cualquier endpoint que la use (`WARNING`; responde `503`); en `migrate` (toda la CLI, también `limpiar-validacion`), la CLI termina con 2 (`ERROR`) |
| `configuracion_incompleta` | `migrate`, `api`, `worker` | `faltan`, `invalidas` (nombres de variables o, para la contraseña de `crear-usuario`, `CREAR_USUARIO_PASSWORD` o `terminal`), `motivo` (sin el valor recibido) | En `migrate`: faltan `DB_*` (o `ADMIN_INICIAL_*` cuando hay que crear el admin), una variable tiene un valor no válido, como `DB_SSLMODE` o `DB_PORT`, falta o no vale la contraseña de `crear-usuario`, o falta `S3_BUCKET_DATASET` en `limpiar-validacion` (`ERROR`); la CLI termina con 3. En `api` (BE-1.3): falta `JWT_SECRET` en un login o una ruta protegida; desde BE-2.1, falta `S3_BUCKET_DATASET` (o no se pudo crear el cliente de S3) en `images` o `complete` (`ERROR`; responde `500`). En `worker` (BE-2.2), al arrancar sin `SQS_URL_INGESTA`, `S3_BUCKET_DATASET`, `EMBEDDING_URL` o `DB_*` (`faltan`; `motivo = la ingesta no puede empezar`), y sigue con latidos sin consumir (`ERROR`) |
| `video_creado` | `api` | `video_id`, `numero`, `nuevo` (`false` si ya existía con ese `ref_cliente`) | `POST /v1/collect/videos` con `201` o `200` (BE-2.1) |
| `lugar_guardado` | `api` | `operacion` (`crear` \| `editar`), `lugar_id`, `cambios` (campos que cambiaron; al crear, los 7 de `LugarEntrada`) | `POST /v1/admin/places` con `201`, o `PUT` que cambió algo (BE-3.1, `INFO`). Sin el nombre |
| `lugar_eliminado` | `api` | `lugar_id`, `existia`, `fotos_sin_lugar` | `DELETE /v1/admin/places/{id}` con `204` (BE-3.1, `INFO`), también de un id que no existía (`existia = false`) |
| `imagenes_registradas` | `api` | `video_id`, `recibidas`, `nuevas`, `actualizadas` (pendientes con metadatos nuevos y URL), `marcadas_subida` (pendientes que el `HEAD` encontró en S3), `sin_cambios` (ya `subida`, `procesada` o `error`), `urls` | `POST …/images` con `200` (BE-2.1). Nunca las URL |
| `subida_completada` | `api` | `video_id`, `comprobadas` (pendientes con `HEAD`), `encontradas`, `fallidas`, `estado`, `conteo` | `POST …/complete` con `200` (BE-2.1) |
| `s3_fallido` | `api`, `migrate` | `operacion` (`firmar` \| `head` \| `borrar` \| `listar` \| `crear_cliente`), `motivo` (clase y código de AWS, nunca la URL); en `head`, `video_id` y `claves` (cuántas fallaron); en `firmar`, `video_id` | `firmar`: `images` responde `500` (`ERROR`). `head`: alguna foto queda pendiente y la respuesta sigue (`WARNING`). `borrar` (primera pasada) o `listar` (`--simular`): `limpiar-validacion` termina con 1 (`ERROR`). `crear_cliente`: al arrancar `api` (`ERROR`) |
| `limpieza_validacion` | `migrate` | `videos`, `objetos`, `video_ids` | `limpiar-validacion` terminó con 0 (BE-2.1). Después imprime `LIMPIEZA {"videos": n, "objetos": m}` |
| `limpieza_rechazada` | `migrate` | `inexistentes`, `sin_prefijo` (ids), `motivo` | `limpiar-validacion --video …` (con o sin `--simular`) con algún id inexistente o sin el prefijo `validacion-` en `nombre` y `ref_cliente` (`ERROR`); no borra nada y termina con 1 |
| `limpieza_simulada` | `migrate` | `videos`, `objetos`, `video_ids` (lo que borraría) | `limpiar-validacion --simular` terminó con 0 (no borró nada). Después imprime `SIMULACION {"videos": n, "objetos": m}` |
| `limpieza_s3_incompleta` | `migrate` | `prefijos` (los de la segunda pasada que fallaron), `motivo` | `limpiar-validacion` ya borró las filas y la segunda pasada por S3 falló (`WARNING`): pueden quedar objetos huérfanos; el comando sale con 0 (§4.5) |
| `login` | `api` | `resultado` (`exito` \| `fallo` \| `rechazado`), `motivo` (`null` \| `correo_desconocido` \| `password_incorrecta` \| `usuario_inactivo` \| `cola_llena` \| `espera_agotada`), `usuario_id` (`null` si el correo no existe o no se buscó) | Cada `POST /v1/auth/login` con el cuerpo válido que llega a la cola del hash (`INFO` si entró; `WARNING` si no). `rechazado` = `503 SERVICIO_OCUPADO`, sin fila de auditoría. Nunca el correo escrito ni la contraseña |
| `autorizacion_rechazada` | `api` | `codigo` (`NO_AUTENTICADO`, `TOKEN_INVALIDO`, `TOKEN_EXPIRADO`, `SIN_PERMISOS`), `usuario_id` (el `sub` si el token era válido; si no, `null`) | `requiere_admin` rechaza una petición (`INFO`) |
| `usuario_guardado` | `migrate` | `resultado` (`creado` \| `actualizado`), `usuario_id`, `rol`, `reactivado`, `rol_anterior` (solo al actualizar) | `crear-usuario` terminó con 0 |
| `usuario_desactivado` | `migrate` | `usuario_id`, `ya_estaba_inactivo` | `desactivar-usuario` terminó con 0 |
| `usuario_no_encontrado` | `migrate` | — | `desactivar-usuario` con un correo que no existe (`WARNING`); termina con 1 |
| `usuario_rechazado` | `migrate` | `motivo` | `crear-usuario` o `desactivar-usuario` dejaría sin ningún admin activo (`ERROR`); termina con 1 |
| `comando_fallido` | `migrate` | `comando`, `motivo` (y la traza en `excepcion`) | Error de `crear-usuario`, `desactivar-usuario` o `limpiar-validacion` que no es de conexión (p. ej. la base sin migrar) (`ERROR`); termina con 1 |
| `migracion_iniciada` | `migrate` | `version`, `commit`, `entorno`, `revision_objetivo` | Al empezar `migrar` |
| `migracion_terminada` | `migrate` | `revision_anterior`, `revision`, `aplicada`, `admin_inicial` (`creado` \| `ya_habia_admin`), `usuario_id` (si lo creó), `duracion_ms` | `migrar` terminó con 0. Los mensajes de Alembic (`Running upgrade  -> 0001, …`) salen antes como `evento = log` |
| `migracion_fallida` | `migrate` | `motivo` (y la traza en `excepcion`) | Falló una migración o el admin inicial, o esperó más de 5 min a otro `migrar` (`LockNotAvailableError`) (`ERROR`); la CLI termina con 1 |
| `esquema_diferencia` | `migrate` | `objeto` (p. ej. `columna alertas.radio_m`), `aspecto` (`falta`, `sobra`, `tipo`, `nulo`, `defecto`, `generada`, `definicion`, `valores`, `propietaria`, `revision`), `esperado`, `encontrado` | Una por diferencia de `verificar-esquema` (`WARNING`) |
| `esquema_verificado` | `migrate` | `resultado` (`coincide` \| `difiere`), `diferencias`, `revision`, `revision_esperada`, `servidor`, `pgvector` | Al terminar `verificar-esquema` (`INFO` si coincide; si no, `WARNING`) |
| `verificacion_fallida` | `migrate` | `motivo` (y la traza en `excepcion`) | Error que impide comparar y no es de conexión: al leer el catálogo, al cargar las migraciones o al esperar más de 5 min a un `migrar` en curso (`LockNotAvailableError`) (`ERROR`); la CLI termina con 2 |

### 5.11 Validadores del backend

El contrato común (nombres, argumentos, códigos de salida, informe, reglas de datos de prueba) está en
`INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Aquí solo lo propio del backend.

**Entornos**

| Entorno | Qué hay | Qué no se puede validar ahí |
|---|---|---|
| `local` | `project/docker-compose.yml`: PostgreSQL 17 con pgvector (`pgvector/pgvector:pg17`), `api` y `worker` construidos desde `project/`, y la imagen de embeddings si se pasa `EMBEDDING_IMAGEN` con el perfil `embedding` (`docker compose --profile embedding up --build`). Puertos en la máquina: `DB_PUERTO_LOCAL` (5432), `API_PUERTO_LOCAL` (8000), `EMBEDDING_PUERTO_LOCAL` (8080); `GIT_COMMIT` (por defecto `local`) llega a `/v1/health`. Las contraseñas del archivo son solo locales. La base se migra con `docker compose run --rm api python -m app.cli migrar`, que crea el admin inicial con el `ADMIN_INICIAL_*` local del archivo | S3 y SQS no se emulan: lo que dependa de ellos solo corre en `dev` |
| `dev` | Lo desplegado en AWS (infra §2) | — |

**Variables que leen**

| Variable | Uso | En `dev`, si falta |
|---|---|---|
| `VALIDACION_API_URL` | URL base con `/v1` | Se arma con el output `api_base_url` de infra |
| `VALIDACION_ADMIN_CORREO`, `VALIDACION_ADMIN_PASSWORD` | Iniciar sesión como admin (hacen falta las dos; en `local`, las del compose: `admin@campus.edu.co` / `local-solo-desarrollo-admin`) | Se leen del secreto `campus-locator/dev/admin-inicial` |
| `JWT_SECRET` | Solo `validate13.py` en `local`: comprobar y falsificar firmas (la del compose, `local-solo-desarrollo-no-usar-en-aws`) | Se lee del secreto `campus-locator/dev/jwt` (clave `secret`) |
| `AWS_PROFILE` | Inspeccionar S3, SQS, logs y lanzar tareas | Obligatoria en `dev` |

**Cómo comprueban lo que no se ve desde fuera**
- La base de datos es privada: las comprobaciones de esquema lanzan una tarea suelta con la definición
  `campus-locator-dev-migrate` y el comando `python -m app.cli verificar-esquema` (§5.9), y leen su código de salida y
  su log.
- Para **leer** la base (auditoría, vectores, `purgado_en`…) lanzan la tarea de validación de infra §5.11
  (`campus-locator-dev-validacion`, `psql -tAc "<consulta>"`) y leen su log. Solo consultas `SELECT`: lo que se escribe
  pasa por la API o por los comandos de §5.9.
- La comprobación de disco de BE-3.2 usa ECS Exec sobre la tarea de `api` (infra §3.4): `aws ecs execute-command` necesita
  el *Session Manager plugin* de la CLI de AWS en la máquina de quien valida (`validate32.py` P1).
- Los que necesitan `embedding` (ingesta, localización) lo encienden si está apagado con el contrato de infra §5.10
  (`comun.EmbeddingDev`, abajo), esperan hasta 10 min a que esté sano y a `"embedding": "ok"` en `/v1/health/ready` y
  al terminar lo dejan como lo encontraron (infra §5.11). Como a las 22:00 (hora de Bogotá) se apaga solo, cada uno
  declara la hora límite para empezar.
- Los mensajes y objetos se comprueban con las APIs de SQS y S3; los logs, con CloudWatch Logs.
- La localización (BE-3.2) usa el conjunto de consulta de `evaluacion/` (infra §5.5) que prepara EMB-3.2.
- Lo que devuelve el índice para una foto concreta (por ejemplo, que un video borrado ya no aparece) se ve con
  `POST /v1/admin/diagnostico/vecinos` (§5.5).

**Código común (`project/src/ops/comun.py`)**. Lo usan todos los `validate<fase><n>.py`:
- `Validador(lote="BE-x.y", validacion="validation-x-y", entornos=("dev", …), descripcion=__doc__)`. `iniciar()` lee
  `--entorno local|dev`, `--informe <ruta>`, `--solo C1,C3` y `--sin-limpieza`; un error de uso o un entorno que el
  validador no admite terminan con 3. `ejecutar(precondiciones=[("P1", f), …], comprobaciones=[("C1", f), …],
  manuales=[("M1", "instrucción"), …], limpieza=f, preparacion=None)` sigue el orden del contrato común, imprime una
  línea por precondición y comprobación (`[PASA] C1 …`), escribe el informe JSON (por defecto en
  `project/.validacion/<lote>-<AAAAMMDD-HHMMSS>.json`, que git ignora) y devuelve el código de salida. `preparacion`
  (BE-2.1) corre una vez si las precondiciones pasan, antes de las comprobaciones (p. ej. borrar restos `validacion-`),
  e imprime `[PREPARACION] <detalle>`; si lanza, imprime `[PREPARACION] falló: …` y sigue sin cambiar el código. Va
  también con `--solo` y con `--sin-limpieza` (que solo omite la limpieza del final).
- Cada `f` devuelve el detalle (un texto corto) o lanza una excepción. En una precondición, `PrecondicionNoCumplida`
  (otro lote no está listo) termina con 2 y cualquier otra (`ErrorConfiguracion`, `Falla` o una inesperada), con 3;
  en ambos casos no se ejecutan las comprobaciones. En una comprobación, cualquier excepción la deja en `falla`
  (código 1): `Falla` con su mensaje (`exigir(condición, mensaje)` la lanza) y las demás como «error inesperado: …».
- AWS e infraestructura: `sesion_aws()` (perfil de `AWS_PROFILE`, `us-east-1`), `verificar_cuenta(sesion)` (exige la
  cuenta del proyecto), `outputs_terraform()` (`terraform output -json` de `INFRASTRUCTURA_TERRAFORM/project/envs/dev`,
  con `terraform init` ya hecho), `url_api(outputs)` (`VALIDACION_API_URL`, o `api_base_url` + `/v1`),
  `ejecutar_proceso([...], cwd=None, timeout=600, entorno=None)` (un comando externo; devuelve el resultado con su
  código; `entorno` añade variables al proceso hijo sin ponerlas en la línea de comandos) y `commit_local()`.
- Tareas sueltas de ECS (BE-1.2): `red_tareas(outputs)` arma la red de `run-task` (`subredes_tareas`, `sg_migrate`, IP
  pública; sin esos outputs, `PrecondicionNoCumplida`). `lanzar_tarea(ecs, logs, definicion=…, red=…, familia=…,
  comando=None, iniciada_por="validacion", entorno=None)` lanza la definición (familia o ARN de una revisión) en
  Fargate, en `campus-locator-dev` y sin etiquetas; `comando` sustituye el del contenedor `app`, `entorno` (BE-1.3) le
  añade variables (`environment` del *override*: no se imprimen, pero quedan en `describe-tasks`, así que solo valores
  de prueba), y `familia` (`FAMILIA_MIGRATE`, `FAMILIA_VALIDACION` o, desde BE-2.1, `FAMILIA_WORKER`; `LOGS_TAREA`
  da `/campus-locator/dev/<migrate|validacion|worker>` y el prefijo del mismo nombre) elige el log group y el prefijo
  del stream. Espera hasta 900 s a que la tarea pare y devuelve
  un `ResultadoTarea`: `id`, `arn`, `definicion` (ARN de la revisión), `codigo` (salida del contenedor `app`; `None` si
  no llegó a correr), `motivo`, `lineas` (el log) y `eventos(nombre)` (las líneas JSON de §5.10, todas o las de un
  evento). `leer_log(logs, grupo, stream, completo=None)` lee un stream desde el principio y, mientras no exista,
  esté vacío o (BE-2.1) `completo(mensajes)` sea falso, lo intenta hasta 12 veces, con 5 s entre intentos; agotados,
  devuelve lo último leído (`[]` si nunca llegó). CloudWatch puede entregar las líneas en varias tandas: sin
  `completo`, la primera tanda no vacía se da por buena. `lanzar_tarea(…, log_completo=f)` y
  `EntornoBackend.cli(…, log_completo=f)` pasan `f(codigo, mensajes)` (p. ej. `fin_limpieza`). Al lanzar la tarea o leer el log, un error de
  AWS por falta de permiso es `ErrorConfiguracion` y cualquier otro, `Falla`; un error mientras espera a que pare
  también es `Falla` («no se detuvo en 900 s»), y uno de `describe-tasks` llega sin convertir.

Ayudas de BE-1.3 (para los validadores que inician sesión o usan la CLI; las de BE-2.1 y BE-3.1 las reutilizan):

| Elemento | Qué hace |
|---|---|
| `leer_secreto(sesion, secreto, lote="INF-1.2")` → `dict` | JSON de un secreto de Secrets Manager. Sin permiso → `ErrorConfiguracion`; no existe → `PrecondicionNoCumplida` del `lote`; no es un objeto JSON → `ErrorConfiguracion`. Constantes `SECRETO_ADMIN` (`campus-locator/dev/admin-inicial`) y `SECRETO_JWT` (`campus-locator/dev/jwt`) |
| `credenciales_admin(entorno, sesion=None)` → `(correo, password)` | `VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` si están las dos; si no y es `dev`, las claves `correo` y `password` de `SECRETO_ADMIN`; si no, `ErrorConfiguracion` |
| `ClienteApi(url_base, http=None, dormir=time.sleep, reloj=time.monotonic)` | `pedir(metodo, ruta, token=None, **kwargs)` (ruta relativa a la URL con `/v1`; `token` añade `Authorization: Bearer`; un `429` **de API Gateway** se reintenta tras 1, 2, 4 y 8 s, y un `500 {"message": "Internal Server Error"}` **de API Gateway** —`api` sin instancias en Cloud Map, infra §5.13: la petición no llegó al backend— tras 2, 4 y 8 s; si no ceden, se devuelve el último; los 429 y 500 del backend (formato §5.1) no se reintentan; `reintentos_429`, `reintentos_500`); `login(correo, password)` (`POST /auth/login` con al menos `PAUSA_LOGIN_S` = 0,6 s desde el anterior, por el *throttling* de 2 req/s de infra §5.10; cuenta `logins_ok` y `logins_fallidos`); `token(correo, password, quien=…)` (el token de un 200, o `Falla` con el código, y con «¿está desplegado BE-1.3?» ante un 404); `ultima_duracion_ms`, `reintentos_429`, `cerrar()`. `http` es un `httpx.Client` (15 s) o, en las pruebas, un objeto con `request()` y `close()` |
| `es_respuesta_api_gateway(r)`, `codigo_error(r)`, `describir_respuesta(r)` | ¿Cuerpo `{"message": …}` de API Gateway (infra §5.13)?; `error.codigo` o `None`; texto corto para un detalle (`401 CREDENCIALES_INVALIDAS`, `429 (API Gateway)`), nunca el cuerpo |
| `EntornoBackend(entorno, sesion=None, outputs=None, iniciada_por="validacion", dormir=time.sleep)` | `cli(argumentos, entorno=None, familia=FAMILIA_MIGRATE)` → `ResultadoTarea`: en `local`, `docker compose run --rm -T [-e VAR…] <servicio> python -m app.cli …` desde `project/` (`api` con `FAMILIA_MIGRATE`, `worker` con `FAMILIA_WORKER`: `SERVICIO_COMPOSE`), con los valores solo en el entorno del proceso; en `dev`, tarea suelta con la última revisión de la familia (`campus-locator-dev-migrate` o, para `limpiar-validacion`, `campus-locator-dev-worker`), que debe usar la imagen del servicio `api` (si no, `Falla`: `backend.yml` no terminó). `sql(consulta)` → líneas de `psql -tAc` (en `local`, `docker compose exec -T db psql -U campus_app -d campus_locator`; en `dev`, la tarea `campus-locator-dev-validacion`) o `Falla` si `psql` no termina con 0. También `imagen(definicion)` → `(arn, imagen)`, `revision(familia=FAMILIA_MIGRATE)` → ARN (con la comprobación de imagen; una vez por familia) y `revision_migrate()`. `outputs` es una función que devuelve los outputs (por defecto, `outputs_terraform`) |
| `motivo_cli(resultado)` | Por qué un `app.cli` no dio 0, a partir de sus eventos (`base_no_disponible`, `configuracion_incompleta`, `comando_fallido`, `usuario_rechazado`, `usuario_no_encontrado`, `migracion_fallida`, `verificacion_fallida` y, desde BE-2.1, `limpieza_rechazada` y `s3_fallido`) |
| `USUARIO_VALIDACION`, `crear_usuario_validacion(backend)` → contraseña, `desactivar_usuario_validacion(backend, tolerar_inexistente=False)` → detalle | El usuario de prueba de rol `user` (abajo): `crear-usuario --rol user` con una contraseña aleatoria `validacion-pw-<uuid>` en `CREAR_USUARIO_PASSWORD` (se devuelve, nunca se imprime) y `desactivar-usuario`; `Falla` con `motivo_cli` si no terminan con 0. Con `tolerar_inexistente` (para la limpieza), «no existe» (1 con `usuario_no_encontrado`) no es un fallo |

`validate13.py` es el ejemplo de uso: el `Contexto` crea `ClienteApi` y `EntornoBackend` en P2, pide los tokens la
primera vez que una comprobación los necesita (así `--solo` funciona) y, en `limpieza`, desactiva el usuario de prueba
si pudo quedar activo. Marca «pudo quedar activo» **antes** de lanzar `crear-usuario`: si la tarea reactiva al usuario
y después falla la espera o la lectura del log, la limpieza lo desactiva igual (y si no llegó a crearlo, lo tolera). Sus funciones `partes_jwt`, `firma_valida`, `firmar` y `alterar_firma` hacen el HMAC a mano,
sin la biblioteca del backend; `alterar_firma` cambia un carácter **del medio** de la firma, porque el último puede
codificar solo bits de relleno de base64url y no cambiarla.

Ayudas de BE-2.1 (para los validadores que suben fotos o borran videos de prueba; BE-2.2 y BE-4.1 las reutilizan):

| Elemento | Qué hace |
|---|---|
| `FAMILIA_WORKER` (`campus-locator-dev-worker`), `SERVICIO_COMPOSE` | Familia con la que corre `limpiar-validacion` (`backend.cli([...], familia=FAMILIA_WORKER)`); su log: `/campus-locator/dev/worker`, stream `worker/app/<id>`. `backend.revision(FAMILIA_WORKER)` exige que use la imagen de `api` (`Falla` si no: en una precondición, conviértela en `PrecondicionNoCumplida`) |
| `PREFIJO_VALIDACION` (`validacion-`), `ENCABEZADOS_PUT`, `TIMEOUT_PUT_S` (60), `LINEA_LIMPIEZA` (`"LIMPIEZA "`), `LINEA_SIMULACION` (`"SIMULACION "`) | Constantes |
| `put_prefirmado(http, subida, cuerpo, *, que)` → respuesta | `PUT` a `subida["url"]` con **exactamente** `subida["encabezados"]`; devuelve la respuesta de httpx (`status_code`, `text`: el XML de error de S3). Cualquier excepción → `Falla("PUT de <que>: <clase> (sin respuesta de S3)")`, **sin el mensaje** (podría llevar la URL prefirmada) |
| `head_objeto(s3, bucket, clave)` → `dict \| None` | `head-object` con el cliente de boto3 de quien valida: la respuesta (`ContentType`, `ContentLength`…) o `None` si 404. 403/`AccessDenied` → `ErrorConfiguracion`; otro → `Falla` |
| `claves_s3(s3, bucket, prefijo)` → `list[str]` | Todas las claves bajo `prefijo` (`list-objects-v2` paginado). Sin permiso → `ErrorConfiguracion`; otro → `Falla` |
| `comprobar_bucket(s3, bucket)` → detalle | Para la precondición de S3: `head-bucket`, `list-objects-v2 --max-keys 1` en `dataset/` y `head-object` de una clave que no existe (`dataset/validacion-sonda-<uuid>.jpg`, 404 esperado; sin `s3:ListBucket` S3 respondería 403). Bucket inexistente → `PrecondicionNoCumplida` (INF-1.2); permisos → `ErrorConfiguracion` (código 3 en la precondición, no 1 a mitad de una comprobación) |
| `hora_s3(s3, bucket)` → `datetime`; `desfase_s3_s(s3, bucket, ahora)` → segundos | Hora de S3 (encabezado `Date` de un `head-bucket`, resolución 1 s) y lo que hay que sumar al reloj local para tenerla (positivo si el local va atrasado). `Falla` si no viene `Date` |
| `fin_limpieza(codigo, lineas)` → `bool` | ¿Está entero el log de `limpiar-validacion`? Con 0, cuando aparece `LIMPIEZA …` o `SIMULACION …` (se imprimen después del evento JSON); con otro código, cuando aparece un evento de `EVENTOS_DE_FALLO`; sin código, ya |
| `limpiar_videos(backend, video_ids=None, *, simular=False)` → `ResultadoTarea` | `limpiar-validacion [--video ID …] [--simular]` con `FAMILIA_WORKER`, leyendo el log hasta `fin_limpieza`. `None` = sin `--video` (todos los `validacion-`); `[]` no lanza nada (código 0, sin líneas): nunca equivale a «todos» |
| `linea_limpieza(tarea, prefijo=LINEA_LIMPIEZA)` → `dict \| None` | El JSON de la línea `LIMPIEZA {…}` (o `SIMULACION {…}`), o `None` si no está o no es JSON. Con código 0 y `None`, el log llegó incompleto: la limpieza final no lo trata como fallo |
| `videos_validacion(api, token)` → `list[dict]` | Los `VideoResumen` con `nombre` **y** `ref_cliente` que empiezan por `validacion-` (lo que borraría `limpiar-validacion` sin `--video`), recorriendo todas las páginas de `GET /v1/admin/videos?q=validacion-` (100 por página). No 200 → `Falla` |
| `borrar_restos(api, token, backend)` → detalle | La `preparacion` de los validadores que crean videos: si `videos_validacion` encuentra algo, `limpiar_videos(backend, None)`; `Falla` si la tarea no sale con 0. Devuelve `sin restos validacion- …` o `restos borrados: {…}` |
| `RecorridoPrueba(api, token, nombre, *, total_fotos=4, http_s3=None, lat=1.0, lng=-100.0, semilla=0)` | Un video de prueba (`nombre` = `ref_cliente`; exige el prefijo, si no `Falla`) por la API de §5.4. `token` es una función. `crear()` → respuesta (con 201/200 guarda `video`; `video_id`); `registrar(ordenes)` → respuesta (con 200 guarda cada `ImagenRegistrada` en `registro[orden]`); `subir(orden, subida=None)` → respuesta del `PUT` (por defecto con la `subida` de `registro[orden]` y `foto(orden)`; con 200 añade el orden a `subidas`; sin `subida` → `Falla`); `asegurar_subidas(ordenes)` (registra las que falten en `subidas` —URL nueva— y las sube; `Falla` si algo no da 200; para validadores que solo necesitan fotos subidas, como BE-2.2); `completar()` → respuesta de `complete`; `foto(orden)` → `jpeg_sintetico(1024, 768, semilla * 1000 + orden)`; `elemento(orden)` → el elemento de `images` (coordenada fuera del campus, rumbos 0/90/180/270, `bytes` reales); `cerrar()` (cierra el `httpx.Client` de los `PUT`, que crea con 60 s si no se le pasa uno) |
| `jpeg_sintetico(ancho=1024, alto=768, semilla=0)` → `bytes` | JPEG *baseline* en escala de grises hecho a mano, sin Pillow (bloques de 8×8 de tono uniforme: solo coeficientes DC, AC con un EOB de un bit). La misma semilla da los mismos bytes; semillas distintas, ETag distintos. 1024×768 ocupa ~12 KB. Decodificado con Pillow (libjpeg) en `local` el 2026-10-25: `JPEG (1024, 768) L` (`tests/ops/test_comun_recoleccion.py`, que se omite sin Pillow). Sirve como foto válida para el `worker` (lado menor 768 ≥ `REC_LADO_MIN_PX`) |
| `Validador.ejecutar(…, preparacion=f)` | Arriba: limpieza de restos al empezar |

Ayudas de BE-2.2 (para los validadores que necesitan `embedding` encendido o miran las colas y el log del `worker`;
BE-2.4, BE-3.2 y BE-4.1 las reutilizan):

| Elemento | Qué hace |
|---|---|
| `EmbeddingDev(sesion, dormir=time.sleep, reloj=…, avisar=…)` | El contrato de encendido de infra §5.10, reescrito aquí (las carpetas no comparten código de validación; el `embedding.py` de infra hace lo mismo). `comprobar_inf21()` → detalle (objetivos escalables de `embedding` y `worker`, política `campus-locator-dev-worker-cola`, acción `campus-locator-dev-embedding-apagar-noche`; si falta, `PrecondicionNoCumplida` «INF-2.1»). `servicio(nombre)` → el `describe-services`. `latido()` → `PutMetricData` de `EmbeddingEncendidos` = 1 (`Count`, sin dimensiones, con `Timestamp` explícito) en `campus-locator/dev`. `encender(listo_en_api)` → segundos: rango 0-1 de `embedding` y `worker`, latido, hasta 5 min a que `GetMetricStatistics` (`Sum`, periodo 60 s, ±2 min de la marca) lo vea, 60 s más, hasta que la alarma `campus-locator-dev-embedding-inactivo` no esté en `ALARM` (dentro de los mismos 5 min), `desiredCount = 1`, hasta 10 min desde el principio a despliegue `PRIMARY` `COMPLETED` con una tarea `HEALTHY` (`list-tasks` + `describe-tasks`) registrada en Cloud Map (desde 0.9.2: `servicediscovery list-instances` del `registryArn` del servicio con la IP privada de esa tarea en `AWS_INSTANCE_IPV4`; **no** `get-instances-health-status`, que en este servicio sin configuración de salud responde siempre `InstanceNotFound`), y hasta 2 min más a que `listo_en_api()` sea cierto; si no, `Falla`. Durante esas esperas, los límites de peticiones son «todavía no» y se sigue esperando (`_sondear`, `CODIGOS_TODAVIA_NO`; trampa del arranque, abajo). `ips_privadas(tarea)` → IPs del ENI de una tarea de `describe-tasks`. `apagar()`: rango 0-0 y `desiredCount = 0` de `embedding` y `worker` (no espera). `poner(servicio, n)`: solo `update-service`. Permisos: `application-autoscaling:Describe*` y `RegisterScalableTarget`, `cloudwatch:PutMetricData`, `GetMetricStatistics`, `DescribeAlarms`, `ecs:DescribeServices`, `ListTasks`, `DescribeTasks`, `UpdateService`, `servicediscovery:ListInstances`; los errores de AWS se traducen como en el resto (`ErrorConfiguracion` si es un permiso, si no `Falla`) |
| `embedding_en_api(api)` → `"ok" \| "no_disponible" \| None` | El campo `embedding` de `GET /v1/health/ready` (`None` si no da 200) |
| `hora_bogota(ahora=None)`, `ZONA_BOGOTA`, `HORA_APAGADO_NOCHE` (22) | America/Bogota como UTC−5 fijo (Colombia no tiene horario de verano; no depende de `tzdata`) |
| `mensajes_cola(sqs, url)` → `(visibles, en_vuelo)` | `ApproximateNumberOfMessages` y `…NotVisible` (aproximados y con retraso de hasta ~1 min) |
| `enviar_mensaje(sqs, url, cuerpo)` → `MessageId` | `SendMessage` con el cuerpo en JSON |
| `eventos_worker(logs, imagen_id, desde)` → `list[dict]` | Las líneas JSON de `/campus-locator/dev/worker` con ese `imagen_id` desde `desde` (`filter-log-events` con el id entre comillas, todas las páginas). Sirve para saber que el `worker` consumió un mensaje concreto sin fiarse de los contadores de SQS |
| Constantes | `SERVICIO_EMBEDDING`, `SERVICIO_WORKER`, `ALARMA_INACTIVIDAD`, `POLITICA_WORKER_COLA`, `ACCION_NOCHE_EMBEDDING`, `METRICA_ESPACIO`, `METRICA_ENCENDIDOS`, `LIMITE_ALARMA_S` (300), `LIMITE_ENCENDIDO_S` (600), `PAUSA_SONDEO_S` (15), `LOG_WORKER`, `CODIGOS_TODAVIA_NO` (0.9.1: `InstanceNotFound`, `ThrottlingException`, `Throttling`, `TooManyRequestsException`, `RequestLimitExceeded`; `InstanceNotFound` ya no debería salir desde 0.9.2); `recurso_ecs(servicio)` → `service/campus-locator-dev/<servicio>` |

`validate22.py` es el ejemplo de un validador que enciende `embedding` (P6 con `asegurar_embedding`: si ya está
encendido y `/v1/health/ready` dice `ok`, solo un `latido()`; si no, `encender`), marca `encendido_por_mi` **antes**
de encender (la limpieza lo apaga aunque el encendido falle a medias) y, en la limpieza, lo deja como lo encontró
antes de borrar sus videos. Para saber que el `worker` consumió un mensaje inyectado espera su evento en el log
(`eventos_worker`), y lee `embeddings` con `extract(epoch FROM creado_en)` para comparar instantes como números.

Lo que tiene `validate22.py` y no está en `comun.py` (un lote siguiente que lo necesite lo copia o lo sube a `comun.py`
con su fila en la tabla de arriba; `lote_hecho` subió a `comun.py` con BE-2.4 y `validate22.py` la importa de ahí):
- Constantes: `VERSION_VECTOR` (`dinov2-vits14/pp-v1`), `MINIATURA_LADO_PX` (320), `LIMITE_PROCESADO_S` (20 min),
  `LIMITE_CONSUMO_S` (5 min, espera de un evento del `worker`), `LIMITE_APAGADO_S` (5 min), `GUARDA_APAGADO_S` (45 s),
  `MUESTREO_C3_S` (6 min), `PAUSA_MUESTREO_S` (30 s), `PAUSA_SONDEO_S` (15 s), `HORA_LIMITE` (21, Bogotá) y
  `MARGEN_C3_MIN` (25 min antes de las 22:00).
- `Contexto`: `asegurar_video()` (el `RecorridoPrueba` de 6 fotos), `fotos()` (`orden → ImagenAdmin` del detalle),
  `esperar_estados(ordenes, estado, limite_s, que)` (sondea cada 15 s; una foto en `error` cuando no se espera es
  `Falla` inmediata), `asegurar_procesadas(ordenes)`, `sql(consulta)` (líneas de `psql -tA` partidas por `|`),
  `leer_vectores(ids)` → `{imagen_id: [(version, epoch)]}` (los ids pasan por `uuid.UUID` antes de ir al SQL),
  `vector_de(orden)`, `dlq()` (visibles + en vuelo de la DLQ), `esperar_evento(imagen_id, desde, aceptar, que)` (busca
  desde 60 s antes de `desde`, por si el reloj local va adelantado), `evento_s3(orden)` (el evento de §5.8 con el ETag
  y el tamaño reales de `head-object`), `asegurar_embedding()` y `limpiar()`. Las pruebas sustituyen `http`,
  `http_s3`, `dormir`, `ahora` y `sello`.

Trampas de BE-2.2: `--sin-limpieza` también se salta dejar `embedding` como estaba (queda encendido si lo encendió el
validador: se apaga con `embedding.py apagar` de infra, `validation-2-2` §5 paso 7). `EmbeddingDev.servicio` lanza
`PrecondicionNoCumplida` (INF-1.3) si el servicio no existe. La DLQ se compara con `ApproximateNumberOfMessages` +
`…NotVisible`, aproximados: un mensaje ajeno que llegue a la DLQ durante la ejecución haría fallar C2 o C3b.

Ayudas de BE-2.4 (para los validadores que consultan el índice o miran los logs de `api`; BE-3.2 y BE-4.1 las
reutilizan):

| Elemento | Qué hace |
|---|---|
| `lote_hecho(texto, lote)` → `bool` | ¿La fila `\| <lote> \| … \| Hecho \|` de la tabla de estado (§3) de un PLAN dice «Hecho» en la tercera columna? Una fila de §2.1 con el mismo id no cuenta. La usan `validate22.py` (EMB-2.1 en `SERVICE_EMBEDDING/docs/PLAN.md`) y `validate24.py` (BE-2.2 en el PLAN de esta carpeta) |
| `pedir_vecinos(api, token, foto, *, k=None, tipo="image/jpeg", parte="foto")` → respuesta | `POST /v1/admin/diagnostico/vecinos[?k=…]` con `foto` como única parte `parte` (`consulta.jpg`, `tipo`), como la manda la herramienta de evaluación de embeddings. `token=None` = sin `Authorization`; `k` puede ser cualquier valor (para probar el `422`). BE-4.1 C1 la usa para ver que un video borrado ya no sale |
| `jpeg_patron(semilla, ancho=1024, alto=768, *, calidad=90)` → `bytes` | JPEG en color (Pillow) con un patrón según `semilla % 4` (franjas, tablero, círculos, figuras), colores con esa semilla y 12 líneas encima; la misma semilla, los mismos bytes. Semillas con distinto `semilla % 4` dan fotos muy distintas para el modelo (`jpeg_sintetico`, en gris y de bloques uniformes, no lo garantiza). 1024×768 pesa ~30–200 KB |
| `jpeg_ruido(semilla, ancho=512, alto=384)` → `bytes` | Ruido RGB (Pillow, calidad 85): una foto sin relación con ningún dataset, < 1,5 MB |
| `png_sintetico(ancho=320, alto=240)` → `bytes`; `jpeg_relleno(n_bytes)` → `bytes` | Un PNG; un `jpeg_sintetico` de 64×48 seguido de ceros hasta `n_bytes` (sigue siendo un JPEG válido: el relleno va tras el EOI) |
| `mensajes_log(logs, grupo, desde)` → `list[str]` | Todos los mensajes de un log group desde `desde` (`filter-log-events` sin patrón, todas las páginas). Sin permiso → `ErrorConfiguracion`; otro error → `Falla` |
| Constantes | `RUTA_VECINOS` (`/admin/diagnostico/vecinos`), `LOG_API` (`/campus-locator/dev/api`), `LOG_EMBEDDING` (`/campus-locator/dev/embedding`) |

`validate24.py` (validation-2-4) es el ejemplo de un validador que consulta el índice. Lo que tiene y no está en
`comun.py`:
- `RecorridoPatrones(comun.RecorridoPrueba)`: igual, pero `foto(orden)` = `jpeg_patron(semilla · 1000 + orden)` (las
  fotos 1, 2 y 3 salen con patrones tablero, círculos y figuras, porque `semilla · 1000` es múltiplo de 4).
- `incluida(solo, id_)`: la regla de `--solo` de `comun.Validador` (`C4` incluye `C4a` y `C4b`), para decidir en la
  `preparacion` si hacen falta las lecturas iniciales de C4a.
- `SQL_CONTEOS`: `SELECT (SELECT count(*) FROM eventos_localizacion), (SELECT count(*) FROM embeddings WHERE
  version_vector = 'dinov2-vits14/pp-v1')` → una línea `eventos|vectores` de `psql -tAc`.
- Constantes: `ORDENES` (1, 2, 3), `VERSION_VECTOR`, `SIMILITUD_PROPIA_MIN` (0,95), `LOC_SIM_MIN` (0,55, solo como
  evidencia), `K_C1` (5), `K_MAX` (50), `TAM_GRANDE` (1 677 722 = 1,6 MiB), `EVENTO_MAX_BYTES` (16 384),
  `LIMITE_PROCESADO_S` (20 min), `HORA_LIMITE` (21), `MARGEN_LOGS_S` (60), `PLAN_BACKEND`, `GRUPOS_LOG`.
- `Contexto`: lo de `validate22.py` (`preparar`, `token`, `asegurar_video`, `fotos`, `asegurar_embedding`,
  `_restaurar_embedding`, `limpiar`) más `vecinos(foto, k=None, token=…, tipo=…, parte=…)` (con el token del admin si
  no se pasa otro; `token=None` sin `Authorization`), `asegurar_procesadas()` (sube las 3 fotos y sondea cada 15 s hasta
  `procesada`; `procesadas` guarda las que llegaron), `conteos()` → `(eventos, vectores)`, `claves()` (todas las claves
  del bucket), `lecturas_iniciales()`, `n_indice()` (N = vectores iniciales + fotos de C1 procesadas, sin otra tarea; sin
  lecturas iniciales —`--solo` sin C4— lo cuenta con SQL una vez) y `preparacion()` (`borrar_restos` y, si C4a está
  incluida, las lecturas iniciales). La limpieza deja `embedding` como estaba, borra el video y desactiva el usuario de
  prueba si `usuario_pudo_quedar_activo` (se marca antes de lanzar `crear-usuario`); un fallo en una parte no impide
  las otras.
- Pruebas: `tests/ops/test_validate24.py` carga el mundo falso de `test_validate22.py` con `importlib` (no es un
  paquete) y lo extiende: el endpoint de vecinos (la misma foto → 0,9931; las del índice previo, 0,81, 0,62, 0,41,
  0,30…; las demás, < 0,5), el usuario y su login, `crear-usuario`/`desactivar-usuario` como tareas, los conteos de
  `psql`, el paginador de `list-objects-v2` (páginas de 3) y los logs de `api` y `embedding` (páginas de 2).
  Interruptores de backend defectuoso: `desplegado`, `filtra_umbral`, `guarda_consulta`, `registra_evento`,
  `registra_foto`, `user_entra`, `otro_primero`.
- Para la comprobación de privacidad de BE-3.2 (C4) se puede copiar el método de C4a y C4b: `c4a_nada_guardado`
  compara las claves de **todo** el bucket antes y después (`comun.claves_s3(s3, bucket, "")`) y solo admite las
  nuevas bajo `dataset/<video>/` y `thumbs/<video>/` de sus videos, y los conteos de `SQL_CONTEOS` (BE-3.2 espera,
  al revés, una fila más de `eventos_localizacion` por localización); `c4b_logs` lee con `comun.mensajes_log` los
  grupos `LOG_API` y `LOG_EMBEDDING` desde 60 s antes de P2 y falla si algún mensaje contiene `/9j/` (un JPEG en
  base64) o pesa más de 16 384 bytes en UTF-8. El disco (ECS Exec) no lo mira BE-2.4.
- En `dev` (2026-10-25, `50d931d`): `embedding` tardó 311 s en encenderse (BE-2.2 midió 172 y 202 s) y las 3 fotos
  llegaron a `procesada` en 4,1 min (C1).

Trampas de BE-2.4: C4a supone que nadie sube fotos ni localiza en `dev` mientras corre (si no, falla con los dos
valores para descartarlo). C2a no usa `GET /v1/admin/stats` (BE-2.3 no es dependencia de BE-2.4): N sale de
`SQL_CONTEOS`. Tras la espera de C1, C2a publica un `latido()` (aleja el apagado por inactividad, infra §5.11).
`--sin-limpieza` deja también `embedding` como esté y el usuario de prueba activo (con una contraseña aleatoria que
nadie conoce; la siguiente ejecución lo reactiva y lo desactiva).

Ayudas de BE-3.1 (para los validadores que crean lugares de prueba; BE-2.3 y BE-4.1 las reutilizan):

| Elemento | Qué hace |
|---|---|
| `RUTA_LUGARES` (`/places`), `RUTA_LUGARES_ADMIN` (`/admin/places`) | Rutas relativas a la URL con `/v1` |
| `CAMPOS_LUGAR_PUBLICO`, `CAMPOS_LUGAR_ADMIN` | Los conjuntos exactos de campos de `LugarPublico` (§5.3) y `LugarAdmin` (§5.5), para comparar con `set(respuesta)` |
| `normalizar_nombre(texto)` | La regla de nombres de §5.5 (NFKD sin marcas, `casefold`, espacios reducidos), **copiada** sin importar el backend; `tests/ops/test_validate31.py` comprueba que coincide con `app.dominio.lugares.normalizar_nombre` |
| `lugares_validacion(api, token, prefijo=PREFIJO_VALIDACION)` → `list[dict]` | Los `LugarAdmin` cuyo nombre normalizado empieza por `prefijo` (`GET /v1/admin/places?q=<prefijo normalizado>`). No 200 → `Falla` |
| `borrar_lugares(api, token, ids)` → `int` | `DELETE /v1/admin/places/{id}` de cada id sin repetir (cuenta los `DELETE`); otro código que 204 → `Falla`. Un id que ya no existe también da 204 |
| `borrar_lugares_restos(api, token)` → detalle | La `preparacion` de quien crea lugares: borra **todos** los `validacion-` (de cualquier lote, como `borrar_restos` con los videos). Devuelve `sin lugares validacion- de ejecuciones anteriores` o `lugares validacion- borrados: n` |

`validate31.py` (validation-3-1) es el ejemplo de un validador sin AWS más allá de las credenciales: corre igual en
`local` (contra el compose) y en `dev`. Lo que tiene y no está en `comun.py`:
- Constantes: `LAT`, `LNG` (0.001, 0.001: fuera del campus), `DISTANCIA_ESTE_M` (111,2: 0,001° de longitud a esa
  latitud) y `TOLERANCIA_M` (0,5).
- `_definiciones(prefijo)`: los cuerpos de los lugares de prueba A (`<prefijo> Biblioteca Lago`, con alias y textos),
  B (`… Bloque Sur`, en la posición de consulta), C (`… Entrada Este`, 0,001° al este) y D (`… Cafe Norte`); el
  `prefijo` es `validacion-31-<AAAAMMDD-HHMMSS>` (UTC, `Contexto.sello`).
- `Contexto`: `token()` (el del login de P3), `pedir(metodo, ruta, con_token=True, **kwargs)`, `crear(cuerpo)` (`POST`;
  con 201 apunta el id en `otros_ids`, por si un backend defectuoso crea lo que debía rechazar), `lugar(clave)` (el
  `LugarAdmin` de A–D, creándolo si falta: así `--solo` funciona; apunta el id en `creados`), `publico(**params)`
  (`GET /v1/places`, comprueba `{items, total}` y `total`), `admin_lista(q)`, `buscar_admin(id)` y `limpiar()` (borra
  los que siguen existiendo con el prefijo de la ejecución más los apuntados; informa cuántos existían).
- Pruebas: `tests/ops/test_validate31.py` corre el validador contra **el backend real** (la app con una base efímera,
  marca `base`) usando un `TestClient` como el `http` de `ClienteApi`, en `local` y en `dev` (con `sesion_aws`,
  `verificar_cuenta` y `outputs_terraform` sustituidos), y con backends defectuosos por `monkeypatch` (normalización
  que distingue tildes → C3b falla; lista al revés → C2a falla; `GET /v1/places` con 404 → código 2; contraseña mala
  → código 3). Un validador sin AWS puede copiar ese patrón en lugar de un mundo falso.

Trampas de BE-3.1: C2a supone que nadie más tiene un lugar en (0.001, 0.001) (allí no hay campus; la preparación
borra los `validacion-`). C2c compara el orden de **todos** los lugares con la copia de `normalizar_nombre`: si la
regla de §5.5 cambia, cambian las dos (y la prueba que las compara). La limpieza no borra lugares sin el prefijo de la
ejecución salvo los que apuntó.

**`validate32.py`** (validation-3-2, BE-3.2; solo `dev`; **sin ejecutar todavía en `dev`**). Es el ejemplo de un
validador que localiza con el conjunto de EMB-3.2 y usa ECS Exec. No añade ayudas a `comun.py`: usa `Validador`,
`EmbeddingDev`, `ClienteApi`, `EntornoBackend.sql`, `red_tareas`, `lote_hecho`, `claves_s3`, `mensajes_log`,
`mensajes_cola`, `embedding_en_api`, `hora_bogota`, `describir_respuesta`, `codigo_error`, `es_acceso_denegado` y
`codigo_error_aws`. Lo que tiene y no está en `comun.py`:
- Orden: P1 credenciales (y, si C4c está incluida, `aws` y `session-manager-plugin` en el PATH: si faltan, 3) → P2
  BE-2.2, BE-2.4 y BE-3.1 «Hecho», hora (3 si son las 21:00 o más en Bogotá) y `/v1/health/ready` con `"db": "ok"` → P3
  BE-3.2 desplegado (`POST /v1/localize` con una sola parte `otra` → `400 FOTOS_INVALIDAS`; un `404` es 2; no llama a
  embeddings ni escribe evento), `GET /v1/places` → `200` y, si C4c está incluida, `enableExecuteCommand` en `api`
  (si no, 2, INF-1.3) → P4 EMB-3.1 y EMB-3.2 «Hecho» y el conjunto: la última carpeta `evaluacion/<AAAA-MM><letra>/`
  (orden lexicográfico; las que no tienen esa forma se ignoran), su `puntos.json` y las fotos que existen en S3 (≥ 10
  puntos con fotos, si no 2) → P5 FE-2.1 «Hecho», la red de tareas, `campus-locator-dev-validacion` y `SQL_DATASET`
  con la tarea de validación (posiciones del dataset indexado, redondeadas a 5 decimales; ninguna → 2) → P6 `embedding`
  (como `validate24.py` P5; se salta si `--solo` no incluye ninguna comprobación que localice: C1, C2, C3, C4a, C5).
  Comprobaciones en este orden: C1, C3, C5, C2 (necesita las respuestas de C1 y C3), C4a, C4b, C4c, C6.
- Constantes: `VERSION_VECTOR`, `APP_VERSION` (`validacion-32`), `HORA_LIMITE` (21), `DATASET_CERCA_M` (30),
  `LEJOS_M` (150), `PUNTOS_MIN` (10), `ERROR_MEDIANO_MAX_M` (15), `ERROR_ALTA_MAX_M` (30), `FOTOS_POR_CONSULTA` (5),
  `LADO_MAX_PX` (1024), `CALIDAD_JPEG` (85), `PETICIONES_C3` (100), `CALENTAMIENTO_C3` (3), `P95_MAX_MS` (1000),
  `ESPERA_LOGS_C3_S` (120), `REINTENTOS_LOGS_C3` (3, cada `PAUSA_LOGS_C3_S` = 30 s), `CPU_EMBEDDING`/`MEMORIA_EMBEDDING`
  (`"2048"`/`"4096"`), `EVENTO_MAX_BYTES` (16 384), `MARGEN_LOGS_S` (60), `TAMANO_C4C` (`+50k`), `EXCLUIDOS_C4C`
  (`/var/log/amazon/`: los logs del agente de ECS Exec dentro del contenedor; a verificar en la primera ejecución),
  `LOG_APIGW`, `GRUPOS_LOG_C4B`, `COMPROBACIONES_QUE_LOCALIZAN`, `PLAN_BACKEND`, `PLAN_EMBEDDING`, `PLAN_FRONTEND`,
  `ARQUITECTURA`, `CAMBIOS`, `VERSION_SIN_CALIBRAR` (0.12.0) y `SQL_DATASET`.
- Funciones: `haversine_m` (copia de `geo.distancia_m`; una prueba compara las dos), `preparar_foto(bytes)` (como la app
  y la herramienta de EMB-3.2: EXIF aplicado, RGB, lado mayor ≤ 1024 px con Lanczos sin ampliar, JPEG calidad 85, sin
  EXIF; > 1,5 MB → `Falla`), `md5`, `percentil(valores, p)` (rango más cercano: con 100 valores, p95 = el 95.º),
  `puntos_de(json)` (`Punto(id, lat, lng, fotos=[(archivo, rumbo)], distancia_m)`; algo sin la forma de embeddings §5.9
  → `PrecondicionNoCumplida`), `incluida(solo, id)`.
- `Contexto`: `foto(archivo)` (descarga `evaluacion/<versión>/<archivo>` y la reduce, una vez, **en memoria**: nada se
  escribe en disco), `consulta(punto)` (las 5 primeras fotos del punto en el orden de `puntos.json`, con sus rumbos),
  `con_dataset()` (≤ 30 m) y `lejanos()` (> 150 m; los intermedios no se consultan), `localizar(consulta, que)` (`POST
  /v1/localize` con `fotos` `0.jpg`… y `metadatos` = `{"rumbos", "origen": "escaneo", "app_version":
  "validacion-32"}`; guarda `Respuesta(que, punto, codigo, cuerpo, error_m, request_id, cliente_ms)`, con `error_m` =
  haversine a la coordenada real o ∞ con `sin_coincidencias`, y el MD5 de cada foto enviada; no 200 → `Falla`),
  `asegurar_c1()`, `asegurar_c3()` (3 de calentamiento, que no cuentan, y 100 medidas recorriendo los puntos con 5
  fotos; con `--solo C2` se hacen igual), `latencias_apigw(ids, desde)` (`requestId → integrationLatency` de
  `/campus-locator/dev/apigw`, valores en texto, infra §5.10), `exec(tarea, comando)` (por defecto `aws ecs
  execute-command --interactive` con `comun.ejecutar_proceso`, 120 s; las pruebas lo sustituyen), `hay_plugin()` y
  `limpiar()` (deja `embedding` como estaba y vacía las fotos de la memoria).
- C4c: `ecs list-tasks` del servicio `api` y, en cada tarea, `find / -xdev -type f -newermt @<epoch del inicio> -size
  +50k`; cuentan las líneas que empiezan por `/` (los avisos `find: … Permission denied` y los mensajes de la sesión
  no), salvo `EXCLUIDOS_C4C`. `-newermt @epoch` (GNU find) evita comillas en el comando de ECS Exec. Que funcione sin
  terminal (`--interactive` desde un proceso sin TTY) y que el agente no deje otros archivos de más de 50 KB: **sin
  comprobar** hasta la primera ejecución en `dev`.
- C6 lee los documentos de la copia local: §5.10 sin «inicial» en las filas de `LOC_SIM_MIN` y de los cortes,
  versión del encabezado posterior a 0.12.0 y una entrada del CHANGELOG posterior a 0.12.0 cuyo «Lote que la motivó»
  diga BE-3.2 y que mencione la calibración («calibr»). Con los documentos de hoy falla (a propósito).
- Pruebas: `tests/ops/test_validate32.py` carga el mundo falso de `test_validate22.py` con `importlib` y lo extiende: el
  conjunto `evaluacion/2026-11a/` (12 puntos con dataset cada 100 m, uno intermedio a 80 m y uno lejano a 2 km, con
  fotos de 1200×900 que el validador reduce; una foto de `puntos.json` que falta en S3), `SQL_DATASET`, `GET
  /v1/places`, `POST /v1/localize` (reconoce cada consulta por la foto ya reducida: a 4 m con nivel `alta`, o
  `sin_coincidencias` lejos del dataset; cabecera `apigw-requestid`), los logs de `api`, `apigw` y `embedding` (páginas
  de 7), el tamaño de la tarea de `embedding`, `ingesta` y ECS Exec. Interruptores de backend defectuoso:
  `error_grande` (C1), `alta_lejos` (C2), `lento` (C3), `guarda_consulta` (C4a), `registra_foto` (C4b), `deja_archivo`
  (C4c), `coincide_lejos` (C5); y los casos de código 2 (BE-3.2 sin desplegar, un lote sin «Hecho», sin conjunto, pocos
  puntos, sin dataset, `api` sin ECS Exec) y 3 (hora, sin plugin).

Trampas de BE-3.2: el validador no crea datos de prueba; cada localización deja una fila en `eventos_localizacion`
(≈ 116 por ejecución completa con 12 puntos, `app_version = validacion-32`) que caduca a los 180 días. C3 falla si
`ingesta` tiene mensajes (el `worker` competiría por `embedding`): esperar a que se vacíe. C4a compara MD5 con ETags,
así que solo ve copias exactas de lo enviado (es lo que pide el criterio). `--sin-limpieza` deja `embedding` como esté.

**Trampa del arranque de `embedding`: Cloud Map sin configuración de salud (0.9.1 y 0.9.2).** El servicio de Cloud
Map de `embedding` (`srv-josm7lql7ddxgzm6`, `embedding.campus-locator.local`, registro A con TTL 10 s) **no tiene
`HealthCheckConfig` ni `HealthCheckCustomConfig`** (comprobado en `dev` con `servicediscovery get-service`,
2026-10-25), así que `servicediscovery get-instances-health-status` no da nunca un estado: responde **error**
`InstanceNotFound` («Instance(s) not found for service …») aunque la tarea esté registrada. Dos ejecuciones de
`validate22.py` en `dev` lo destaparon: sobre `c5917bd`, P6 terminó con código 3 («error inesperado:
InstanceNotFound»); sobre `54fdf18` (0.9.1, que lo trataba como «todavía no»), P6 esperó 10 min y terminó con código 2
aunque ECS tenía la tarea `HEALTHY` y el servicio estable a los ~2 min. En las dos la limpieza apagó `embedding`.

Desde 0.9.2, «instancia en Cloud Map» (paso 5 del contrato de infra §5.10, que no dice qué llamada usar) es:
`servicediscovery list-instances --service-id <id del registryArn de serviceRegistries>` devuelve al menos una
instancia cuya `Attributes.AWS_INSTANCE_IPV4` es la IP privada de una tarea `HEALTHY` de `embedding`
(`ips_privadas(tarea)`: el detalle `privateIPv4Address` de sus *attachments* `ElasticNetworkInterface` en
`describe-tasks`). Si la tarea no trae IP, basta con ≥ 1 instancia registrada. Lista vacía → «Cloud Map sin instancias
registradas» (ECS aún no la registró: se sigue esperando); instancias solo con otras IP (registros viejos de una tarea
parada) → «Cloud Map sin la IP de la tarea sana». No se usa `get-instances-health-status`. Permiso:
`servicediscovery:ListInstances` (con `campus-admin`, sí).

Todas las llamadas de AWS que `EmbeddingDev.encender` repite mientras espera (`describe-services`, `list-tasks`,
`describe-tasks`, `list-instances`, `get-metric-statistics`, `describe-alarms`) pasan por `EmbeddingDev._sondear(que,
llamada)` → `(respuesta, None)` o `(None, motivo)` (0.9.1): los códigos de `CODIGOS_TODAVIA_NO` (límites de peticiones;
también `InstanceNotFound`, que ya no debería aparecer) son «todavía no» y se sigue esperando hasta
`LIMITE_ENCENDIDO_S` (o el límite de la alarma); un permiso que falta es `ErrorConfiguracion` (código 3) y cualquier
otro error, `Falla` (en P6, código 2), nunca una excepción de botocore sin traducir. Una tarea que para entre
`list-tasks` y `describe-tasks` no es un error: va en `failures` y cuenta como «sin tarea `HEALTHY`». Las llamadas
sueltas fuera de esa espera (`servicio()` en C3a, `register-scalable-target`, `update-service`, `put-metric-data`)
siguen traduciéndose con `_errores_aws` (un *throttling* ahí es `Falla`).

Pruebas en `tests/ops/test_validate22.py`: `test_cloud_map_sin_health_config_usa_list_instances_y_espera_el_registro`
(lista vacía las 3 primeras veces; P6 pasa), `test_instancia_de_cloud_map_con_otra_ip_no_cuenta` (código 2 tras
10 min simulados; la limpieza apaga `embedding`) y `test_cloud_map_sin_permiso_es_codigo_3_y_apaga_lo_encendido`. El
doble es la clase `CloudMap(mundo)` (cliente `servicediscovery` de la `Sesion` falsa), como en `dev`:
`get_instances_health_status` lanza siempre `InstanceNotFound`; `list_instances(ServiceId)` exige `"srv-emb"` (el
`registryArn` del ECS falso), cuenta las llamadas en `llamadas`, devuelve `{"Instances": []}` en las primeras
`mundo.cloud_map_sin_instancia` (por defecto 0) y después una instancia con `AWS_INSTANCE_IPV4 = mundo.cloud_map_ip`
(por defecto `IP_TAREA`, `10.0.1.57`, la IP del ENI que da el `describe-tasks` falso), o lanza siempre
`mundo.cloud_map_error` si no es `None`. Un validador de BE-2.4 o BE-3.2 que copie ese mundo falso hereda los casos.

`validate21.py` es el ejemplo de un validador que sube a S3, montado sobre esas ayudas: un `RecorridoPrueba` por video
y, en su `Contexto`, `asegurar_video`, `asegurar_registro` (guarda la respuesta de C1b: C3a usa su URL de la foto 4) y
`asegurar_todas_subidas` (`RecorridoPrueba.asegurar_subidas`), así `--solo C4` sube la foto 4 con una URL nueva sin
esperar 15 min. De cada `PUT` solo informa el código. Inspecciona S3 con el perfil de quien valida. `ctx.ahora` y
`ctx.dormir` se sustituyen en las pruebas (reloj falso: la espera de C3a no tarda).

**Trampa del reloj (C3a).** S3 da una URL por vencida con **su** hora; el reloj de la máquina que valida puede ir
atrasado (WSL suele atrasarse tras suspender el equipo). Si el validador esperara con el reloj local, haría el `PUT`
antes de tiempo, S3 lo aceptaría (200) y la foto quedaría subida. Por eso P4 mide el desfase con el `Date` de S3
(`desfase_s3_s`), C3a espera con `ahora + desfase` hasta `expira_en + 10 s` y vuelve a medir el desfase justo antes del
`PUT`. No se reintenta el `PUT` «hasta que dé 403»: antes de vencer, un intento sube la foto. Un 200 es `falla` con ese
motivo. `expira_en` lo calcula `api` (Fargate, con hora de AWS), así que solo cuenta el reloj local.

**Datos de prueba**: videos con `ref_cliente` y `nombre` que empiezan por `validacion-` (con coordenadas fuera del
campus, para no mezclarse con el dataset real), lugares cuyo nombre normalizado (§5.5) empieza por `validacion-`,
alertas cuyo mensaje empieza por `validacion-` (BE-3.3), y un usuario `validacion+user@campus.edu.co` de rol `user`
para las pruebas de permisos.

**Limpieza**

| Qué | Cómo se borra |
|---|---|
| Lugares | `DELETE /v1/admin/places/{id}` (BE-3.1; `comun.borrar_lugares`); al empezar, `comun.borrar_lugares_restos` |
| Alertas | `DELETE /v1/admin/alerts/{id}` (BE-3.3, sin implementar) |
| Videos de prueba, antes de BE-4.1 | `limpiar-validacion --video <id> …` en una tarea suelta con la definición `campus-locator-dev-worker` (§5.9) |
| Videos de prueba, con BE-4.1 hecho | `DELETE /v1/admin/videos/{id}`; su purga limpia S3 |
| Usuario `validacion+user@campus.edu.co` | Lo crea o reactiva `crear-usuario --rol user` (contraseña aleatoria en `CREAR_USUARIO_PASSWORD`, nunca impresa) y lo desactiva `desactivar-usuario` al terminar, ambos en una tarea suelta de `migrate` (en `local`, con `docker compose run`): `crear_usuario_validacion` y `desactivar_usuario_validacion` de `comun.py`. La fila queda inactiva entre ejecuciones; reactivarla devuelve la validez a sus tokens sin vencer (§5.2), que solo tuvo el validador |

Al empezar, cada validador que crea videos borra los `validacion-` que haya dejado una ejecución interrumpida
(`limpiar-validacion` sin `--video`, o los `DELETE` si BE-4.1 está hecho), con `preparacion` de `Validador`
(`borrar_restos`). Para no lanzar una tarea en vano, antes busca restos con `videos_validacion` (todas las páginas y el
prefijo en `nombre` **y** `ref_cliente`, el mismo criterio que la CLI). Al terminar borra solo los suyos con `--video`
(y solo los que aún existen: un id que ya no existe haría que la orden se negara entera); si la tarea sale con 0 pero
el log no trae la línea `LIMPIEZA`, no es un fallo. Para comprobar que la orden se niega con un video real, se usa
`--simular`: la orden real nunca se apunta a un video ajeno. Las filas de
`auditoria` que generan las pruebas se conservan (son registro) y las de `eventos_localizacion` caducan a los
`EVENTOS_RETENCION_DIAS` (§5.10).

Los `PUT` de un validador generan eventos de S3 en la cola `ingesta` (infra §5.5). El validador no los borra: recibir
mensajes ajenos para buscar los suyos subiría su `ApproximateReceiveCount` y podría mandarlos a la DLQ. Con BE-2.2
desplegado, el `worker` los consume cuando `embedding` está encendido: procesa las fotos que aún existen y descarta
las borradas (`imagen_no_existe` o `video_no_existe`, §4.6); con `embedding` apagado esperan en la cola hasta la
retención (4 días, infra §5.6). Mientras haya mensajes visibles en `ingesta`, la alarma `embedding-inactivo` no apaga
`embedding` por inactividad (sí a las 22:00) y, con `embedding` encendido, el autoescalado puede subir `worker` (R13).

---

## 6. Decisiones de diseño (ADR)

**ADR-BE-01 — Pila: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 asíncrono, asyncpg, Alembic, uv (aceptada).**
Mismo lenguaje que el servicio de embeddings; los esquemas Pydantic son el contrato ejecutable de §5 y generan el
OpenAPI para revisión.

**ADR-BE-02 — API versionada en `/v1`, en español, `snake_case` y enumerados en minúsculas (aceptada).**
Coherente con el resto del proyecto. La app convierte los enumerados a sus `enum` de Kotlin con `uppercase()`.

**ADR-BE-03 — JWT propio HS256, 12 h, sin *refresh*, roles `user`/`admin` (aceptada).** Resuelve la decisión abierta
11 del frontend. Cognito añade costo de integración sin beneficio para un solo tipo de cuenta administrada; API
Gateway HTTP solo valida JWT de emisores OIDC, así que la validación vive en FastAPI. *Consecuencia:* revocar un token
exige desactivar al usuario (se comprueba en cada petición de admin).

**ADR-BE-04 — Subida directa a S3 con URL prefirmada PUT e ingesta asíncrona (aceptada).**
Evita el límite de 10 MB y 30 s de API Gateway y no ocupa a `api`. *Consecuencia:* una URL PUT no limita el tamaño;
lo valida el `worker` (riesgo R4).

**ADR-BE-05 — El `worker` vive en el backend (aceptada).**
El servicio de embeddings queda sin estado, sin base de datos y sin permisos de AWS: solo convierte píxeles en
vectores. Se mantiene la regla del README: el backend es el único que habla con embeddings, base y almacenamiento.

**ADR-BE-06 — Las fotos de `/v1/localize` se descartan tras responder (aceptada).** Resuelve la decisión abierta 7 del
frontend. Solo queda un evento anónimo con posición redondeada, sin identificadores. *Consecuencia:* no se pueden usar
esas fotos para mejorar el dataset; si se quisiera, haría falta consentimiento explícito y una decisión nueva.

**ADR-BE-07 — Borrado lógico, retiro inmediato de vectores, purga asíncrona y auditoría (aceptada).** Resuelve la
decisión abierta 10 del frontend: el borrado es definitivo (sin papelera), cualquier admin puede borrar cualquier
video, y queda quién y cuándo. Los vectores se borran en la misma transacción para que los resultados de ubicación
cambien de inmediato; lo pesado (S3) va a la cola.

**ADR-BE-08 — Localización v1 por vecinos más cercanos + agrupación geográfica (aceptada, revisable).**
Simple, explicable y sin entrenamiento. No usa verificación geométrica (p. ej. emparejar puntos locales); se
reevaluará con los resultados de EMB-3.2. Los parámetros son iniciales y se calibran con datos reales. Los detalles
que no fijaba (centroide, margen, desempates, radio, truncado de la confianza) están en ADR-BE-18.

**ADR-BE-09 — Vectores en tabla propia con `version_vector` e índice HNSW parcial por versión (aceptada).**
Permite indexar con un modelo o preprocesamiento nuevo en paralelo y cambiar de versión sin tiempo fuera de servicio.

**ADR-BE-10 — Alertas con id del cliente, `PUT` idempotente, *tombstones* y sincronización por diferencias
(aceptada).** Encaja con el editor «local primero» de la app (7.8) y con la caché sin conexión del flujo público (2.5).
Desde 0.11.0 se implementa en BE-3.3, fuera del núcleo (decisión del usuario, 2026-10-25; §4.9).

**ADR-BE-11 — Cálculo de rutas diferido a Fase 5 (aceptada).** Decisión abierta 2 del frontend: el grafo de caminos
no existe todavía. `GET /v1/route` queda reservado.

**ADR-BE-12 — Rumbo en norte verdadero, [0, 360), en todos los contratos (aceptada).**
El PDR de la app ya usa norte verdadero; el escaneo 360° hoy entrega acimut magnético en (−180, 180]. Unificar en el
contrato obliga a convertir en un solo sitio (la app) y permite comparar rumbos del dataset con los de la consulta.

**ADR-BE-13 — Login uniforme y autorización con el estado actual de la base (aceptada, BE-1.3).**
- Todo intento de login hace lo mismo: una consulta, **una** verificación argon2id (contra un hash ficticio si el
  correo no existe) y una fila de auditoría; y responde lo mismo. Así ni el cuerpo ni el tiempo dicen qué correos
  existen o están inactivos (el motivo solo queda en el log y en `auditoria`).
- `requiere_admin` comprueba el token y después, en cada petición, que el usuario exista, esté activo y siga siendo
  `admin` en la base (además de en el token). Es la consecuencia de ADR-BE-03 (revocar = desactivar) y cuesta una
  consulta por clave primaria. El usuario inactivo da `401` antes que el rol `403`: su sesión ya no vale.
- PyJWT firma y comprueba (`algorithms=["HS256"]` fijo: ni `none` ni otros algoritmos); el validador hace el HMAC a mano
  para no compartir el error de una biblioteca.
- La verificación argon2id tiene una cola acotada en número (`LOGIN_HASH_COLA_MAX`) y en tiempo
  (`LOGIN_HASH_ESPERA_MAX_S`): lo que no cabe recibe `503 SERVICIO_OCUPADO` con `Retry-After`, un código propio y no
  `BASE_NO_DISPONIBLE`, que diría algo falso al diagnosticar. No se anota en `auditoria` (no se comprobó ninguna
  contraseña y una avalancha escribiría una fila por petición); queda el evento `login` con `resultado = rechazado`.
- *Alternativas descartadas:* comprobar solo el token (no permite revocar); una dependencia con `yield` que tenga la
  conexión toda la petición (el hash ocuparía el pool, y sus excepciones pasarían por ella, §4.4).
- *Consecuencias:* reactivar a un usuario devuelve la validez a sus tokens sin vencer; cambiar la contraseña no los
  invalida. Sin límite de intentos por cuenta (R7).

**ADR-BE-14 — Recolección: S3 confirma la subida y el estado del video se deriva de los conteos (aceptada, BE-2.1).**
- Una foto pasa a `subida` por el evento de S3 (BE-2.2) **o** por un `HEAD` que hace `api` en `complete` y en las
  repeticiones de `images` (§4.5). Sin el `HEAD`, con el `worker` apagado (lo está siempre que `embedding` lo está,
  infra §5.10) el conteo diría que faltan fotos ya subidas y repetir `images` les daría URL otra vez. El `HEAD` usa el
  `s3:GetObject` que el rol de `api` ya tiene para firmar; sin `s3:ListBucket`, «no existe» llega como 403 y se trata
  igual que 404.
- El estado del video no se guarda «a mano» en cada endpoint: `estado_video(conteo, subida_completa)` lo calcula
  siempre igual y `recalcular_estado` lo guarda en la misma transacción que cambia las fotos (también el `worker`).
  `pendiente` dura hasta que la app llama a `complete`, aunque todas las fotos estén subidas: solo la app sabe si
  faltan lotes por registrar.
- Idempotencia: `POST /collect/videos` devuelve el existente sin cambiarlo (gana el primero; la app reintenta con el
  mismo cuerpo); `images` por (`video_id`, `orden`).
- *Alternativas descartadas:* contar como subida toda foto con URL emitida (falso: la app pudo no subirla); listar el
  prefijo del video en S3 (exige `s3:ListBucket` en `api`, un cambio de infra; con él, el `HEAD` daría 404 y seguiría
  igual); esperar al `worker` (no hay `worker` sin `embedding`).
- *Consecuencias:* `complete` cuesta un `HEAD` por foto pendiente (8 a la vez; 200 fotos ≈ 25 rondas, muy por debajo
  de los 30 s de API Gateway; sin medir en `dev`). La imagen del backend lleva boto3.

**ADR-BE-15 — Worker de ingesta: no recibir sin `embedding`, transitorio = el mensaje se queda, idempotencia por ETag
(aceptada, BE-2.2).**
- **Puerta de `embedding` antes de recibir.** Cada `ReceiveMessage` cuenta una recepción y a la sexta el mensaje va a
  la DLQ: si el `worker` recibiera con `embedding` apagado o cargando, las fotos válidas acabarían en la DLQ. Por eso
  comprueba `/health/ready` antes de cada recepción y, si `embedding` se apaga durante la espera larga, devuelve los
  mensajes con visibilidad 0 en lugar de retenerlos 180 s (C3 exige 0 en vuelo con `embedding` apagado).
- **Transitorio: no se toca el mensaje.** Un fallo dentro del procesado (embeddings saturado, S3, base) deja el
  mensaje en vuelo hasta que vence la visibilidad (180 s): así un servicio que falla de forma intermitente no quema las
  5 recepciones en un minuto. *Alternativa descartada:* devolverlo con visibilidad 0 (reintento inmediato, DLQ en
  ~75 s si el fallo sigue).
- **Permanente: la foto en `error`, el mensaje se borra.** Una foto que no vale nunca va a valer; ir a la DLQ solo
  haría ruido en la alarma. La foto vuelve a procesarse si la app la sube otra vez (otro ETag) o con
  `reprocesar_imagen`.
- **Idempotencia por ETag** del evento contra `imagenes.etag` de una foto ya terminada, y `ON CONFLICT … DO UPDATE` en
  `embeddings`: un evento repetido no descarga ni vectoriza; uno que se cuela (p. ej. dos copias en vuelo a la vez) no
  crea un segundo vector.
- **Versión del vector**: se compara la `version_vector` de cada respuesta de `/v1/embed` (viene en todas), sin
  `GET /v1/info`; distinta = error de configuración transitorio (no se guarda un vector incomparable).
- **Copia reducida sin EXIF**: el `worker` ya aplicó la orientación; embeddings la vuelve a aplicar (pp-v1), así que
  la copia que se envía no lleva la marca.
- *Consecuencias:* con `embedding` apagado no hay ingesta (las fotos se quedan en `pendiente_subida`, o en `subida`
  si `complete` las vio en S3); el `worker` necesita
  Pillow en la imagen; un error de configuración (versión distinta) llena la DLQ en ~15 min y la alarma lo hace
  visible.

**ADR-BE-16 — Diagnóstico de vecinos: foto en memoria, una sola consulta de vecinos y errores de embeddings
(aceptada, BE-2.4).**
- **Multipart partido en memoria** (`dominio.multipart`, cuerpo leído con tope por `api.cuerpo.leer_cuerpo`). La foto
  de consulta no debe tocar el disco (ADR-BE-06; BE-3.2 C4 lo mira con ECS Exec) y `request.form()` de Starlette pasa
  a un archivo temporal toda parte de más de 1 MB, además de exigir `python-multipart`. *Alternativas descartadas:*
  `python-multipart` con `UploadFile` (disco y una dependencia más en la imagen); subir el umbral de volcado de
  Starlette (`MultiPartParser.spool_max_size`, atributo de clase: global y frágil entre versiones).
- **Una sola consulta de vecinos** (`db.consultas.buscar_vecinos`) para el diagnóstico y para `/v1/localize`: lo que
  mide EMB-3.2 con `vecinos` es lo que usará la localización. Versión como literal (índice parcial, §5.7),
  `ef_search = max(LOC_EF_SEARCH, k)` con `SET LOCAL`, unión con `imagenes` fuera de la subconsulta ordenada. Sin
  `LOC_SIM_MIN`: el umbral es de la localización.
- **Errores de embeddings**: imagen que embeddings no puede decodificar → `400 FOTOS_INVALIDAS` (es la foto, no el
  servicio; la propuesta de §4.6); servicio apagado, lento, saturado, con una respuesta fuera de contrato o con otra
  `version_vector` → `503 EMBEDDING_NO_DISPONIBLE` (no se busca con un vector incomparable). La versión se compara con
  cada respuesta de `/v1/embed`, sin `GET /v1/info` (viene en todas; la regla de «cada 10 min» de §5.10 sigue sin
  código).
- **Prioridad `baja`**: el diagnóstico no debe retrasar a quien se está ubicando.
- *Consecuencias:* la API no decodifica la foto (una que no es JPEG pero empieza por `FF D8 FF` llega a embeddings y
  vuelve como `400`); el evento `vecinos_consultados` da latencias y similitud máxima sin datos de la foto; la búsqueda
  es aproximada (HNSW, R16).

**ADR-BE-17 — Lugares: nombre normalizado por la aplicación, distancias y orden en Python, `DELETE` idempotente y sin
foto (aceptada, BE-3.1).**
- **Nombre único «sin mayúsculas ni tildes»** = igualdad tras NFKD sin marcas combinantes, `casefold()` y espacios
  reducidos (`dominio.lugares.normalizar_nombre`), guardado en `lugares.nombre_normalizado` con su restricción única
  (§5.7). La ñ cuenta como n: quien busca o dicta un destino suele escribir sin tildes. *Alternativas descartadas:*
  la extensión `unaccent` de PostgreSQL con un índice por expresión (una extensión y un cambio de esquema más, y su
  diccionario no es el mismo que el del validador); `lower()` sin quitar tildes (no cumple C3).
- **Crear** con `ON CONFLICT … DO NOTHING` (sin excepción ni auditoría en el `409`); **reemplazar** con una
  comprobación previa y, para las carreras, la restricción única traducida también a `409`.
- **Distancia y orden en Python** (`geo.distancia_m`, haversine con el radio medio): los lugares son decenas, así no
  hace falta PostGIS ni un índice espacial, y el orden por nombre no depende de la intercalación de la base (puntos de
  código, igual en local, CI y RDS). *Consecuencia:* `GET /v1/places` lee la tabla entera (trampa en §4.9).
- **`DELETE` de un lugar desconocido = `204`**, como el de alertas: un reintento tras perder la respuesta no es un
  error. *Consecuencia:* un id equivocado tampoco da error.
- **Sin foto del lugar en BE-3.1**: §5.5 no tenía cómo subirla (infra §5.5 reserva `lugares/` para la Fase 4);
  `imagen_url` sigue siendo `null` hasta que un lote defina el endpoint (§4.9).
- **Orden de bloqueo** de `borrar` (videos → lugar → fotos) para respetar el «video → imágenes» de §4.5.

**ADR-BE-18 — Localización v1 construida: centroide sin ponderar, margen relativo, confianza truncada y una sola
transacción (aceptada, BE-3.2; las dos primeras decisiones, provisionales).** Fija lo que ADR-BE-08 y el §4.10 anterior
no decían:
- **Centroide de grupo = media sin ponderar** de sus miembros, recalculada al añadir cada uno, y **margen `m` = (p₁ −
  p₂) / p₁** (1 con un solo grupo). *Decisión del maestro con autorización del usuario (2026-10-25), a confirmar por
  el usuario*: es lo que ya simula la herramienta de calibración de EMB-3.2 (`SERVICE_EMBEDDING/docs/ARCHITECTURE.md`
  §4.5 y §5.9, «Detalle del cálculo»), así lo que se calibra allí es lo que corre aquí. *Alternativas descartadas:*
  centroide ponderado por similitud (un vecino muy parecido arrastraría el grupo y lo haría depender del orden aún
  más) o fijo en el primer miembro (no se ajusta al crecer el grupo); margen absoluto p₁ − p₂ (no acotado a [0, 1]).
  Si el usuario cambia alguna, cambian aquí, en `dominio/localizacion.py` y en la simulación de EMB-3.2 a la vez, y
  hay que recalibrar.
- **Desempates deterministas**: a igual similitud, el orden de llegada (foto y rango del vecino); a igual puntuación,
  el grupo creado antes; a igual distancia, el orden de los lugares de `leer_todos`. Entra en el primer grupo creado
  que esté a < `LOC_RADIO_GRUPO_M`, no en el más cercano (el «primer grupo» de ADR-BE-08).
- **Radio** = desviación ponderada (mismos pesos que la posición) de las distancias de los miembros a la posición, con
  mínimo `LOC_RADIO_MIN_M`. **Corrección de rumbo**: una diferencia por foto (su mejor coincidencia **con rumbo** del
  grupo), media circular y «dispersión circular» = desviación estándar circular `√(−2·ln R)`.
- **Confianza truncada a 2 decimales y nivel decidido con el valor truncado**: la app nunca ve 0,70 con `media`.
  Frente a EMB-3.2, que compara sin truncar, solo cambia una confianza a menos de 5·10⁻⁷ de un corte.
- **`referencias` sin el lugar cercano**: el ejemplo de §5.3 ya lo suponía (dos lugares distintos).
- **Una transacción** para buscar, leer los lugares y escribir el evento: la conexión se tiene unos milisegundos más
  (el algoritmo es Python puro) y a cambio la respuesta y `eventos_localizacion` no se contradicen; un fallo de la base
  al escribir da `503`. **Evento solo con `200`**: `resultado = 'error'` (§5.7) queda sin uso en BE-3.2 (es la opción
  conservadora: no registra peticiones que fallan por la base o por embeddings).
- **Errores de `metadatos`** con los códigos generales de §5.6 (`422 VALIDACION` y `400 SOLICITUD_INVALIDA`); `400
  FOTOS_INVALIDAS` solo para lo que §5.3 ya decía (fotos y largo de `rumbos`).
- *Consecuencias:* los umbrales siguen siendo iniciales hasta la calibración (C6); la simulación de EMB-3.2 y este
  código deben cambiar juntos.

---

## 7. Riesgos

| ID | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | La precisión de ubicación no alcanza (dataset escaso, cambios de luz, lugares parecidos) | Alta | Alto | Conjunto de evaluación (EMB-3.2), calibrar umbrales, confianza honesta (`baja` → repetir), cobertura visible en el panel. BE-3.2 construido (0.12.0) con los umbrales iniciales: precisión sin medir hasta C1/C2 de `validation-3-2.md` |
| R2 | `/v1/localize` supera 1 s en el servidor | Media | Medio | Modelo pequeño (ViT-S/14) en 2 vCPU (infra ADR-INF-14); medir en EMB-3.1 y BE-3.2; fotos de 1024 px; palancas de embeddings §4.4. EMB-3.1 midió 413 ms de p95 para 5 fotos; BE-3.2 en `dev` (C3), sin medir |
| R3 | La ingesta retrasa la localización (un solo servicio de embeddings, que no interrumpe un lote en curso) | Media | Medio | Prioridad `alta` para localización (embeddings §5.2); lotes de 4 imágenes reducidas en el `worker` |
| R4 | Una URL PUT permite subir archivos enormes | Baja | Bajo | URL de 15 min ligada a una clave; el `worker` rechaza > 4 MB y la purga los borra. Un objeto de más de 2 GiB deja `imagenes.bytes` nulo en el `HEAD` (no cabe en `integer`, §4.5) |
| R5 | Rumbos de fuentes distintas (magnético vs. verdadero) | Alta | Medio | ADR-BE-12; lote del frontend para convertir en el escaneo |
| R6 | Eventos de S3 duplicados o fuera de orden | Media | Bajo | Idempotencia por imagen y ETag |
| R7 | Fuerza bruta contra el login | Baja | Alto | *Throttling* de API Gateway (aproximado y común a todos los clientes: frena volumen, no intentos sueltos, infra §3.3), argon2id, auditoría de cada intento con su motivo (`usuario.login`, §5.7), alarma de 5xx. **Sin límite de intentos por cuenta:** infra lo propone (su CHANGELOG 0.12.0 y R10: 5 fallos en 15 min por correo → `429` con `Retry-After` durante 15 min, fallos en PostgreSQL); no entra en BE-1.3 y está pendiente de decisión. Si se adopta, cambia §5.3 (un error nuevo del login) y la app lo consume |
| R8 | Reloj del teléfono desajustado (`capturada_en`) | Media | Bajo | El servidor guarda `creado_en` propio; `capturada_en` solo informa |
| R9 | `db.t4g.micro` se queda corto (memoria del índice, conexiones) | Baja | Medio | Pools pequeños; ver infra R4 |
| R10 | Formatos de error distintos cuando responde API Gateway | Alta | Bajo | §5.1 lo documenta; la app decide por código HTTP |
| R11 | El texto del catálogo (restricciones, índices) cambia con una versión mayor de PostgreSQL y `verificar-esquema` da diferencias que no lo son | Baja | Bajo | RDS actualiza por su cuenta solo la versión menor (infra §3.5); CI usa la misma mayor (`pg17`) y prueba que la migración deja exactamente `esquema.py`; un cambio de mayor actualiza `esquema.py` en el mismo cambio |
| R12 | argon2id en 0,25 vCPU: login lento, falta de memoria o el *health check* sin CPU con varios a la vez | Media | Medio | Como mucho `LOGIN_HASH_CONCURRENTES` (2) a la vez, fuera de la base, 64 MiB cada uno; como mucho 8 más esperando y 10 s de espera (luego `503 SERVICIO_OCUPADO`, §4.4). En `local` tarda ~92 ms; en `dev`, 1,1–1,2 s por login, uno a la vez (C2 de `validate13.py`, 2026-10-25), así que con 2 verificando a la vez los 8 que esperan pueden pasar de los 10 s y recibir el 503 (sin medir). **Riesgo que queda:** con un flujo sostenido de logins, las dos verificaciones argon2 (t = 3, 64 MiB, p = 4) pueden ocupar los 0,25 vCPU y retrasar `GET /v1/health`; si el *health check* del contenedor (cada 30 s, 5 s de plazo, 3 fallos, infra §5.7) falla, ECS reinicia la tarea. Sin comprobar. Palancas: `LOGIN_HASH_CONCURRENTES = 1`, bajar los parámetros de argon2 (los hashes viejos siguen verificándose, §4.3) o el límite por cuenta de R7 |
| R13 | Eventos de S3 de los validadores (y de subidas reales con `embedding` apagado) esperan en `ingesta` sin consumidor | Media | Bajo | Antes de BE-2.2 el `worker` no consumía (§4.2) y `validate21.py` dejaba 6 mensajes por ejecución que caducan a los 4 días (infra §5.6). Mientras estén visibles, `embedding` no se apaga por inactividad (sí a las 22:00). Con BE-2.2 el `worker` los consume en cuanto `embedding` está encendido y descarta los de fotos borradas (§4.6); con `embedding` apagado siguen esperando (es lo que mide C3 de BE-2.2). No se purgan desde el validador (§5.11) |
| R15 | Un fallo transitorio repetido (embeddings saturado, `version_vector` distinta, S3 o base caídos) manda a la DLQ eventos de fotos válidas | Baja | Medio | El `worker` no recibe sin `embedding` listo (§4.6); un mensaje retenido vuelve cada 180 s y va a la DLQ a la sexta recepción (~15 min de fallos seguidos); la alarma de DLQ avisa (infra §5.10). Se re-encola con *redrive* de la DLQ o, con BE-4.1, `POST /v1/admin/images/{id}/reprocesar`. La foto queda en `subida` (no en `error`) |
| R14 | boto3 en `api` (0,25 vCPU, 0,5 GB): memoria y tiempo de arranque | Media | Bajo | El cliente se crea una vez, en un hilo, al arrancar (§4.5); argon2id ya usa hasta 128 MiB (R12). Sin medir en `dev`: anotar la memoria de la tarea tras desplegar BE-2.1 |
| R16 | La búsqueda HNSW es aproximada: con muchos vectores, algún vecino exacto puede faltar en `vecinos` y en `/v1/localize`; con pocos, PostgreSQL puede no usar el índice (§4.8) | Media | Bajo | `ef_search` = 64 ≥ `k` (§4.8); la herramienta de evaluación de embeddings compara con fuerza bruta (`SERVICE_EMBEDDING/docs/ARCHITECTURE.md` §4.5); si el *recall* no alcanza, subir `LOC_EF_SEARCH` (variable de §5.10). `EXPLAIN` en `dev` con un dataset real: a verificar |
