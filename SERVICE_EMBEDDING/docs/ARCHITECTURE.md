# ARCHITECTURE — Servicio de embeddings (`SERVICE_EMBEDDING`)

| Campo | Valor |
|---|---|
| Versión del documento | **0.9.0** (historia en [`CHANGELOG.md`](./CHANGELOG.md)) |
| Fecha | 2026-10-25 |
| Estado | En construcción: código de EMB-1.1 (servicio base e imagen), EMB-2.1 (vectorización por lotes), EMB-3.1 (benchmark y su validador; latencias de `dev` medidas en §5.7) y la parte de EMB-3.2 que no necesita dataset (protocolo de captura, `tools/evaluacion/` y `validate32.py`, probados con datos sintéticos; sin ejecutar en `dev`); el resto de lotes, pendiente |
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
| Herramienta de evaluación y `validate32.py` (EMB-3.2): `POST /v1/auth/login`, `GET /v1/admin/videos` y `/videos/{id}` (BE-2.1), `POST /v1/admin/diagnostico/vecinos` (BE-2.4), parámetros `LOC_*` y algoritmo v1 | Backend §5.3, §5.5, §5.10 y §4.10 |
| Prefijo `evaluacion/` del bucket del dataset y secreto `campus-locator/dev/admin-inicial` | Infra §5.5; backend §5.11 |

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
    │   ├── benchmark.py          EMB-3.1: latencia de POST /v1/embed por tamaño de lote (va dentro de la
    │   │                         imagen; §4.4, uso y salida en §5.9)
    │   ├── dorados.py            EMB-2.1: imágenes de referencia y vectores esperados de tests/golden/ (§5.4)
    │   └── evaluacion/           EMB-3.2: recuperación sobre el conjunto de consulta (§4.5; órdenes y API, §5.9)
    │       ├── __main__.py       `uv run python tools/evaluacion <orden>`: pone tools/ y src/ en sys.path
    │       ├── cli.py            órdenes revisar, cobertura, evaluar y variantes; informe JSON y Markdown
    │       ├── conjunto.py       puntos.json: carga, revisión, haversine, cobertura y criterio C1 (solo stdlib)
    │       ├── fuentes.py        interfaces BuscadorVecinos y FuenteDataset; cliente del backend (httpx),
    │       │                     fuerza bruta, carpeta local; preparar_foto (como /v1/localize)
    │       ├── metricas.py       recall a 15 m, similitudes, simulación del algoritmo v1, recomendaciones
    │       └── variantes.py      variantes de preprocesamiento/extracción y ExtractorDinov2 (pesos locales)
    ├── tests/                    contrato HTTP, configuración, modelo, preproceso, planificador, validadores
    │                             (test_ops_comun, test_validate31 y test_validate32 con dobles de AWS),
    │                             benchmark, evaluación (test_evaluacion, datos sintéticos) y vectores
    │                             dorados (golden/: cinco imágenes y esperados.json, §5.4)
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
Objetivo: lote de 5 en p95 ≤ 800 ms en `dev` (2 vCPU), para que `POST /v1/localize` quede en p95 ≤ 1 s (infra §5.10;
el resto se va en el backend y en la búsqueda en RDS, backend §4.10). Estimación previa, sin medir: 0,5–1,5 s
(ADR-EMB-11). Medido en `dev` el 2026-10-25: lote de 5 en p95 413 ms, holgado bajo el objetivo (C3 no aplica);
tablas completas en §5.7.

**Qué mide `tools/benchmark.py`** (ADR-EMB-13; argumentos, salida y códigos en §5.9):
1. Genera las imágenes en memoria: JPEG sintéticos de 1024 × 768 px y calidad 85 (como las fotos de `/v1/localize`,
   backend §5.3), con semilla fija: fondo suave, 40 bloques y ruido (~129 KiB de media; una foto real de 1024 px suele
   pesar algo más, así que decodificarla tarda algo más).
2. Arranca el servicio como **subproceso** con el comando de la imagen (`uvicorn app.main:app`, un proceso), pero
   solo en `127.0.0.1:8080` y con `TORCH_NUM_THREADS` = `--hilos` (por defecto, la variable de la tarea: 2 en `dev`).
   Sus logs salen por la salida de error. Espera a `GET /health/ready` = 200 (máx. 300 s) y lee `GET /v1/info`
   (`commit`, `version_vector`).
3. Para cada lote (por defecto 1, 4, 5 y 8 imágenes; 40, 30, 60 y 30 repeticiones medidas, más 3 de calentamiento
   que se descartan) envía **en serie** el mismo `POST /v1/embed` con `X-Prioridad: alta`, por una conexión HTTP
   persistente, y mide en el cliente desde que empieza a enviarlo hasta tener la respuesta completa: subida en
   *loopback*, multipart, cola (vacía), pp-v1, modelo y JSON. Guarda también `tiempos_ms.inferencia` y `.cola` de
   cada respuesta. El lote de 4 no lo pide el PLAN: es el del `worker` (backend §5.10), el que una localización puede
   tener que esperar.
4. Lee la memoria del proceso del servicio (`VmRSS` y el pico `VmHWM` de `/proc/<pid>/status`), lo detiene y, ya
   sin servicio, mide pp-v1 por imagen en su propio proceso, el modelo de CPU (`/proc/cpuinfo`) y la ruta SIMD de
   PyTorch (`torch.backends.cpu.get_cpu_capability()`).
5. Escribe una sola línea `BENCHMARK_JSON {…}` (o una tabla con `--salida texto`). Percentiles por rango más cercano:
   p95 de 60 repeticiones = la 57.ª más rápida.

**Cómo se mide en `dev`** (`validate31.py`, §5.8): una **tarea suelta** con la misma revisión de
`campus-locator-dev-embedding` y la misma red que el servicio `embedding` (hoy la subred `publica-a`, que es el output
`subredes_tareas`, el grupo `campus-locator-dev-embedding` y `assignPublicIp = ENABLED`, sin la cual no llegaría a ECR
ni a CloudWatch porque no hay NAT, infra §3.2), con el comando sobrescrito a
`python tools/benchmark.py --salida json`. No necesita el servicio encendido ni lo toca (infra §5.11): no entra en
Cloud Map, así que nadie le envía tráfico, y como su `group` es `family:…` y no `service:embedding`, su parada no
dispara la regla de EventBridge (infra §3.8). Su log va a `/campus-locator/dev/embedding`, stream
`embedding/app/<id-de-la-tarea>`. El *health check* de la definición (infra §5.7) también corre: pasa en cuanto el
servicio del benchmark queda listo en el puerto 8080.

**Imagen.** Hasta `f2ddc42` (EMB-2.1, la desplegada al escribir esto) la imagen trae un `tools/benchmark.py`
provisional que termina con código 1 sin medir (comprobado con `docker run`): para medir hay que desplegar antes un
commit con EMB-3.1. `validate31.py` P1 lo detecta leyendo con `git` el `tools/benchmark.py` del SHA de la imagen
desplegada.

**Ensayo local** (solo prueba de humo: la CPU y la forma de repartirla no son las de Fargate; **no vale para §5.7**).
Imagen `f2ddc42` con el `benchmark.py` de EMB-3.1 encima, `--memory 4g`, `TORCH_NUM_THREADS=2`, AMD Ryzen 7 6800HS
(AVX2), 2026-10-25:

| Ensayo | Lote 1 p50 / p95 | Lote 4 p50 / p95 | Lote 5 p50 / p95 | Lote 8 p50 / p95 |
|---|---|---|---|---|
| `--cpus 2`, repeticiones por defecto | 129 / 150 ms | 468 / 567 ms | 605 / 846 ms | 1063 / 1158 ms |
| `--cpus 2`, 30 / 40 / 20 repeticiones | 147 / 172 ms | — | 641 / 699 ms | 1053 / 1129 ms |
| `--cpuset-cpus 2,3`, 30 / 40 / 20 | 158 / 195 ms | — | 658 / 695 ms | 1035 / 1135 ms |
| `--cpus 2`, **1 hilo**, 10 repeticiones | 195 / 210 ms | — | 943 / 967 ms | — |

En el primer ensayo: listo a los 12,6 s, memoria del proceso 477 MiB en reposo y 541 MiB de pico, pp-v1 12,3 ms por
imagen (p50) y `tiempos_ms.inferencia` a 10 ms o menos del total en p50 y en p95 de todos los lotes (el HTTP en
*loopback* casi no pesa). La dispersión del primer p95 del lote de 5 (846 ms frente a ~700 en los otros dos) es ruido de la máquina
anfitriona: por eso `dev` mide con 60 repeticiones.

**Palancas si el lote de 5 pasa de 800 ms en p95** (C3: la decide quien cierra el lote y la registra como ADR
nuevo; **sin decidir**). Se prueban en este orden; los efectos son estimaciones generales, no medidas de este
proyecto, salvo donde se dice:

