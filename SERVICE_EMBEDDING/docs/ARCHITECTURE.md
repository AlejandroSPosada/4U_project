# ARCHITECTURE — Servicio de embeddings (`SERVICE_EMBEDDING`)

| Campo | Valor |
|---|---|
| Versión del documento | **0.6.0** (historia en [`CHANGELOG.md`](./CHANGELOG.md)) |
| Fecha | 2026-10-24 |
| Estado | En construcción: código de EMB-1.1 (servicio base e imagen) y EMB-2.1 (vectorización por lotes); el resto de lotes, pendiente |
| Qué se construye y en qué orden | [`PLAN.md`](./PLAN.md) · cómo se comprueba cada lote: [`validation/`](./validation/) |

Servicio HTTP interno que convierte fotos en **vectores de 384 dimensiones** con **DINOv2 ViT-S/14** sobre CPU
(ADR-EMB-11). No guarda nada, no conoce la base de datos ni S3, y solo lo llaman los procesos `api` y `worker` del
backend.

Su **§5 es la única fuente de verdad** de: la API interna, el modelo y su revisión, el preprocesamiento, el
identificador de versión del vector (`version_vector`), el formato del vector, la imagen de contenedor y los
parámetros operativos del servicio.

---

## 1. Propósito y alcance

### 1.1 Qué cubre
- Cargar el modelo una vez, preprocesar imágenes y devolver vectores normalizados.
- Atender primero las peticiones de localización (interactivas) frente a las de ingesta (en segundo plano).
- Herramientas de evaluación de la calidad de recuperación (EMB-3.2) y medición de rendimiento (EMB-3.1).

### 1.2 Qué no cubre
- Búsqueda de vecinos, agrupación y cálculo de posición: backend (`BACKEND_FASTAPI/docs/ARCHITECTURE.md` §4.10).
- Almacenamiento de vectores: pgvector, esquema del backend (§5.7 de su documento).
- Infraestructura (tamaño de tarea, DNS interno, encendido y apagado): `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md`.

### 1.3 Regla de contratos
Este documento define lo que el servicio **expone**. Lo que consume se enlaza:

| Consume | Definido en |
|---|---|
| Variables de entorno `TORCH_NUM_THREADS`, `LOG_LEVEL`, `APP_ENV` | Infra §5.4 |
| Tamaño de la tarea (2 vCPU / 4 GB), encendido manual y apagado automático | Infra §3.4 y ADR-INF-14 |
| Nombre DNS `embedding.campus-locator.local:8080`, grupo de seguridad, *health check* del contenedor | Infra §5.7 |
| Contrato de despliegue (imagen `linux/amd64`, etiqueta = SHA) | Infra §5.9 |

---

## 2. Contexto en el sistema

```
  api    ──POST /v1/embed (X-Prioridad: alta, 1–5 fotos)──┐
                                                           ▼
                                        ┌──────────────────── embedding ────────────────────┐
                                        │ FastAPI ─► cola con prioridad ─► 1 hilo de        │
                                        │            (alta antes que baja)  inferencia      │
                                        │                                   DINOv2 ViT-S/14 │
                                        └───────────────────────────────────────────────────┘
                                                           ▲
  worker ──POST /v1/embed (X-Prioridad: baja, hasta 8)─────┘
```

- **Un único modelo cargado** y **una única inferencia a la vez**: con los 2 vCPU de la tarea (infra §3.4), dos en
  paralelo no terminan antes que en serie y retrasan a la de prioridad `alta` (ADR-EMB-07).
- Llamado por `api` (`POST /v1/localize`) y por `worker` (ingesta). El backend comprueba que `version_vector`
  coincide con la que espera en la primera llamada tras cada arranque del servicio y cada 10 min (backend §5.10).

---

## 3. Arquitectura en AWS (vista del servicio)

- Servicio ECS `embedding` en Fargate con 2 vCPU y 4 GB (infra §3.4, ADR-INF-14); red y DNS interno en infra §3.4 y
  §5.7. Escucha en el puerto de §5.5 y no recibe tráfico desde internet.
- En `dev` está **apagado por defecto**: se enciende a mano (`embedding.py encender` de infra, INF-2.1) y se apaga solo
  tras 45 min sin uso y a las 22:00 (infra §3.4 y §5.10). Apagado, el backend responde `503 EMBEDDING_NO_DISPONIBLE`
  en `/v1/localize` y la ingesta espera en la cola.
- Arranque: descarga de la imagen (~1,8 GB) + carga del modelo + calentamiento: 2–3 min desde el encendido (infra R6);
  el *health check* del contenedor tiene un *start period* de 180 s.
- Sin rol de tarea con permisos: el servicio no llama a ningún servicio de AWS.
- Logs JSON a `/campus-locator/dev/embedding`.

---

## 4. Componentes y funcionamiento (por lote)

### 4.1 Estructura del código

```
SERVICE_EMBEDDING/
├── docs/
│   ├── ARCHITECTURE.md, PLAN.md, CHANGELOG.md
│   └── validation/               validation-<fase>-<n>.md: cómo se comprueba cada lote (§5.8)
└── project/                      todo el código
    ├── src/
    │   ├── app/
    │   │   ├── main.py           FastAPI: rutas, arranque (carga + calentamiento), errores, X-Request-Id, logs JSON
    │   │   ├── config.py         Identidad del modelo y del vector (§5.3) y parámetros de §5.7 (pydantic-settings)
    │   │   ├── modelo.py         Carga de DINOv2 desde MODELO_DIR, inferencia por lotes, normalización L2
    │   │   ├── preproceso.py     Pipeline pp-v1 (función pura: bytes → tensor)
    │   │   └── planificador.py   Cola con prioridad y el hilo único de inferencia
    │   └── ops/                  validate<fase><n>.py y comun.py: validadores de los lotes EMB-x.y (§5.8)
    ├── tools/
    │   ├── descargar_modelo.py   Se ejecuta en el build: baja la revisión fija a /opt/modelo y deja revision.json
    │   ├── benchmark.py          EMB-3.1: latencia por tamaño de lote (va dentro de la imagen, §5.8)
    │   ├── dorados.py            EMB-2.1: imágenes de referencia y vectores esperados de tests/golden/ (§5.4)
    │   └── evaluacion/           EMB-3.2: recuperación sobre un conjunto etiquetado
    ├── tests/                    contrato HTTP, configuración, modelo, preproceso, planificador, validadores y
    │                             vectores dorados (golden/: cinco imágenes y esperados.json, §5.4)
    ├── .dockerignore             solo entra a la imagen lo de §5.5
    ├── .gitignore                incluye .validacion/ (informes de los validadores) y .modelo/ (pesos para dorados)
    ├── Dockerfile                tres etapas (§4.2)
    ├── pyproject.toml            uv (PyTorch desde su índice de CPU); ruff; pytest; grupo `ops` para los validadores
    └── uv.lock                   versiones exactas de todas las dependencias (R4); se versiona
```

