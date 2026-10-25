# CHANGELOG — Backend (`BACKEND_FASTAPI`)

Una entrada por versión de [`ARCHITECTURE.md`](./ARCHITECTURE.md), la más reciente primero.

**Cómo se numera la versión del documento**
- **Mayor:** cambio incompatible en un contrato de §5 (renombrar un campo, cambiar un código de error, quitar un
  endpoint, cambiar el formato de un mensaje). Mientras la versión sea `0.x`, un cambio incompatible sube la **menor**.
- **Menor:** endpoint, campo opcional, tabla o mensaje nuevos; decisión nueva (ADR); parámetros calibrados.
- **Parche:** aclaraciones o correcciones de redacción sin efecto en contratos.

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

## [0.6.0] — 2026-10-24

- **Lote que la motivó:** BE-1.2 (Base de datos y migraciones).
- **Qué cambió:**
  - §4.1: estructura real de `db/`, `cli.py`, `servicios/migracion.py`, `dominio/`, `migrations/` y `tests/base/`.
  - §4.2: `backend.yml` instala el grupo `ops`, prueba con un PostgreSQL efímero y registra también la revisión de
    `migrate`.
  - §4.3: cómo funcionan el motor (TLS, tiempo de conexión, `api` arranca sin base), `migrar` (bloqueo consultivo,
    transacción, admin inicial solo si no hay ninguna fila `admin`, conflicto si el correo es de un `user`),
    `verificar-esquema` (solo lectura, eventos), la coherencia migración/modelos/`esquema.py`, las pruebas con base
    (`PRUEBAS_DB_URL`, `PRUEBAS_DB_OBLIGATORIA`) y el paso `migrate` de `backend.yml` con los permisos de `gha-deploy`.
  - §4.1 y §5.10: los logs tampoco llevan valores de sentencias SQL (`hide_parameters`, `DETAIL` de PostgreSQL omitido en
    las trazas).
  - R11: el texto del catálogo depende de la versión mayor de PostgreSQL.
  - `validation/validation-1-2.md`: qué precondiciones se evalúan en cada entorno, C1 exige que el segundo `migrar` no
    aplique nada, C2 copia los eventos `esquema_diferencia` y distingue el código 2, detalles de las tareas sueltas
    (`startedBy`, streams), herramientas y cómo se ve una ejecución sin despliegue previo.
  - PLAN: alineado con 0.6.0; BE-1.2 pasa a «En curso».
- **Contratos tocados (§5):**
  - §5.7 (completa lo que no fijaba; `verificar-esquema` compara contra exactamente esto): nulabilidad y valores por
    defecto de todas las columnas; restricciones `CHECK` (rangos y longitudes de §5.7, WGS84, rumbo, no negativos,
    `s3_key = dataset/{video_id}/{id}.jpg`, `imagen_key = lugares/{id}.jpg`, coherencia del borrado de videos, `error`
    solo con `estado = 'error'`, `vigencia_hasta > vigencia_desde`, `detalle` objeto); nombres de restricciones e índices
    con la convención de PostgreSQL; índices nuevos `imagenes_lugar_id_idx` (ya decía «índice») y
    `eventos_localizacion_creado_en_idx` (retención); secuencias `videos_numero_seq` (`integer`),
    `eventos_localizacion_id_seq` y `auditoria_id_seq`; `origen`, `resultado` y `nivel` de `eventos_localizacion` como
    `text` con `CHECK` (no tipos enumerados); FK de `auditoria.actor_id` a `usuarios`; `alembic_version`.
  - §5.3 `GET /v1/health/ready`: desaparece `db = no_configurada` (solo existía en BE-1.1); sin `DB_*` o sin respuesta
    de la base en `DB_CONNECT_TIMEOUT_S`, `503 BASE_NO_DISPONIBLE`. La app no usa este endpoint (§5.3: diagnóstico).
  - §5.9: rutas de la imagen (`/srv/app`, `/srv/migrations`), códigos de salida de `migrar` y `verificar-esquema` y
    tabla común de `python -m app.cli` (0 hecho, 1 negativo, **2 base no disponible**, 3 uso o configuración; argparse
    usaría 2 y se cambia a 3). `verificar-esquema` ya no «imprime» diferencias: son eventos de log.
  - §5.10: parámetro `DB_CONNECT_TIMEOUT_S` (5 s) y eventos `base_no_disponible`, `configuracion_incompleta`,
    `migracion_iniciada`, `migracion_terminada`, `migracion_fallida`, `esquema_diferencia`, `esquema_verificado` y
    `verificacion_fallida`.
  - §5.11: en `local`, la base se migra con `docker compose run --rm api python -m app.cli migrar`.
  - Cambio incompatible en §5.3 (un valor que desaparece); mientras la versión sea `0.x`, sube la menor.