| Orden | Palanca | Qué cambia | Efecto esperado | Costo | ¿`version_vector` nueva? |
|---|---|---|---|---|---|
| 1 | Ajustar hilos y el trabajo fuera del modelo | Probar `TORCH_NUM_THREADS` de 1 a 4 con `benchmark.py --hilos N` (en local, 1 → 2 hilos bajó el lote de 5 de 943 a ~640 ms); decodificar y preprocesar las imágenes del lote en paralelo (hoy van en serie en el hilo de inferencia: ~12 ms × 5 en la CPU de ensayo) | Pequeño: como mucho lo que pesa pp-v1 en el lote (`preproceso_ms_por_imagen` × lote) más lo que ganen los hilos | Ninguno en AWS. Cambiar `TORCH_NUM_THREADS` en `dev` es infra §5.4; paralelizar pp-v1, código del servicio (`preprocesar_lote`, que hoy llama el hilo de inferencia, §4.3) | No: los hilos no cambian un bit (ADR-EMB-12, medido con 1 y 2) y pp-v1 da el mismo tensor sea cual sea el orden |
| 2 | ONNX Runtime (float32) | Exportar `Dinov2Model` a ONNX y servirlo con `onnxruntime` en lugar de PyTorch | Del orden de 1,2–2× en CPU para ViT pequeños (sin medir aquí) | Un lote de código: exportación, dependencia nueva, dorados nuevos; imagen distinta. Sin costo de AWS | **Sí** (ADR-EMB-08). Sin vectores indexados todavía, no obliga a re-indexar si se decide antes de la primera ingesta real (BE-2.2 + FE-2.1) |
| 3 | 4 vCPU | Tarea de 4 vCPU / 8 GB (el mínimo de memoria de Fargate con 4 vCPU) y `TORCH_NUM_THREADS = 4` | Menos de 2×: escala la parte del modelo, no pp-v1 ni el HTTP (sin medir) | ~0,197 USD/h encendido frente a ~0,099 (el doble): +4 USD/mes con 40 h y +16 USD/mes con 160 h (tarifas de infra §3.10). Lo cambia infra (§3.4, §5.4, ADR-INF-14) | No, pero hay que pasar los dorados con 4 hilos (ADR-EMB-12 solo midió 1 y 2) |
| 4 | int8 (cuantización dinámica de las capas lineales) | `torch.ao.quantization.quantize_dynamic` o int8 en ONNX Runtime | Del orden de 1,5–2,5× en las capas lineales (sin medir), con pérdida de precisión en la recuperación que tendría que medir EMB-3.2 | Un lote de código y su evaluación | **Sí** (ADR-EMB-08) |

Exportar o cuantizar cambia los vectores, así que conviene decidirlo antes de indexar el dataset real.

**Lo que los lotes siguientes (BE-3.2, EMB-3.2) deben saber de estas cifras.**
- Son de `POST /v1/embed` con el servicio **ocioso** y en *loopback*: no incluyen la red de la VPC ni la subida de 5
  fotos desde `api`, ni el trabajo del backend.
- Con ingesta en curso, una localización espera a que termine el lote `baja` que se está calculando (§4.3): el peor
  caso de embeddings es ≈ p95 del lote de 4 + p95 del lote de 5. Por eso el benchmark mide también el de 4.
- Fargate puede dar a cada tarea una generación de CPU distinta (sin comprobar aquí): cada medida guarda `cpu` y
  `capacidad_cpu_torch`; si dos medidas difieren mucho, mirar eso primero.
- El *health check* (cada 30 s) arranca un `python` dentro del contenedor y roba unos milisegundos de CPU: puede
  producir algún valor alto suelto, igual que en el servicio real.
- En local, `docker run --cpus 2` reparte por cuota, no da dos núcleos: sirve para ensayar, no para comparar con `dev`.

### 4.5 EMB-3.2 — Conjunto de evaluación y calibración

**Estado (0.9.0).** Hecho lo que no necesita dataset: el protocolo de captura (abajo), `tools/evaluacion/` y
`src/ops/validate32.py`, probados con datos sintéticos (`tests/test_evaluacion.py`, `tests/test_validate32.py`).
**Falta**, porque depende de otros lotes y del trabajo de campo: el dataset real indexado (FE-2.1 + BE-2.2), el
endpoint de vecinos desplegado (BE-2.4), tomar y subir las fotos, generar el informe, ejecutar `validate32.py` en
`dev` y entregar los valores a BE-3.2 (C3). La comparación de variantes necesita además BE-4.1 (las URL de las
imágenes del dataset). Ningún número de calidad de recuperación de este documento está medido todavía.

**Qué se mide** (PLAN EMB-3.2; método y por qué en ADR-EMB-14):
- Cada foto de consulta de un **punto con dataset** (alguna imagen del dataset a ≤ 30 m) se envía a
  `POST /v1/admin/diagnostico/vecinos` con `k = 10` (`LOC_TOP_K`, backend §5.10). Acierto a `k` = alguno de los `k`
  primeros vecinos está a ≤ 15 m del punto. *recall@1* y *recall@5* = fracción de fotos con acierto a 1 y a 5.
- Similitudes de los 5 primeros vecinos de esas fotos: **mismo lugar** (vecino a ≤ 15 m del punto) y **otro lugar**
  (a > 50 m); entre 15 y 50 m no cuentan. De las fotos de **puntos lejanos** (toda imagen a > 150 m) se guarda la
  similitud de su mejor vecino (`lejos_del_dataset`): son las que deben dar `sin_coincidencias` (BE-3.2 C5).
  Percentiles por rango más cercano, como §5.9. Los puntos «intermedios» (entre 30 y 150 m) no se consultan.
- *Recall* por franja horaria (`por_hora`), para ver si la luz importa.

**Qué se recomienda** (`recomendado` del informe; todo en rejilla de 0,01):
1. `LOC_SIM_MIN` = el umbral que maximiza TPR − FPR entre «mismo lugar» y «otro lugar» (Youden; a igualdad, el
   menor), subido si hace falta hasta 0,01 por encima de la mejor similitud de un punto lejano (si no, BE-3.2 C5
   fallaría), y limitado a [0,01; 0,98]. `detalle_recomendacion` dice qué parte decidió y qué fracción de vecinos
   «mismo lugar» sobrevive.
2. `LOC_SIM_ALTA` = el menor umbral por encima de `LOC_SIM_MIN` con el que ≥ 95 % de los vecinos (mínimo 5) por
   encima son «mismo lugar»; si ninguno, el p90 de «mismo lugar» (al menos `LOC_SIM_MIN` + 0,05; máximo 1).
3. Cortes de nivel: se **simula** `/v1/localize` (pasos 3–7 de backend §4.10, con `LOC_RADIO_GRUPO_M` = 20,
   `LOC_PESO_EXPONENTE` = 4 y los dos umbrales recomendados) sobre «consultas» de hasta 5 fotos: las de una misma
   `vuelta` del punto o, sin `vuelta`, las del mismo punto, día y franja. `corte_alta` = el menor valor en
   [0,50; 0,99] con el que ninguna consulta de nivel alta yerra > 30 m (BE-3.2 C2) y ≥ 90 % quedan a ≤ 15 m;
   `corte_media` = el menor por debajo con ≥ 60 % a ≤ 15 m. Donde §4.10 no fija la fórmula, la simulación asume (a
   confirmar con BE-3.2): centroide de grupo = media sin ponderar de sus miembros; `m = (p₁ − p₂) / p₁`, 1 con un solo
   grupo. Los parámetros del backend están copiados en `metricas.py`: si cambian en backend §5.10, se cambian ahí.
4. Los valores son una propuesta para C3: con ~50 fotos y ~10–20 consultas son ruidosos; la persona los revisa con
   `detalle_recomendacion` y `simulacion` antes de entregarlos.

**Variantes** (las compara la orden `variantes`, §5.9; no se despliegan: si una gana, EMB-5.1): `pp-v1-local` (pp-v1
calculada aquí: referencia de la fuerza bruta), `sin-recorte` (lado menor 224, el mayor proporcional truncado a
múltiplo de 14, tope 896: no pierde el tercio de altura de las fotos verticales, ADR-EMB-04), `res-448` (lado menor
512 y recorte central 448) y `media-parches` (pp-v1 con la media de los *tokens* de parches tras la *layernorm* final
en lugar del CLS, ADR-EMB-03). Se calculan en el proceso de la herramienta con los pesos de `project/.modelo/`
(`ExtractorDinov2` comprueba `revision.json` como el servicio; con pp-v1 reproduce los vectores dorados a ≤ 1e-5,
prueba `test_extractor_reproduce_los_vectores_dorados_de_pp_v1`, comprobado en local con los pesos de la revisión
fijada), y el dataset, reducido a 1024 px como lo envía el `worker`, se vectoriza con la misma variante y se busca por
fuerza bruta. Hoy no se puede ejecutar contra el dataset real: `GET /v1/admin/videos/{id}` devuelve `url = null` hasta
BE-4.1 (backend §5.5) y la orden termina con 2 (`[PENDIENTE]`).

#### Protocolo para tomar las fotos de consulta

Para una persona en el campus. Cumple C1 (≥ 50 fotos en ≥ 10 puntos con dataset, ≥ 1 punto con ≥ 3 fotos a > 150 m
del dataset) con margen. El resultado es una carpeta con la forma de §5.9 que se revisa y sube con
`validation-3-2.md` §5 (pasos 3 a 6).

**Antes de salir: elegir los puntos.**
1. Esperar a que el dataset esté grabado (FE-2.1) o, como mínimo, conocer sus recorridos. Elegir **12 puntos** sobre
   esos recorridos (2 de margen: si alguno queda a más de 30 m de toda imagen tras la ingesta, no cuenta), separados
   entre sí ≥ 50 m y variados: entradas, plazoletas, pasillos exteriores y lugares que se parezcan entre sí (los
   difíciles).
2. Elegir **1 o 2 puntos lejanos**, en zona transitable y segura, a más de 150 m de cualquier recorrido del dataset.
3. Cada punto en un sitio que se reconozca a simple vista **y** en el mapa satelital (una esquina de edificio, un poste,
   una puerta, el centro de una plazoleta): hay que volver a él en otra franja sin desviarse más de 2–3 m.
4. Identificadores `P01`, `P02`… y una descripción corta (`Entrada de la biblioteca`).
5. Las fotos de consulta **nunca** entran al dataset: no se toman con la app en modo recolección ni se suben a
   `dataset/`.

