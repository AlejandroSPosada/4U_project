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

## [0.9.2] — 2026-10-26

- **Lote que la motivó:** EMB-3.2 (sigue «En curso»).
- **Qué cambió:** el usuario confirmó backend ADR-BE-18 (centroide sin ponderar y `m = (p₁ − p₂) / p₁`, backend
  0.12.1): §4.5 (paso 3 de «Qué se recomienda») y ADR-EMB-14 dejan de decir «a confirmar por el usuario». PLAN:
  alineado con 0.9.2.
- **Contratos tocados (§5):** ninguno.
- **Cómo se verificó:** sin cambios de código; la simulación ya usaba esas fórmulas (0.9.1).
- **Pendiente:** la docstring de `metricas.localizar` («a confirmar con BE-3.2»), con el próximo cambio de código de
  EMB-3.2.

## [0.9.1] — 2026-10-26

- **Lote que la motivó:** EMB-3.2 (sigue «En curso»), al construirse BE-3.2 (backend 0.12.0, `c287989`).
- **Qué cambió:**
  - §4.5 (paso 3 de «Qué se recomienda»), §5.9 («Detalle del cálculo») y ADR-EMB-14: los dos supuestos de la
    simulación, «a confirmar con BE-3.2» (centroide de grupo = media sin ponderar; `m = (p₁ − p₂) / p₁`), pasan a
    remitir a backend **ADR-BE-18**, que los fijó igual; siguen a confirmar por el usuario y, si cambian, cambian a la
    vez en el backend y en `metricas.py` (y hay que recalibrar).
  - Se anota que el backend **trunca la confianza a 2 decimales y decide el nivel con el valor truncado** (backend
    §4.10, paso 7), mientras que la simulación compara sin truncar: con cortes en la rejilla de 0,01 da el mismo nivel
    salvo una confianza a menos de 5·10⁻⁷ de un corte (ADR-BE-18).
  - §5.9: lo que la simulación no hace (radio y truncado, además de rumbo y contexto) y lo que coincide con el código
    del backend, incluidos los desempates de ADR-BE-18 (orden de llegada a igual similitud, grupo creado antes a igual
    puntuación, «primer grupo» y no el más cercano), comprobados leyendo `metricas.localizar` y `conjunto.haversine_m`
    (mismo radio terrestre, 6 371 008,8 m). Las demás diferencias de ADR-BE-18 (`referencias` sin el lugar cercano,
    evento solo con `200`, errores de `metadatos`) no afectan a la calibración.
  - PLAN: alineado con 0.9.1.
- **Contratos tocados (§5):** ninguno (aclaración de §5.9).
- **Cómo se verificó:** lectura de backend ARCHITECTURE §4.10, ADR-BE-18 y CHANGELOG 0.12.0, y de
  `tools/evaluacion/metricas.py` (`localizar`) y `conjunto.py` (`haversine_m`). Sin cambios de código.
- **Pendiente:** la docstring de `metricas.localizar` todavía dice «a confirmar con BE-3.2»; se corrige con el próximo
  cambio de código de EMB-3.2 (cambiarla sola dispararía `embedding.yml`). Confirmar ADR-BE-18 con el usuario.

## [0.9.0] — 2026-10-25

- **Lote que la motivó:** EMB-3.2 (conjunto de evaluación y calibración), solo la parte que no necesita dataset. El
  lote sigue «En curso»: falta el dataset real (FE-2.1 + BE-2.2), BE-2.4 desplegado y las fotos de consulta.