- **Código:** dependencias `sqlalchemy[asyncio]`, `asyncpg`, `alembic` y `argon2-cffi` (`uv.lock` solo añade
  paquetes); `src/app/db/` (`sesion.py`, `modelos.py` con un tipo `vector` propio, sin el paquete `pgvector` que
  arrastraría numpy, `esquema.py`), `src/app/cli.py`, `src/app/servicios/migracion.py`, `src/app/seguridad/hash.py`,
  `src/app/dominio/enumerados.py` y `validaciones.py`; `src/app/logs.py` (trazas sin el `DETAIL` de PostgreSQL); `migrations/` (`env.py` y `versions/0001_esquema_inicial.py`);
  `/v1/health/ready` con la base; `config.py` (`db_connect_timeout_s`); `Dockerfile` y `.dockerignore` con
  `migrations/`; `docker-compose.yml` con `ADMIN_INICIAL_*` locales; `src/ops/validate12.py` y, en `src/ops/comun.py`,
  `ejecutar_proceso`, `lanzar_tarea`, `leer_log`, `red_tareas` y `ResultadoTarea`; `.github/workflows/backend.yml`.
- **Cómo se verificó:**
  - Revisión independiente del código (otra sesión, sin ver cómo se escribió). Encontró cuatro defectos, corregidos y
    con prueba: (1) un error al insertar el admin dejaba el hash argon2id y el correo en la traza del log, tanto por los
    parámetros de SQLAlchemy (ahora `hide_parameters`) como por el `DETAIL` de PostgreSQL (ahora omitido en toda traza);
    (2) `DB_PORT=abc` o la falta de `migrations/` salían con código 1 y una traza suelta (ahora 3 con
    `configuracion_incompleta`, o 1 con `migracion_fallida`); (3) la clasificación de fallos de conexión tomaba un
    `FileNotFoundError` o un `PermissionError` por «base no disponible» y no contaba la falta de permiso `CONNECT` ni la
    clase 08 (ahora todo fallo al abrir la conexión es 2 y, después, solo los de red y la clase 08); (4)
    `verificar-esquema` podía decir «difiere» durante un `migrar` (ahora espera su bloqueo). Además, `ready` informaba
    «faltan DB_*» con un `DB_SSLMODE` no válido.
  - `ruff check` y `ruff format --check` limpios. `pytest`: 199 pruebas con PostgreSQL 16.15 y pgvector 0.6.0
    (`PRUEBAS_DB_URL`) y el grupo `ops`; sin base ni `ops`, 142 pasan y 34 se omiten; con `PRUEBAS_DB_OBLIGATORIA=1` y
    sin base, las 32 pruebas con base fallan. Entre ellas: la migración y los modelos dejan exactamente `esquema.py`
    (0 diferencias), §5.7 del documento coincide con `esquema.py` (tablas, columnas, tipo, nulo y valor por defecto,
    tipos enumerados y nombres citados), `migrar` es idempotente y dos a la vez van en fila, admin inicial (correo
    normalizado, argon2id, no revive un admin desactivado, 3 sin variables, 1 si el correo es de un `user`),
    `verificar-esquema` detecta 15 cambios hechos a mano y no modifica nada, las restricciones rechazan datos
    incoherentes, un vector de 384 ida y vuelta, y `/v1/health/ready` con base, sin base y con credenciales malas.
  - CLI contra un PostgreSQL real: código 2 con conexión rechazada, contraseña incorrecta, base inexistente, tiempo
    agotado y TLS rechazado; 0 con `DB_SSLMODE=require` contra un servidor con TLS; 3 sin `DB_*`, con `DB_SSLMODE` no
    válido y con un argumento desconocido.
  - Imagen simulada fuera de Docker (solo las dependencias de producción de `uv.lock`, código en `/srv`): `migrar`,
    `verificar-esquema` y `uvicorn` con el comando de §5.9; `ready` da 200 con base y 503 `BASE_NO_DISPONIBLE` sin ella,
    con su `X-Request-Id` y el evento `base_no_disponible`.
  - `backend.yml`: `actionlint` con `shellcheck`. El job de despliegue se ejecutó con `aws`, `docker` y `sleep`
    simulados (23 escenarios): las entradas de `register-task-definition` y `run-task` se validaron contra el modelo de
    botocore 1.43 y `--query` se aplicó con JMESPath; todas las llamadas están en los permisos de `gha-deploy`; `run-task`
    no lleva etiquetas; `migrate` conserva su comando; si `migrate` sale con 1, no arranca, `run-task` no lanza la tarea
    o no para a tiempo, el workflow falla sin tocar `api` ni `worker`; un log que nunca llega no impide un `migrate`
    con 0; sin `SUBREDES_TAREAS` o `SG_MIGRATE`, falla antes de llamar a AWS.
  - `validate12.py` con AWS, HTTP y Docker simulados (17 pruebas): `dev` y `local` completos, C2 «difiere» frente a
    «no se pudo verificar», migrate con otra imagen que `api`, segundo `migrar` que aplica, contenedor que no arranca,
    RDS 16.4 o en `modifying` (código 2), sin outputs de red (2), sin `AWS_PROFILE` (3), y nunca imprime la contraseña
    del secreto.