**La coordenada de cada punto.**
- Se lee del mapa satelital tocando el sitio exacto, en grados decimales WGS84 con 6 decimales (≈ 0,1 m), en lo
  posible el mismo mapa con el que se fija el inicio de los recorridos del dataset (la app lo fija con un toque en el
  mapa: frontend ARCHITECTURE, recolección), para compartir el mismo error de referencia.
- Comprobación cruzada: el GPS del teléfono quieto 30 s en el punto. Si difiere más de 10 m, se repite la lectura en
  el mapa; la que vale es la del mapa (el GPS entre edificios suele errar varios metros: sin medir aquí).
- Una coordenada por punto; todas sus fotos se toman desde ahí (±3 m). El *recall* se mide a 15 m: el error de la
  coordenada debe ser muy inferior.

**Las fotos: una vuelta por punto y sesión.**
- De pie en el punto, 5 fotos girando ~72° entre una y otra (una vuelta como la de `/v1/localize`), con el teléfono
  como lo sostiene la app al escanear (orientación a confirmar con frontend; mientras tanto, vertical, a la altura del
  pecho y sin inclinar). Sin zoom ni flash; JPEG (en iPhone, formato «Más compatible», no HEIC). El tamaño da igual:
  la herramienta las reduce a 1024 px como la app.
- Rumbo de cada foto con una brújula en **norte verdadero** (backend ADR-BE-12), redondeado al grado; si la brújula
  no da norte verdadero o no se pudo leer, `null` (no se inventa).
- Evitar caras en primer plano y matrículas; no fotografiar interiores de aulas ni oficinas.
- Anotar en la hoja de registro: punto, número de foto, vuelta, hora local (Bogotá) y rumbo.

**Las horas del día.** Franjas por la hora de Bogotá: `manana` 05:00–11:59, `tarde` 12:00–17:59, `noche` el resto
(la herramienta avisa si `hora` no cuadra con `capturada_en`).
- Mínimo para C1: los puntos con dataset con 1 vuelta de 5 (≥ 50 fotos) y el lejano con 1 vuelta (≥ 3 fotos).
- **Recomendado**: cada punto con dataset en **2 franjas** (mañana y tarde; cada sesión es una `vuelta` nueva: 1, 2…),
  ≈ 120 fotos, y si se puede en un día distinto del de la grabación del dataset (cambian la gente y la luz). La noche
  es opcional (3 puntos bastan para ver la caída en `por_hora`).

**De la hoja a `puntos.json`** (formato §5.9). Carpeta local `project/.validacion/evaluacion/<version_conjunto>/`
(ignorada por Git), con la versión `AAAA-MM<letra>` (`2026-11a`; si se rehace, `2026-11b`: nunca se reutiliza una
versión ya subida con otro contenido, porque BE-3.2 toma la última en orden lexicográfico).
- Fotos en `fotos/<punto>/<n>.jpg`, con `n` consecutivo por punto a través de las vueltas (1–5 la vuelta 1, 6–10 la 2).
- `capturada_en` en UTC con `Z`: hora local de Bogotá + 5 h (Colombia no tiene horario de verano). También se puede
  copiar de la fecha EXIF de la foto (`DateTimeOriginal`, hora local del teléfono) sumando 5 h.
- Revisar con `tools/evaluacion revisar`, comprobar la cobertura con `cobertura` y subir solo bajo `evaluacion/`
  (`validation-3-2.md` §5, pasos 3 a 6).

**Trampas conocidas.**
- Un `.jpg` subido por error bajo `dataset/` dispara la ingesta (infra §5.5) y contamina el dataset.
- El EXIF de las fotos trae la posición GPS: la herramienta lo descarta al preparar cada foto (`preparar_foto`), pero
  los originales del bucket lo conservan (el bucket es privado, infra §5.5).
- `POST /v1/admin/diagnostico/vecinos` vectoriza con `embedding`: la orden `evaluar` necesita el servicio encendido
  (recurso compartido; ~0,10 USD/h) y, si no, termina con `503 EMBEDDING_NO_DISPONIBLE`.
- `GET /v1/admin/images` y `GET /v1/admin/images/{id}` son de BE-4.1: la herramienta y el validador leen el dataset con
  `GET /v1/admin/videos` + `GET /v1/admin/videos/{id}` (BE-2.1) y excluyen los videos `validacion-…`.