- **Qué cambió:**
  - Código: nuevo `tools/evaluacion/` (`__main__.py`, `cli.py`, `conjunto.py`, `fuentes.py`, `metricas.py`,
    `variantes.py`) con las órdenes `revisar`, `cobertura`, `evaluar` y `variantes`; nuevo `src/ops/validate32.py`;
    pruebas nuevas `tests/test_evaluacion.py` (campus sintético, cliente del backend con `httpx.MockTransport`, el
    extractor de variantes contra los vectores dorados si hay pesos) y `tests/test_validate32.py` (dobles de S3,
    Secrets Manager y del backend). No cambian el servicio, el `Dockerfile`, el `.dockerignore` (ya dejaba fuera
    `tools/evaluacion/`), `pyproject.toml`, `uv.lock` ni `comun.py`.
  - §4.5 reescrito: estado, qué se mide, cómo se recomiendan `LOC_SIM_MIN`, `LOC_SIM_ALTA` y los cortes (con la
    simulación del algoritmo v1 y sus dos supuestos), variantes, el **protocolo de toma de fotos** y las trampas.
  - Nuevo ADR-EMB-14 (evaluación con el endpoint de vecinos y reglas fijas de recomendación).
  - §1.3: contratos que consume la evaluación (backend e infra). §4.1: estructura de `tools/evaluacion/` y pruebas. R2.
  - `validation-3-2.md`: orden de las precondiciones (P4 → P1 → P2 → P2b → P3) y sus códigos; P2 deja de usar
    `GET /v1/admin/images` y `/images/{id}` (BE-4.1, que no es dependencia del lote) y usa `GET /v1/admin/videos`;
    P2b acepta `503 EMBEDDING_NO_DISPONIBLE` (el validador no enciende `embedding`); C1 lee el dataset con
    `/admin/videos/{id}` y concreta qué es «punto con dataset»; C2 dice cómo elige el informe; §5 completo
    (variables, nueve pasos de preparación con su salida esperada, ejecución con su salida esperada y la de hoy).
  - PLAN: alineado con 0.9.0; EMB-3.2 «En curso»; §2.1 anota BE-4.1 solo para la comparación de variantes.
- **Contratos tocados (§5):**
  - §5.8: `validate32.py` (orden, códigos, que no enciende `embedding` ni escribe) y la herramienta sobre una copia
    local del conjunto.
  - §5.9, conjunto: campo **nuevo opcional** `fotos[].vuelta` (compatible: la validación de BE-3.2 solo lee `archivo`, `punto` y `rumbo`) y tabla de reglas
    (formas de `version_conjunto`, `id`, `archivo`; franjas de `hora` en hora de Bogotá).
  - §5.9, informe: las claves de 0.8.0 siguen siendo el contrato; se documentan los extras (`similitud.*.n`,
    `similitud.lejos_del_dataset`, `por_hora`, `actual_backend`, `detalle_recomendacion`, `simulacion`, `cobertura`…)
    y que `variantes` añade `pp-v1-local`, `sin-recorte`, `res-448` y `media-parches`.
  - §5.9: los vecinos se piden con `k = 10` (`LOC_TOP_K`), no `k = 5`; el dataset sale de `GET /v1/admin/videos` (no
    de `GET /v1/admin/images`, que es de BE-4.1); las variantes se calculan en el proceso de la herramienta, no en un
    contenedor. Órdenes, opciones, códigos de salida y la API de los módulos de `tools/evaluacion`.
  - §5.9: parámetros exactos de `metricas.py`, detalle del cálculo (percentiles, Youden, `LOC_SIM_ALTA`, simulación,
    cortes y sus valores de respaldo, agrupación de consultas), de `fuentes.py`, `cli.py` y `variantes.py`, y los
    nombres internos de `validate32.py`, para cerrar el lote y BE-3.2 sin leer el código.
  - `version_vector` **no cambia** (`dinov2-vits14/pp-v1`).
- **Cómo se verificó:** en WSL (Ubuntu 26.04), desde `project/`: `uv run ruff check .`, `uv run ruff format --check .`
  y `uv run --group ops pytest`, en verde; `test_extractor_reproduce_los_vectores_dorados_de_pp_v1` corrió con los
  pesos de `project/.modelo/` (ExtractorDinov2 con pp-v1 da los dorados a ≤ 1e-5). Nada se ejecutó en AWS ni con el
  backend real.
- **Pendiente:** tomar las fotos (protocolo de §4.5), generar el informe y `validate32.py` en `dev` (necesita FE-2.1,
  BE-2.2 y BE-2.4); C3 (entrega a BE-3.2); comparar variantes (BE-4.1). A confirmar con BE-3.2 los dos supuestos de la
  simulación (centroide de grupo y margen `m`, backend §4.10). La orientación del teléfono en el protocolo, a confirmar
  con frontend.

---

## [0.8.0] — 2026-10-25