- **Pendiente:** colocar `.github/workflows/backend.yml` (las herramientas de edición no pueden escribir en
  `.github/workflows/`) y subirlo a `main`; la primera ejecución de CI, con PostgreSQL 17, confirma los textos del
  catálogo de `esquema.py` (aquí se probó con 16, R11); ejecutar `validate12.py --entorno dev` cuando `backend.yml`
  termine en verde.

---

## [0.5.1] — 2026-10-24

- **Lote que la motivó:** BE-1.1. La primera validación en `dev` falló en C1–C3 porque `.github/workflows/backend.yml`
  no estaba en el repositorio: el servicio `api` nunca se había desplegado (imagen `bootstrap`, 0 réplicas).
- **Qué cambió:**
  - §4.2 describe `backend.yml` tal como queda: disparadores (también su propio archivo), pruebas antes de desplegar
    y sin base hasta BE-1.2, convenciones de `infra.yml` (permisos mínimos, acciones fijadas por SHA, uv 0.11.32),
    *login* en ECR con los permisos de `gha-deploy`, campos que se quitan al registrar una revisión (incluido
    `deleteRequestedAt`, que añadió la API de ECS), espera de hasta 2 min a `COMPLETED` y cómo volver a desplegar el
    mismo commit.
  - BE-1.1 C3a (`validate11.py` y `validation/validation-1-1.md`): además del último commit que tocó `project/`, acepta
    un commit posterior de `main` con `project/` idéntico. `backend.yml` se dispara también con su propio archivo, y un
    commit que solo lo toca despliega el mismo código con otro SHA; antes C3a lo rechazaba.
  - `validation/validation-1-1.md` §5: `AWS_PROFILE` obligatoria aunque se use el perfil `default`, y cómo se ve una
    ejecución sin despliegue previo.
  - PLAN §3: nota de BE-1.1 con el estado real.
- **Contratos tocados (§5):** ninguno.
- **Cómo se verificó:** `actionlint` con `shellcheck` sobre `backend.yml`. Los pasos del job de despliegue se
  ejecutaron con `aws` y `docker` simulados: la entrada de `register-task-definition` se validó contra el modelo de
  botocore 1.43 y `--query` se aplicó con JMESPath. Escenarios: primer despliegue (`api` de 0 a 1, `worker` conserva
  su comando), reintento con la imagen ya publicada (no reconstruye ni toca réplicas), *rollback* de `api` (falla),
  familia sin contenedor `app` (falla antes de registrar) y variable del repositorio ausente (falla sin llamar a AWS).
  En un entorno aparte: `uv sync --frozen`, `ruff check`, `ruff format --check` y `pytest` (65 pruebas, sin base de
  datos; 6 nuevas de C3a sobre un repositorio git temporal), los mismos comandos del job de pruebas. C3a contra el
  historial real: el SHA de `origin/main` (`0990740`, solo infraestructura) y `26db1e2` pasan; `41d1461` (`project/`
  distinto) y `bootstrap` fallan.