El workflow `embedding.yml` vive en `.github/workflows/` de la raíz del monorepo (infra §3.9).

### 4.2 EMB-1.1 — Servicio base e imagen
- El `Dockerfile` instala PyTorch para CPU desde el índice de ruedas de CPU de PyTorch (evita las dependencias de
  CUDA y ahorra más de 1 GB) y `transformers`, y **descarga los pesos durante el
  build** a `/opt/modelo` con la revisión fija de §5.3. En ejecución se activa `HF_HUB_OFFLINE=1`: el servicio no sale a internet para nada.
- La imagen se construye en **tres etapas**:
  1. `dependencias`: `uv sync --locked --no-dev` instala en `/opt/venv` exactamente lo de `uv.lock`.
  2. `pesos`: `tools/descargar_modelo.py` baja `config.json`, `model.safetensors` y `preprocessor_config.json` de la
     revisión fija y escribe `revision.json`. La etapa solo depende de `config.py` y del script, así que cambiar el
     resto del código reutiliza la caché y no vuelve a bajar ~90 MB.
  3. Final: `python:3.12-slim` con `/opt/venv`, `/opt/modelo`, `src/app/` y `tools/benchmark.py`; sin uv ni caché de
     descargas, usuario `app` (uid 10001) sin carpeta personal.
- **Arranque** (ADR-EMB-09). Uvicorn empieza a escuchar de inmediato y el modelo se prepara en un hilo aparte:
  mientras tanto `GET /health` responde 200, `GET /health/ready` 503 y `GET /v1/info` 200. El hilo, en orden:
  1. comprueba que `revision.json` coincide con el modelo y la revisión de §5.3;
  2. fija los hilos: `OMP_NUM_THREADS` y `MKL_NUM_THREADS` = `TORCH_NUM_THREADS` antes de importar PyTorch,
     `torch.set_num_threads(TORCH_NUM_THREADS)` y un hilo entre operadores;
  3. carga `Dinov2Model` desde `MODELO_DIR` (solo archivos locales, *safetensors*) en float32 y modo evaluación, y
     comprueba que produce 384 dimensiones;
  4. calienta con dos inferencias sobre tensores de ceros de 224 × 224 (lote 1 y lote 8);
  5. solo entonces `GET /health/ready` responde 200 y se registra `modelo_listo` con los tiempos de carga y
     calentamiento.

  Si cualquier paso falla, registra `carga_del_modelo_fallida` con la traza y el proceso termina con código 1.
- **Logs**: todo sale en JSON por la salida estándar desde la primera línea, también lo de uvicorn y `transformers`
  (sus barras de progreso se desactivan); el registro de acceso de uvicorn se sustituye por el evento `peticion`
  (formato en §5.7).
- `GET /v1/info` publica la versión del vector para que el backend la compruebe.
- **CI/CD** (`embedding.yml`, contrato de infra §5.9):
  - En PR: `uv sync --locked`, `ruff check`, `ruff format --check` y `pytest`, este con los pesos de la revisión fijada
    (bajados con `tools/descargar_modelo.py` y guardados en la caché de Actions) y `DORADOS_OBLIGATORIOS=1`, para que
    los vectores dorados no se omitan (ADR-EMB-12).
  - En `main` (o a mano con `workflow_dispatch`, p. ej. tras un cambio de Terraform en la tarea, ADR-INF-09): las
    mismas pruebas; imagen `linux/amd64` con `GIT_COMMIT` = SHA, publicada en ECR solo si esa etiqueta no existe
    (son inmutables); nueva revisión de `campus-locator-dev-embedding` a partir de la última de la familia,
    cambiando solo la imagen del contenedor `app`; `update-service`.
  - Si el servicio tiene réplicas, espera hasta 25 min a que el despliegue quede `COMPLETED` con la revisión nueva y
    falla si el *circuit breaker* revierte a la anterior (que `wait services-stable` daría por buena). Con 0
    réplicas (servicio apagado en `dev`) no espera: la revisión nueva se toma al encender.
  - El job de despliegue no declara `environment`: el rol `gha-deploy` solo confía en
    `sub = repo:<github_repo>:ref:refs/heads/main` (infra §5.8).

### 4.3 EMB-2.1 — Vectorización por lotes
1. `POST /v1/embed` recibe 1–8 imágenes y valida antes de encolar, en este orden: tamaño del cuerpo (lo lee entero con
   tope; si declara más de `BYTES_MAX_PETICION`, hasta 4 veces ese tamaño lo lee y lo descarta antes de responder `413`,
   para que el cliente pueda leer la respuesta, y por encima responde sin leerlo), `X-Prioridad`, `multipart/form-data`
   bien formado, número de partes `imagenes` y, para cada una en orden, tipo y tamaño (§5.6). El multipart se lee en un
   hilo del *pool* de Starlette, no en el bucle de eventos, sin guardar las partes con otro nombre y cortando en la
   novena imagen. Después, si el modelo aún carga, `503 NO_LISTO`.
2. La petición entra en una **cola con prioridad**: `alta` (localización) antes que `baja` (ingesta); dentro de cada
   prioridad, por orden de llegada. La prioridad no interrumpe un lote que ya se está calculando: una petición `alta`
   espera como máximo a que termine el lote en curso (por eso el `worker` envía lotes pequeños, backend §5.10). Si con
   ella las imágenes en espera superarían `COLA_MAX_IMAGENES` (el lote en curso no cuenta), responde `503 SATURADO` con
   `Retry-After` (el `worker` reintenta). La prioridad ordena la atención, no la admisión: con la cola llena de `baja`,
   una `alta` también recibe `503`. Eso solo pasa si el `worker` tiene más de `COLA_MAX_IMAGENES` imágenes en espera a
   la vez.