- **Lote que la motivó:** EMB-3.1 (rendimiento en CPU), cierre con la medida en `dev` (C2 y C3).
- **Qué cambió:** §5.7 «Latencias medidas en `dev`» con los números de la tarea suelta (lotes de 1, 4, 5 y 8 en
  p50 / p95: 91 / 92, 326 / 331, 406 / 413 y 659 / 668 ms; inferencia p95 90, 327, 409 y 663 ms), CPU, memoria, pp-v1
  por imagen y el peor caso con ingesta en curso (≈ 744 ms); §5.5 memoria en `dev` (475 MiB en reposo, 538 de pico);
  §4.4 resume la medida; §5.9 da por comprobado que `limites_de` sale `ecs` con 2 / 4096 en `dev`. PLAN: EMB-3.1
  «Hecho».
- **Contratos tocados (§5):** §5.5 y §5.7 (parámetros medidos; la latencia objetivo no cambia). Sube la menor, como
  anunciaba 0.7.0.
- **Cómo se verificó:** `validate31.py --entorno dev` con código 0 sobre `a7d2907` (2026-10-25 19:16 UTC, informe
  `.validacion/EMB-3.1-20261025-191654.json` y `EMB-3.1-benchmark-55cdd0de6c41465ba5bd5c043082a031.json`): pasan P3,
  P2, P1, C1a (tarea `campus-locator-dev-embedding:5`, 2048 CPU / 4096 MB, salida 0, descarga 15 s, ejecución 96 s) y
  C1b. C3: el lote de 5 queda en p95 413 ms ≤ 800 ms, no aplica ninguna palanca. `embedding.yml` publicó la imagen y
  registró `:5` sin encender el servicio (sigue en 0).
- **Pendiente:** una sola medida en una generación de CPU (Xeon 6975P-C): la variación entre tareas de Fargate sigue
  sin medir. La latencia real de `/v1/localize` (red, backend y RDS) la mide BE-3.2.

---

## [0.7.0] — 2026-10-25

- **Lote que la motivó:** EMB-3.1 (rendimiento en CPU), antes de su validación en `dev`.
- **Qué cambió:**
  - Código: `tools/benchmark.py` deja de ser el provisional de EMB-1.1 (salía con 1 sin medir): arranca el servicio
    como subproceso en `127.0.0.1:8080`, envía en serie lotes de 1, 4, 5 y 8 JPEG sintéticos de 1024 × 768 (calidad
    85), mide cada petición desde el cliente y escribe una línea `BENCHMARK_JSON`; atiende `SIGTERM` como PID 1.
    Nuevo `src/ops/validate31.py`. `comun.py` añade `PLAN`, `estado_lote()` y `archivo_en_commit()`. Pruebas nuevas
    `test_benchmark.py` y `test_validate31.py`. No cambian el `Dockerfile` (ya copiaba `tools/benchmark.py`), el
    `.dockerignore`, `pyproject.toml` ni `uv.lock`.
  - §4.4 describe lo construido: qué mide el benchmark, cómo se corre en `dev`, que la imagen desplegada aún trae el
    provisional, el ensayo local, la tabla de palancas (orden, efecto esperado, costo y si exige `version_vector`
    nueva; **sin decidir**: es C3) y lo que BE-3.2 y EMB-3.2 deben saber de las cifras (servicio ocioso y en
    *loopback*; peor caso con ingesta ≈ p95 del lote de 4 + p95 del lote de 5; CPU de Fargate variable; *health
    check*; `--cpus` en local).
  - Nuevo ADR-EMB-13: el benchmark arranca el servicio en su propia tarea y lo mide por HTTP en *loopback*.
  - §4.1 (benchmark y pruebas), R1 y R6 con lo medido en local.
  - `validation-3-1.md` reescrito con la forma de `validation-1-1` y `validation-2-1`: orden de las precondiciones
    (P3 → P2 → P1) y su código; P1 comprueba con `git` que la imagen desplegada trae el benchmark y, si no, termina
    con 2 sin lanzar nada; C1b exige además el `commit` desplegado y ≥ 20 repeticiones y guarda el JSON; C1 no falla
    por pasar de 800 ms (eso es C3); §4 con el costo; §5 con variables y permisos, preparación en cuatro pasos con su
    salida esperada, ejecución con su salida esperada y cómo explorar palancas. IDs y criterios no cambian.
  - PLAN: alineado con 0.7.0; EMB-3.1 «En curso».