- Los vecinos del endpoint salen del índice HNSW (aproximado); los de las variantes, de fuerza bruta (exacta): por eso
  las variantes se comparan con `pp-v1-local`, no con la fila `pp-v1` del backend.

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
  componente se aleja más de 1e-5. Uso de la herramienta, formato de `esperados.json` y cómo obtener los pesos: §5.9.
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
| Contenido | `src/app/` (como paquete `app`, en `/srv/app`) y `tools/benchmark.py` (en `/srv/tools/`; el directorio de trabajo es `/srv`); `src/ops/`, `tests/`, `tools/dorados.py` y `tools/evaluacion/` quedan fuera. Las imágenes anteriores a EMB-3.1 (`44fdff8`, `f2ddc42`) traen un `benchmark.py` provisional que sale con código 1 sin medir |
| Variables fijadas en el `Dockerfile` | `MODELO_DIR=/opt/modelo`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_HOME=/tmp/huggingface` (el usuario de la imagen no tiene carpeta personal) y `GIT_COMMIT` (argumento de build con el SHA del commit, por defecto `desconocido`; `/v1/info` publica sus 7 primeros caracteres como `commit`) (la aplicación además aplica `TORCH_NUM_THREADS` a PyTorch y a OpenMP al arrancar) |
| Variables que inyecta la infraestructura | `TORCH_NUM_THREADS`, `LOG_LEVEL`, `APP_ENV` (infra §5.4) |
| Tamaño esperado | ~1,8 GB (PyTorch CPU + transformers + pesos de ~90 MB) |
| Memoria en ejecución | Medida en local (ensayo de EMB-3.1, §4.4): 477 MiB de RSS en reposo y 541 MiB de pico tras lotes de hasta 8. En `dev` (EMB-3.1, §5.7): 475 MiB en reposo y 538 MiB de pico (campo `memoria_proceso_mb` del benchmark). La tarea tiene 4 GB |

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
| Latencia objetivo | En `dev` (2 vCPU): lote de 5 p95 ≤ 800 ms; lote de 1 p95 ≤ 250 ms | Para `POST /v1/localize` en p95 ≤ 1 s (infra §5.10). Lo medido, en «Latencias medidas» abajo; estimación previa en ADR-EMB-11 |
| Formato de log | JSON por línea en la salida estándar: siempre `ts` (UTC, ms), `nivel` y `evento`; además, según el evento, `request_id`, `prioridad`, `n_imagenes`, `cola_ms`, `inferencia_ms` (vectorización, EMB-2.1: en el evento `peticion` de `POST /v1/embed`), `metodo`, `ruta`, `estado_http`, `duracion_ms` (cada petición), `carga_ms`, `calentamiento_ms`, `revision`, `version_vector`, `hilos`, `commit` (arranque) y `traza` (errores) | Nunca bytes de imagen. Eventos: `arranque`, `modelo_listo`, `carga_del_modelo_fallida`, `peticion`, `error_no_previsto` y los de uvicorn; los avisos de Python (`warnings`, logger `py.warnings`) también salen en JSON, con el aviso en `evento`. Las peticiones a `/health` y `/health/ready` van en nivel `DEBUG` (el *health check* llama cada 30 s) |

Cada parámetro tiene su valor por defecto en `config.py` y se puede sobrescribir con una variable de entorno del mismo nombre; si alguna se vuelve necesaria en `dev`, se añade antes a infra §5.4.

**Latencias medidas en `dev`** (EMB-3.1: `tools/benchmark.py` en una tarea suelta con la definición de
`campus-locator-dev-embedding`, 2 vCPU / 4 GB, `TORCH_NUM_THREADS = 2`; qué mide cada columna en §4.4 y §5.9). Las
copia quien cierra el lote del detalle de C1b de `validate31.py` y del JSON que guarda (C2), y sube la versión.

| Lote | p50 | p95 | `inferencia` p95 | Repeticiones |
|---|---|---|---|---|
| 1 | 91 ms | 92 ms | 90 ms | 40 |
| 4 (el del `worker`) | 326 ms | 331 ms | 327 ms | 30 |
| 5 | 406 ms | 413 ms | 409 ms | 60 |
| 8 | 659 ms | 668 ms | 663 ms | 30 |

| Dato de la medida | Valor |
|---|---|
| Fecha, commit de la imagen y tarea | 2026-10-25 19:16 UTC; imagen `a7d2907` (`campus-locator-dev-embedding:5`); tarea `55cdd0de6c41465ba5bd5c043082a031` (descarga de la imagen 15 s, ejecución 96 s; arranque del servicio dentro de la tarea 4,0 s) |
| CPU (`cpu`, `capacidad_cpu_torch`) | `Intel(R) Xeon(R) 6975P-C`, `AVX512`; 2 hilos; límites 2 vCPU / 4096 MiB leídos de ECS (`limites_de = ecs`) |
| Memoria del proceso (reposo / pico) | 475 / 538 MiB |
| pp-v1 por imagen (p50) | 8,4 ms (`preproceso_ms_por_imagen`) |
| Peor caso de embeddings en `/v1/localize` con ingesta en curso (≈ p95 del lote de 4 + p95 del lote de 5, §4.4) | ≈ 744 ms (331 + 413) |
| ¿Lote de 5 en p95 ≤ 800 ms? Si no, palanca elegida (C3, ADR) | Sí (413 ms): C3 no aplica, ninguna palanca |

Máximos observados: 95, 399, 588 y 867 ms (lotes de 1, 4, 5 y 8); `cola_max_ms` = 0 en todos (servicio ocioso).
Una sola tarea: la variación entre generaciones de CPU de Fargate sigue sin medir (§4.4).

Son tiempos de `POST /v1/embed` con el servicio ocioso, medidos en *loopback* dentro de la tarea: lo que el backend
añada (red de la VPC, subida de las fotos, su propio trabajo) va aparte (§4.4).

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

**Variables que leen**: `EMBEDDING_IMAGEN` (en `local`), `AWS_PROFILE` (en `dev`, y en `local` si `EMBEDDING_IMAGEN`
es de ECR, para el `docker login`) y, para EMB-3.2,
`VALIDACION_API_URL`, `VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` (las mismas del backend, su §5.11). Las
imágenes de referencia de los vectores dorados y sus vectores esperados están en `project/tests/golden/` (§5.4).
Los validadores no usan la cadena de credenciales por defecto de AWS: sin `AWS_PROFILE` terminan con código 3 aunque
`aws` funcione en esa terminal; con el perfil por defecto se define `AWS_PROFILE=default`.

**Lo que la imagen incluye para los validadores**: `tools/benchmark.py` va dentro de la imagen (en `/srv/tools/`) para
poder ejecutarlo como tarea suelta en `dev` con el comando `python tools/benchmark.py --salida json`; el resultado
(formato en §5.9) se lee del log `/campus-locator/dev/embedding`. `tools/evaluacion/` no va en la imagen: se ejecuta en
la máquina de quien valida sobre una copia local del conjunto de `evaluacion/` del bucket (infra §5.5) y obtiene los
vecinos del dataset con el endpoint de diagnóstico del backend (§5.9).

**Tareas sueltas en `dev`** (`validate11.py` C1b y `validate31.py` C1a). `ecs run-task` con: `cluster` =
`campus-locator-dev`; `taskDefinition` = la revisión que usa el servicio `embedding` (`describe-services` →
`taskDefinition`: la última que registró `embedding.yml`), no la última de la familia; `launchType = FARGATE`;
`networkConfiguration` = la del servicio, copiada tal cual (hoy subred `publica-a` = output `subredes_tareas`, grupo
`campus-locator-dev-embedding` y `assignPublicIp = ENABLED`; sin IP pública no descarga la imagen, infra §3.2);
`startedBy = validacion-emb<fase><n>`; y, si se mide, `overrides.containerOverrides = [{"name": "app", "command":
[…]}]`. No se usa `sg_migrate` (el grupo `-api`, infra §5.7): el de `embedding` es el del servicio y también sale a
todo. La tarea termina sola (el benchmark) o la detiene la limpieza; su log queda en el stream
`<awslogs-stream-prefix>/app/<id>` (`embedding/app/<id>`; el prefijo se lee de la definición).

**`validate31.py`** (EMB-3.1, solo `dev`): P3 credenciales → P2 INF-1.3 (clúster, familia, log group) → P1 EMB-2.1
«Hecho» en PLAN §3 y la imagen del servicio es de CI (`…/campus-locator/embedding:<SHA de 40>`) y su
`tools/benchmark.py`, leído con `git` en ese SHA, contiene `BENCHMARK_JSON` (si no, código 2 sin lanzar nada). C1a
lanza el benchmark como tarea suelta y espera `STOPPED` (cada 15 s, máx. 30 min): pasa con salida 0, familia
`campus-locator-dev-embedding` y tamaño `2048` / `4096`. C1b lee el stream (paginado, reintenta 2 min si el log
llega tarde), toma la última línea `BENCHMARK_JSON` y exige `version_vector` = la de §5.3, `commit` = los 7 primeros
del SHA desplegado y, en los lotes 1, 5 y 8, `0 < p50_ms ≤ p95_ms` con ≥ 20 repeticiones; guarda el JSON en
`project/.validacion/EMB-3.1-benchmark-<id>.json` y dice en el detalle si C3 aplica (p95 del lote de 5 > 800 ms). C2
y C3 son manuales. Detalle completo en `validation-3-1.md`.

**`validate32.py`** (EMB-3.2, solo `dev`, solo lectura): P4 credenciales → P1 EMB-2.1 «Hecho» → P2 login de admin
(`VALIDACION_API_URL` obligatoria; correo y contraseña de `VALIDACION_ADMIN_*` o del secreto
`campus-locator/dev/admin-inicial`; `401` → 3, otro fallo → 2) y algún video real con imágenes procesadas
(`GET /v1/admin/videos`) → P2b `POST /v1/admin/diagnostico/vecinos` responde `200` con la `version_vector` de §5.3 o
`503 EMBEDDING_NO_DISPONIBLE` (no enciende `embedding`) → P3 hay algún `evaluacion/<version_conjunto>/puntos.json`. C1
revisa `puntos.json`, los archivos del bucket y la cobertura frente al dataset con `evaluacion.conjunto`; C2, el
informe más reciente con `evaluacion.metricas.revisar_informe` (el mismo código que la herramienta: no se pueden
desalinear). C3 es manual. Importa `tools/evaluacion` añadiendo `project/tools` a `sys.path`. Sus pruebas
(`tests/test_validate32.py`) usan dobles de S3, Secrets Manager y del cliente del backend, sin `botocore`. Detalle en
`validation-3-2.md`.

**Datos de prueba**: imágenes sintéticas generadas por el propio validador y las cinco imágenes de
`project/tests/golden/`; el servicio no guarda nada, así que no hay limpieza más allá de detener las tareas sueltas.

**`src/ops/comun.py`** (desde EMB-1.1) reúne lo que comparten los validadores de esta carpeta. No es el `comun.py`
de infraestructura (su §5.11 describe el suyo, con otra API): las carpetas comparten el contrato, no el código.
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
- Docker se usa por su CLI y AWS con boto3 desde `AWS_PROFILE` (región `us-east-1`); para una imagen de ECR hace
  `docker login` con el token de `ecr:GetAuthorizationToken`, sin imprimirlo.
- Necesita en la máquina de quien valida: Docker (`local`), credenciales de AWS (`dev`) y `git` (commit del informe y,
  desde EMB-3.1, `archivo_en_commit`).

API (basta para escribir un validador nuevo sin leer el código; si cambia, esta tabla cambia en el mismo commit):

| Elemento | Qué hace |
|---|---|
| `Lote(lote=, validacion=, entornos=, precondiciones=[Paso…], comprobaciones=[Paso…], manuales=[Manual…], limpiar=fn, descripcion=)` | Declaración del validador. `precondiciones` y `comprobaciones` van en orden de ejecución; el informe ordena las precondiciones por ID y deja las comprobaciones en ese orden |
| `Paso(id, entornos, funcion)`; `Manual(id, instruccion, entornos=ambos)`; `entornos("dev", …)` → `frozenset` | Un paso solo corre en sus entornos (en los demás queda `omitida`). `funcion(ctx)` devuelve el texto del detalle |
| `Contexto` (`ctx`) | `ctx.entorno`, `ctx.aws` (la sesión que deje una precondición), `ctx.datos` (diccionario libre entre pasos), `ctx.sin_limpieza`, `ctx.limpiar_restos()` (llama a `limpiar` una sola vez; cada validador lo llama en la primera precondición que ya puede limpiar) |
| `ejecutar(lote, argv=None)` → código | `--entorno`, `--informe`, `--solo`, `--sin-limpieza`; imprime `[PASA] …`, ejecuta la limpieza al final (sus errores solo dan `[AVISO]`) y escribe el informe en `DIR_INFORMES/<lote>-<AAAAMMDD-HHMMSS>.json` (UTC) |
| `Falla` (1), `PrecondicionNoCumplida` (2), `ErrorConfiguracion` (3) | En una precondición: 2, 3, y cualquier otra excepción → 3. En una comprobación: `Falla` o una excepción inesperada → `falla` (1) y sigue; `ErrorConfiguracion` o credenciales de boto3 → 3 y las siguientes quedan `omitida` |
| `revision_architecture()` → SHA | El de la fila «Revisión» de §5.3 (`Falla` si no está) |
| `estado_lote("EMB-2.1")` → `"Hecho"`… | Estado de un lote en la tabla §3 de `PLAN.md`; si no está, `ErrorConfiguracion` (EMB-3.1) |
| `archivo_en_commit(commit, ruta)` → texto o `None` | `git show <commit>:./<ruta>` desde `project/`; `None` si el commit no tiene esa ruta; `ErrorConfiguracion` sin `git` o si el commit no está en el clon (hay que `git fetch`) (EMB-3.1) |
| `sesion_aws(region=REGION)` | `boto3.Session` con `AWS_PROFILE`; sin la variable, con credenciales inválidas o de otra cuenta → `ErrorConfiguracion` |
| `imagen_local()` → imagen | `EMBEDDING_IMAGEN` descargada (con `login_ecr` si es de ECR) y `linux/amd64`, o 3 / 2 (EMB-2.1) |
| `docker(*args, entrada=, timeout=900)`, `borrar_contenedores(*nombres)`, `en_marcha(nombre)`, `logs_contenedor(nombre, lineas=15)`, `puerto_ocupado(puerto)`, `es_imagen_ecr(imagen)`, `login_ecr(imagen)` | CLI de Docker sin imprimir nada (devuelve `CompletedProcess`; sin `docker` → `ErrorConfiguracion`) |
| `CUENTA_AWS`, `REGION`, `CLUSTER`, `SERVICIO_ECS`, `FAMILIA_TAREA`, `LOG_GROUP`, `CONTENEDOR`, `REPOSITORIO_ECR`, `PUERTO`, `URL_LOCAL`, `MODELO_ID`, `VERSION_VECTOR`, `PLAZO_ARRANQUE_S` (180), `COMANDO_SALUD` | Nombres del contrato |
| `DIR_PROYECTO`, `ARCHITECTURE`, `PLAN`, `DIR_INFORMES` | Rutas: `project/`, `docs/ARCHITECTURE.md`, `docs/PLAN.md`, `project/.validacion/` |

Forma de un validador: `from comun import …` (el script se ejecuta como `python src/ops/validate<fase><n>.py`), un
`LOTE = Lote(…)` a nivel de módulo (las pruebas comprueban que sus IDs son los de su `validation-<fase>-<n>.md`) y
`raise SystemExit(ejecutar(LOTE))`. `validate11.py` es el ejemplo de tarea suelta que espera `HEALTHY`;
`validate31.py`, el de tarea suelta con comando sobrescrito que lee su log; `validate21.py`, el de contenedor local;
`validate32.py`, el de solo lectura de S3 y de la API del backend.
Sus pruebas sin AWS usan dobles de los clientes de boto3 (`tests/test_validate31.py`).

### 5.9 Formatos de las herramientas, de los vectores dorados y del conjunto de evaluación

**`tools/benchmark.py`** (EMB-3.1, §4.4, ADR-EMB-13). Dentro de la imagen, desde `/srv`:
`python tools/benchmark.py [opciones]`; desde `project/`, `MODELO_DIR=.modelo uv run python tools/benchmark.py` (los
pesos de `project/.modelo/`, cómo copiarlos en «Vectores dorados», más abajo; con `--puerto` si el 8080 está ocupado).
Solo usa la biblioteca estándar, NumPy, Pillow y el paquete `app`.

| Opción | Por defecto | Qué hace |
|---|---|---|
| `--salida texto\|json` | `texto` | `json`: una sola línea `BENCHMARK_JSON {…}` en la salida estándar; `texto`: una tabla |
| `--lotes 1,4,5,8` | `1,4,5,8` | Tamaños de lote, cada uno entre 1 y `LOTE_MAX` (8) |
| `--repeticiones N` o `N1,N2,…` | 40, 30, 60 y 30 (otro lote: 30) | Repeticiones medidas: una cifra para todos o una por lote |
| `--calentamiento N` | 3 | Peticiones de cada lote que se envían y no se cuentan |
| `--hilos N` | `TORCH_NUM_THREADS` o 1 | `TORCH_NUM_THREADS` del servicio que arranca (para probar la palanca 1 de §4.4) |
| `--prioridad alta\|baja` | `alta` | `X-Prioridad` de las peticiones (la de `/v1/localize`) |
| `--puerto N` | 8080 | Puerto del servicio en `127.0.0.1`; si ya está ocupado, termina con 1 (no mediría este servicio) |
| `--plazo-arranque S` | 300 | Segundos máximos hasta `/health/ready` = 200 |
| `--url http://anfitrion:puerto` | — | Mide un servicio ya en marcha en vez de arrancar uno: `hilos`, `arranque_s` y `memoria_proceso_mb` salen `null`, y `cpu`, `vcpu` y `memoria_mb` describen la máquina del benchmark |

