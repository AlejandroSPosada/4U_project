# ARCHITECTURE — Backend (`BACKEND_FASTAPI`)

| Campo | Valor |
|---|---|
| Versión del documento | **0.7.0** (historia en [`CHANGELOG.md`](./CHANGELOG.md)) |
| Fecha | 2026-10-25 |
| Estado | En construcción: hay código de BE-1.1 a BE-1.3 (`project/`); lo de lotes posteriores es diseño propuesto |
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
| `api` | Endpoints HTTP, autenticación, firma de URLs, localización síncrona, encolar purgas y re-procesados, reconciliador de purgas | RDS, S3 (firmar), SQS (enviar), embedding |
| `worker` | Ingesta (miniatura + vector + estado) y purga (borrar objetos y filas) | RDS, S3 (leer, escribir, borrar), SQS (recibir), embedding |
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
    │   │   │   ├── dependencias.py  obtener_ajustes, obtener_motor, obtener_limitador_hash (BE-1.3, §4.4)
    │   │   │   └── v1/          Routers: salud (BE-1.1), auth y reservados (BE-1.3); __init__.py monta /admin y /collect con requiere_admin (§4.4). Después: localize, places, alerts, collect, admin_*
    │   │   ├── esquemas/        Modelos Pydantic de entrada y salida (son el contrato de §5.3–§5.5): errores, salud, auth (BE-1.3)
    │   │   ├── dominio/         Lógica pura y probable sin red ni base: enumerados.py, validaciones.py (BE-1.2 y BE-1.3; qué ofrecen, en §4.3 y §4.4); localizacion.py, geo.py, rumbo.py
    │   │   ├── servicios/       Casos de uso: migracion (BE-1.2); autenticacion, usuarios y auditoria (BE-1.3, §4.4); localizar, recolectar, ingerir, purgar, alertas, lugares, estadisticas
    │   │   ├── db/              modelos.py (SQLAlchemy), sesion.py (motor, conexiones y `transaccion`), esquema.py (§5.7 comprobable), qué ofrecen en §4.3 y §4.4; consultas (incluida la búsqueda vectorial)
    │   │   ├── clientes/        embedding.py (httpx), s3.py y sqs.py (boto3 en hilos de anyio)
    │   │   ├── seguridad/       hash.py (argon2id, §4.3), tokens.py (JWT, §5.2) y dependencias.py (requiere_admin), BE-1.3 (§4.4)
    │   │   ├── worker.py        Bucle de consumo de las colas (python -m app.worker)
    │   │   └── cli.py           python -m app.cli: migrar y verificar-esquema (BE-1.2), crear-usuario y desactivar-usuario (BE-1.3), limpiar-validacion (BE-2.1)
    │   └── ops/                 validate<fase><n>.py y comun.py: validadores de los lotes BE-x.y (§5.11)
    ├── migrations/              Alembic: env.py y versions/ (SQL explícito; 0001 = esquema inicial de §5.7)
    ├── tests/                   unit/, api/, contrato/ (vs §5), base/ (marca `base`: PostgreSQL efímero, §4.3) y ops/ (validadores)
    ├── docker-compose.yml       entorno `local` (§5.11)
    ├── Dockerfile               python:3.12-slim, usuario sin privilegios, puerto 8000 (§5.9)
    ├── .dockerignore            la imagen solo recibe src/app/, migrations/, pyproject.toml, uv.lock y .python-version
    ├── pyproject.toml           uv; ruff; pytest; grupo `ops` para los validadores
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

**`worker` provisional.** `backend.yml` despliega `api` y `worker` con la misma imagen (infra §5.9). Para que una tarea
de `worker` no falle al arrancar, en BE-1.1 `python -m app.worker` solo registra un latido cada 60 s (`evento = latido`,
`modo = sin_consumo`) y termina limpio con SIGTERM: **no consume las colas**. La ingesta llega con BE-2.2 (§4.6) y la
purga con BE-4.1 (§4.11). Hasta entonces, si el autoescalado lo enciende por mensajes en `ingesta` o `purga`, esos
mensajes siguen en la cola (igual que con la imagen de prueba de infra).

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
  `worker` creará el suyo con `DB_POOL_WORKER` (BE-2.2), y cada comando de la CLI usa uno sin pool.
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
0,25 vCPU, será más lento (**a verificar en dev**). No hay límite de intentos por cuenta: R7.

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
La app graba sin conexión y sube al terminar (vista 7.5 de la app). Secuencia:
1. `POST /v1/collect/videos` con los metadatos del recorrido y una referencia local (`ref_cliente`, p. ej.
   `rec_0003`). Idempotente por (admin, `ref_cliente`): reintentar no duplica el video.
2. `POST /v1/collect/videos/{id}/images` en lotes de hasta 50: registra cada foto (orden, coordenada, rumbo, hora) y
   devuelve una **URL prefirmada PUT** por foto pendiente. Las fotos ya subidas no reciben URL. Llamarlo de nuevo
   regenera URLs vencidas: así se retoma una subida interrumpida.
3. La app hace `PUT` de cada JPEG directo a S3 con el encabezado firmado `Content-Type: image/jpeg`.
4. S3 avisa a la cola `ingesta`; el `worker` continúa (BE-2.2).
5. `POST /v1/collect/videos/{id}/complete` marca la subida como terminada y devuelve el conteo por estado. La app
   consulta `GET /v1/admin/videos/{id}` para la barra de progreso; ese endpoint y `GET /v1/admin/videos` llegan con
   este lote (el resto de §5.5 sobre videos, con BE-4.1).

**Paso a `subida`.** Una foto pasa de `pendiente_subida` a `subida` cuando el `worker` recibe su evento de S3 (antes
de procesarla) o cuando `complete` comprueba con `HEAD` que el objeto ya está en S3; lo que ocurra primero. Así el
conteo es correcto aunque el `worker` esté apagado (con `embedding` apagado).

**Limpieza de datos de prueba.** `python -m app.cli limpiar-validacion` (§5.9) borra de forma definitiva —filas de
`videos`, `imagenes` y `embeddings`, y sus objetos de `dataset/` y `thumbs/`— los videos cuyo `nombre` y `ref_cliente`
empiezan por `validacion-`. Se ejecuta como tarea suelta con la definición de `worker`, que es la que puede borrar en
S3. Lo usan los validadores mientras no existe el borrado de BE-4.1 (§5.11); nunca toca otros videos.