3. El hilo de inferencia toma una petición, aplica el preprocesamiento pp-v1 a cada imagen (decodificación incluida),
   corre **un solo lote** con todas las imágenes de esa petición y normaliza cada vector. `tiempos_ms.cola` mide desde
   que la petición entra en la cola hasta que el hilo la toma; `tiempos_ms.inferencia`, desde ahí hasta tener los
   vectores.
4. Responde los vectores en el mismo orden de entrada, con los tiempos de cola e inferencia.

Si una sola imagen no se puede decodificar, se rechaza **la petición completa** con `400 IMAGEN_INVALIDA` y el índice
de la imagen: el que llama decide si reintenta sin ella (el `worker` marca esa imagen en `error` y reintenta el
resto).

Código: `planificador.py` (dos colas FIFO bajo un `threading.Condition` y un futuro por petición, que la ruta asíncrona
espera sin bloquear el bucle de eventos; al detenerse el proceso, lo que esperaba recibe `503 NO_LISTO`) y
`preproceso.py` (función pura sin PyTorch: devuelve un array de NumPy que `modelo.inferir` usa sin copiarlo). Los
vectores dorados (§5.4) y dónde se calculan: ADR-EMB-12.

### 4.4 EMB-3.1 — Rendimiento en CPU
`project/tools/benchmark.py` mide p50 y p95 para lotes de 1, 5 y 8 imágenes en una tarea igual a la de `dev` (2 vCPU,
§5.8). Objetivo: lote de 5 en p95 ≤ 800 ms, para que `POST /v1/localize` quede en p95 ≤ 1 s (infra §5.10; el resto
se va en el backend y en la búsqueda en RDS, backend §4.10). Estimación previa, sin medir: 0,5–1,5 s (ADR-EMB-11). Si
no se alcanza, en este orden: ajustar hilos; exportar a ONNX Runtime; subir la tarea a 4 vCPU (duplica el costo por
hora encendida, infra §3.10); cuantizar a int8. Exportar o cuantizar cambia los vectores: exige una `version_vector`
nueva (ADR-EMB-08), así que conviene decidirlo antes de indexar el dataset real.

### 4.5 EMB-3.2 — Conjunto de evaluación y calibración
- Conjunto: fotos de consulta tomadas en puntos conocidos del campus (no usadas en el dataset), con su coordenada.
- Métricas: *recall@1* y *recall@5* «a 15 m» (algún vecino recuperado está a ≤ 15 m del punto real), y la distribución
  de similitudes entre «mismo lugar» y «otro lugar».
- Salida: valores recomendados de `LOC_SIM_MIN`, `LOC_SIM_ALTA` y cortes de nivel para el backend (BE-3.2), y la
  comparación de pp-v1 con variantes (sin recorte central, resolución mayor, media de *tokens* de parches en lugar del
  CLS). Las variantes no se despliegan: si alguna gana, se abre EMB-5.1.

### 4.6 EMB-5.1 — Nueva versión del vector (diferido)
Procedimiento previsto para cambiar de modelo o preprocesamiento sin dejar de ubicar:
1. Nueva `version_vector` (§5.3) y vectores dorados nuevos.
2. Backend: migración con el índice parcial de la nueva versión (backend ADR-BE-09).
3. Re-indexado: el `worker` re-procesa todas las imágenes con un servicio temporal de la nueva versión (el servicio
   expone **una sola** versión a la vez).
4. Cambio de `EMBEDDING_VERSION_VECTOR` en el backend y despliegue de la nueva versión del servicio.
5. Borrado de los vectores e índice de la versión anterior.

---

## 5. Interfaces (contratos)

> **Única fuente de verdad** de lo que expone este servicio. Cambiar algo aquí sube la versión de este documento y
> exige entrada en `CHANGELOG.md`. Cambiar el modelo, la revisión o el preprocesamiento exige además una
> `version_vector` nueva.

### 5.1 Convenciones

| Tema | Regla |
|---|---|
| URL base | `EMBEDDING_URL` (valor en infra §5.4). HTTP sin TLS: tráfico privado dentro de la VPC |
| Autenticación | Ninguna. El acceso lo limita el grupo de seguridad (solo `api` y `worker`) |
| Formato | JSON UTF-8, `snake_case`, en español |
| Errores | `{"error": {"codigo": "…", "mensaje": "…", "detalle": {…} \| null}}` (mismo formato que el backend) |
| Correlación | Respeta y devuelve `X-Request-Id` si tiene de 1 a 128 caracteres de `[A-Za-z0-9._:-]`; si falta o no cumple, genera uno (32 caracteres hexadecimales). Va en todas las respuestas, también en las de error |
| Documentación interactiva | `/docs` y `/openapi.json` solo con `APP_ENV=local`; en `dev` responden `404` |

### 5.2 Endpoints

#### `GET /health`
`200` → `{"estado": "ok"}` mientras el proceso viva (aunque el modelo esté cargando).

#### `GET /health/ready`
`200` → `{"estado": "listo"}` con el modelo cargado y calentado. `503` → `{"estado": "cargando"}` antes. Lo usan el
*health check* del contenedor (infra §5.7), `/v1/health/ready` del backend y el `worker` antes de tomar mensajes.

#### `GET /v1/info`
`200`:
```json
{
  "servicio": "campus-locator-embedding",
  "version": "0.1.0",
  "commit": "a1b2c3d",
  "modelo": "facebook/dinov2-small",
  "revision": "ed25f3a31f01632728cabb09d1542f84ab7b0056",
  "arquitectura": "ViT-S/14",
  "preprocesamiento": "pp-v1",
  "version_vector": "dinov2-vits14/pp-v1",
  "dim": 384,
  "normalizacion": "l2",
  "metrica": "coseno",
  "lote_max": 8,
  "dispositivo": "cpu"
}
```
- Responde también mientras el modelo carga: son datos fijos de la imagen, y si los pesos no fueran la revisión
  anotada el proceso no llegaría a quedar listo (§4.2).