Códigos de salida: **0** medido; **1** el servicio no quedó listo, terminó o una petición no dio `200` con tantos
vectores como imágenes (lo dice el evento `benchmark_fallido`); **2** uso. Progreso en la salida de error, en JSON por
línea como el log del servicio (§5.7): `benchmark_inicio`, `benchmark_listo`, `benchmark_lote` (cada lote) y
`benchmark_fallido`; los logs del servicio arrancado van también a la salida de error. En la tarea suelta el
benchmark es el PID 1 y atiende `SIGTERM` (`stop-task`): detiene el servicio y sale con 143.

**Salida de `--salida json`**: una sola línea, de menos de 4 KiB (se escribe de una vez en el log), precedida de
`BENCHMARK_JSON ` para poder encontrarla. Ejemplo **real del ensayo local** de §4.4 (no de `dev`):
```json
{ "version_vector": "dinov2-vits14/pp-v1", "commit": "f2ddc42", "hilos": 2, "vcpu": 2, "memoria_mb": 4096,
  "limites_de": "cgroup", "cpu": "AMD Ryzen 7 6800HS with Radeon Graphics", "capacidad_cpu_torch": "AVX2",
  "imagen": { "ancho": 1024, "alto": 768, "calidad_jpeg": 85, "bytes_media": 132139 },
  "prioridad": "alta", "calentamiento": 3, "arranque_s": 12.6,
  "memoria_proceso_mb": { "reposo": 477, "final": 502, "pico": 541 }, "preproceso_ms_por_imagen": 12.3,
  "resultados": [
    { "lote": 1, "repeticiones": 40, "p50_ms": 129, "p95_ms": 150, "max_ms": 154,
      "inferencia_p50_ms": 126, "inferencia_p95_ms": 146, "cola_max_ms": 1 },
    { "lote": 4, "repeticiones": 30, "p50_ms": 468, "p95_ms": 567, "max_ms": 573,
      "inferencia_p50_ms": 462, "inferencia_p95_ms": 562, "cola_max_ms": 0 },
    { "lote": 5, "repeticiones": 60, "p50_ms": 605, "p95_ms": 846, "max_ms": 980,
      "inferencia_p50_ms": 598, "inferencia_p95_ms": 838, "cola_max_ms": 2 },
    { "lote": 8, "repeticiones": 30, "p50_ms": 1063, "p95_ms": 1158, "max_ms": 1175,
      "inferencia_p50_ms": 1055, "inferencia_p95_ms": 1148, "cola_max_ms": 0 } ] }
```
| Campo | Significado |
|---|---|
| `p50_ms`, `p95_ms`, `max_ms` | Tiempo de la petición visto por el cliente, en ms enteros: de empezar a enviar el `POST /v1/embed` a tener la respuesta completa (subida en *loopback*, multipart, cola, pp-v1, modelo y JSON). Percentil por rango más cercano: el valor en la posición ⌈p/100 · n⌉ de los n ordenados |
| `inferencia_p50_ms`, `inferencia_p95_ms`, `cola_max_ms` | Los mismos percentiles de `tiempos_ms.inferencia` (pp-v1 + modelo, §5.2) y el máximo de `tiempos_ms.cola` (≈ 0: las peticiones van en serie) |
| `repeticiones`, `calentamiento` | Peticiones medidas por lote y las descartadas antes |
| `commit`, `version_vector` | De `GET /v1/info` del servicio medido |
| `hilos` | `TORCH_NUM_THREADS` con que se arrancó el servicio |
| `vcpu`, `memoria_mb`, `limites_de` | Límites del contenedor: de los metadatos de la tarea de ECS (`ECS_CONTAINER_METADATA_URI_V4` → `Limits`, `ecs`; en `dev` sale 2 / 4096 por esta vía, comprobado en EMB-3.1), del cgroup v2 o v1 (`cgroup`) o de la máquina (`sistema`, sin memoria) |
| `cpu`, `capacidad_cpu_torch` | Modelo de CPU (`/proc/cpuinfo`) y ruta SIMD de PyTorch (`AVX2`, `AVX512`…) |
| `imagen` | Las imágenes enviadas: tamaño, calidad JPEG y bytes de media |
| `arranque_s` | Segundos desde lanzar el servicio hasta `/health/ready` = 200 (carga y calentamiento; sin la descarga de la imagen) |
| `memoria_proceso_mb` | RSS del proceso del servicio en MiB: tras quedar listo (`reposo`), al terminar (`final`) y el pico de toda su vida (`pico`, `VmHWM`, incluye la carga) |
| `preproceso_ms_por_imagen` | p50 de pp-v1 por imagen (decodificar, redimensionar, recortar, normalizar), medido en el proceso del benchmark con el servicio ya detenido |

**Vectores dorados** (§5.4, ADR-EMB-12), en `project/tests/golden/`: las cinco imágenes `validacion-0<n>-<nombre>.jpg`
o `.png` y `esperados.json`:
```json
{ "version_vector": "dinov2-vits14/pp-v1", "modelo": "facebook/dinov2-small",
  "revision": "ed25f3a31f01632728cabb09d1542f84ab7b0056", "dim": 384, "tolerancia": 1e-05,
  "calculado": { "fecha": "2026-10-25T03:40:07Z", "herramienta": "tools/dorados.py vectores", "hilos": 1,
                 "cpu": "AMD Ryzen 7 6800HS with Radeon Graphics", "capacidad_cpu_torch": "AVX2", "python": "3.12.15",
                 "torch": "2.14.1+cpu", "transformers": "5.20.2", "numpy": "2.5.4", "pillow": "13.0.0" },
  "imagenes": [ { "archivo": "validacion-01-campus.jpg", "tipo": "image/jpeg", "sha256": "…",
                  "sha256_preprocesado": "…", "vector": [ 0.0123, -0.0456, … ] } ] }
```
`sha256` es el del archivo; `sha256_preprocesado`, el de los bytes del array float32 (3, 224, 224) contiguo que
devuelve pp-v1; `vector`, los 384 componentes con todos sus dígitos.

`tools/dorados.py` se ejecuta desde `project/` con `uv run python tools/dorados.py <orden>`:

| Orden | Qué hace | Código de salida |
|---|---|---|
| `imagenes` | Dibuja las cinco imágenes (escenas sintéticas, semilla fija). Solo se usa al estrenar una `version_vector`: con otra versión de Pillow los bytes cambiarían | 0 |
| `vectores [--modelo DIR] [--hilos N] [--forzar]` | Calcula los vectores en proceso (el mismo `preproceso` + `ModeloDinov2` que el servicio; por defecto 1 hilo) y escribe `esperados.json`. Si ya existe y algún componente cambia más de 1e-5, no lo sobrescribe, salvo con `--forzar` (solo con una `version_vector` nueva) | 0 escrito · 1 no sobrescrito |
| `comparar [--modelo DIR] [--hilos N]` | Calcula igual que `vectores`, imprime la diferencia máxima de cada imagen y no escribe nada | 0 dentro de 1e-5 · 1 fuera, o sin `esperados.json` |