- **Contratos tocados (§5):**
  - §5.5: «Contenido» (rutas `/srv/app` y `/srv/tools`; las imágenes `44fdff8` y `f2ddc42` traen el provisional) y
    «Memoria en ejecución» (antes «~1 GB estimado»; medido en local: 477 MiB en reposo y 541 MiB de pico; `dev`,
    pendiente).
  - §5.7: tablas nuevas «Latencias medidas en `dev`», con la estructura lista y los valores **pendientes de medir
    en `dev`**; la fila «Latencia objetivo» remite a ellas.
  - §5.8: parámetros exactos de las tareas sueltas de `dev` (revisión y red del servicio; por qué no `sg_migrate`;
    stream del log), `validate31.py` y la API de `comun.py` en una tabla.
  - §5.9: opciones y códigos de salida de `benchmark.py`; salida JSON ampliada (campos nuevos `limites_de`, `cpu`,
    `capacidad_cpu_torch`, `imagen`, `prioridad`, `calentamiento`, `arranque_s`, `memoria_proceso_mb`,
    `preproceso_ms_por_imagen` y, por lote, `max_ms`, `inferencia_p50_ms`, `inferencia_p95_ms`, `cola_max_ms`), lote
    de 4 y repeticiones 40/30/60/30 por defecto, con un ejemplo real del ensayo local en lugar del ilustrativo.
  - La `version_vector` **no** cambia.
- **Contradicciones corregidas:**
  - §5.9 decía que cada repetición se mide «desde que la petición entra en la cola hasta que sale la respuesta»: el
    benchmark (ADR-EMB-13) mide toda la petición desde el cliente; ahora §5.9 lo define así, con el percentil.
  - `validation-3-1` C2 pedía quitar «aún sin datos» de §5.7, texto que §5.7 no tenía («A medir en EMB-3.1»); ahora
    remite a las tablas nuevas.
  - `validation-3-1` daba P1 por cumplida con EMB-2.1 «Hecho» («la imagen desplegada trae `tools/benchmark.py`»),
    pero la imagen de EMB-2.1 (`f2ddc42`) trae el provisional; P1 lo comprueba.
  - `validation-3-1` no decía en qué orden se evalúan las precondiciones (infra §5.11 pide las de credenciales
    primero); duración de 10–20 min estimada de nuevo en 6–10 min.
- **Cómo se verificó:** en WSL (AMD Ryzen 7 6800HS, Docker 29, uv 0.13): `ruff check` y `ruff format --check`
  limpios y 135 pruebas en verde con `DORADOS_OBLIGATORIOS=1` y el grupo `ops` instalado (`embedding.yml` instala
  solo `dev`: allí `test_validate31.py` se omite con `importorskip`, porque necesita `botocore`; el primer push,
  `aff448b`, falló en CI por esa importación) (entre ellas, el bucle completo de `benchmark.py`
  contra el servicio HTTP con un modelo falso, cuya salida acepta `validate31.revisar_resultado`, y `validate31` de
  punta a punta con dobles de ECS y Logs: pasa, bloquea con `bootstrap` o con el provisional sin lanzar tareas, falla
  con la tarea en salida 1 o de otro tamaño). `benchmark.py` dentro de la imagen `f2ddc42` con el benchmark nuevo
  encima (lo mismo que copia la última etapa del `Dockerfile`; la imagen no se construyó desde cero): código 0 en
  115 s y la línea `BENCHMARK_JSON` (números en §4.4 y §5.9); `--salida texto`; `docker stop` lo detiene en 1 s con
  salida 143 y el servicio se apaga ordenadamente; desde `project/` con `MODELO_DIR=.modelo`; la imagen `f2ddc42`
  sin cambios sale con 1 («pendiente de EMB-3.1»), y `git show` confirma el provisional en `44fdff8` y `f2ddc42`.
  `validate31.py` contra AWS real con un gancho de botocore que bloquea `RunTask`, `StopTask`, `UpdateService` y
  `RegisterTaskDefinition`: código 3 sin `AWS_PROFILE` y código 2 con él (P3 y P2 pasan; P1: «la imagen desplegada
  (f2ddc42) trae el tools/benchmark.py provisional…»), sin intentar ninguna escritura. Lecturas de AWS: el servicio
  `embedding` usa `campus-locator-dev-embedding:4` (imagen `f2ddc42`, 2048 / 4096, `TORCH_NUM_THREADS = 2`, *health
  check* de infra §5.7, prefijo de log `embedding`) con la subred `campus-locator-dev-publica-a`, el grupo
  `campus-locator-dev-embedding` y `assignPublicIp = ENABLED`, y 0 réplicas. **Sin comprobar en `dev`:** la medida
  (C1), que `limites_de` salga `ecs` y la duración real de la tarea.