La clave del objeto sigue el formato de infra §5.5 (`dataset/{video_id}/{imagen_id}.jpg`): el `worker` recupera la
fila de la imagen a partir de la clave sin otra consulta.

### 4.6 BE-2.2 — Worker de ingesta
Bucle con espera larga sobre `ingesta` (hasta 10 mensajes). Antes de recibir comprueba que `embedding` esté listo
(`GET /health/ready`); si no lo está, espera y no toma mensajes (evita que se agoten los 5 reintentos y caigan en la
DLQ mientras el modelo carga). Por cada objeto:
1. Decodifica la clave (las claves de los eventos S3 vienen codificadas como URL) y busca la imagen. Si no existe o
   su video está `eliminado`, borra el mensaje (la purga se ocupará del objeto).
2. Si la imagen ya está `procesada` con el mismo ETag, borra el mensaje (idempotencia ante eventos repetidos).
3. Descarga, valida (JPEG decodificable, ≤ 4 MB, lado menor ≥ 320 px), corrige la orientación EXIF, genera la
   miniatura en `thumbs/…` y una copia reducida en memoria (lado mayor `WORKER_LADO_EMBEDDING_PX`, JPEG calidad 90)
   para el modelo: así cada lote queda muy por debajo del límite de 16 MB de embeddings.
4. Agrupa hasta `WORKER_LOTE_EMBEDDING` (4) imágenes reducidas por llamada a `POST /v1/embed` (prioridad `baja`) y
   guarda cada vector en `embeddings` con la `version_vector` que devuelve el servicio. Lotes pequeños acotan lo que
   espera una localización que llega mientras se procesa un lote (embeddings no interrumpe un lote en curso). Si no
   coincide con la esperada (§5.10), no guarda y lo registra como
   error de configuración.
5. Marca la imagen `procesada` y recalcula el estado del video.

Errores **permanentes** (imagen corrupta, demasiado grande): imagen en `error` con el motivo, mensaje borrado.
Errores **transitorios** (embedding caído, base no disponible): el mensaje no se borra y vuelve a la cola tras la
visibilidad; al quinto intento va a la DLQ y la alarma avisa. Mensajes `reprocesar_imagen` (§5.8) siguen el mismo
camino a partir del paso 3.

### 4.7 BE-2.3 — Resumen del panel
`GET /v1/admin/stats` agrega totales en una consulta (fotos procesadas, lugares, alertas activas, último video). Las
«fotos pendientes de subir» del panel salen de la cola local de la app, no del backend.

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

### 4.9 BE-3.1 — Lugares y alertas (lectura pública y administración)
**Lectura pública.** `GET /v1/places` devuelve todos los lugares (decenas, sin paginación) con la distancia a la
posición si se envía.
`GET /v1/alerts` alimenta la caché local de la app, que debe funcionar sin conexión: sin `desde` entrega la foto
completa de alertas activas (incluidas las de vigencia futura, para que lleguen antes de empezar; la app filtra por
vigencia al anunciar); con `desde` entrega solo lo cambiado y los identificadores borrados
(*tombstones*, 90 días). La app guarda `generado_en` y lo envía como `desde` la próxima vez.

**Administración.**
- Lugares: CRUD con nombre único sin distinguir mayúsculas ni tildes. Al borrar un lugar, sus imágenes quedan sin
  lugar.
- Alertas: el editor de la app trabaja local primero y genera los UUID. `PUT /v1/admin/alerts/{id}` crea o reemplaza
  (idempotente); `DELETE` de un id desconocido responde `204` (así, una alerta creada y borrada antes de sincronizar
  no da error). `POST /v1/admin/alerts/sincronizar` aplica una lista de cambios independientes y devuelve el resultado
  de cada uno: la app quita de «pendientes» solo los que salieron `ok`. Control de concurrencia opcional con
  `If-Match: <version>`.

### 4.10 BE-3.2 — Localización (`POST /v1/localize`)
Algoritmo v1 (ADR-BE-08), con los parámetros de §5.10:
1. **Validar**: 1–5 fotos JPEG, cada una ≤ 1,5 MB; `rumbos` con el mismo largo que `fotos`.
2. **Vectorizar**: una sola llamada a `POST /v1/embed` con prioridad `alta`; las fotos no se guardan en ningún sitio
   (ADR-BE-06).
3. **Buscar**: por cada vector, los `LOC_TOP_K` vecinos por distancia coseno en el índice HNSW de la versión de vector
   activa (`SET LOCAL hnsw.ef_search`). Similitud = `1 − distancia`. Se descartan los vecinos con similitud menor que
   `LOC_SIM_MIN`.
4. **Agrupar** todos los vecinos (de todas las fotos) por cercanía geográfica: se recorren de mayor a menor
   similitud; cada uno se une al primer grupo cuyo centroide esté a menos de `LOC_RADIO_GRUPO_M`, o abre uno nuevo.
5. **Puntuar** cada grupo como la suma, sobre las fotos de la consulta, de la mejor similitud que esa foto aporta al
   grupo. Premia los lugares que coinciden con **varias direcciones** de la vuelta, no con una sola foto.
6. **Posición**: centroide del mejor grupo ponderado por `similitud ^ LOC_PESO_EXPONENTE`. Radio de incertidumbre =
   desviación ponderada de las distancias al centroide, con mínimo `LOC_RADIO_MIN_M`.
7. **Confianza** (0–1): `0,5 · s + 0,3 · c + 0,2 · m`, donde `s` es la mejor similitud del grupo normalizada entre
   `LOC_SIM_MIN` y `LOC_SIM_ALTA`; `c` la fracción de fotos con al menos una coincidencia en el grupo; `m` el margen
   relativo frente al segundo grupo. Nivel `alta`, `media` o `baja` según los cortes de §5.10.