- **Pendiente:** colocar `.github/workflows/backend.yml` (las herramientas de edición no pueden escribir en
  `.github/workflows/`), subirlo a `main` y ejecutar `validate11.py` en `dev` cuando el workflow termine en verde.

---

## [0.5.0] — 2026-10-24

- **Lote que la motivó:** ninguno; sin cupo de GPU, `embedding` corre en Fargate con 2 vCPU y con DINOv2 ViT-S/14
  (`INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` 0.9.0, ADR-INF-14; `SERVICE_EMBEDDING/docs/ARCHITECTURE.md` 0.5.0,
  ADR-EMB-11). El encendido bajo demanda de 0.4.0 no cambia.
- **Qué cambió:**
  - §3, §4.5, §5.3: «GPU» pasa a «`embedding`»; el script de infra es `embedding.py`.
  - §4.10: se esperan ≤ 800 ms de embeddings para 5 fotos (antes ≤ 500 ms en GPU); el límite duro sigue en 5 s.
  - §5.11: los validadores esperan hasta 10 min (antes 15) a que `embedding` quede listo.
  - R2: la mitigación es el modelo pequeño en 2 vCPU y las palancas de embeddings §4.4.
  - PLAN: BE-3.2 C3 sin «GPU». Validaciones 2-2, 2-3, 2-4, 3-2 y 4-1: encendido de ~3 min; 3-2 C3 comprueba
    `cpu = "2048"` y `memory = "4096"` para `embedding`.
- **Contratos tocados (§5):**
  - §5.7: `embeddings.vector` pasa a **`vector(384)`** y el índice parcial a `embeddings_hnsw_dinov2_vits14_pp_v1`
    sobre `version_vector = 'dinov2-vits14/pp-v1'`.
  - §5.10: `EMBEDDING_VERSION_VECTOR` = **`dinov2-vits14/pp-v1`**; nota de `EMBEDDING_TIMEOUT_S`.
  - §5.3 y §5.5: `version_vector` de los ejemplos.
  - No hay vectores guardados todavía, así que no hace falta re-indexar. Cambio incompatible con 0.4.0 en el esquema;
    mientras la versión sea `0.x`, sube la menor.
- **Código:** `src/app/config.py` (`embedding_version_vector = "dinov2-vits14/pp-v1"`, `embedding_timeout_s = 5.0`;
  el 20 → 5 venía de 0.4.0) y `tests/unit/test_config.py`.
- **Cómo se verificó:** revisión cruzada con embeddings 0.5.0 (§5.2–§5.4) e infra 0.9.0 (§3.4, §5.10, §5.11); 59
  pruebas en verde, `ruff check` y `ruff format --check` limpios.
- **Pendiente:** la primera migración (BE-1.2) debe crear `vector(384)`.

---

## [0.4.0] — 2026-10-24

- **Lote que la motivó:** ninguno; el equipo pide que `POST /v1/localize` responda en menos de 1 s, y la
  infraestructura pasa `embedding` a una GPU bajo demanda, apagada por defecto, en lugar del horario fijo de `dev`
  (`INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` 0.7.0, ADR-INF-13).
- **Qué cambió:**
  - §3: `embedding` apagado por defecto y encendido a mano; `worker` escala solo con `embedding` encendido; desaparece
    el horario de `dev`.
  - §4.5 y §5.3: «fuera de horario» pasa a «con la GPU apagada».
  - §4.10: presupuesto de tiempo con `EMBEDDING_TIMEOUT_S` (5 s) y objetivo p95 en el servidor ≤ 1 s (antes p95 total
    ≤ 5 s).
  - §5.11: los validadores que necesitan `embedding` lo encienden si está apagado y lo dejan como estaba (infra §5.11).
  - R2: el riesgo pasa a superar 1 s en el servidor; la mitigación principal es la GPU.
  - Ejemplos de `latencia_ms` (localización y diagnóstico de vecinos) acordes con la GPU.
  - PLAN: BE-3.2 C3 mide p95 de `integrationLatency` ≤ 1 s con `embedding` en su GPU.
  - Validaciones 2-2, 2-3, 2-4, 3-2 y 4-1: en lugar de exigir el horario, encienden `embedding` si hace falta y solo
    piden empezar con margen antes del apagado de las 22:00. 2-2 C3b espera hasta 15 min a que `embedding` vuelva. 3-2
    C3 comprueba el tamaño con GPU (3 vCPU, 12 GB, una GPU) y mide en los *access logs* de API Gateway, no en el
    cliente.