- **Pendiente:** llevar EMB-3.1 a `main` para que `embedding.yml` publique y registre su imagen (la desplegada no
  puede medir); `validate31.py --entorno dev`; C2 (copiar los números a §5.7 y §5.5, versión 0.8.0 por «parámetros
  medidos»); C3 si el p95 del lote de 5 pasa de 800 ms; la fila de PLAN §3.

---

## [0.6.1] — 2026-10-25

- **Lote que la motivó:** EMB-2.1, al cerrarlo: ARCHITECTURE debe bastar para operar el servicio sin leer el código, y
  parte de lo necesario solo estaba en el código o en la conversación.
- **Qué cambió:**
  - §5.9 documenta los vectores dorados: formato de `esperados.json`, órdenes de `tools/dorados.py` (`imagenes`,
    `vectores`, `comparar`) con sus códigos de salida, cómo copiar los pesos de la imagen a `project/.modelo/`,
    `MODELO_DIR` y `DORADOS_OBLIGATORIOS` en las pruebas, y cuándo se recalculan. §5.4 y ADR-EMB-12 lo enlazan.
  - §5.8: `AWS_PROFILE` también en `local` si la imagen es de ECR; los validadores no usan la cadena de credenciales
    por defecto de AWS (con el perfil por defecto, `AWS_PROFILE=default`).
  - §5.7: los campos de vectorización van en el evento `peticion`; los avisos de Python también salen en JSON.
  - `validation-2-1.md` §5 remite a §5.9 para los pesos y aclara `AWS_PROFILE`.
  - PLAN: alineado con 0.6.1; EMB-2.1 «Hecho».
- **Contratos tocados (§5):** ninguno; aclaraciones de §5.4, §5.7, §5.8 y §5.9 sobre lo que ya hace el código. La
  `version_vector` **no** cambia. Sube el parche.
- **Cómo se verificó:** `validate21.py --entorno local` con código 0 sobre la imagen `f2ddc42` (informe
  `EMB-2.1-20261025-172923.json`): P3 listo a los 11 s; C1 con diferencia 0,0 frente a los dorados (misma CPU en que se
  calcularon); C2 0,0 entre lote y solas; C4 con lote de 8 de 1794 ms, la `alta` a 0,9 s, 3 `baja` esperando y 722 ms en
  cola frente al límite de 2120 ms; C5c con 2 × 503 y 6 × 200 al primer intento. Antes, en la misma máquina: 107
  pruebas en verde con `DORADOS_OBLIGATORIOS=1`. Los comandos de §5.9 son los que se usaron para copiar los pesos.
- **Pendiente:** EMB-3.1 (latencias en Fargate) y EMB-3.2 (calibración).

---

## [0.6.0] — 2026-10-24