8. **Corrección de rumbo**: para cada foto con coincidencia en el grupo, diferencia circular entre el rumbo de la foto
   del dataset y el rumbo informado por el teléfono. Si hay ≥ 2 y su dispersión circular es ≤ 30°, se devuelve la
   media como `correccion_rumbo_grados` (la app la suma a su brújula); si no, `null`.
9. **Contexto**: lugar más cercano a ≤ 60 m y hasta 3 referencias a ≤ 150 m con su rumbo absoluto desde la
   posición (la app lo convierte en «a tu derecha», «al frente»…).
10. Registra un evento anónimo en `eventos_localizacion` (sin fotos, sin identificadores del dispositivo).

Sin vecinos por encima del umbral (o dataset vacío) la respuesta es `200` con `resultado = "sin_coincidencias"`.
Presupuesto de tiempo: embedding ≤ `EMBEDDING_TIMEOUT_S` (5 s, límite duro; en `dev` se esperan ≤ 800 ms para 5
fotos, embeddings §5.7), búsquedas < 100 ms; objetivo p95 en el servidor ≤ 1 s con `embedding` encendido
(infra §5.10).

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
| `GET /v1/alerts` | Caché local de alertas (2.5, 6.3, 6.5) | BE-3.1 |
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

Errores: `400 FOTOS_INVALIDAS` (cantidad, tipo, tamaño o `rumbos` de distinto largo; `detalle.indice` señala la
foto), `503 EMBEDDING_NO_DISPONIBLE` (apagado, caído o sin respuesta en `EMBEDDING_TIMEOUT_S`), `503 BASE_NO_DISPONIBLE`.

#### `GET /v1/places`
Parámetros opcionales: `lat`, `lng` (ambos o ninguno), `categoria`.

`200` → `{"items": [LugarPublico…], "total": 6}`, ordenado por `distancia_m` si se envió posición; si no, por nombre.

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
`imagen_url` es una URL prefirmada de 1 h o `null`.

#### `GET /v1/alerts`
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
- `ref_cliente` (1–40 caracteres) es obligatorio. `nombre` opcional (1–40 tras recortar; vacío → `video_<numero>`).
  `total_fotos` ∈ [0, 200].
- `201` → `VideoResumen` (§5.5) con `estado = "pendiente"`. Si ya existe un video del mismo admin con ese
  `ref_cliente`: `200` con el mismo video (idempotente).

#### `POST /v1/collect/videos/{video_id}/images`
```json
{
  "imagenes": [
    { "orden": 1, "lat": 6.2001, "lng": -75.5786, "rumbo": 90.0, "capturada_en": "2026-10-20T14:00:05Z", "bytes": 345678 }
  ]
}
```
- 1 a 50 elementos; `orden` ∈ [1, 200] y único dentro del video; `bytes` ≤ 4 MB (4 194 304); `rumbo` puede ser `null`.
- `200`:
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
- Idempotente por (`video_id`, `orden`): repetir actualiza los metadatos mientras la foto siga `pendiente_subida` y
  devuelve URLs nuevas. Si la foto ya está `subida`, `procesada` o `error`, `subida` es `null`.
- La app sube con `PUT` a `url`, enviando **exactamente** los `encabezados` indicados y el JPEG como cuerpo. S3
  responde `200`; una URL vencida da `403` de S3 → pedir URLs de nuevo.
- Errores: `404 NO_ENCONTRADO`, `409 VIDEO_ELIMINADO`, `422 VALIDACION`.

#### `POST /v1/collect/videos/{video_id}/complete`
Sin cuerpo. Antes de responder hace `HEAD` en S3 de las fotos que siguen `pendiente_subida` y pasa a `subida` las que
ya existen (§4.5). `200` →
```json
{ "id": "…", "estado": "procesando", "conteo": { "pendiente_subida": 0, "subida": 37, "procesada": 83, "error": 0 } }
```
Repetirlo es seguro.

### 5.5 Endpoints de administración (requieren `admin`)

**Objetos comunes**