- **Contratos tocados (§5):** §5.3 (`/v1/health/ready`: solo redacción; `POST /v1/localize`: el
  `503 EMBEDDING_NO_DISPONIBLE` por lentitud llega a los 5 s en lugar de 20 s, y ejemplo de `latencia_ms`), §5.5
  (ejemplo de `latencia_ms` del diagnóstico de vecinos), §5.10 (`EMBEDDING_TIMEOUT_S` 20 → 5), §5.11. Ningún cambio incompatible en la API: sube la menor.
- **Cómo se verificó:** revisión cruzada con infra 0.7.0 (§3.4, §5.4, §5.10, ADR-INF-13) y embeddings 0.4.0 (§4.4,
  §5.7, ADR-EMB-10). Sin código: lo cambiado entra con BE-2.2 y BE-3.2.
- **Pendiente:** si `docker-compose.yml` de `local` usa embeddings en CPU para probar `/v1/localize`, subir allí
  `EMBEDDING_TIMEOUT_S` (lo hace el lote que implemente la localización, BE-3.2).

---

## [0.3.0] — 2026-10-23

- **Lote que la motivó:** BE-1.1 (Base del servicio). El código se escribió antes que este cambio; ambos van en el
  mismo PR para que contrato y código se revisen juntos.
- **Qué cambió:**
  - Encabezado: ya hay código (desde BE-1.1).
  - §3 y §4.1: `migrate` en `backend.yml` desde BE-1.2; estructura real de `project/` (`logs.py`, `middleware.py`,
    `errores.py`, `.dockerignore`, `uv.lock`, `.python-version`, pruebas de los validadores).
  - §4.2: cómo funcionan el middleware, los manejadores de error y los logs; `worker` provisional (solo latido, sin
    consumir colas hasta BE-2.2); lo propio del backend en `backend.yml` (publicación idempotente de la imagen, revisión
    que parte de la última de su familia, primer despliegue, comprobación de la revisión tras `services-stable` y job
    sin `environment:` por la confianza del rol `gha-deploy`).
  - §5.1: reglas de `X-Request-Id` (se reutiliza solo con 1 a 128 caracteres `[A-Za-z0-9._:-]`; si no, UUID v4; también
    en los `500`), cuerpo de error con la clave `error` sola y rutas sin redirección por barra final.
  - §5.3: `GET /v1/openapi.json` y `GET /v1/docs` fuera de `prod`; qué son `version` y `commit` en `/v1/health`;
    cuándo `embedding` es `ok` en `/v1/health/ready`.
  - §5.6: fila para `405` (`SOLICITUD_INVALIDA` con `detalle.metodos_permitidos` y encabezado `Allow`); una ruta que no
    existe es `404 NO_ENCONTRADO`; regla para otros estados del framework (4xx → `SOLICITUD_INVALIDA`, 5xx →
    `ERROR_INTERNO`).
  - §5.9: tabla de la imagen (base, código, usuario) y `APP_COMMIT`, fijado con `--build-arg GIT_COMMIT`;
    `migrations/` entra en la imagen desde BE-1.2; ninguna variable es obligatoria para arrancar.
  - §5.10: nombres de los cortes de nivel (`LOC_NIVEL_ALTA_MIN`, `LOC_NIVEL_MEDIA_MIN`) y del pool (`DB_POOL_API`,
    `DB_POOL_API_DESBORDE`, `DB_POOL_WORKER`), que §5.9 permite sobrescribir con variables; formato de log en detalle y
    catálogo de eventos (`peticion`, `error_no_controlado`, `error_api`, `api_*`, `worker_*`, `latido`).
  - §5.11: uso de `docker-compose.yml` en `local` (perfil `embedding`, puertos, `GIT_COMMIT`).
  - `validation/validation-1-1.md`: P3 y P5 terminan con código 3 cuando falla una herramienta, credencial o permiso
    (infra §5.11); C2b envía su propia petición si C2a se omitió con `--solo`.
  - PLAN: BE-1.1 incluye el `worker` provisional y pasa a «En curso».