- **Lote que la motivó:** EMB-2.1 (vectorización por lotes, `POST /v1/embed`).
- **Qué cambió:**
  - Código: `preproceso.py` (pp-v1 como función pura, sin PyTorch), `planificador.py` (dos colas FIFO, admisión por
    `COLA_MAX_IMAGENES` y un único hilo de inferencia), `POST /v1/embed` en `main.py` (lectura del cuerpo con tope,
    validación en orden, errores de §5.6, campos de vectorización en el evento `peticion`) y `modelo.inferir`, que
    acepta el array de NumPy sin copiarlo. Nuevos `tools/dorados.py` y `tests/golden/` (cinco imágenes sintéticas,
    ~130 KB, y `esperados.json`); pruebas `test_preproceso`, `test_planificador`, `test_embed_http` y `test_dorados`;
    `src/ops/validate21.py`. `comun.imagen_local()` reúne lo que hacía P4 de `validate11.py`, que ahora la llama sin
    cambiar de comportamiento. Dependencias nuevas: `pillow` 13.0.0 y `python-multipart` 0.0.32 (`uv.lock`).
  - §4.1 (estructura) y §4.3 (orden de las validaciones, multipart leído fuera del bucle de eventos y cortado en la
    novena imagen, preprocesamiento en el hilo de inferencia, qué mide cada tiempo, piezas del código; la prioridad
    ordena la atención, no la admisión).
  - Tras una revisión independiente del código: rechazo de imágenes de más de 32:1 (una de 64 × 500 000 px, de menos
    de 0,5 MB, llevaba la redimensión a 2,7 GB y una de 89 MP a unos 6 GB); una frontera de multipart de más de 256
    caracteres daba `500` y ahora `400`; tipos de medio sin distinguir mayúsculas; `config.py` exige
    `COLA_MAX_IMAGENES` ≥ `LOTE_MAX`; C4 de `validate21.py` descuenta las `baja` que salen de la cola mientras la
    `alta` todavía sube.
  - Nuevo ADR-EMB-12: dorados calculados con la pila de `uv.lock` en la CPU de quien cierra, 1e-5 también entre CPU
    (medido) y pesos en CI con `DORADOS_OBLIGATORIOS=1`. R4 lo cita.
  - `validation-2-1.md`: C4 lanza la `alta` a mitad del primer lote, con su duración medida en la máquina (antes, 1 s
    fijo), y repite si quedan menos de 2 `baja` esperando; C5c suelta las 8 peticiones con una barrera y repite si no
    hubo saturación; C1 comprueba el `sha256` de las doradas; §1 da el código de cada precondición y §5, la
    preparación. Criterios, IDs y datos de prueba no cambian.
  - `embedding.yml` (raíz del monorepo): en las pruebas, los pesos de la revisión fijada con `actions/cache` y
    `pytest` con `MODELO_DIR` y `DORADOS_OBLIGATORIOS=1`; §4.2 lo describe. El resto del workflow no cambia.
  - PLAN: alineado con 0.6.0.
- **Contratos tocados (§5):**
  - §5.2: se ignoran las partes con otro nombre; el tipo es el `Content-Type` de cada parte; los 16 MB son bytes del
    cuerpo (MB = 2²⁰ bytes); `X-Prioridad` no distingue mayúsculas y otro valor da `400 SOLICITUD_INVALIDA`; qué mide
    cada campo de `tiempos_ms`.
  - §5.3: lo que la tabla no detallaba (truncado del lado largo, inicio del recorte, escala en float64 y normalización
    en float32), igual que el procesador publicado con el modelo. La tabla no cambia.
  - §5.4: formato de los dorados, quién los comprueba y lo medido entre CPU y entre tamaños de lote.
  - §5.5: `tools/dorados.py` queda fuera de la imagen.
  - §5.6: `SOLICITUD_INVALIDA` también por cuerpo que no es multipart o `X-Prioridad` inválido; `IMAGEN_INVALIDA`
    también por superar `Image.MAX_IMAGE_PIXELS` de Pillow (~89,5 MP) o pasar de 32:1; `detalle.indice` en `413` y
    `415` cuando los causa una imagen; `NO_LISTO` también al detenerse; orden en que se responden los errores.
  - §5.7: parámetro nuevo `PROPORCION_MAX` = 32; `COLA_MAX_IMAGENES` debe ser ≥ `LOTE_MAX`.
  - §5.8: `comun.imagen_local()` y `esperados.json`.
  - La `version_vector` **no** cambia (`dinov2-vits14/pp-v1`): los dorados son los primeros vectores de esa versión y
    aún no hay vectores indexados.
- **Cómo se verificó:** 107 pruebas en verde con `DORADOS_OBLIGATORIOS=1` y los pesos reales (copiados de la imagen
  `44fdff8`; el SHA-256 de `model.safetensors` coincide con §5.3) en un AMD Ryzen 7 6800HS (torch 2.14.1+cpu) y en un
  Intel Xeon con AVX-512 (torch 2.14.1 de PyPI); `ruff check` y `ruff format --check` limpios. pp-v1 da los mismos bits
  que `BitImageProcessorPil` de transformers 5.20.2. Medición entre CPU, hilos y rutas de ISA en ADR-EMB-12 (peor caso,
  6,3e-7). `validate21.py` C1–C5c pasó contra el servicio arrancado con `uvicorn` (modelo real y
  `TORCH_NUM_THREADS=1`) y contra el mismo servicio con modelos falsos de 8 s y 0,07 s por lote de 8. La imagen no se
  construyó aquí (sin Docker ni acceso al índice de PyTorch). `embedding.yml` pasa `actionlint` 1.7.12. Un agente que
  no escribió el código lo revisó (concurrencia, multipart, límites, validador, coherencia con §5); sus hallazgos están
  corregidos arriba. Redimensionar solo la zona del recorte (`resize(box=…)`) evitaría el límite de 32:1, pero no da los
  mismos bits que pp-v1 (1470 de 1512 tamaños probados cambian, hasta 26 niveles en un píxel), así que se descartó.