`VideoResumen`:
```json
{
  "id": "…", "numero": 12, "nombre": "Entrada norte", "estado": "procesado",
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
listados.

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
`url` y `url_miniatura` son prefirmadas GET de 1 h (`null` mientras no existan).

`LugarAdmin` = `LugarPublico` sin `distancia_m`, más `creado_en`, `actualizado_en` y `total_fotos`.

`AlertaAdmin` = `Alerta` más `creado_en`, `creado_por` y `actualizado_por` (`{id, nombre}`).

Lote que entrega cada grupo: `GET /v1/admin/videos` y `GET /v1/admin/videos/{id}`, BE-2.1; `GET /v1/admin/stats`,
BE-2.3; diagnóstico, BE-2.4; lugares y alertas, BE-3.1; el resto de videos y todas las de imágenes, BE-4.1.

| Método y ruta | Petición | Respuesta |
|---|---|---|
| `GET /v1/admin/stats` | — | `200` `{"total_fotos": 2842, "total_lugares": 48, "alertas_activas": 3, "ultimo_video": {"numero": 12, "creado_en": "…"} \| null}`. `total_fotos` = imágenes `procesada` de videos no eliminados |
| `GET /v1/admin/videos` | `?q=&orden=fecha\|nombre\|fotos&dir=desc\|asc&pagina&por_pagina` | Página de `VideoResumen` |
| `GET /v1/admin/videos/{id}` | — | `VideoResumen` + `"fotos": [ImagenAdmin…]` en orden |
| `PATCH /v1/admin/videos/{id}` | `{"nombre": "Entrada norte"}` (1–40 tras recortar) | `200` `VideoResumen` |
| `DELETE /v1/admin/videos/{id}` | — | `202` `{"id": "…", "estado": "eliminado", "fotos_retiradas": 120, "purga": "programada"}`. Repetir da la misma respuesta |
| `GET /v1/admin/images` | `?video_id&lugar_id&estado&calidad&q&pagina&por_pagina` | Página de `ImagenAdmin`, por video (más reciente primero) y `orden` |
| `GET /v1/admin/images/{id}` | — | `ImagenAdmin` + `"video": {id, numero, nombre}` + `"vector": {"version_vector", "creado_en"} \| null` |
| `PATCH /v1/admin/images/{id}` | Cualquiera de: `lat`+`lng` (juntos), `lugar_id` (o `null`), `calidad`, `notas` (≤ 500) | `200` `ImagenAdmin` |
| `DELETE /v1/admin/images/{id}` | — | `204`. Retira el vector al instante y encola `purgar_imagen` |
| `POST /v1/admin/images/lote` | `{"accion": "eliminar" \| "reasignar", "ids": [≤ 200], "lugar_id": "…" \| null}` | `200` `{"procesadas": 10, "fallidas": [{"id": "…", "codigo": "NO_ENCONTRADO"}]}` |
| `POST /v1/admin/images/{id}/reprocesar` | — | `202`; la imagen vuelve a `subida` y se encola `reprocesar_imagen` |
| `GET /v1/admin/places` | `?q=&categoria=` | `{"items": [LugarAdmin…], "total": n}` |
| `POST /v1/admin/places` | `LugarEntrada` | `201` `LugarAdmin` |
| `PUT /v1/admin/places/{id}` | `LugarEntrada` | `200` `LugarAdmin` |
| `DELETE /v1/admin/places/{id}` | — | `204`; sus imágenes quedan con `lugar = null` |
| `GET /v1/admin/alerts` | `?q=&tipo=&prioridad=&activa=` | `{"items": [AlertaAdmin…], "total": n}` (sin borradas) |
| `PUT /v1/admin/alerts/{id}` | `AlertaEntrada`; opcional `If-Match: <version>` | `201` si se creó, `200` si se reemplazó; cuerpo `AlertaAdmin` |
| `DELETE /v1/admin/alerts/{id}` | — | `204`, también si no existe |
| `POST /v1/admin/alerts/sincronizar` | `{"cambios": [{"op": "upsert", "alerta": {"id": "…", …AlertaEntrada}}, {"op": "eliminar", "id": "…"}]}` (≤ 100) | `200` `{"generado_en": "…", "resultados": [{"id": "…", "op": "upsert", "estado": "ok" \| "error", "codigo": null \| "VALIDACION"}]}` |
| `GET /v1/admin/stats/uso` | — | BE-5.2 (hasta entonces `501`) |
| `POST /v1/admin/diagnostico/vecinos` | `multipart/form-data` con una foto; `?k=` | Ver abajo (BE-2.4) |

`LugarEntrada`: `nombre` (2–80), `categoria`, `lat`, `lng`, `alias` (≤ 20 textos de ≤ 60), `descripcion` (≤ 300),
`referencias` (≤ 300). Nombre único sin distinguir mayúsculas ni tildes → `409 NOMBRE_DUPLICADO`.

`AlertaEntrada`: `lat`, `lng`, `mensaje` (1–200 tras recortar), `tipo` (por defecto `otro`), `prioridad` (por defecto
`normal`), `radio_m`
(5–100, por defecto 15), `activa` (por defecto `true`), `vigencia_desde`, `vigencia_hasta` (si ambas,
`hasta > desde`). En `sincronizar`, cada cambio es independiente: un error no revierte los demás.

#### `POST /v1/admin/diagnostico/vecinos`
`multipart/form-data` con una sola parte `foto` (`image/jpeg`, ≤ `LOC_MAX_BYTES_FOTO`, las mismas reglas que una foto
de `/v1/localize`). Parámetro `k` en la URL: entero de 1 a 50, por defecto 5.

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

Errores: `400 FOTOS_INVALIDAS` (falta la foto, tipo o tamaño; `detalle.indice = 0`), `422 VALIDACION` (`k`),
`503 EMBEDDING_NO_DISPONIBLE`, `503 BASE_NO_DISPONIBLE`, y los de §5.2 y `403 SIN_PERMISOS`.

### 5.6 Códigos de error

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `SOLICITUD_INVALIDA` | Cuerpo mal formado (JSON inválido, multipart roto) |
| 400 | `FOTOS_INVALIDAS` | `/v1/localize` y `/v1/admin/diagnostico/vecinos`: cantidad, tipo o tamaño de fotos, o `rumbos` incoherente |
| 401 | `NO_AUTENTICADO` · `TOKEN_INVALIDO` · `TOKEN_EXPIRADO` | §5.2 (con `WWW-Authenticate: Bearer`) |
| 401 | `CREDENCIALES_INVALIDAS` | Login fallido (cuerpo fijo, §5.3) |
| 403 | `SIN_PERMISOS` | Token válido de un usuario activo sin rol `admin` (§5.2) |
| 404 | `NO_ENCONTRADO` | Recurso inexistente (o video eliminado en rutas de lectura); también una ruta que no existe |
| 405 | `SOLICITUD_INVALIDA` | Método no permitido en una ruta que existe; `detalle.metodos_permitidos` (p. ej. `["GET"]`) y encabezado `Allow` |
| 409 | `NOMBRE_DUPLICADO` · `VIDEO_ELIMINADO` · `CONFLICTO_VERSION` | Lugar repetido · subir fotos a un video borrado · `If-Match` no coincide |
| 422 | `VALIDACION` | Campos fuera de rango; `detalle.campos` = `[{"campo": "radio_m", "motivo": "…"}]` |
| 500 | `ERROR_INTERNO` | Fallo no previsto (el `X-Request-Id` permite encontrarlo en los logs) |
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
| `eliminada_en` | `timestamptz` | sí | | *tombstone*: borrar fija `eliminada_en` y `actualizado_en`, así `GET /v1/alerts?desde=` usa el mismo índice; las borradas hace más de 90 días se eliminan físicamente |

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
| `subida_completa_en` | `timestamptz` | sí | | |
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
| `bytes` | `integer` | sí | | ≥ 0; tamaño real en S3 |
| `etag` | `text` | sí | | |
| `ancho`, `alto` | `smallint` | sí | | > 0; tras corregir EXIF |
| `estado` | `estado_imagen` | | `pendiente_subida` | índice `imagenes_estado_idx` |
| `error` | `text` | sí | | motivo legible; no nulo si y solo si `estado = 'error'` (`imagenes_error_check`) |
| `intentos` | `smallint` | | `0` | ≥ 0 |
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
borra.

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
| `worker` | `python -m app.worker` | — | proceso vivo; registra un latido cada 60 s (en BE-1.1 solo eso, §4.2) |
| `migrate` | `python -m app.cli migrar` (§4.3) | — | código de salida 0 = migrado y admin inicial en orden; 1 = falló una migración o el admin inicial, o esperó más de 5 min a otro `migrar`; 2 y 3, abajo |
| Verificación de esquema (tarea suelta con la definición de `migrate`) | `python -m app.cli verificar-esquema` (compara la base con §5.7 en una transacción de solo lectura) | — | código de salida 0 = coincide; 1 = difiere (un evento `esquema_diferencia` por diferencia); 2 = no se pudo verificar (base no disponible o error al leer el catálogo); 3, abajo |
| Usuarios (tarea suelta con la definición de `migrate`; BE-1.3) | `python -m app.cli crear-usuario --correo X --nombre Y [--rol admin\|user]`. Si el correo existe, actualiza nombre, contraseña y, si se pasa `--rol`, rol (sin `--rol` conserva el suyo), y lo reactiva; un usuario nuevo sin `--rol` es `user`. Resultado: evento `usuario_guardado` (`resultado` = `creado` \| `actualizado`) | — | 0 = hecho; 1 = dejaría sin ningún admin activo (`usuario_rechazado`) u otro error de la base (`comando_fallido`); 2 y 3, abajo |
| | `python -m app.cli desactivar-usuario --correo X`. Resultado: evento `usuario_desactivado` | — | 0 = desactivado (también si ya lo estaba); 1 = no existe (`usuario_no_encontrado`), dejaría sin ningún admin activo (`usuario_rechazado`) u otro error (`comando_fallido`); 2 y 3, abajo |
| Limpieza de pruebas (tarea suelta con la definición de `worker`) | `python -m app.cli limpiar-validacion [--video ID …]` (§4.5): sin `--video`, todos los videos `validacion-`; con `--video`, solo esos, y se niega (código 1) si alguno no lleva el prefijo. Imprime `LIMPIEZA {"videos": n, "objetos": m}` | — | código 0 = hecho |

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

**Códigos de salida de `python -m app.cli`**, comunes a todos los comandos. Sus logs son líneas JSON de §5.10 con
`proceso = migrate`; todos informan su resultado solo como eventos de log (desde BE-1.3, también `crear-usuario`).
La excepción es un error en los argumentos: argparse escribe el uso y el error en texto por stderr, sin evento.

| Código | Significado |
|---|---|
| 0 | Hecho (en `verificar-esquema`, la base coincide) |
| 1 | Resultado negativo: el que diga cada comando arriba (difiere, falló, no existe) |
| 2 | No se pudo trabajar con la base: no se pudo abrir la conexión (red, DNS, TLS, credenciales, permiso `CONNECT`, base inexistente, tiempo agotado) o se perdió después (evento `base_no_disponible`). En `verificar-esquema`, también un error que impide comparar sin ser de conexión: al leer el catálogo, al cargar las migraciones o al esperar más de 5 min a un `migrar` en curso (evento `verificacion_fallida`) |
| 3 | Uso o configuración: argumentos (argparse daría 2; aquí es 3; escribe el uso y el error en texto por stderr, sin evento), una variable con un valor no válido (p. ej. `DB_PORT=abc`), `DB_*` que faltan, `ADMIN_INICIAL_*` cuando hay que crear el admin o la contraseña de `crear-usuario` (evento `configuracion_incompleta`) |

Variables que lee: las de infra §5.4 para `api`, `worker` y `migrate`, `APP_COMMIT`, que fija la imagen, y
`CREAR_USUARIO_PASSWORD` (solo `crear-usuario`). `api` necesita `JWT_SECRET` (infra §5.4) para el login y las rutas
protegidas: sin ella arranca, pero esas rutas responden `500` (§5.2); con menos de 32 bytes, PyJWT avisa
(`InsecureKeyLengthWarning`, en texto por stderr). Ningún otro valor es obligatorio; los parámetros de §5.10 tienen valor por defecto en `config.py` y pueden sobrescribirse con
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
| `EMBEDDING_VERSION_VECTOR` | `dinov2-vits14/pp-v1` | Debe coincidir con `GET /v1/info` de embeddings. Se comprueba en la primera llamada tras cada arranque del servicio y cada 10 min (no al arrancar `api`, porque embeddings puede estar apagado); si no coincide, no se usa el servicio y `/v1/health/ready` lo informa |
| `EMBEDDING_TIMEOUT_S` / `EMBEDDING_CONNECT_TIMEOUT_S` | 5 / 3 | Un reintento solo si la conexión fue rechazada. 5 s deja margen sobre los ≤ 800 ms esperados para 5 fotos en `dev` (embeddings §5.7); si hace falta, se sube con la variable del mismo nombre |
| `LOC_MAX_FOTOS` / `LOC_MAX_BYTES_FOTO` | 5 / 1 572 864 (1,5 MB) | |
| `LOC_TOP_K` / `LOC_EF_SEARCH` | 10 / 64 | Por foto |
| `LOC_SIM_MIN` / `LOC_SIM_ALTA` | 0,55 / 0,80 | **Iniciales: se calibran en BE-3.2 con el conjunto de evaluación de EMB-3.2** |
| `LOC_RADIO_GRUPO_M` / `LOC_PESO_EXPONENTE` / `LOC_RADIO_MIN_M` | 20 / 4 / 5 | |
| `LOC_NIVEL_ALTA_MIN` / `LOC_NIVEL_MEDIA_MIN` (cortes de nivel) | 0,70 / 0,45 | `alta` ≥ 0,70 · `media` ≥ 0,45 · `baja` < 0,45. Iniciales |
| `LOC_DISPERSION_RUMBO_MAX` | 30° | Para devolver `correccion_rumbo_grados` |
| `LOC_LUGAR_CERCANO_M` / `LOC_REFERENCIAS_M` / `LOC_REFERENCIAS_MAX` | 60 / 150 / 3 | |
| `REC_MAX_FOTOS_VIDEO` / `REC_MAX_LOTE` | 200 / 50 | 200 coincide con `MAX_FOTOS_VIDEO` de la app |
| `REC_MAX_BYTES_FOTO` / `REC_LADO_MIN_PX` | 4 194 304 (4 MB) / 320 | Se valida en el `worker` (una URL PUT no limita tamaño) |
| `PRESIGN_PUT_TTL_S` / `PRESIGN_GET_TTL_S` | 900 / 3600 | |
| `MINIATURA_LADO_PX` / `MINIATURA_CALIDAD` | 320 / 80 | |
| `WORKER_MAX_MENSAJES` / `WORKER_LOTE_EMBEDDING` | 10 / 4 | Embeddings admite hasta 8; se usan 4 para no retrasar la localización |
| `WORKER_LADO_EMBEDDING_PX` | 1024 | Copia reducida que se envía al modelo (el original y la miniatura no cambian) |
| `WORKER_ESPERA_EMBEDDING_S` | 15 | Pausa entre comprobaciones de `/health/ready` |
| `RECONCILIADOR_CADA_MIN` | 10 | Purgas pendientes |
| `ALERTAS_TOMBSTONE_DIAS` / `EVENTOS_RETENCION_DIAS` | 90 / 180 | Limpieza diaria desde `api` |
| `PAGINA_POR_DEFECTO` / `PAGINA_MAX` | 24 / 100 | 24 coincide con `FOTOS_POR_PAGINA` de la Galería |
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
| `worker_iniciado` / `latido` / `worker_detenido` | `worker` | Al iniciar: `version`, `commit`, `entorno`, `modo`; en cada latido: `modo` | Arranque, cada 60 s y parada. `modo = sin_consumo` hasta BE-2.2 |
| `base_no_disponible` | `api`, `migrate` | `motivo` (clase y mensaje del error, sin secretos) | La base no respondió. En `api`, en `/v1/health/ready` y, desde BE-1.3, en cualquier endpoint que la use (`WARNING`; responde `503`); en `migrate`, la CLI termina con 2 (`ERROR`) |
| `configuracion_incompleta` | `migrate`, `api` | `faltan`, `invalidas` (nombres de variables o, para la contraseña de `crear-usuario`, `CREAR_USUARIO_PASSWORD` o `terminal`), `motivo` (sin el valor recibido) | En `migrate`: faltan `DB_*` (o `ADMIN_INICIAL_*` cuando hay que crear el admin), una variable tiene un valor no válido, como `DB_SSLMODE` o `DB_PORT`, o falta o no vale la contraseña de `crear-usuario` (`ERROR`); la CLI termina con 3. En `api` (BE-1.3): falta `JWT_SECRET` en un login o una ruta protegida (`ERROR`; responde `500`) |
| `login` | `api` | `resultado` (`exito` \| `fallo` \| `rechazado`), `motivo` (`null` \| `correo_desconocido` \| `password_incorrecta` \| `usuario_inactivo` \| `cola_llena` \| `espera_agotada`), `usuario_id` (`null` si el correo no existe o no se buscó) | Cada `POST /v1/auth/login` con el cuerpo válido que llega a la cola del hash (`INFO` si entró; `WARNING` si no). `rechazado` = `503 SERVICIO_OCUPADO`, sin fila de auditoría. Nunca el correo escrito ni la contraseña |
| `autorizacion_rechazada` | `api` | `codigo` (`NO_AUTENTICADO`, `TOKEN_INVALIDO`, `TOKEN_EXPIRADO`, `SIN_PERMISOS`), `usuario_id` (el `sub` si el token era válido; si no, `null`) | `requiere_admin` rechaza una petición (`INFO`) |
| `usuario_guardado` | `migrate` | `resultado` (`creado` \| `actualizado`), `usuario_id`, `rol`, `reactivado`, `rol_anterior` (solo al actualizar) | `crear-usuario` terminó con 0 |
| `usuario_desactivado` | `migrate` | `usuario_id`, `ya_estaba_inactivo` | `desactivar-usuario` terminó con 0 |
| `usuario_no_encontrado` | `migrate` | — | `desactivar-usuario` con un correo que no existe (`WARNING`); termina con 1 |
| `usuario_rechazado` | `migrate` | `motivo` | `crear-usuario` o `desactivar-usuario` dejaría sin ningún admin activo (`ERROR`); termina con 1 |
| `comando_fallido` | `migrate` | `comando`, `motivo` (y la traza en `excepcion`) | Error de `crear-usuario` o `desactivar-usuario` que no es de conexión (p. ej. la base sin migrar) (`ERROR`); termina con 1 |
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
- La comprobación de disco de BE-3.2 usa ECS Exec sobre la tarea de `api` (infra §3.4).
- Los que necesitan `embedding` (ingesta, localización) lo encienden si está apagado, esperan hasta 10 min a
  `"embedding": "ok"` en `/v1/health/ready` y al terminar lo dejan como lo encontraron (infra §5.11). Como a las 22:00
  (hora de Bogotá) se apaga solo, cada uno declara la hora límite para empezar.
- Los mensajes y objetos se comprueban con las APIs de SQS y S3; los logs, con CloudWatch Logs.
- La localización (BE-3.2) usa el conjunto de consulta de `evaluacion/` (infra §5.5) que prepara EMB-3.2.
- Lo que devuelve el índice para una foto concreta (por ejemplo, que un video borrado ya no aparece) se ve con
  `POST /v1/admin/diagnostico/vecinos` (§5.5).

**Código común (`project/src/ops/comun.py`)**. Lo usan todos los `validate<fase><n>.py`:
- `Validador(lote="BE-x.y", validacion="validation-x-y", entornos=("dev", …), descripcion=__doc__)`. `iniciar()` lee
  `--entorno local|dev`, `--informe <ruta>`, `--solo C1,C3` y `--sin-limpieza`; un error de uso o un entorno que el
  validador no admite terminan con 3. `ejecutar(precondiciones=[("P1", f), …], comprobaciones=[("C1", f), …],
  manuales=[("M1", "instrucción"), …], limpieza=f)` sigue el orden del contrato común, imprime una línea por
  precondición y comprobación (`[PASA] C1 …`), escribe el informe JSON (por defecto en
  `project/.validacion/<lote>-<AAAAMMDD-HHMMSS>.json`, que git ignora) y devuelve el código de salida.
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
  de prueba), y `familia` (`FAMILIA_MIGRATE` o
  `FAMILIA_VALIDACION`) elige el log group y el prefijo del stream. Espera hasta 900 s a que la tarea pare y devuelve
  un `ResultadoTarea`: `id`, `arn`, `definicion` (ARN de la revisión), `codigo` (salida del contenedor `app`; `None` si
  no llegó a correr), `motivo`, `lineas` (el log) y `eventos(nombre)` (las líneas JSON de §5.10, todas o las de un
  evento). `leer_log(logs, grupo, stream)` lee un stream desde el principio y, mientras no exista o esté vacío, lo
  intenta hasta 12 veces, con 5 s entre intentos (`[]` si nunca llega). Al lanzar la tarea o leer el log, un error de
  AWS por falta de permiso es `ErrorConfiguracion` y cualquier otro, `Falla`; un error mientras espera a que pare
  también es `Falla` («no se detuvo en 900 s»), y uno de `describe-tasks` llega sin convertir.

Ayudas de BE-1.3 (para los validadores que inician sesión o usan la CLI; las de BE-2.1 y BE-3.1 las reutilizan):

| Elemento | Qué hace |
|---|---|
| `leer_secreto(sesion, secreto, lote="INF-1.2")` → `dict` | JSON de un secreto de Secrets Manager. Sin permiso → `ErrorConfiguracion`; no existe → `PrecondicionNoCumplida` del `lote`; no es un objeto JSON → `ErrorConfiguracion`. Constantes `SECRETO_ADMIN` (`campus-locator/dev/admin-inicial`) y `SECRETO_JWT` (`campus-locator/dev/jwt`) |
| `credenciales_admin(entorno, sesion=None)` → `(correo, password)` | `VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` si están las dos; si no y es `dev`, las claves `correo` y `password` de `SECRETO_ADMIN`; si no, `ErrorConfiguracion` |
| `ClienteApi(url_base, http=None, dormir=time.sleep, reloj=time.monotonic)` | `pedir(metodo, ruta, token=None, **kwargs)` (ruta relativa a la URL con `/v1`; `token` añade `Authorization: Bearer`; un `429` **de API Gateway** se reintenta tras 1, 2, 4 y 8 s, y un `500 {"message": "Internal Server Error"}` **de API Gateway** —`api` sin instancias en Cloud Map, infra §5.13: la petición no llegó al backend— tras 2, 4 y 8 s; si no ceden, se devuelve el último; los 429 y 500 del backend (formato §5.1) no se reintentan; `reintentos_429`, `reintentos_500`); `login(correo, password)` (`POST /auth/login` con al menos `PAUSA_LOGIN_S` = 0,6 s desde el anterior, por el *throttling* de 2 req/s de infra §5.10; cuenta `logins_ok` y `logins_fallidos`); `token(correo, password, quien=…)` (el token de un 200, o `Falla` con el código, y con «¿está desplegado BE-1.3?» ante un 404); `ultima_duracion_ms`, `reintentos_429`, `cerrar()`. `http` es un `httpx.Client` (15 s) o, en las pruebas, un objeto con `request()` y `close()` |
| `es_respuesta_api_gateway(r)`, `codigo_error(r)`, `describir_respuesta(r)` | ¿Cuerpo `{"message": …}` de API Gateway (infra §5.13)?; `error.codigo` o `None`; texto corto para un detalle (`401 CREDENCIALES_INVALIDAS`, `429 (API Gateway)`), nunca el cuerpo |
| `EntornoBackend(entorno, sesion=None, outputs=None, iniciada_por="validacion", dormir=time.sleep)` | `cli(argumentos, entorno=None)` → `ResultadoTarea`: en `local`, `docker compose run --rm -T [-e VAR…] api python -m app.cli …` desde `project/`, con los valores solo en el entorno del proceso; en `dev`, tarea suelta con la última revisión de `campus-locator-dev-migrate`, que debe usar la imagen del servicio `api` (si no, `Falla`: `backend.yml` no terminó). `sql(consulta)` → líneas de `psql -tAc` (en `local`, `docker compose exec -T db psql -U campus_app -d campus_locator`; en `dev`, la tarea `campus-locator-dev-validacion`) o `Falla` si `psql` no termina con 0. También `imagen(definicion)` → `(arn, imagen)` y `revision_migrate()`. `outputs` es una función que devuelve los outputs (por defecto, `outputs_terraform`) |
| `motivo_cli(resultado)` | Por qué un `app.cli` no dio 0, a partir de sus eventos (`base_no_disponible`, `configuracion_incompleta`, `comando_fallido`, `usuario_rechazado`, `usuario_no_encontrado`, `migracion_fallida`, `verificacion_fallida`) |
| `USUARIO_VALIDACION`, `crear_usuario_validacion(backend)` → contraseña, `desactivar_usuario_validacion(backend, tolerar_inexistente=False)` → detalle | El usuario de prueba de rol `user` (abajo): `crear-usuario --rol user` con una contraseña aleatoria `validacion-pw-<uuid>` en `CREAR_USUARIO_PASSWORD` (se devuelve, nunca se imprime) y `desactivar-usuario`; `Falla` con `motivo_cli` si no terminan con 0. Con `tolerar_inexistente` (para la limpieza), «no existe» (1 con `usuario_no_encontrado`) no es un fallo |

`validate13.py` es el ejemplo de uso: el `Contexto` crea `ClienteApi` y `EntornoBackend` en P2, pide los tokens la
primera vez que una comprobación los necesita (así `--solo` funciona) y, en `limpieza`, desactiva el usuario de prueba
si pudo quedar activo. Marca «pudo quedar activo» **antes** de lanzar `crear-usuario`: si la tarea reactiva al usuario
y después falla la espera o la lectura del log, la limpieza lo desactiva igual (y si no llegó a crearlo, lo tolera). Sus funciones `partes_jwt`, `firma_valida`, `firmar` y `alterar_firma` hacen el HMAC a mano,
sin la biblioteca del backend; `alterar_firma` cambia un carácter **del medio** de la firma, porque el último puede
codificar solo bits de relleno de base64url y no cambiarla.

**Datos de prueba**: videos con `ref_cliente` y `nombre` que empiezan por `validacion-` (con coordenadas fuera del
campus, para no mezclarse con el dataset real), lugares cuyo nombre empieza por `validacion-`, alertas cuyo mensaje
empieza por `validacion-`, y un usuario `validacion+user@campus.edu.co` de rol `user` para las pruebas de permisos.

**Limpieza**

| Qué | Cómo se borra |
|---|---|
| Lugares y alertas | Con sus `DELETE` de §5.5 (BE-3.1) |
| Videos de prueba, antes de BE-4.1 | `limpiar-validacion --video <id> …` en una tarea suelta con la definición `campus-locator-dev-worker` (§5.9) |
| Videos de prueba, con BE-4.1 hecho | `DELETE /v1/admin/videos/{id}`; su purga limpia S3 |
| Usuario `validacion+user@campus.edu.co` | Lo crea o reactiva `crear-usuario --rol user` (contraseña aleatoria en `CREAR_USUARIO_PASSWORD`, nunca impresa) y lo desactiva `desactivar-usuario` al terminar, ambos en una tarea suelta de `migrate` (en `local`, con `docker compose run`): `crear_usuario_validacion` y `desactivar_usuario_validacion` de `comun.py`. La fila queda inactiva entre ejecuciones; reactivarla devuelve la validez a sus tokens sin vencer (§5.2), que solo tuvo el validador |

Al empezar, cada validador que crea videos borra los `validacion-` que haya dejado una ejecución interrumpida
(`limpiar-validacion` sin `--video`, o los `DELETE` si BE-4.1 está hecho). Las filas de `auditoria` que generan las
pruebas se conservan (son registro) y las de `eventos_localizacion` caducan a los `EVENTOS_RETENCION_DIAS` (§5.10).

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
reevaluará con los resultados de EMB-3.2. Los parámetros son iniciales y se calibran con datos reales.

**ADR-BE-09 — Vectores en tabla propia con `version_vector` e índice HNSW parcial por versión (aceptada).**
Permite indexar con un modelo o preprocesamiento nuevo en paralelo y cambiar de versión sin tiempo fuera de servicio.

**ADR-BE-10 — Alertas con id del cliente, `PUT` idempotente, *tombstones* y sincronización por diferencias
(aceptada).** Encaja con el editor «local primero» de la app (7.8) y con la caché sin conexión del flujo público (2.5).

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

---

## 7. Riesgos

| ID | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | La precisión de ubicación no alcanza (dataset escaso, cambios de luz, lugares parecidos) | Alta | Alto | Conjunto de evaluación (EMB-3.2), calibrar umbrales, confianza honesta (`baja` → repetir), cobertura visible en el panel |
| R2 | `/v1/localize` supera 1 s en el servidor | Media | Medio | Modelo pequeño (ViT-S/14) en 2 vCPU (infra ADR-INF-14); medir en EMB-3.1 y BE-3.2; fotos de 1024 px; palancas de embeddings §4.4 |
| R3 | La ingesta retrasa la localización (un solo servicio de embeddings, que no interrumpe un lote en curso) | Media | Medio | Prioridad `alta` para localización (embeddings §5.2); lotes de 4 imágenes reducidas en el `worker` |
| R4 | Una URL PUT permite subir archivos enormes | Baja | Bajo | URL de 15 min ligada a una clave; el `worker` rechaza > 4 MB y la purga los borra |
| R5 | Rumbos de fuentes distintas (magnético vs. verdadero) | Alta | Medio | ADR-BE-12; lote del frontend para convertir en el escaneo |
| R6 | Eventos de S3 duplicados o fuera de orden | Media | Bajo | Idempotencia por imagen y ETag |
| R7 | Fuerza bruta contra el login | Baja | Alto | *Throttling* de API Gateway (aproximado y común a todos los clientes: frena volumen, no intentos sueltos, infra §3.3), argon2id, auditoría de cada intento con su motivo (`usuario.login`, §5.7), alarma de 5xx. **Sin límite de intentos por cuenta:** infra lo propone (su CHANGELOG 0.12.0 y R10: 5 fallos en 15 min por correo → `429` con `Retry-After` durante 15 min, fallos en PostgreSQL); no entra en BE-1.3 y está pendiente de decisión. Si se adopta, cambia §5.3 (un error nuevo del login) y la app lo consume |
| R8 | Reloj del teléfono desajustado (`capturada_en`) | Media | Bajo | El servidor guarda `creado_en` propio; `capturada_en` solo informa |
| R9 | `db.t4g.micro` se queda corto (memoria del índice, conexiones) | Baja | Medio | Pools pequeños; ver infra R4 |
| R10 | Formatos de error distintos cuando responde API Gateway | Alta | Bajo | §5.1 lo documenta; la app decide por código HTTP |
| R11 | El texto del catálogo (restricciones, índices) cambia con una versión mayor de PostgreSQL y `verificar-esquema` da diferencias que no lo son | Baja | Bajo | RDS actualiza por su cuenta solo la versión menor (infra §3.5); CI usa la misma mayor (`pg17`) y prueba que la migración deja exactamente `esquema.py`; un cambio de mayor actualiza `esquema.py` en el mismo cambio |
| R12 | argon2id en 0,25 vCPU: login lento, falta de memoria o el *health check* sin CPU con varios a la vez | Media | Medio | Como mucho `LOGIN_HASH_CONCURRENTES` (2) a la vez, fuera de la base, 64 MiB cada uno; como mucho 8 más esperando y 10 s de espera (luego `503 SERVICIO_OCUPADO`, §4.4). En `local` tarda ~92 ms; en `dev`, **a verificar** (C2 de `validate13.py` informa los tiempos). **Riesgo que queda:** con un flujo sostenido de logins, las dos verificaciones argon2 (t = 3, 64 MiB, p = 4) pueden ocupar los 0,25 vCPU y retrasar `GET /v1/health`; si el *health check* del contenedor (cada 30 s, 5 s de plazo, 3 fallos, infra §5.7) falla, ECS reinicia la tarea. Sin comprobar. Palancas: `LOGIN_HASH_CONCURRENTES = 1`, bajar los parámetros de argon2 (los hashes viejos siguen verificándose, §4.3) o el límite por cuenta de R7 |