- `commit` = los 7 primeros caracteres de `GIT_COMMIT` (§5.5), o `desconocido` si la imagen se construyó sin ese
  argumento. `lote_max` = `LOTE_MAX` (§5.7). `dispositivo` es siempre `cpu` (ADR-EMB-11).

#### `POST /v1/embed`
- `multipart/form-data` con 1 a `LOTE_MAX` (8) partes llamadas `imagenes` (las partes con otro nombre se ignoran), de
  tipo `image/jpeg` o `image/png` (el `Content-Type` de cada parte), cada una ≤ 4 MB y la petición completa ≤ 16 MB
  (bytes del cuerpo; MB = 2²⁰ bytes). Los bytes se decodifican como JPEG o PNG sea cual sea, de esos dos, el tipo
  declarado.
- Encabezado opcional `X-Prioridad: alta | baja` (por defecto `baja`; no distingue mayúsculas; otro valor →
  `400 SOLICITUD_INVALIDA`). `api` envía `alta`; `worker`, `baja`.

`200`:
```json
{
  "version_vector": "dinov2-vits14/pp-v1",
  "dim": 384,
  "vectores": [[0.0123, -0.0456, …], [ … ]],
  "tiempos_ms": { "cola": 3, "inferencia": 650 }
}
```
- `vectores[i]` corresponde a la `i`-ésima parte `imagenes`, en el orden recibido.
- Cada vector tiene exactamente `dim` números (float32 serializados como números JSON) y norma L2 = 1 (±1e-4).
- `tiempos_ms.cola`: milisegundos desde que la petición entra en la cola hasta que el hilo de inferencia la toma;
  `tiempos_ms.inferencia`: desde ahí hasta tener los vectores, preprocesamiento pp-v1 incluido (§4.3).

### 5.3 Modelo, preprocesamiento y `version_vector`

| Elemento | Valor en `pp-v1` |
|---|---|
| Modelo | `facebook/dinov2-small` (DINOv2 ViT-S/14, 22 M parámetros, licencia Apache 2.0) en `transformers` (`Dinov2Model`) |
| Revisión | `ed25f3a31f01632728cabb09d1542f84ab7b0056`: cabeza de `main` en Hugging Face al fijarla en 0.5.0 (commit «Update README.md», 2023-09-06, que solo cambia la licencia del README a Apache 2.0). De ella se usan `config.json`, `model.safetensors` (88 249 960 bytes, SHA-256 `ae1e99fcefd534ed978cdeb8326f08030c96e28b7a81ffcbc98a857c84d14be1`) y `preprocessor_config.json` |
| Precisión | float32, `torch.inference_mode()`, modo evaluación |
| 1. Decodificación | Pillow; orientación EXIF aplicada (`ImageOps.exif_transpose`); convertir a RGB (descarta alfa) |
| 2. Redimensión | Lado **menor** a 256 px, interpolación bicúbica con antialias, manteniendo proporción |
| 3. Recorte | Central de 224 × 224 px (16 × 16 parches de 14 px) |
| 4. Normalización | Escala [0, 1]; media (0,485; 0,456; 0,406); desviación (0,229; 0,224; 0,225) |
| 5. Salida del modelo | *Token* CLS de la última capa tras la *layernorm* final (`pooler_output` de `Dinov2Model`) |
| 6. Normalización del vector | L2 |

Lo que la tabla no detalla lo fija el código igual que el procesador publicado con el modelo
(`preprocessor_config.json` con `BitImageProcessorPil` de transformers 5.20.2, con el que pp-v1 coincide bit a bit; una
prueba lo comprueba): Pillow `Image.Resampling.BICUBIC` sin `reducing_gap`; el lado largo se trunca,
`int(256 · largo / corto)`; el recorte empieza en `(lado − 224) // 2`; la escala multiplica en float64 por 1/255 y pasa
a float32, y `(x − media) / desviación` se calcula en float32. Lo único que pp-v1 añade a ese procesador es la
orientación EXIF del paso 1. Los vectores dorados (§5.4) fijan todo esto.

**`version_vector`** = `dinov2-vits14/pp-v1`. Identifica de forma única la combinación modelo + revisión +
preprocesamiento + extracción. Dos vectores solo son comparables si tienen la misma `version_vector`. Cambiar
**cualquiera** de las filas de la tabla (incluida la revisión del modelo o una librería que altere los números más allá
de la tolerancia de §5.4) exige una versión nueva (ADR-EMB-08).

### 5.4 Formato y garantías del vector

- Dimensión 384, float32, norma L2 = 1. Métrica prevista: **coseno**; como están normalizados, coseno = producto
  escalar. En pgvector se guardan como `vector(384)` y se buscan con `vector_cosine_ops` (backend §5.7).
- **Determinismo:** la misma imagen produce el mismo vector en la misma imagen de contenedor, con diferencia máxima
  por componente ≤ 1e-5. Se verifica con **vectores dorados** (`tests/golden/`): cinco imágenes de referencia generadas
  por `tools/dorados.py` (sin derechos de terceros: JPEG apaisado, JPEG vertical con orientación EXIF, PNG con alfa, PNG
  en gris de lados impares y JPEG de 96 × 72) y `esperados.json`, con sus vectores, el `sha256` de cada archivo y del
  tensor preprocesado, y con qué se calcularon (CPU, hilos, versiones). Los comprueban `tests/test_dorados.py` (en CI,
  con los pesos de la revisión fijada) y `validate21.py` C1 (contra la imagen). Dónde se calculan y por qué la misma
  tolerancia vale entre CPU distintas (medido: ≤ 6,3e-7): ADR-EMB-12. Si una actualización de dependencias rompe esa
  tolerancia, no se despliega sin versión nueva; `tools/dorados.py vectores` no sobrescribe los dorados si algún
  componente se aleja más de 1e-5.
- **Independencia del tamaño de lote:** el vector de una imagen no depende de con qué otras imágenes viajó, con la
  misma tolerancia de 1e-5 (la aritmética float32 en CPU puede variar mínimamente con el tamaño del lote; medido en
  EMB-2.1: idéntico bit a bit en lotes de 1, 5 y 8).