- **Contratos tocados (§5):** §5.1, §5.3 (rutas nuevas de documentación), §5.6 (405 y regla general), §5.9, §5.10,
  §5.11. Ningún cambio incompatible: sube la menor.
- **Cómo se verificó:** 59 pruebas (API, contrato contra los esquemas de §5.1 y §5.3, unitarias y de los validadores),
  `ruff check` y `ruff format --check`; `actionlint` con `shellcheck` sobre `.github/workflows/backend.yml`; la
  transformación de la definición de tarea, contra el modelo de `RegisterTaskDefinition` de botocore; la imagen,
  simulada fuera de Docker (mismas dependencias de `uv.lock`, mismo comando de §5.9 y el *health check* de infra §5.7):
  logs JSON, `X-Request-Id`, 404 y parada del `worker`; `validate11.py` completo con AWS simulado (código 0 y, con otro
  commit desplegado, código 1).
- **Pendiente:** construir la imagen con Docker (no se pudo en el entorno donde se escribió) y ejecutar `validate11.py`
  en `dev`, que espera INF-1.3 e INF-1.4.

---

## [0.2.0] — 2026-10-23

- **Lote que la motivó:** ninguno; cambio de organización del monorepo pedido por el equipo.
- **Qué cambió:**
  - El código de la carpeta irá en `project/` y la documentación en `docs/`, con una carpeta nueva
    `docs/validation/` (un documento por lote) y un validador por lote en `project/src/ops/validate<fase><n>.py`.
  - Los lotes se renumeran como `<PREFIJO>-<fase>.<n>` para que el nombre de su validación coincida con el lote
    (`validation-2-2.md` ↔ `validate22.py` ↔ lote x-2.2).
  - El PLAN separa las dependencias «para construir» de las «para validar», numera los criterios de cierre (C1, C2…)
    y añade a §3 las columnas «Validación» y «Última validación».
  - §4.1 describe la estructura nueva (`project/src/app/`, `project/src/ops/`, `project/docker-compose.yml` para el
    entorno `local`).
  - Nuevo §5.11: entornos, variables y datos de prueba de los validadores del backend.
  - Lote nuevo **BE-2.4 Diagnóstico de búsqueda** (§4.8): `POST /v1/admin/diagnostico/vecinos` devuelve los `k`
    vecinos crudos de una foto. Lo necesita la evaluación de embeddings (EMB-3.2) para calibrar antes de BE-3.2, y
    BE-3.2 reutiliza su consulta. Las secciones de §4 a partir de BE-3.1 se desplazan un número (§4.9–§4.12).
  - Tras escribir los documentos de validación: `GET /v1/admin/videos` y `GET /v1/admin/videos/{id}` pasan de BE-4.1
    a BE-2.1 (la app los necesita para el progreso de la subida); `complete` hace `HEAD` y pasa a `subida` lo que ya
    está en S3; nuevos comandos `desactivar-usuario` y `limpiar-validacion`, y `crear-usuario` pasa a ser idempotente.
  - BE-2.3 se valida con BE-2.2 y BE-3.1; BE-4.1, con BE-2.4 en lugar de BE-3.2 (su C1 usa el endpoint de vecinos), lo
    que rompe el ciclo BE-4.1 → BE-3.2 → FE-2.1.
  - Se precisan: la clave del JWT se usa como texto; `db = no_configurada` en `/v1/health/ready`; los endpoints
    reservados de admin validan el token antes del `501`; la caché de alertas de la app evalúa la vigencia al anunciar.
  - §5.11: la tarea de validación de infra para leer la base (solo `SELECT`), ECS Exec para BE-3.2 y tabla de limpieza.
- **Contratos tocados (§5):** §5.2 (clave del JWT), §5.3 (`db = no_configurada`, alertas y reservados), §5.4
  (`complete`), §5.5 (endpoint nuevo `POST /v1/admin/diagnostico/vecinos` y lote de cada grupo), §5.6 (`FOTOS_INVALIDAS`
  también en ese endpoint), §5.9 (la imagen se construye desde `project/` y no incluye `src/ops/`; comandos nuevos
  `verificar-esquema` y `crear-usuario`, que sustituye a `crear-admin` y acepta `--rol`), §5.11 (nuevo).
