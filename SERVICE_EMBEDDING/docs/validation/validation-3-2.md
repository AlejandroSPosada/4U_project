# Validación 3-2 — EMB-3.2 Conjunto de evaluación y calibración

| Campo | Valor |
|---|---|
| Lote | `EMB-3.2` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate32.py` |
| Entornos | `dev` (**cierra el lote**): el conjunto vive en el bucket de `dev` y el dataset indexado, en el backend de `dev`. `local` no aplica: no usa el contenedor |
| Criterios | Automáticos: C1, C2 · Manuales: C3 |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.8. El diseño que se valida está en ARCHITECTURE §4.5 (protocolo de captura, métricas y
recomendación), §5.9 (formato del conjunto, del informe y órdenes de `tools/evaluacion`) y ADR-EMB-14.

**Estado (ARCHITECTURE 0.9.0):** el validador y la herramienta están escritos y probados con datos sintéticos
(`tests/test_validate32.py`, `tests/test_evaluacion.py`), pero **no se pueden ejecutar en `dev`** hasta que existan
BE-2.2 y BE-2.4 desplegados, un dataset real indexado (FE-2.1) y el conjunto de fotos de consulta subido a
`evaluacion/`. Hoy terminarían con código 2 en P2 (o con 3 si falta `VALIDACION_API_URL`).

## 1. Precondiciones

El script las evalúa en este orden y, si una falla, no sigue: P4 (código 3 sin `AWS_PROFILE`, con credenciales
inválidas o de otra cuenta), P1, P2 (código 3 si falta `VALIDACION_API_URL` o el backend rechaza el login con `401`;
código 2 si el backend no responde a lo que se le pide o falta el dataset), P2b y P3 (código 2). Ninguna escribe nada
ni enciende `embedding`.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | `EMB-2.1` en «Hecho»: vectores `dinov2-vits14/pp-v1` estables (§5.3, §5.4) | Fila EMB-2.1 de `docs/PLAN.md` §3 en `Hecho` |
| P2 | `BE-2.2` y `FE-2.1` en «Hecho»: un dataset **real** del campus indexado | `POST /v1/auth/login` con `VALIDACION_ADMIN_*` o, si falta alguna, con las claves `correo` y `password` del secreto `campus-locator/dev/admin-inicial` (backend §5.11); `GET /v1/admin/videos` (todas las páginas, BE-2.1) → al menos un video cuyo `nombre` no empieza por `validacion-` con `conteo.procesada` ≥ 1 |
| P2b | `BE-2.4` en «Hecho»: el endpoint de vecinos existe | `POST /v1/admin/diagnostico/vecinos?k=5` con `project/tests/golden/validacion-01-campus.jpg` (backend §5.5). Pasa con `200`, `version_vector = dinov2-vits14/pp-v1` y `vecinos` no vacío, **o** con `503 EMBEDDING_NO_DISPONIBLE` (el endpoint existe y `embedding` está apagado; la `version_vector` la comprueba `tools/evaluacion` en cada respuesta y la cita el informe de C2). Cualquier otra respuesta (`404`, `405`, `501`…) → 2 |
| P3 | Conjunto de fotos de consulta subido a `evaluacion/` (infra §5.5) | `s3api list-objects-v2 --bucket campus-locator-dev-dataset-648617469176 --prefix evaluacion/ --delimiter /` → al menos un `evaluacion/<version_conjunto>/` con la forma `AAAA-MM<letra>`; `s3api head-object` del `puntos.json` del último (orden lexicográfico) |
| P4 | `AWS_PROFILE` de la cuenta `648617469176` con lectura de `evaluacion/` | `sts get-caller-identity` → `Account` (`comun.sesion_aws`). Sin variable, con credenciales inválidas o sin permiso de lectura: código 3 (§5.11) |

P2 ya no usa `GET /v1/admin/images` ni `GET /v1/admin/images/{id}` (lo hacía hasta 0.8.0): son de BE-4.1 (backend
§5.5), que no es dependencia de este lote. La `version_vector` del dataset la da `POST /v1/admin/diagnostico/vecinos`.

## 2. Comprobaciones automáticas

Orden: C1 y después C2. Las dos usan el mismo `<version_conjunto>`: el que cita el informe más reciente de C2 si está
en `evaluacion/`; si no hay informe, el último conjunto (orden lexicográfico).

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1 | `s3api get-object` de `evaluacion/<version_conjunto>/puntos.json` y `list-objects-v2` (paginado) de `evaluacion/<version_conjunto>/fotos/`; revisa la estructura con `evaluacion.conjunto.revisar` (formato de §5.9); con `GET /v1/admin/videos` y `GET /v1/admin/videos/{id}` (BE-2.1) toma la coordenada de cada imagen `procesada` de los videos reales y calcula (haversine, R = 6 371 008,8 m) la distancia de cada punto a la imagen más cercana | `puntos.json` sin errores de estructura; cada `archivo` existe en el bucket; ≥ 50 fotos en puntos con dataset (alguna imagen a ≤ 30 m), repartidas en ≥ 10 de esos puntos, y ≥ 1 punto con ≥ 3 fotos a > 150 m de toda imagen. El detalle da las fotos, los puntos lejanos y el tamaño del dataset |
| C2 | Toma el informe más reciente (por `<AAAAMMDD>` y luego `<version_conjunto>`) de `evaluacion/*/informes/dinov2-vits14_pp-v1-<AAAAMMDD>.json`, que genera `tools/evaluacion evaluar` (formato de §5.9) | Está en la carpeta del conjunto que cita y ese conjunto existe; `version_vector = dinov2-vits14/pp-v1`; `recall_1_15m` y `recall_5_15m` en [0, 1], el primero ≤ el segundo; `fotos` = las fotos en puntos con dataset que cuenta C1; `similitud.mismo_lugar` y `similitud.otro_lugar` con p10 ≤ p50 ≤ p90; `recomendado` con los cuatro valores numéricos. El detalle copia los *recall*, las p50 y los valores recomendados |

C2 no juzga si el *recall* es bueno: eso lo decide quien lee el informe (C3) y lo mide BE-3.2 de punta a punta.

## 3. Comprobaciones manuales

| ID | Qué hace la persona | Evidencia en el PR |
|---|---|---|
| C3 | Revisa en el informe (el `.md` al lado del JSON) los valores recomendados de `LOC_SIM_MIN` y `LOC_SIM_ALTA` (0 < `LOC_SIM_MIN` < `LOC_SIM_ALTA` ≤ 1; hoy 0,55 / 0,80) y de los cortes de nivel (0 < `media` < `alta` < 1; hoy `alta` ≥ 0,70 y `media` ≥ 0,45), todos de backend §5.10, con `detalle_recomendacion` y `simulacion` (cómo se calcularon: ARCHITECTURE §4.5 y ADR-EMB-14), y los entrega a quien lleva BE-3.2, que los registra en esa sección | Enlace al informe y a la entrega a BE-3.2 (*issue* o PR del backend) con los valores recomendados |

## 4. Datos de prueba y limpieza

Solo lee: no crea datos (el servicio no guarda nada, §5.8), no lanza tareas sueltas y no enciende `embedding`, así que
no hay restos que limpiar entre ejecuciones (su función de limpieza no hace nada). Nunca escribe en `evaluacion/` (lo
escriben personas del equipo, infra §5.5) y lee `puntos.json` y el informe en memoria. No imprime el token, las
credenciales de admin ni las URL prefirmadas (`url`, `url_miniatura`) que puedan venir en `GET /v1/admin/videos/{id}`.
P2b hace una búsqueda de vecinos: con `embedding` encendido, una vectorización de prioridad `baja` (backend §4.8); no
deja nada en `eventos_localizacion`.

## 5. Cómo ejecutarlo

```bash
cd SERVICE_EMBEDDING/project
uv run --group ops python src/ops/validate32.py --entorno dev
```

**Variables.**
- `AWS_PROFILE` con el perfil de la persona (§5.8 de ARCHITECTURE; sin la cadena por defecto: con el perfil por
  defecto, `AWS_PROFILE=default`). Permisos: `s3:ListBucket` sobre `campus-locator-dev-dataset-648617469176` con
  prefijo `evaluacion/`, `s3:GetObject` sobre `evaluacion/*` y, si no se pasan `VALIDACION_ADMIN_*`,
  `secretsmanager:GetSecretValue` sobre `campus-locator/dev/admin-inicial`. Región `us-east-1`.
- `VALIDACION_API_URL`: URL base del backend **con** `/v1` (backend §5.11). Obligatoria aquí: el script no lee el
  estado de Terraform; sin ella termina con 3. Se obtiene de API Gateway (paso 4).
- `VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` (opcionales: si falta alguna, se leen del secreto).

La herramienta (`tools/evaluacion`, pasos 3, 5, 7 y 8) lee las mismas tres `VALIDACION_*`, pero no lee el secreto: hay
que exportar las tres. En la máquina: `uv`, `git` y la CLI `aws`. Duración del validador: 1–2 min (un `GET` por
video del dataset). El informe queda en `project/.validacion/EMB-3.2-<AAAAMMDD-HHMMSS>.json` (hora UTC) salvo que se
indique `--informe`.

**Preparación.** Todo desde `SERVICE_EMBEDDING/project`, salvo donde se dice. `DIR` es la carpeta local del conjunto,
dentro de `project/.validacion/` (ignorada por Git), con la versión del conjunto como nombre:
`DIR=.validacion/evaluacion/2026-11a`.

1. Pruebas y estilo:
   ```bash
   uv sync --locked
   uv run ruff check . && uv run ruff format --check . && uv run --group ops pytest tests/test_evaluacion.py tests/test_validate32.py
   ```
   Esperado: `ruff` limpio y `pytest` en verde (`test_extractor_reproduce_los_vectores_dorados_de_pp_v1` se omite sin
   pesos en `project/.modelo/`; con ellos tarda ~1–2 min en `/mnt/c`).
2. Comprobar que los lotes de los que depende están hechos, desde la raíz del monorepo:
   ```bash
   grep -E '^\| (BE-2\.2|BE-2\.4) \| [0-9]' BACKEND_FASTAPI/docs/PLAN.md
   grep -E '^\| FE-2\.1 \| [0-9]' FRONTEND_KOTLIN/docs/PLAN.md
   ```
   Esperado: las tres filas de su §3 con `Hecho` en la tercera columna. Si alguna dice otra cosa, el validador
   terminará con 2: no sigas.
3. Tomar las fotos con el protocolo de ARCHITECTURE §4.5, copiarlas en `$DIR/fotos/<punto>/<n>.jpg`, escribir
   `$DIR/puntos.json` (formato de §5.9) y revisarlo:
   ```bash
   uv run python tools/evaluacion revisar "$DIR"
   ```
   Esperado: `conjunto 2026-11a: <n> puntos, <m> fotos; estructura válida` y código 0. Con errores, una línea
   `[ERROR] …` por cada uno y código 1; los `[AVISO]` (p. ej. `hora` que no cuadra con `capturada_en`) no impiden
   seguir, pero conviene corregirlos.
4. Exportar las variables sin imprimir secretos:
   ```bash
   export AWS_PROFILE=campus-admin
   export VALIDACION_API_URL="$(aws apigatewayv2 get-apis --region us-east-1 --query "Items[?Name=='campus-locator-dev-api'].ApiEndpoint | [0]" --output text)/v1"
   export VALIDACION_ADMIN_CORREO="$(aws secretsmanager get-secret-value --region us-east-1 --secret-id campus-locator/dev/admin-inicial --query SecretString --output text | python3 -c 'import json,sys; print(json.load(sys.stdin)["correo"])')"
   export VALIDACION_ADMIN_PASSWORD="$(aws secretsmanager get-secret-value --region us-east-1 --secret-id campus-locator/dev/admin-inicial --query SecretString --output text | python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')"
   echo "$VALIDACION_API_URL"
   ```
   Esperado: sin salida salvo la última línea, `https://<id>.execute-api.us-east-1.amazonaws.com/v1` (infra §5.2).
5. Comprobar la cobertura frente al dataset real (no necesita `embedding`):
   ```bash
   uv run --group ops python tools/evaluacion cobertura "$DIR"
   ```
   Esperado: una línea por punto (`P01: 5 fotos, dataset más cercano a 4.2 m (con dataset)`…, el lejano con
   `(lejano)`), una línea JSON con `fotos_con_dataset` ≥ 50, ≥ 10 `puntos_con_dataset` y ≥ 1 `puntos_lejanos`, y
   código 0. Con `[NO CUMPLE C1] …` (código 1): mover o añadir puntos y volver al paso 3. Un punto `intermedio` (entre
   30 y 150 m) no cuenta para nada.
6. Subir el conjunto al bucket (**solo** bajo `evaluacion/`: un `.jpg` en `dataset/` dispararía la ingesta, infra
   §5.5):
   ```bash
   aws s3 sync "$DIR" s3://campus-locator-dev-dataset-648617469176/evaluacion/2026-11a/ --exclude "informes/*"
   ```
   Esperado: una línea `upload: …` por archivo, `puntos.json` incluido.
7. Generar el informe. Necesita `embedding` encendido (los vecinos se vectorizan con `/v1/embed`, backend §4.8):
   recurso compartido, un solo lote a la vez; empezar antes de las **21:30** de Bogotá (se apaga solo a las 22:00).
   Desde `INFRASTRUCTURA_TERRAFORM/project`, `uv run --group ops python src/ops/embedding.py estado` y, si tiene 0
   tareas, `uv run --group ops python src/ops/embedding.py encender` (infra §5.11; esperado: código 0 en 2–3 min).
   Después, desde `SERVICE_EMBEDDING/project`:
   ```bash
   uv run --group ops python tools/evaluacion evaluar "$DIR"
   ```
   Esperado: progreso `1/<n> fotos/P01/1.jpg`… en la salida de error (~1–2 s por foto) y al final
   `informe: …/informes/dinov2-vits14_pp-v1-<AAAAMMDD>.json (y …md)` más una línea JSON con `recall_1_15m`,
   `recall_5_15m` y `recomendado`; código 0. Con `[ERROR] … 503 EMBEDDING_NO_DISPONIBLE …`, `embedding` no está
   encendido. Si lo encendiste tú, apágalo al terminar: `uv run --group ops python src/ops/embedding.py apagar` (desde
   `INFRASTRUCTURA_TERRAFORM/project`; esperado: código 0).
8. (Opcional, **pendiente de BE-4.1**) Comparar variantes, con los pesos en `project/.modelo/` (ARCHITECTURE §5.9):
   ```bash
   uv run --group ops python tools/evaluacion variantes "$DIR" --informe "$DIR/informes/dinov2-vits14_pp-v1-<AAAAMMDD>.json"
   ```
   Esperado hoy: `[PENDIENTE] las imágenes del dataset no traen url (llega con BE-4.1 …)` y código 2. Con BE-4.1:
   una línea `<variante>: recall@1 …, recall@5 …` por variante y el informe reescrito. No necesita `embedding`.
9. Subir el informe:
   ```bash
   aws s3 cp "$DIR/informes/" s3://campus-locator-dev-dataset-648617469176/evaluacion/2026-11a/informes/ --recursive
   ```
   Esperado: dos líneas `upload: …` (`.json` y `.md`).

**Ejecución.** Con la preparación hecha y las variables del paso 4:
```bash
cd SERVICE_EMBEDDING/project
uv run --group ops python src/ops/validate32.py --entorno dev
```
Esperado: código 0 y estas líneas (los números, los del conjunto):
```
EMB-3.2 · validation-3-2 · entorno dev
[PASA] P4 AWS_PROFILE de la cuenta del proyecto
[PASA] P1 EMB-2.1 Hecho
[PASA] P2 <n> videos reales con <m> imágenes procesadas
[PASA] P2b POST /v1/admin/diagnostico/vecinos → 503 EMBEDDING_NO_DISPONIBLE: el endpoint existe; … (con embedding encendido: → 200, dinov2-vits14/pp-v1)
[PASA] P3 conjuntos en evaluacion/: 2026-11a
[PASA] C1 2026-11a: <f> fotos en <p> puntos con dataset (≤ 30 m); puntos lejanos (> 150 m, ≥ 3 fotos): P11; dataset de <m> imágenes
[PASA] C2 evaluacion/2026-11a/informes/dinov2-vits14_pp-v1-<AAAAMMDD>.json: recall@1 …, recall@5 … (<f> fotos); similitud mismo lugar p50 …, otro lugar p50 …; recomendado LOC_SIM_MIN …, LOC_SIM_ALTA …, cortes alta … / media …
[MANUAL] C3 Revisa en el informe de C2 (y su .md) los valores recomendados …
Resultado: pasa (código 0) · informe: …/.validacion/EMB-3.2-<AAAAMMDD-HHMMSS>.json
```
Hoy, sin dataset real, lo esperado es `[FALLA] P2 ningún video real con imágenes procesadas …` (o
`BE-2.1: GET /admin/videos → …` si el backend aún no expone esa ruta) y `Resultado: bloqueado (código 2)`. Después de
pasar: C3 (§3) y la fila EMB-3.2 de PLAN §3 a «Hecho» con el commit, la fecha y la versión de ARCHITECTURE; los
números del informe se anotan en ARCHITECTURE §4.5 (sube la menor) y su entrada en `CHANGELOG.md`.