- **Pendiente:** `uv lock` con acceso al índice de PyTorch; la primera ejecución de `embedding.yml` con los pesos;
  imagen del commit en ECR; `validate21.py` en `local` y la fila de PLAN §3.

---

## [0.5.1] — 2026-10-24

- **Lote que la motivó:** EMB-1.1 (servicio base e imagen), antes de su primera validación: INF-1.3 ya está «Hecho»
  (`INFRASTRUCTURA_TERRAFORM` 0.10.0, validado en `a0f2dc5`), así que P1 de `validation-1-1` ya se cumple en `dev`.
- **Qué cambió:**
  - `validation-1-1.md` sigue la forma de `INFRASTRUCTURA_TERRAFORM/docs/validation/validation-2-1.md`: el encabezado
    cita el diseño que se valida (§4.2, §5.3, §5.5, ADR-EMB-05, ADR-EMB-09, ADR-EMB-11); §1 dice en qué orden se
    evalúan las precondiciones en cada entorno y qué código da cada una; §2 abre con el orden de las comprobaciones y
    lleva a la tabla los detalles que estaban en una lista aparte; §4 deja claro que el validador no toca el servicio
    `embedding` (vale a cualquier hora, encendido o apagado), que la tarea suelta no entra en Cloud Map ni dispara la
    regla de EventBridge y lo que cuesta; §5 añade los permisos de AWS, lo que hace falta en la máquina, el orden
    (`dev` y después `local`), una **preparación** (`uv.lock`, pruebas con PyTorch, despliegue con `embedding.yml`,
    cómo leer la imagen desplegada para `local`) y el resultado esperado. Criterios, IDs, comandos, nombres y plazos no
    cambian.
  - §5.8: las tareas sueltas de `dev` usan la red del servicio y el comando de la imagen o uno sobrescrito (EMB-1.1 C1b
    no lo sobrescribe; EMB-3.1 sí).
  - PLAN: nota de EMB-1.1 en §3 (ya no espera INF-1.3).
- **Contratos tocados (§5):** ninguno; aclaración de §5.8. La `version_vector` **no** cambia. Sube el parche.
- **Cómo se verificó:** revisión cruzada con `INFRASTRUCTURA_TERRAFORM/docs` 0.11.1 (PLAN §3: INF-1.3 e INF-1.4
  «Hecho»; ARCHITECTURE §3.4, §3.8, §3.10, §5.1, §5.7, §5.8, §5.9 y §5.11; `validation-1-3` y `validation-2-1`). Solo
  documentos: no se leyó ni se ejecutó el código.
- **Pendiente:** la preparación de `validation-1-1` §5 (`uv.lock`, `pytest` con PyTorch, que incluye la coherencia de
  `validation-1-1` con `validate11.py`, e imagen en ECR) y las dos ejecuciones de `validate11.py`.

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
  - Código de EMB-1.1 alineado: `config.py` y `src/ops/comun.py` (modelo, revisión, arquitectura, `version_vector`,
    `DIM = 384`), comentario del `Dockerfile`, descripción de `pyproject.toml` y pruebas (`test_config`,
    `test_contrato_http`, `test_modelo`: la dimensión «equivocada» de la prueba pasa de 384 a 192). EMB-1.1 sigue
    «En curso».
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
  ADR-INF-13; no se midió con PyTorch ni en Fargate. Código: 27 pruebas en verde y 2 omitidas (las del modelo, que
  necesitan PyTorch: su índice no era accesible desde donde se cambió), `ruff check` y `ruff format --check` limpios.
- **Pendiente:** correr `pytest` completo con PyTorch (incluye `test_modelo.py`), generar `uv.lock` y construir la
  imagen (EMB-1.1); medir en EMB-3.1.

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