### 5.5 Imagen de contenedor y proceso

| Elemento | Valor |
|---|---|
| Repositorio ECR | `campus-locator/embedding` (infra §5.1) |
| Base | `python:3.12-slim`, usuario sin privilegios `app` (uid 10001), contenedor `app` |
| Construcción | Desde `project/`: `docker build --platform linux/amd64 --build-arg GIT_COMMIT=<sha> .`; tres etapas (§4.2) y dependencias exactas de `uv.lock` (uv 0.11.32). Sin `uv.lock` el build falla |
| Comando (`CMD`) | `uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1 --no-server-header` |
| Puerto | `8080` |
| Pesos | En la imagen, `/opt/modelo` (descargados en el build por `tools/descargar_modelo.py`, que deja `revision.json` con el modelo y la revisión; si no coinciden con §5.3, el servicio no arranca) |
| Contenido | `src/app/` (como paquete `app`) y `tools/benchmark.py`; `src/ops/`, `tests/`, `tools/dorados.py` y `tools/evaluacion/` quedan fuera |
| Variables fijadas en el `Dockerfile` | `MODELO_DIR=/opt/modelo`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_HOME=/tmp/huggingface` (el usuario de la imagen no tiene carpeta personal) y `GIT_COMMIT` (argumento de build con el SHA del commit, por defecto `desconocido`; `/v1/info` publica sus 7 primeros caracteres como `commit`) (la aplicación además aplica `TORCH_NUM_THREADS` a PyTorch y a OpenMP al arrancar) |
| Variables que inyecta la infraestructura | `TORCH_NUM_THREADS`, `LOG_LEVEL`, `APP_ENV` (infra §5.4) |
| Tamaño esperado | ~1,8 GB (PyTorch CPU + transformers + pesos de ~90 MB) |
| Memoria en ejecución | ~1 GB en reposo (estimado; se mide en EMB-3.1); la tarea tiene 4 GB para lotes de 8 |

### 5.6 Códigos de error

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `SOLICITUD_INVALIDA` | Sin partes `imagenes`, cuerpo que no es `multipart/form-data` o mal formado, o `X-Prioridad` distinto de `alta` y `baja` |
| 400 | `IMAGEN_INVALIDA` | Una imagen no se pudo decodificar como JPEG o PNG, supera `Image.MAX_IMAGE_PIXELS` de Pillow (~89,5 MP, protección contra bombas de descompresión), mide menos de 64 px de lado o su lado largo pasa de 32 veces el corto (`PROPORCION_MAX`: la redimensión de pp-v1 crearía un intermedio de varios GB); `detalle.indice` = posición de la primera que falla |
| 404 | `NO_ENCONTRADO` | Ruta inexistente |
| 405 | `METODO_NO_PERMITIDO` | Método no admitido en una ruta existente |
| 413 | `LOTE_DEMASIADO_GRANDE` | Más de 8 imágenes o una petición de más de 16 MB (`detalle: null`), o una imagen de más de 4 MB (`detalle.indice` = posición) |
| 415 | `TIPO_NO_SOPORTADO` | Tipo distinto de `image/jpeg` o `image/png`; `detalle.indice` = posición |
| 503 | `NO_LISTO` | El modelo aún carga (o el proceso se está deteniendo) |
| 503 | `SATURADO` | Cola por encima de `COLA_MAX_IMAGENES`; incluye `Retry-After` en segundos |
| 500 | `ERROR_INTERNO` | Fallo no previsto (incluida falta de memoria) |

En `POST /v1/embed`, si hay varios errores responde el primero en el orden de §4.3: tamaño del cuerpo, `X-Prioridad`,
multipart, número de imágenes, tipo y tamaño de cada imagen en orden, `NO_LISTO`, `SATURADO` y, ya en el hilo de
inferencia, `IMAGEN_INVALIDA`.

### 5.7 Parámetros operativos

| Parámetro | Valor | Notas |
|---|---|---|
| `LOTE_MAX` | 8 | El `worker` del backend envía lotes de 4 (backend §5.10) |
| `BYTES_MAX_IMAGEN` / `BYTES_MAX_PETICION` | 4 MB / 16 MB | |
| `LADO_MIN_PX` | 64 | Antes del preprocesamiento |
| `PROPORCION_MAX` | 32 | Lado largo / lado corto máximo, antes del preprocesamiento; con 32 el intermedio de la redimensión no pasa de 256 × 8192 px |
| `COLA_MAX_IMAGENES` | 40 | Imágenes esperando, sumando todas las peticiones; no cuenta el lote que se está calculando. Debe ser ≥ `LOTE_MAX` (si no, el servicio no arranca: un lote completo nunca entraría) |
| `RETRY_AFTER_S` | 5 | En `503 SATURADO` |
| Hilos de PyTorch | `TORCH_NUM_THREADS` (valor en infra §5.4) | Igual a los vCPU de la tarea (2) |
| Latencia objetivo | En `dev` (2 vCPU): lote de 5 p95 ≤ 800 ms; lote de 1 p95 ≤ 250 ms | Para `POST /v1/localize` en p95 ≤ 1 s (infra §5.10). **A medir en EMB-3.1**; estimación previa en ADR-EMB-11 |
| Formato de log | JSON por línea en la salida estándar: siempre `ts` (UTC, ms), `nivel` y `evento`; además, según el evento, `request_id`, `prioridad`, `n_imagenes`, `cola_ms`, `inferencia_ms` (vectorización, EMB-2.1), `metodo`, `ruta`, `estado_http`, `duracion_ms` (cada petición), `carga_ms`, `calentamiento_ms`, `revision`, `version_vector`, `hilos`, `commit` (arranque) y `traza` (errores) | Nunca bytes de imagen. Eventos: `arranque`, `modelo_listo`, `carga_del_modelo_fallida`, `peticion`, `error_no_previsto` y los de uvicorn. Las peticiones a `/health` y `/health/ready` van en nivel `DEBUG` (el *health check* llama cada 30 s) |

Cada parámetro tiene su valor por defecto en `config.py` y se puede sobrescribir con una variable de entorno del mismo nombre; si alguna se vuelve necesaria en `dev`, se añade antes a infra §5.4.

### 5.8 Validadores del servicio

El contrato común (nombres, argumentos, códigos de salida, informe, reglas de datos de prueba) está en
`INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Aquí solo lo propio de este servicio.

