# CHANGELOG — Servicio de embeddings (`SERVICE_EMBEDDING`)

Una entrada por versión de [`ARCHITECTURE.md`](./ARCHITECTURE.md), la más reciente primero.

**Cómo se numera la versión del documento**
- **Mayor:** cambio incompatible en la API de §5 (renombrar un campo, quitar un endpoint, cambiar un código de error).
  Mientras la versión sea `0.x`, un cambio incompatible sube la **menor**.
- **Menor:** endpoint o campo nuevo, decisión nueva (ADR), **`version_vector` nueva**, parámetros medidos.
- **Parche:** aclaraciones o correcciones de redacción sin efecto en contratos.

Toda entrada que cambie la `version_vector` lo indica de forma explícita en «Contratos tocados», porque obliga a
re-indexar el dataset.

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

## [0.5.0] — 2026-10-24

- **Lote que la motivó:** ninguno; la cuenta tiene cupo 0 de instancias con GPU y el equipo no puede esperar el
  aumento. La infraestructura pasa `embedding` a Fargate con 2 vCPU, sin cambiar el encendido bajo demanda
  (`INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` 0.9.0, ADR-INF-14).
- **Qué cambió:**
  - Nuevo ADR-EMB-11: modelo **DINOv2 ViT-S/14** (`facebook/dinov2-small`, 22 M parámetros) en CPU con 2 vCPU.
    Reemplaza a ADR-EMB-01 (ViT-B/14) y ADR-EMB-10 (GPU), que no llegó a aplicarse. ADR-EMB-02, ADR-EMB-05 y
    ADR-EMB-07 vuelven a describir CPU.
  - Se elimina el lote **EMB-2.2 Imagen con GPU** (PLAN, §4 y `validation/validation-2-2.md`), con `EMBEDDING_DEVICE`,
    los extras `cpu`/`cuda`, `tools/dorados.py`, la tolerancia entre dispositivos y R8.
  - EMB-3.1 vuelve a «Rendimiento en CPU»: objetivo del lote de 5 en p95 ≤ 800 ms en 2 vCPU (§4.4); palancas: hilos,
    ONNX Runtime, 4 vCPU, int8. §4 se renumera: EMB-3.1 §4.4, EMB-3.2 §4.5, EMB-5.1 §4.6.
  - §1–§3: Fargate con 2 vCPU / 4 GB, apagado por defecto (`embedding.py encender` de infra), arranque de 2–3 min.
    R1, R2, R3 y R6 actualizados.
  - Validaciones: 1-1 y 3-1 lanzan las tareas sueltas con `--launch-type FARGATE` y 3-1 comprueba 2 vCPU / 4 GB; 2-1
    espera vectores de 384.
  - PLAN: EMB-1.1 sigue «En curso»; su código usa `dinov2-base` y hay que pasarlo a `dinov2-small`.
- **Contratos tocados (§5):**
  - **`version_vector` nueva: `dinov2-vits14/pp-v1`** (antes `dinov2-vitb14/pp-v1`), dimensión **384** (antes 768).
    No hay vectores indexados todavía, así que no hay que re-indexar; el backend cambia `EMBEDDING_VERSION_VECTOR`,
    la columna a `vector(384)` y el nombre del índice (backend 0.5.0).
  - §5.2: `/v1/info` con `modelo = facebook/dinov2-small`, la revisión nueva, `arquitectura = ViT-S/14`, `dim = 384` y
    `dispositivo = cpu`.
  - §5.3: modelo y revisión `ed25f3a31f01632728cabb09d1542f84ab7b0056`, cabeza de `main` en Hugging Face (commit
    «Update README.md», 2023-09-06, que solo cambia la licencia del README a Apache 2.0); `model.safetensors` de
    88 249 960 bytes, SHA-256 `ae1e99fcefd534ed978cdeb8326f08030c96e28b7a81ffcbc98a857c84d14be1`. El preprocesamiento
    pp-v1 y la extracción no cambian.
  - §5.4: vuelve a una sola tolerancia (1e-5, mismo contenedor); §5.5: imagen de ~1,8 GB, ~1 GB de memoria, tarea de
    4 GB; sin `EMBEDDING_DEVICE`. §5.7: `TORCH_NUM_THREADS = 2` y latencia objetivo en 2 vCPU. §5.8: tareas sueltas
    en Fargate. §5.9: ejemplo de `benchmark.py` en 2 vCPU; fuera el formato de `tools/dorados.py`.