`--modelo` es la carpeta de los pesos con su `revision.json`; por defecto, `MODELO_DIR` o `project/.modelo/`, que Git
y Docker ignoran. Se copian de la imagen publicada, que ya los trae, sin salir a Hugging Face:
```bash
cd SERVICE_EMBEDDING/project
IMG=<ecr_embedding_url>:<sha>
docker create --name validacion-pesos "$IMG" >/dev/null && docker cp validacion-pesos:/opt/modelo ./.modelo
docker rm validacion-pesos
sha256sum .modelo/model.safetensors   # el SHA-256 de §5.3
```
(con acceso a Hugging Face también vale `PYTHONPATH=src uv run python tools/descargar_modelo.py .modelo`). Las pruebas
`tests/test_dorados.py` leen la misma carpeta (`MODELO_DIR` o `project/.modelo/`); sin pesos se omiten, salvo con
`DORADOS_OBLIGATORIOS=1`, que las hace fallar (así corren en `embedding.yml`, §4.2). Se recalculan con `vectores` en dos
casos: con una `version_vector` nueva (§4.6), o si una actualización de dependencias cambia `sha256_preprocesado` (la
prueba lo detecta) y `comparar` confirma que los vectores siguen dentro de 1e-5.

**Conjunto de evaluación** (EMB-3.2, §4.5), en el bucket del dataset bajo `evaluacion/<version_conjunto>/` (infra
§5.5), y con la misma forma en la carpeta local de la herramienta (`project/.validacion/evaluacion/<version_conjunto>/`):
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
  "fotos": [ { "archivo": "fotos/P01/1.jpg", "punto": "P01", "rumbo": 90.0, "capturada_en": "2026-11-05T14:02:10Z",
               "hora": "manana", "vuelta": 1 } ] }
```
Reglas (las aplica `evaluacion.conjunto.revisar`, que usan la herramienta y `validate32.py` C1):

| Campo | Regla |
|---|---|
| `version_conjunto` | `AAAA-MM<letra minúscula>` (`2026-11a`); igual al nombre de la carpeta |
| `creado_en`, `fotos[].capturada_en` | ISO-8601 en UTC con `Z` (backend §5.1) |
| `puntos[].id` | `P` + 2 o 3 cifras, único |
| `puntos[].lat`, `.lng` | WGS84 (backend §5.1); `(0, 0)` se rechaza como «sin rellenar» |
| `puntos[].descripcion` | Texto libre, opcional |
| `fotos[].archivo` | `fotos/<punto>/<n>.jpg`, único, en la carpeta de su `punto`, que debe existir en `puntos` |
| `fotos[].rumbo` | Norte verdadero en [0, 360) o `null` |
| `fotos[].hora` | `manana` (05:00–11:59 en Bogotá), `tarde` (12:00–17:59) o `noche` (el resto). Si no cuadra con `capturada_en` es un aviso, no un error |
| `fotos[].vuelta` | **Opcional** (desde 0.9.0): entero ≥ 1, la sesión de 5 fotos del punto. Agrupa las consultas de la simulación (§4.5); sin él, se agrupan por punto, día y franja. BE-3.2 no lo usa (su validación lee `archivo`, `punto` y `rumbo`, backend validation-3-2) |

Las fotos no se usan nunca en el dataset. Un punto con dataset tiene alguna imagen `procesada` a ≤ 30 m; uno lejano,
todas a > 150 m (sus fotos no entran en el *recall* y sirven para `sin_coincidencias`, BE-3.2 C5); los demás
(«intermedios») no cuentan. C1 exige ≥ 50 fotos en ≥ 10 puntos con dataset y ≥ 1 punto lejano con ≥ 3 fotos.

**Informe de evaluación** (`informes/<version_vector>-<AAAAMMDD>.json`; lo escribe `tools/evaluacion evaluar`, junto
con un `.md` del mismo nombre). Las claves de este ejemplo son el contrato (las comprueba `validate32.py` C2); el resto
son extras para quien revisa (C3):
```json
{ "version_conjunto": "2026-11a", "version_vector": "dinov2-vits14/pp-v1", "fotos": 50, "puntos": 10,
  "recall_1_15m": 0.0, "recall_5_15m": 0.0,
  "similitud": { "mismo_lugar": { "p10": 0.0, "p50": 0.0, "p90": 0.0 }, "otro_lugar": { "p10": 0.0, "p50": 0.0, "p90": 0.0 } },
  "variantes": [ { "nombre": "pp-v1", "recall_1_15m": 0.0, "recall_5_15m": 0.0 } ],
  "recomendado": { "LOC_SIM_MIN": 0.0, "LOC_SIM_ALTA": 0.0, "corte_alta": 0.0, "corte_media": 0.0 } }