**Entornos**

| Entorno | Cómo llega el validador al servicio | Para qué |
|---|---|---|
| `local` | Arranca la **misma imagen** que se despliega (`EMBEDDING_IMAGEN`: etiqueta de ECR o construcción local de `project/`) con `docker run -p 8080:8080` y llama a `http://localhost:8080` | Comprobaciones funcionales de la API, vectores dorados, prioridad, arranque sin red (`--network none`) |
| `dev` | El servicio es privado: el validador lanza **tareas sueltas** con la definición `campus-locator-dev-embedding` (`--launch-type FARGATE`, la red del servicio y el comando de la imagen o uno sobrescrito) o consulta ECS (`describe-tasks`, eventos del servicio) y CloudWatch Logs; además puede comprobar `embedding: ok` en `GET /v1/health/ready` del backend | Tiempos de arranque reales, rendimiento en el tamaño de tarea de `dev`, imagen desplegada |

**El servicio en `dev`**: las tareas sueltas no lo necesitan. Un validador que necesita el servicio `embedding` en
marcha lo enciende si está apagado (como `embedding.py encender`, esperando hasta 10 min a que esté sano) y al
terminar lo deja como lo encontró: si lo encendió él, lo apaga; si ya estaba encendido, no lo toca (infra §5.11).

**Variables que leen**: `EMBEDDING_IMAGEN` (en `local`), `AWS_PROFILE` (en `dev`) y, para EMB-3.2,
`VALIDACION_API_URL`, `VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` (las mismas del backend, su §5.11). Las
imágenes de referencia de los vectores dorados y sus vectores esperados están en `project/tests/golden/` (§5.4).

**Lo que la imagen incluye para los validadores**: `tools/benchmark.py` va dentro de la imagen (en `/srv/tools/`) para
poder ejecutarlo como tarea suelta en `dev` con el comando `python tools/benchmark.py --salida json`; el resultado
(formato en §5.9) se lee del log `/campus-locator/dev/embedding`. `tools/evaluacion/` no va en la imagen: se ejecuta en
la máquina de quien valida, lee el conjunto de `evaluacion/` del bucket (infra §5.5) y obtiene los vecinos del dataset
con el endpoint de diagnóstico del backend (§5.9).

**Datos de prueba**: imágenes sintéticas generadas por el propio validador y las cinco imágenes de
`project/tests/golden/`; el servicio no guarda nada, así que no hay limpieza más allá de detener las tareas sueltas.

**`src/ops/comun.py`** (desde EMB-1.1) reúne lo que comparten los validadores de esta carpeta:
- Los nombres del contrato (cuenta, clúster, servicio, familia, log group, contenedor y repositorio de infra §5.1;
  puerto, `version_vector` y comando del *health check* de infra §5.7) y la lectura del SHA anotado en §5.3.
- `ejecutar(lote)`: argumentos, orden, estados, códigos de salida e informe de infra §5.11. Las precondiciones se
  evalúan en el orden en que el validador las declara y se para en la primera que no se cumple; el informe las lista
  por ID. Cada validador declara una función de limpieza que se usa dos veces: al empezar (restos de una ejecución
  anterior, antes de comprobar puertos o recursos) y al terminar.
- Clasificación de errores: falta de Docker o de una variable, credenciales inválidas, permisos insuficientes de AWS,
  `--solo` con un ID inexistente o un error inesperado en una precondición → **3**; `PrecondicionNoCumplida` → **2**;
  una comprobación que falla o lanza un error inesperado → **1**, y se siguen ejecutando las demás.
- `--solo C1` incluye las subcomprobaciones (`C1a`, `C1b`).
- `imagen_local()` (desde EMB-2.1): `EMBEDDING_IMAGEN` descargada (tras `docker login` si es de ECR) y de plataforma
  `linux/amd64`, o los códigos de error de §5.11; `en_marcha(contenedor)`. La usan `validate11.py` (P4) y
  `validate21.py` (P2).
- Docker se usa por su CLI y AWS con boto3 desde `AWS_PROFILE` (región `us-east-1`); para una imagen de ECR hace
  `docker login` con el token de `ecr:GetAuthorizationToken`, sin imprimirlo.
- Necesita en la máquina de quien valida: Docker (`local`), credenciales de AWS (`dev`) y `git` (commit del informe).

### 5.9 Formatos de las herramientas y del conjunto de evaluación

**Salida de `tools/benchmark.py --salida json`**: una sola línea en la salida estándar (y por tanto en el log),
precedida de `BENCHMARK_JSON ` para poder encontrarla:
```json
{ "version_vector": "dinov2-vits14/pp-v1", "commit": "a1b2c3d", "hilos": 2, "vcpu": 2, "memoria_mb": 4096,
  "resultados": [ { "lote": 1, "repeticiones": 30, "p50_ms": 160, "p95_ms": 210 },
                  { "lote": 5, "repeticiones": 20, "p50_ms": 650, "p95_ms": 760 },
                  { "lote": 8, "repeticiones": 10, "p50_ms": 1000, "p95_ms": 1150 } ] }
```
(Los números del ejemplo son ilustrativos, no medidos.) Cada repetición usa imágenes sintéticas de 1024 px, mide desde
que la petición entra en la cola hasta que sale la respuesta y descarta las 3 primeras como calentamiento.

**Conjunto de evaluación** (EMB-3.2), en el bucket del dataset bajo `evaluacion/<version_conjunto>/` (infra §5.5):
```
evaluacion/2026-11a/
├── puntos.json
├── fotos/<punto>/<n>.jpg
└── informes/<version_vector>-<AAAAMMDD>.json   (y .md, el mismo informe para leer)
```
En el nombre del informe, la `/` de la `version_vector` se escribe `_` (`dinov2-vits14_pp-v1-20261105.json`).
`puntos.json`:
```json
{ "version_conjunto": "2026-11a", "creado_en": "2026-11-05T14:00:00Z",
  "puntos": [ { "id": "P01", "lat": 6.200104, "lng": -75.578612, "descripcion": "Entrada de la biblioteca" } ],
  "fotos": [ { "archivo": "fotos/P01/1.jpg", "punto": "P01", "rumbo": 90.0, "capturada_en": "2026-11-05T14:02:10Z", "hora": "manana" } ] }
```
`rumbo` en norte verdadero [0, 360) o `null`; `hora` ∈ {`manana`, `tarde`, `noche`}. Las fotos no se usan nunca en
el dataset. El conjunto incluye además al menos un punto lejos del dataset (> 150 m de toda imagen): sus fotos no
entran en el *recall* y sirven para comprobar `sin_coincidencias` (BE-3.2 C5).