- **Cómo se verificó:** revisión, archivos y tamaños leídos en las páginas del repositorio `facebook/dinov2-small` en
  Hugging Face el 2026-10-24 (árbol de `main` en `ed25f3a`, 7 commits; `model.safetensors` añadido en `150c8e7`). La
  estimación de 0,5–1,5 s para 5 fotos escala por el cómputo de ViT-S/14 la medición de referencia de ViT-B/14 de infra
  ADR-INF-13; no se midió con PyTorch ni en Fargate.
- **Pendiente:** pasar el código de EMB-1.1 a `dinov2-small` (`config.py`, la revisión que comprueba
  `descargar_modelo.py` y las pruebas que comparan §5.3 con el código); medir en EMB-3.1.

---

## [0.4.0] — 2026-10-24

- **Lote que la motivó:** ninguno; el equipo pide que `POST /v1/localize` responda en menos de 1 s, y la
  infraestructura pasa `embedding` a una GPU bajo demanda (`INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` 0.7.0,
  ADR-INF-13). En 1 vCPU, 5 fotos tardan ~5,5 s.
- **Qué cambió:**
  - Nuevo ADR-EMB-10: inferencia en GPU (NVIDIA T4) en `dev` y en CPU en `local` y CI, con el mismo código y la misma
    `version_vector`. ADR-EMB-02, ADR-EMB-05 y ADR-EMB-07 anotan lo que cambia.
  - Nuevo lote **EMB-2.2 Imagen con GPU** (§4.4, PLAN, `validation/validation-2-2.md`): extras `cpu` y `cuda` con un
    solo `uv.lock`, `EMBEDDING_DEVICE`, float32 sin TF32, preprocesamiento en CPU, `tools/dorados.py` dentro de la
    imagen.
  - EMB-3.1 pasa a «Rendimiento en GPU»: objetivo del lote de 5 en p95 ≤ 500 ms (antes 3 s en CPU) y palancas nuevas
    (§4.5); `validation-3-1.md` mide en la GPU (proveedor de capacidad `campus-locator-dev-gpu`, 3 vCPU, 12 GB, una
    GPU).
  - §1, §2, §3: el servicio corre en EC2 con GPU, apagado por defecto y encendido a mano; desaparece el horario de
    `dev`. R1, R3 y R6 actualizados; nuevo R8.
  - §4 se renumera: EMB-2.2 es §4.4, EMB-3.1 §4.5, EMB-3.2 §4.6 y EMB-5.1 §4.7.
  - `validation-1-1.md`: C1b lanza la tarea en el proveedor de capacidad de la GPU (antes `--launch-type FARGATE`) y
    P1 comprueba que existe.
- **Contratos tocados (§5):**
  - §5.2: `/v1/info` publica `dispositivo = cuda` en `dev` (el campo ya existía con `cpu`).
  - §5.3: el dispositivo no forma parte de la `version_vector`; precisión sin TF32 en GPU.
  - §5.4: tolerancia nueva **entre dispositivos** (≤ 1e-4 por componente frente a los dorados, calculados en CPU); la
    de 1e-5 queda para el mismo dispositivo.
  - §5.5: variable `EMBEDDING_DEVICE`; imagen de ~6 GB con CUDA desde EMB-2.2; `tools/dorados.py` y los dorados dentro
    de la imagen; memoria en GPU.
  - §5.7: parámetro `EMBEDDING_DEVICE`, latencia objetivo en GPU y campos `dispositivo` y `gpu` en `modelo_listo`.
  - §5.8: tareas sueltas en la GPU; los validadores que necesitan el servicio lo encienden y lo dejan como estaba.
  - §5.9: formato de `tools/dorados.py` y ejemplo de `benchmark.py` en GPU.
  - La `version_vector` **no** cambia: sigue siendo `dinov2-vitb14/pp-v1`, salvo que EMB-2.2 C2 encuentre los
    vectores en GPU a más de 1e-4 de los dorados (R8); en ese caso se decide una versión nueva antes de indexar nada
    en GPU.