```
| Clave | Significado |
|---|---|
| `fotos`, `puntos` | Fotos y puntos **con dataset** evaluados (las de los lejanos no cuentan) |
| `recall_1_15m`, `recall_5_15m` | §4.5; `null` si no hay fotos con dataset |
| `similitud.mismo_lugar`, `.otro_lugar` | p10 / p50 / p90 (rango más cercano, 4 decimales) y `n` de los 5 primeros vecinos a ≤ 15 m y a > 50 m del punto real |
| `similitud.lejos_del_dataset` | Igual, más `max`, de la similitud del mejor vecino de cada foto de un punto lejano |
| `variantes` | Siempre `pp-v1` primero, con los números de arriba (vecinos del backend). La orden `variantes` añade detrás `pp-v1-local`, `sin-recorte`, `res-448` y `media-parches` (con `descripcion` y `"vecinos": "fuerza_bruta_local"`) |
| `recomendado` | Los cuatro valores de §4.5 (2 decimales; `null` si no hay datos para calcularlos) |
| `creado_en`, `herramienta`, `fuente_vecinos` (`backend` o `fuerza_bruta_local`), `k` | Cómo se generó |
| `puntos_lejanos`, `fotos_lejanas`, `cobertura` (`{punto: metros al dataset}`) | Cobertura del conjunto |
| `por_hora` | `{franja: {fotos, recall_1_15m, recall_5_15m}}` de las franjas con fotos |
| `actual_backend` | Los valores vigentes de backend §5.10 copiados en `metricas.py`, para comparar |
| `detalle_recomendacion` | `LOC_SIM_MIN`: `youden`, `lejos_max`, `mismo_lugar_retenido`; `LOC_SIM_ALTA`: `metodo` (`precision` o `p90_mismo_lugar`) y `precision`; `cortes`: `consultas` |
| `simulacion` | `consultas`, `error_mediano_m`, `por_nivel` (`sin_coincidencias` y, por nivel, `consultas`, `a_15m`, `error_max_m`) y `lejanas_sin_coincidencias` (`"n/m"`) |

**`tools/evaluacion`** (EMB-3.2). Desde `project/`: `uv run [--group ops] python tools/evaluacion <orden> DIR
[opciones]` (`DIR` = la carpeta local del conjunto). No va en la imagen (§5.5). Lee el dataset y los vecinos del
backend con `VALIDACION_API_URL` (con `/v1`), `VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` (backend §5.11;
la herramienta no lee el secreto), o de una carpeta local con `--dataset-local D` (`D/dataset.json` =
`{"imagenes": [{"imagen_id", "archivo", "lat", "lng", "rumbo"}]}` y los JPEG al lado; los vecinos, por fuerza bruta con
pp-v1 y los pesos locales). No escribe en AWS: el informe queda en `DIR/informes/` y se sube a mano.

| Orden | Qué hace | Opciones |
|---|---|---|
| `revisar DIR` | Estructura de `puntos.json` y que cada foto exista | — |
| `cobertura DIR` | Distancia de cada punto a la imagen más cercana, clase (`con dataset`, `lejano`, `intermedio`) y criterio C1 | `--dataset-local` |
| `evaluar DIR` | Vecinos de cada foto (puntos con dataset y lejanos), informe JSON + `.md` | `--dataset-local`, `--salida` (por defecto `DIR/informes`), `--fecha AAAAMMDD` (por defecto hoy, UTC), `--k` (5–50, por defecto 10), `--modelo` |
| `variantes DIR --informe RUTA` | Recalcula el *recall* con cada variante (fuerza bruta) y reescribe `variantes` del informe | `--nombres` (por defecto `pp-v1,sin-recorte,res-448,media-parches`), `--dataset-local`, `--modelo` (por defecto `MODELO_DIR` o `project/.modelo/`) |

Códigos de salida: **0** hecho; **1** conjunto con errores (`[ERROR] …`) o `cobertura` sin cumplir C1
(`[NO CUMPLE C1] …`); **2** uso, variables que faltan, error del backend (`[ERROR] … → <estado> <codigo>`; con `503
EMBEDDING_NO_DISPONIBLE` añade cómo encender) o algo pendiente de otro lote (`[PENDIENTE] …`, hoy BE-4.1 en
`variantes` con el backend). Progreso y avisos en la salida de error. Cada foto se prepara como una de `/v1/localize`
(`preparar_foto`: orientación EXIF aplicada, lado mayor ≤ 1024 px con Lanczos, JPEG calidad 85, sin EXIF; si pasa de
1,5 MB, error). El cliente reintenta `429` y `503 SERVICIO_OCUPADO` hasta 3 veces (espera `Retry-After` o 2, 4 y 8 s), hace un
solo login y nunca imprime el token ni las URL prefirmadas.

API de los módulos (para enchufar otra fuente de vecinos o del dataset, o una variante, sin leer el código):

| Elemento | Qué hace |
|---|---|
| `conjunto.revisar(dict)` → `Revision(errores, avisos)`; `cargar(DIR)` → `(Conjunto, Revision)` o `ConjuntoInvalido`; `desde_dict(dict)` | Reglas de la tabla de arriba; `cargar` además exige que existan los archivos |
| `conjunto.haversine_m(lat1, lng1, lat2, lng2)`; `franja(datetime)`; `cobertura(Conjunto, [(lat, lng)])` → `[CoberturaPunto(punto, distancia_m, fotos)]` (`.con_dataset`, `.lejano`); `revisar_c1(cobertura)` → `(errores, resumen)` | R = 6 371 008,8 m; umbrales `DATASET_CERCA_M` 30, `LEJOS_M` 150, `FOTOS_MIN` 50, `PUNTOS_CON_DATASET_MIN` 10, `FOTOS_PUNTO_LEJANO_MIN` 3 |
| `fuentes.BuscadorVecinos` (protocolo): `.version_vector`, `.vecinos(foto_jpeg, k)` → `[Vecino(imagen_id, lat, lng, rumbo, similitud)]` de mayor a menor | Lo implementan `ClienteBackend` (BE-2.4) y `BuscadorFuerzaBruta(imagenes, vectores, vectorizar)` |
| `fuentes.FuenteDataset` (protocolo): `.imagenes()` → `[ImagenDataset(imagen_id, lat, lng, rumbo, video_id, url)]`, `.descargar(imagen)` → bytes | `ClienteBackend` (BE-2.1; `descargar` lanza `PendienteBE41` mientras `url` sea `null`) y `FuenteCarpeta(D)` |
| `fuentes.ClienteBackend(url_base, correo, password)`: `.token()`, `.videos()`, `.imagenes()`, `.vecinos_crudo(foto, k)` (la respuesta HTTP), `.vecinos(foto, k)` | `ErrorFuente(mensaje, estado)` ante una respuesta que no es 200 |
| `fuentes.indexar(fuente, vectorizar)` → `BuscadorFuerzaBruta`; `preparar_foto(bytes)` → JPEG | Vectoriza todo el dataset con una función `bytes → vector` |
| `metricas.consultar(conjunto, cobertura, buscador, leer)` → `[ResultadoFoto]`; `recall`, `distribuciones`, `recomendar_sim_min`, `recomendar_sim_alta`, `localizar`, `simular`, `recomendar_cortes`, `construir_informe`, `revisar_informe(informe, version_vector, fotos)` → errores | §4.5; `revisar_informe` es exactamente lo que comprueba C2 |
| `variantes.VARIANTES` (`nombre` → `Variante(nombre, descripcion, preprocesar, extraccion)`); `ExtractorDinov2(dir, hilos=1).vector(tensor, "cls" \| "media_parches")`; `vectorizador(variante, extractor)`; `comparar(…)` | Una variante nueva = una función `bytes → array (3, H, W)` float32 normalizado (H y W múltiplos de 14) y una entrada en `VARIANTES` |
| `cli.main(argv)`; `cli.evaluar(conjunto, coordenadas, buscador, fuente, salida, fecha=, k=)` → `(ruta, informe)`; `cli.nombre_informe(version_vector, AAAAMMDD)` | Lo que usan las pruebas y `validate32.py` |

**Parámetros exactos de `metricas.py`** (constantes del módulo; cambiarlos cambia las recomendaciones):

| Constante | Valor | Uso |
|---|---|---|
| `MISMO_LUGAR_M` / `OTRO_LUGAR_M` | 15 / 50 m | Vecino «mismo lugar» (≤) y «otro lugar» (>); acierto del *recall* a ≤ 15 m |
| `K_RECALL` | (1, 5) | *recall*; las distribuciones usan los 5 primeros vecinos de cada foto con dataset |
| `LOC_TOP_K`, `LOC_RADIO_GRUPO_M`, `LOC_PESO_EXPONENTE` | 10, 20 m, 4 | Copia de backend §5.10 para la simulación |
| `LOC_SIM_MIN_ACTUAL` / `LOC_SIM_ALTA_ACTUAL` / `CORTE_ALTA_ACTUAL` / `CORTE_MEDIA_ACTUAL` | 0,55 / 0,80 / 0,70 / 0,45 | Copia de backend §5.10 para `actual_backend` |
| `FOTOS_POR_CONSULTA` | 5 | Tamaño máximo de una consulta simulada (`LOC_MAX_FOTOS`) |
| `MARGEN_LEJOS` | 0,01 | `LOC_SIM_MIN` ≥ techo a 2 decimales de (mejor similitud lejana + 0,01) |
| `PRECISION_SIM_ALTA` / `SOPORTE_SIM_ALTA` | 0,95 / 5 vecinos | `LOC_SIM_ALTA` |
| `PRECISION_15M_ALTA` / `ERROR_MAX_ALTA_M` | 0,90 / 30 m | `corte_alta` |
| `PRECISION_15M_MEDIA` | 0,60 | `corte_media` |

**Detalle del cálculo** (lo que §4.5 resume; basta para reproducirlo o revisar un informe):
- Percentil por rango más cercano: posición ⌈p/100 · n⌉ de los n ordenados (mín. 1); lista vacía → `null`. Las
  similitudes del informe se redondean a 4 decimales; los umbrales, a 2.
- Youden: se recorre la rejilla 0,00…1,00; TPR = fracción de «mismo lugar» ≥ t, FPR = fracción de «otro lugar» ≥ t
  (0 si no hay «otro lugar»); gana el primer t con el máximo. Sin «mismo lugar», todo `recomendado` sale `null` y no se
  simula. `LOC_SIM_MIN` = max(Youden, techo(lejos_max + 0,01)), recortado a [0,01; 0,98].
- `LOC_SIM_ALTA`: primer t de la rejilla desde `LOC_SIM_MIN` + 0,01 hasta 1,00 con ≥ 5 vecinos («mismo» + «otro») ≥ t y
  precisión ≥ 0,95; si no hay, max(techo(p90 de «mismo lugar»), `LOC_SIM_MIN` + 0,05), con tope 1,0.
- `localizar` (pasos 3–7 de backend §4.10): descarta vecinos con similitud < `LOC_SIM_MIN`; los recorre de mayor a menor
  similitud y cada uno entra en el **primer** grupo cuyo centroide (media sin ponderar de sus miembros, recalculada en
  cada alta) esté a < 20 m, o abre uno; puntuación de un grupo = suma, por foto, de la mejor similitud que aporta; el
  mejor grupo es el de mayor puntuación (a igualdad, el creado antes); posición = media de lat/lng ponderada por
  similitud⁴; `s` = (similitud máxima del grupo − `LOC_SIM_MIN`) / (`LOC_SIM_ALTA` − `LOC_SIM_MIN`) recortada a [0, 1]
  (1 si `LOC_SIM_ALTA` ≤ `LOC_SIM_MIN`); `c` = fotos con vecino en el grupo / fotos de la consulta (también las que no
  tienen ningún vecino); `m` = (p₁ − p₂)/p₁, 1 con un grupo; confianza = 0,5·s + 0,3·c + 0,2·m. Sin vecinos tras el
  filtro → `sin_coincidencias` (confianza 0, error infinito). No simula la corrección de rumbo ni el contexto (pasos 8–10).
- Cortes: para cada t, el subconjunto de consultas con confianza ≥ t; un subconjunto **vacío cuenta como que cumple**
  (por eso, si ninguna consulta llega a 0,50, `corte_alta` sale 0,50). `corte_alta` = primer t en [0,50; 0,99] que
  cumple (si ninguno, 0,99); `corte_media` = primer t en [0,05; `corte_alta` − 0,01] con ≥ 60 % a ≤ 15 m (si ninguno,
  max(0,01; `corte_alta` − 0,05)). Solo se simulan las consultas de puntos con dataset; las de puntos lejanos solo dan
  `lejanas_sin_coincidencias`.
- Consultas: clave `(punto, "v", vuelta)` si la foto trae `vuelta`; si no, `(punto, fecha local de Bogotá, hora)`. Dentro
  de cada clave, las fotos se ordenan por `archivo` **como texto** (`fotos/P01/10.jpg` va antes que `…/2.jpg`) y se
  parten en trozos de 5. Con `vuelta` de 5 fotos no importa; sin ella, una sesión de más de 5 fotos se parte así.

**Detalle de `fuentes.py` y `cli.py`:**
- `ClienteBackend`: `httpx.Client(timeout=60 s)`; `url_base` sin barra final + la ruta (`/auth/login`,
  `/admin/videos?pagina=N&por_pagina=100`, `/admin/videos/{id}`, `/admin/diagnostico/vecinos?k=K` con la parte
  multipart `foto`, `consulta.jpg`, `image/jpeg`). `videos()` pide páginas hasta tener `total` o una página vacía.
  `imagenes()` salta los videos con `nombre` `validacion-…` o `conteo.procesada` = 0 (sin pedir su detalle) y, de cada
  detalle, las fotos que no están `procesada` o sin `lat`. El token se pide una vez (se renueva solo si se crea otro
  cliente; dura 12 h, backend §5.10). `vecinos()` guarda la primera `version_vector` y falla si cambia. `descargar()`
  baja la `url` prefirmada sin token (`httpx.get`, 60 s).
- `BuscadorFuerzaBruta.vecinos`: producto escalar con la matriz de vectores (L2 = 1 → coseno) y `argsort` estable;
  `indexar` vectoriza el dataset en el orden de `fuente.imagenes()`.
- `ExtractorDinov2`: carpeta = argumento, si no `MODELO_DIR`, si no `project/.modelo/`; `hilos` = 1 por defecto (con
  `app.modelo.fijar_hilos`); `cls` = `pooler_output`, `media_parches` = media de `last_hidden_state[0, 1:]`; el vector se
  normaliza en float64 y se devuelve en float32. Importa `app.preproceso` y `app.modelo` del servicio (no los copia).
- `sin_recorte`: lado largo = min(896, max(224, ⌊⌊224·largo/corto⌋ / 14⌋ · 14)), bicúbica sin `reducing_gap`;
  `resolucion_448`: lado menor 512, el otro `int(512·lado/corto)`, recorte central de 448 empezando en `(lado − 448)//2`.
  Ambas usan `decodificar` de pp-v1 (EXIF, RGB, `LADO_MIN_PX` 64, `PROPORCION_MAX` 32) y su normalización.