**Informe de evaluación** (`informes/<version_vector>-<AAAAMMDD>.json`):
```json
{ "version_conjunto": "2026-11a", "version_vector": "dinov2-vits14/pp-v1", "fotos": 50, "puntos": 10,
  "recall_1_15m": 0.0, "recall_5_15m": 0.0,
  "similitud": { "mismo_lugar": { "p10": 0.0, "p50": 0.0, "p90": 0.0 }, "otro_lugar": { "p10": 0.0, "p50": 0.0, "p90": 0.0 } },
  "variantes": [ { "nombre": "pp-v1", "recall_1_15m": 0.0, "recall_5_15m": 0.0 } ],
  "recomendado": { "LOC_SIM_MIN": 0.0, "LOC_SIM_ALTA": 0.0, "corte_alta": 0.0, "corte_media": 0.0 } }
```
«Mismo lugar» = vecino a ≤ 15 m del punto real; «otro lugar» = vecino a > 50 m. Los vecinos del dataset se obtienen con
`POST /v1/admin/diagnostico/vecinos` del backend (backend §5.5), con `k = 5`. `variantes` incluye siempre `pp-v1`
(los mismos números de arriba); una variante de preprocesamiento distinta se evalúa sin tocar `dev`: la herramienta
descarga las imágenes del dataset con las URL de `GET /v1/admin/images`, las vectoriza con la variante en un
contenedor local y busca los vecinos por fuerza bruta.

---

## 6. Decisiones de diseño (ADR)

**ADR-EMB-01 — DINOv2 ViT-B/14, vectores de 768 dimensiones (reemplazada por ADR-EMB-11 en 0.5.0).**
Elegido por el equipo. ViT-S/14 (384) es más rápido pero menos discriminativo; ViT-L/14 (1024) triplica el costo en
CPU. DINOv2 es autosupervisado y sus descriptores globales funcionan bien para recuperar imágenes del mismo lugar sin
entrenamiento adicional. Licencia Apache 2.0.

**ADR-EMB-02 — PyTorch CPU + `transformers` (aceptada).**
Lo más simple de mantener. ONNX Runtime y cuantización quedan como palancas de rendimiento (EMB-3.1), sabiendo que
cambian los vectores.

**ADR-EMB-03 — Descriptor = *token* CLS normalizado, métrica coseno (aceptada, revisable en EMB-3.2).**
Estándar, compacto y directamente indexable en pgvector. La media de *tokens* de parches o agregaciones tipo GeM se
comparan en EMB-3.2.

**ADR-EMB-04 — Preprocesamiento estándar de ImageNet: lado menor 256, recorte central 224 (aceptada, revisable).**
Es el preprocesamiento con el que se publicó el modelo. *Consecuencia:* en fotos verticales del teléfono se pierde
cerca de un tercio de la altura; EMB-3.2 mide si conviene no recortar o usar más resolución.

**ADR-EMB-05 — Pesos dentro de la imagen, revisión fija, sin red en ejecución (aceptada).**
Arranques reproducibles y sin depender de Hugging Face en producción. *Consecuencia:* imagen de ~1,8 GB y arranque más
lento (riesgo R3).

**ADR-EMB-06 — Servicio sin estado, sin acceso a AWS ni a la base, sin autenticación (aceptada).**
Minimiza su superficie: solo convierte píxeles en números. La red privada y el grupo de seguridad limitan quién lo
llama.

**ADR-EMB-07 — Cola con prioridad y una sola inferencia a la vez (aceptada).**
Con 2 vCPU la concurrencia no aumenta el rendimiento (PyTorch ya usa los dos hilos en una inferencia); la prioridad
protege la latencia de la localización frente a la ingesta.

**ADR-EMB-08 — `version_vector` explícita y cambios nunca silenciosos (aceptada).**
Mezclar vectores de versiones distintas degrada la búsqueda sin dar errores. Cualquier cambio que altere los números
produce una versión nueva y un re-indexado (procedimiento de §4.6).

**ADR-EMB-09 — Modelo preparado en segundo plano; si falla, el proceso termina (aceptada, EMB-1.1).**
`GET /health` debe responder mientras el modelo carga (§5.2), pero uvicorn no acepta conexiones hasta que termina el
arranque de la aplicación; por eso la carga y el calentamiento van en un hilo aparte. Si fallan (pesos ausentes o de
otra revisión, falta de memoria), el proceso termina con código 1: ECS reemplaza la tarea y la regla de EventBridge
avisa (infra §3.8), en lugar de mantener viva una tarea que nunca quedará lista hasta que el *health check* agote el
*start period* y sus reintentos. *Consecuencia:* un error de pesos se ve como tareas que se reinician, con
`carga_del_modelo_fallida` en el log.

**ADR-EMB-10 — Inferencia en GPU en `dev`, con la misma `version_vector` (descartada en 0.5.0 sin aplicarse: no hubo
cupo de GPU a tiempo; la reemplaza ADR-EMB-11).**
El equipo pide que `POST /v1/localize` responda en menos de 1 s; en 1 vCPU, 5 fotos tardan ~5,5 s (infra ADR-INF-13).
*Decisión:* en `dev` el servicio corre en una NVIDIA T4 (`g4dn.xlarge`, infra §3.4) en float32 sin TF32, con el
preprocesamiento en CPU; `local` y CI siguen en CPU con el mismo código (`EMBEDDING_DEVICE`). El dispositivo no forma
parte de la `version_vector` mientras los vectores en GPU estén a ≤ 1e-4 de los dorados (§5.4), lo que EMB-2.2
comprueba antes de indexar nada en GPU. *Alternativas descartadas:* ONNX Runtime o int8 en CPU (cambian los vectores y
no bajan de 1 s con 5 fotos en 1–2 vCPU); fp16 en GPU (más rápido, pero cambia los vectores: queda como palanca de
EMB-3.1). *Consecuencias:* imagen de ~6 GB y *build* más lento; el servicio está apagado por defecto y tarda 5–10 min
en encender (infra R6); con `cuda` y sin GPU, el arranque falla en lugar de caer a CPU; si la tolerancia entre
dispositivos no se cumple, la GPU necesita una `version_vector` propia (R8 de 0.4.0).