- **Cómo se verificó:** revisión cruzada con infra 0.7.0 (§3.4, §5.4, §5.10, ADR-INF-13) y con el backend 0.4.0. Que
  el coseno entre dos vectores unitarios de 768 dimensiones a ≤ 1e-4 por componente supera 0,99999 sale de
  ‖d‖ ≤ 1e-4 · √768 ≈ 2,8e-3 y coseno = 1 − ‖d‖²/2. Sin código: EMB-2.2 aún no se construye.
- **Pendiente:** EMB-2.2 (código y validación). Renombrar la carpeta `SERVICE_EMBEDDINGS_DINOV2` a
  `SERVICE_EMBEDDING`, el nombre que usan los documentos, y ajustar los `paths` de `embedding.yml`.

---

## [0.3.0] — 2026-10-23

- **Lote que la motivó:** EMB-1.1 (servicio base e imagen).
- **Qué cambió:**
  - Revisión de `facebook/dinov2-base` fijada en §5.3: `f9e44c814b77203eaa57a6bdbbd535f21ede1415`, la cabeza de
    `main` en Hugging Face al consultarla (commit «Update README.md» del 2024-01-17). La imagen descarga de ella
    `config.json`, `model.safetensors` y `preprocessor_config.json`.
  - Primer código en `project/`: `/health`, `/health/ready`, `/v1/info`, carga y calentamiento del modelo en
    segundo plano, `Dockerfile`, `src/ops/comun.py` y `validate11.py`; workflow `.github/workflows/embedding.yml`.
  - §4.1 y §4.2 describen lo construido: estructura real (`.dockerignore`, `uv.lock`, pruebas), imagen en tres
    etapas, orden del arranque, logs y comportamiento de `embedding.yml` (espera propia que detecta el *rollback* del
    *circuit breaker*; sin `environment` en el job de despliegue).
  - Nuevo ADR-EMB-09: el modelo se prepara en segundo plano y, si falla, el proceso termina con código 1.
  - §5.8 documenta `src/ops/comun.py` (orden, limpieza al empezar y al terminar, clasificación de errores en
    códigos, `--solo` con subcomprobaciones, acceso a Docker, AWS y ECR).
- **Contratos tocados (§5):**
  - §5.1: reglas de `X-Request-Id` (1–128 caracteres de `[A-Za-z0-9._:-]`; si no, se genera) y documentación
    interactiva solo en `local`.
  - §5.2: ejemplo de `/v1/info` con la revisión real; responde también mientras el modelo carga; `commit` cae a
    `desconocido` sin `GIT_COMMIT`.
  - §5.3: revisión anotada.
  - §5.5: `revision.json` y arranque que la verifica; usuario `app` (uid 10001); cómo se construye; variables
    `GIT_COMMIT` y `HF_HOME=/tmp/huggingface` (el usuario de la imagen no tiene carpeta personal).
  - §5.6: `404 NO_ENCONTRADO` (mismo código que el backend) y `405 METODO_NO_PERMITIDO`, con el formato de §5.1.
  - §5.7: formato completo del log (campos y eventos; salud en `DEBUG`) y sobrescritura de parámetros por variable
    de entorno.
  - La `version_vector` **no** cambia: sigue siendo `dinov2-vitb14/pp-v1`; la revisión se fija por primera vez, antes
    de que exista ningún vector.
- **Cómo se verificó:** SHA leído de la página de archivos de `main` del repositorio en Hugging Face el
  2026-10-23. 37 pruebas en verde (contrato HTTP con un modelo falso; carga, CLS tras la *layernorm* y norma L2 con
  un DINOv2 diminuto en `transformers` 5.20.2 y PyTorch 2.14.1; contrato de los validadores, incluida la coherencia
  de §5.3 y de `validation-1-1` con el código) y `ruff` limpio. Arranque real con `uvicorn`: `/health` 200 durante
  la carga, `/health/ready` 503 → 200, `/v1/info` completo, log JSON desde la primera línea, el *health check* de
  infra §5.7 sale con 0 y el proceso termina con 1 si `revision.json` no coincide. `validate11.py` se ejercitó con
  dobles de Docker y de ECS (códigos 0, 1, 2 y 3) y `embedding.yml` pasa `actionlint` y `shellcheck`. La imagen no
  se construyó (el entorno de trabajo no llegaba al índice de PyTorch ni a Hugging Face): construirla y ejecutar
  `validate11.py` contra AWS queda para quien cierra el lote.