- **Equivalencia de identificadores** (las entradas anteriores usan los viejos; BE-2.4 es nuevo y no tiene equivalente):
  BE-01 → BE-1.1 · BE-02 → BE-1.2 · BE-03 → BE-1.3 · BE-04 → BE-2.1 · BE-05 → BE-2.2 · BE-06 → BE-2.3 · BE-07 → BE-3.1 ·
  BE-08 → BE-3.2 · BE-09 → BE-4.1 · BE-10 → BE-5.1 · BE-11 → BE-5.2 · BE-12 → BE-5.3 · BE-13 → BE-6.1.
- **Cómo se verificó:** comprobación automática de que los lotes citados existen, de que las referencias cruzadas entre
  secciones resuelven, de que cada documento de validación cubre una vez cada criterio de su lote y de que las tablas
  están bien formadas.
- **Pendiente:** escribir los validadores (cada lote los entrega con su código).


---

## [0.1.0] — 2026-10-23

- **Lote que la motivó:** ninguno; diseño inicial previo a BE-01. No hay código.
- **Qué cambió:** primera versión. Define los tres procesos (`api`, `worker`, `migrate`), el flujo de recolección con
  URLs prefirmadas, la ingesta asíncrona, el algoritmo de localización v1 y el borrado con purga. Cierra decisiones
  abiertas que la app tenía pendientes: privacidad de las fotos de ubicación (decisión 7 → ADR-BE-06), borrado de
  videos (decisión 10 → ADR-BE-07), autenticación (decisión 11 → ADR-BE-03) y aplaza el cálculo de rutas (decisión 2
  → ADR-BE-11). Fija el rumbo en norte verdadero [0, 360) para todos los contratos (ADR-BE-12).
- **Contratos tocados (§5):** todos nuevos — convenciones (§5.1), JWT (§5.2), endpoints públicos (§5.3), de
  recolección (§5.4) y de administración (§5.5), errores (§5.6), esquema de la base (§5.7), mensajes de colas
  (§5.8), procesos de la imagen (§5.9) y parámetros (§5.10). Partió de la tabla de «endpoints propuestos» del antiguo
  `FRONTEND_KOTLIN/ARCHITECTURE.md` §3 y la reemplaza. Cambios respecto de esa tabla:
  - todas las rutas llevan el prefijo `/v1`;
  - `POST /collect/videos/{id}/images` ya no recibe las fotos: devuelve URLs prefirmadas y se añade
    `POST /v1/collect/videos/{id}/complete`;
  - las alertas de admin pasan de `POST` + `PUT` a `PUT` idempotente con id del cliente, y se añade
    `POST /v1/admin/alerts/sincronizar`;
  - se añaden `GET /v1/health`, `GET /v1/health/ready`, endpoints de imágenes individuales y en lote, y
    re-procesado.
- **Cómo se verificó:** revisión cruzada de nombres con `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` v0.1.0
  (variables de entorno, colas, bucket, permisos) y `SERVICE_EMBEDDING/docs/ARCHITECTURE.md` v0.1.0 (endpoint,
  dimensión 768, `version_vector`); revisión de compatibilidad con los modelos de la app (`LugarDestino`,
  `CategoriaLugar`, `Alerta`, `ResumenAdmin`, `Sesion`, `EstadoFoto`) descritos en
  `FRONTEND_KOTLIN/docs/ARCHITECTURE.md`
  §5.6. Antes de publicar se aplicó una revisión independiente de coherencia: el `worker` envía a embeddings copias
  reducidas en lotes de 4 (antes, 8 fotos de hasta 4 MB superaban el límite de 16 MB); la foto completa de alertas
  incluye las de vigencia futura; `tipo` de alerta por defecto `otro`; la versión de vector va como literal en la
  consulta (índice parcial) y se comprueba en la primera llamada, no al arrancar; se quitaron ciclos entre lotes.
- **Pendiente:** calibrar los umbrales de localización (BE-08); definir los contratos reservados (`/v1/localize/frame`,
  `/v1/route`, `/v1/eventos`) antes de sus lotes.