- `evaluar` escribe el informe aunque el conjunto aún no cumpla C1 (lo avisa con `[AVISO]`, código 0) e imprime una línea
  JSON con `recall_1_15m`, `recall_5_15m` y `recomendado`. Con `--dataset-local` los vecinos son de fuerza bruta con pp-v1
  y los pesos locales (`fuente_vecinos = fuerza_bruta_local`). `--k` fuera de 5–50 → error de uso de argparse (código 2).
- `variantes` conserva solo la **primera** fila `pp-v1` del informe y sustituye el resto por las que calcula; un nombre
  desconocido → código 2. Necesita los pesos aunque los vecinos de referencia vengan del backend.
- `revisar` sin `puntos.json` o con fotos que faltan → código 1.

**Nombres internos de `validate32.py`:** `BUCKET` = `campus-locator-dev-dataset-648617469176`, `PREFIJO` =
`evaluacion/`, `SECRETO_ADMIN` = `campus-locator/dev/admin-inicial`, `IMAGEN_P2B` = `tests/golden/validacion-01-campus.jpg`
(se pasa por `preparar_foto`), `PATRON_INFORME` = `^evaluacion/<version>/informes/dinov2-vits14_pp-v1-<AAAAMMDD>.json$`
(gana el mayor `(fecha, version, clave)`). Comparte en `ctx.datos`: `cliente`, `imagenes` (el dataset, pedido una sola
vez), `versiones` (de P3), `informe` (`(clave, dict)` o `None`) y `cobertura` (por versión: `errores`,
`fotos_con_dataset`, `resumen`, `dataset`). Una carpeta de `evaluacion/` que no tenga la forma `AAAA-MM<letra>` se ignora.

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
`project/.modelo/` (§5.9), ignorada por Git y por Docker. En CI, `embedding.yml` baja la revisión fijada (con caché)
y corre `pytest` con `DORADOS_OBLIGATORIOS=1`, para que la prueba falle en vez de omitirse si faltan los pesos.
`esperados.json` guarda con qué se calcularon y el `sha256` del tensor preprocesado, que separa un cambio de
decodificación de uno numérico. *Alternativas descartadas:* calcularlos en CI (cada ejecución puede caer en otra CPU) o
pidiéndolos a la imagen por HTTP (obliga a construirla en local antes de cada cambio y da los mismos números); relajar
la tolerancia (no hace falta). *Consecuencias:* si una CPU futura (otra familia en Fargate o en los runners) superara
1e-5, habría que separar la tolerancia entre CPU de la de la misma imagen, como se hizo en 0.4.0 entre dispositivos,
antes de indexar con ella. Actualizar Pillow puede cambiar el `sha256` del tensor sin salir de 1e-5: se mide con
`tools/dorados.py comparar` y, si cabe, se recalculan con `tools/dorados.py vectores`.

**ADR-EMB-13 — El benchmark arranca el servicio dentro de su propia tarea y lo mide por HTTP en *loopback*
(aceptada, 0.7.0, EMB-3.1).**
EMB-3.1 debe medir en la definición de tarea de `dev` (2 vCPU / 4 GB) lo que tarda embeddings en atender a
`/v1/localize`. *Decisión:* `tools/benchmark.py` corre como tarea suelta con esa definición y el comando
sobrescrito; arranca `uvicorn app.main:app` como subproceso en `127.0.0.1:8080` (el mismo código y los mismos hilos que
el servicio) y le envía en serie lotes de JPEG sintéticos de 1024 px, midiendo desde el cliente toda la petición
(multipart, cola, pp-v1, modelo y JSON). El resultado sale en una línea `BENCHMARK_JSON` del log (§5.9), que
`validate31.py` lee de CloudWatch. *Alternativas descartadas:* medir `modelo.inferir` en el mismo proceso (deja fuera
pp-v1, multipart y la cola, que el backend sí paga); medir el servicio `embedding` encendido desde otra tarea (exige
encenderlo, otra definición con permisos de red hacia él y mezcla la red de la VPC, que es del backend); un cliente en
otro contenedor de la misma tarea (otra definición de tarea, que es de infra). *Consecuencias:* no hace falta encender
`embedding` ni cambiar la infraestructura; el cliente comparte los 2 vCPU con el servicio, pero solo trabaja mientras el
servicio espera (sube el cuerpo y lee la respuesta: el total queda a 10 ms o menos de `tiempos_ms.inferencia` en el
ensayo local); los números no incluyen la red ni el backend (§4.4); y la imagen tiene que traer el benchmark, así que
para medir hay que desplegar antes (las imágenes anteriores a EMB-3.1 traen uno provisional).

**ADR-EMB-14 — Evaluación con el endpoint de vecinos del backend y recomendación por reglas fijas (aceptada, 0.9.0,
EMB-3.2).**
EMB-3.2 debe medir la recuperación sobre el dataset **indexado** y proponer `LOC_SIM_MIN`, `LOC_SIM_ALTA` y los cortes
de nivel a BE-3.2, sin que el servicio conozca la base ni S3 (ADR-EMB-06). *Decisión:* `tools/evaluacion` corre en la
máquina de quien valida; los vecinos de pp-v1 los da `POST /v1/admin/diagnostico/vecinos` (BE-2.4: el mismo índice
HNSW y `ef_search` que `/v1/localize`) con `k = LOC_TOP_K` = 10, y el dataset (coordenadas) `GET /v1/admin/videos`
y `/videos/{id}` (BE-2.1), detrás de dos interfaces (`BuscadorVecinos`, `FuenteDataset`) para poder cambiar de
fuente. Las recomendaciones salen de reglas deterministas y explicadas (§4.5): Youden más el margen sobre los puntos
lejanos para `LOC_SIM_MIN` (BE-3.2 C5 exige `sin_coincidencias` en ellos), precisión ≥ 95 % para `LOC_SIM_ALTA` y una
simulación del algoritmo v1 para los cortes (BE-3.2 C2 exige que ningún nivel alta yerre > 30 m). Las variantes se
calculan en proceso con los pesos locales y fuerza bruta. *Alternativas descartadas:* leer los vectores de pgvector
(la base es privada y su esquema es del backend); usar `POST /v1/localize` (agrupa y aplica `LOC_SIM_MIN`: no deja
ver la distribución cruda, y deja eventos); `k = 5` como decía 0.8.0 (la simulación necesita los 10 vecinos de la
localización; el *recall* usa los 5 primeros igual); un contenedor local para las variantes (mismas dependencias que
`uv`, sin ventaja); optimizar umbrales con búsqueda sobre una métrica global (con ~50 fotos sobreajusta).
*Consecuencias:* `evaluar` necesita `embedding` encendido; la simulación copia parámetros de backend §5.10 y supone dos
detalles que §4.10 no fija (centroide de grupo y margen `m`): BE-3.2 debe confirmarlos; la comparación de variantes
espera a BE-4.1 (URL de las imágenes).

---

## 7. Riesgos

| ID | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | Latencia por encima del objetivo (lote de 5 > 800 ms en 2 vCPU) | Media | Medio | EMB-3.1 (`benchmark.py` en `dev`, §5.7; en el ensayo local, p95 de 695–846 ms); palancas de §4.4, decisión en C3 |
| R2 | Calidad de recuperación insuficiente (luz, oclusiones, recorte central, lugares parecidos; ViT-S/14 discrimina algo menos que ViT-B/14) | Media | Alto | EMB-3.2 (`tools/evaluacion` listo, sin medir: falta el dataset real; protocolo con dos franjas horarias y `por_hora`, §4.5); EMB-5.1 si una variante gana (incluido volver a ViT-B/14 con más vCPU o con GPU) |
| R3 | Imagen grande (~1,8 GB): 2–3 min desde el encendido | Alta | Bajo | *Start period* de 180 s; el `worker` espera a `/health/ready`; encender antes de probar (infra R6) |
| R4 | Una actualización de librerías cambia los vectores sin avisar | Media | Alto | Versiones fijadas en `uv.lock`; vectores dorados en CI (con los pesos y `DORADOS_OBLIGATORIOS=1`) y en `validate21` (ADR-EMB-12) |
| R5 | Ingesta masiva satura el servicio | Media | Bajo | Prioridad; `503 SATURADO`; el `worker` reintenta |
| R6 | Falta de memoria con lotes grandes | Baja | Medio | `LOTE_MAX = 8`; 4 GB de tarea; en el ensayo local de EMB-3.1, 541 MiB de pico con lotes de 8 (en `dev`, `memoria_proceso_mb` del benchmark, §5.7) |
| R7 | La revisión fijada desaparece de Hugging Face | Baja | Medio | Las imágenes ya publicadas en ECR conservan los pesos; guardar una copia de los pesos fuera de Hugging Face si se vuelve crítico |