**ADR-EMB-11 — DINOv2 ViT-S/14 (384 dimensiones) en CPU con 2 vCPU (aceptada, 0.5.0; reemplaza a ADR-EMB-01 y
ADR-EMB-10).**
La cuenta no tiene cupo de GPU y el equipo no puede esperar el aumento (infra ADR-INF-14). En CPU, ViT-B/14 tarda
~5,5 s con 5 fotos en 1 vCPU (medición de referencia de infra ADR-INF-13); ViT-S/14 hace unas 4 veces menos cómputo por
foto (22 M parámetros frente a 86 M) y en 2 vCPU se estima en 0,5–1,5 s para 5 fotos (sin medir: EMB-3.1).
*Decisión:* `facebook/dinov2-small` con el mismo preprocesamiento pp-v1 y la misma extracción (CLS tras la
*layernorm*, L2); `version_vector` nueva `dinov2-vits14/pp-v1`, dimensión 384. *Alternativas descartadas:* ViT-B/14 en
4 vCPU (el doble de costo por hora y aun así por encima de 1 s con 5 fotos); esperar la GPU. *Consecuencias:* vectores
y índice más pequeños en pgvector y, previsiblemente, algo menos de precisión en la recuperación, que mide EMB-3.2; si
la latencia no llega al objetivo, palancas de §4.4. Como aún no hay vectores indexados, el cambio no exige re-indexar.

**ADR-EMB-12 — Vectores dorados calculados con la pila de `uv.lock` en la CPU de quien cierra; 1e-5 también entre
CPU (aceptada, 0.6.0, EMB-2.1).**
§5.4 promete 1e-5 en la misma imagen de contenedor, pero los dorados se comprueban en sitios con CPU distintas: CI
(`test_dorados.py`, en el runner de GitHub), la máquina de quien valida (`validate21.py` C1, contra la imagen) y, más
adelante, Fargate. *Medición* (EMB-2.1, pesos de la revisión fijada, las 5 doradas y 3 sintéticas): AMD Ryzen 7 6800HS
(AVX2, torch 2.14.1+cpu) frente a un Intel Xeon con AVX-512 y AMX (torch 2.14.1 de PyPI, mismo commit, compilador y
oneDNN), y en cada uno las rutas AVX2 y SSE de MKL, oneDNN y ATen forzadas, con 1 y 2 hilos: diferencia máxima por
componente entre dos configuraciones cualesquiera, 6,3e-7; el tamaño del lote (1, 5, 8) y los hilos no cambian ni un
bit; el tensor preprocesado es idéntico bit a bit en todas, también sin el SIMD de libjpeg-turbo. *Decisión:* se
mantiene 1e-5 (16 veces lo medido) en las tres comprobaciones. Los dorados se calculan en proceso con
`tools/dorados.py` (el mismo `preproceso` + `ModeloDinov2` que el servicio, versiones exactas de `uv.lock`, 1 hilo) en
la CPU de quien cierra el lote, que es donde corre `validate21`; los pesos se copian de la imagen (`/opt/modelo`) a
`project/.modelo/`, ignorada por Git y por Docker. En CI, `embedding.yml` baja la revisión fijada (con caché) y corre
`pytest` con `DORADOS_OBLIGATORIOS=1`, para que la prueba falle en vez de omitirse si faltan los pesos.
`esperados.json` guarda con qué se calcularon y el `sha256` del tensor preprocesado, que separa un cambio de
decodificación de uno numérico. *Alternativas descartadas:* calcularlos en CI (cada ejecución puede caer en otra CPU) o
pidiéndolos a la imagen por HTTP (obliga a construirla en local antes de cada cambio y da los mismos números); relajar
la tolerancia (no hace falta). *Consecuencias:* si una CPU futura (otra familia en Fargate o en los runners) superara
1e-5, habría que separar la tolerancia entre CPU de la de la misma imagen, como se hizo en 0.4.0 entre dispositivos,
antes de indexar con ella. Actualizar Pillow puede cambiar el `sha256` del tensor sin salir de 1e-5: se mide con
`tools/dorados.py comparar` y, si cabe, se recalculan con `tools/dorados.py vectores`.

---

## 7. Riesgos

| ID | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | Latencia por encima del objetivo (lote de 5 > 800 ms en 2 vCPU) | Media | Medio | EMB-3.1; palancas de §4.4 |
| R2 | Calidad de recuperación insuficiente (luz, oclusiones, recorte central, lugares parecidos; ViT-S/14 discrimina algo menos que ViT-B/14) | Media | Alto | EMB-3.2; EMB-5.1 si una variante gana (incluido volver a ViT-B/14 con más vCPU o con GPU) |
| R3 | Imagen grande (~1,8 GB): 2–3 min desde el encendido | Alta | Bajo | *Start period* de 180 s; el `worker` espera a `/health/ready`; encender antes de probar (infra R6) |
| R4 | Una actualización de librerías cambia los vectores sin avisar | Media | Alto | Versiones fijadas en `uv.lock`; vectores dorados en CI (con los pesos y `DORADOS_OBLIGATORIOS=1`) y en `validate21` (ADR-EMB-12) |
| R5 | Ingesta masiva satura el servicio | Media | Bajo | Prioridad; `503 SATURADO`; el `worker` reintenta |
| R6 | Falta de memoria con lotes grandes | Baja | Medio | `LOTE_MAX = 8`; 4 GB de tarea; medir en EMB-3.1 |
| R7 | La revisión fijada desaparece de Hugging Face | Baja | Medio | Las imágenes ya publicadas en ECR conservan los pesos; guardar una copia de los pesos fuera de Hugging Face si se vuelve crítico |