- **Pendiente:** generar y versionar `project/uv.lock` (`uv lock`; el índice de PyTorch para CPU no era accesible al
  escribir el lote); ejecutar `validate11.py` en `local` y en `dev` (C1 espera INF-1.3). La carpeta del repositorio se
  llama `SERVICE_EMBEDDINGS_DINOV2`, no `SERVICE_EMBEDDING` como dicen los documentos: `embedding.yml` usa el nombre
  real; si se renombra, hay que cambiar sus `paths`.

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
  - §4.1 describe la estructura nueva (`project/src/app/`, `project/src/ops/`, `project/tools/`).
  - Nuevo §5.8: entornos y datos de prueba de los validadores del servicio (`local` con la misma imagen, `dev` con
    tareas sueltas).
  - Nuevo §5.9: formato de la salida de `benchmark.py`, del conjunto de evaluación (`puntos.json`) y de su informe.
  - EMB-3.2 se valida con BE-2.4 (vecinos) y un dataset real (FE-2.1 + BE-2.2); su conjunto incluye un punto lejos del
    dataset para BE-3.2 C5; el nombre del informe cambia `/` por `_`.
- **Contratos tocados (§5):** §5.5 (la imagen incluye `tools/benchmark.py` para ejecutarlo como tarea suelta;
  `src/ops/`, `tests/` y `tools/evaluacion/` quedan fuera), §5.8 y §5.9 (nuevos); §5.7 aclara que `COLA_MAX_IMAGENES` no
  cuenta el lote en curso. La `version_vector` **no**
  cambia.
- **Equivalencia de identificadores** (las entradas anteriores usan los viejos): EMB-01 → EMB-1.1 · EMB-02 → EMB-2.1 ·
  EMB-03 → EMB-3.1 · EMB-04 → EMB-3.2 · EMB-05 → EMB-5.1.
- **Cómo se verificó:** comprobación automática de que los lotes citados existen, de que las referencias cruzadas entre
  secciones resuelven, de que cada documento de validación cubre una vez cada criterio de su lote y de que las tablas
  están bien formadas.
- **Pendiente:** escribir los validadores (cada lote los entrega con su código).


---

## [0.1.0] — 2026-10-23

- **Lote que la motivó:** ninguno; diseño inicial previo a EMB-01. No hay código.
- **Qué cambió:** primera versión. Modelo DINOv2 ViT-B/14 (768 dimensiones, decisión del equipo) en CPU,
  preprocesamiento
  pp-v1, descriptor CLS normalizado, cola con prioridad, pesos dentro de la imagen. ADR-EMB-01 a ADR-EMB-08 y riesgos
  R1–R7.
- **Contratos tocados (§5):** todos nuevos — convenciones (§5.1), endpoints `/health`, `/health/ready`, `/v1/info`,
  `/v1/embed` (§5.2), modelo y preprocesamiento (§5.3), formato del vector (§5.4), imagen (§5.5), errores (§5.6) y
  parámetros (§5.7). **`version_vector` inicial: `dinov2-vitb14/pp-v1`.**
- **Cómo se verificó:** revisión cruzada con `BACKEND_FASTAPI/docs/ARCHITECTURE.md` v0.1.0 (lote máximo 8, prioridad,
  comprobación de `version_vector`, `vector(768)` con coseno) e `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` v0.1.0
  (puerto 8080, `/health/ready` en el *health check*, 1 vCPU / 3 GB, `TORCH_NUM_THREADS`). Antes de publicar se aplicó
  una revisión independiente: se quitó `PORT` de las variables consumidas, se documentó
  que la prioridad no interrumpe un lote en curso, la igualdad entre tamaños de lote pasa a tolerancia 1e-5 y los
  valores que pertenecen a infra (tamaño de tarea, URL, horario) se referencian en lugar de copiarse.
- **Pendiente:** fijar la revisión del modelo (EMB-01); medir latencias reales (EMB-03).
