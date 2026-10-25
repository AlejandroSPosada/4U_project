# Validación 3-1 — EMB-3.1 Rendimiento en CPU

| Campo | Valor |
|---|---|
| Lote | `EMB-3.1` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate31.py` |
| Entornos | `dev` (**cierra el lote**). `local` no aplica: la medida exige la definición de tarea de `dev`; en local solo hay un ensayo de humo del benchmark (§5, paso 2), que no cierra |
| Criterios | Automáticos: C1 (C1a, C1b) · Manuales: C2, C3 |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.8. El diseño que se valida está en ARCHITECTURE §4.4 (qué mide el benchmark, palancas), §5.7
(latencias medidas), §5.8 (tareas sueltas en `dev`), §5.9 (argumentos y salida de `tools/benchmark.py`) y ADR-EMB-13
(el benchmark arranca el servicio en su propia tarea).

## 1. Precondiciones

El script las evalúa en este orden y, si una falla, no sigue: P3 (código 3 sin `AWS_PROFILE`, con credenciales
inválidas o de otra cuenta), P2 (código 2 si falta algo de INF-1.3) y P1 (código 2 si EMB-2.1 no está «Hecho» o la
imagen desplegada no trae el benchmark de EMB-3.1; código 3 si el SHA de esa imagen no está en el clon local). Ninguna
lanza tareas: con P1 en `falla` no se gasta nada.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | `EMB-2.1` en «Hecho» y el servicio `embedding` apunta a una imagen de CI que trae `tools/benchmark.py` de EMB-3.1 | Fila EMB-2.1 de `docs/PLAN.md` §3 en `Hecho`; `ecs describe-services --cluster campus-locator-dev --services embedding` → `taskDefinition` y `networkConfiguration`; `ecs describe-task-definition` → imagen del contenedor `app` = `…/campus-locator/embedding:<SHA de 40>` (no `bootstrap`); `git show <SHA>:./tools/benchmark.py` contiene `BENCHMARK_JSON` (las imágenes hasta `f2ddc42` traen uno provisional que sale con 1 sin medir). Lee también el `awslogs-stream-prefix` del contenedor |
| P2 | `INF-1.3` en «Hecho»: clúster, familia `campus-locator-dev-embedding` y log group `/campus-locator/dev/embedding` | `ecs describe-clusters --clusters campus-locator-dev` → `status = ACTIVE`; `ecs describe-task-definition --task-definition campus-locator-dev-embedding` sin `ClientException`; `logs describe-log-groups --log-group-name-prefix /campus-locator/dev/embedding` → ese grupo. Antes, detiene las tareas que hayan quedado de una ejecución anterior (§4) |
| P3 | `AWS_PROFILE` con credenciales de la cuenta `648617469176` | `sts get-caller-identity` → `Account` (`comun.sesion_aws`). Sin variable o con credenciales inválidas: código 3 (§5.11) |

## 2. Comprobaciones automáticas

Orden: C1a y después C1b. `--solo C1` incluye las dos; C1b sola falla porque lee el log de la tarea de C1a.

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | `ecs run-task --cluster campus-locator-dev --task-definition <revisión de P1> --launch-type FARGATE --started-by validacion-emb31 --network-configuration <la del servicio, de P1> --overrides '{"containerOverrides":[{"name":"app","command":["python","tools/benchmark.py","--salida","json"]}]}'`, es decir, `python tools/benchmark.py --salida json` dentro de la imagen; `ecs describe-tasks` cada 15 s hasta `lastStatus = STOPPED` (máx. 30 min; si vence, falla y la limpieza la detiene) | `containers[app].exitCode = 0`, `taskDefinitionArn` de la familia `campus-locator-dev-embedding`, `cpu = 2048` y `memory = 4096` (tamaño de `dev`, infra §3.4). El detalle da la tarea, la descarga de la imagen (`pullStartedAt` → `pullStoppedAt`) y la ejecución (`startedAt` → `stoppedAt`) |
| C1b | Lee el stream `embedding/app/<id-de-la-tarea>` de `/campus-locator/dev/embedding` (`logs get-log-events --start-from-head`, paginado; reintenta cada 5 s hasta 2 min si el log aún no llegó) y toma la última línea que empieza por `BENCHMARK_JSON` (formato en ARCHITECTURE §5.9) | `version_vector = dinov2-vits14/pp-v1`; `commit` = los 7 primeros caracteres del SHA de P1 (se midió la imagen desplegada); los lotes de 1, 5 y 8 imágenes están, cada uno con ≥ 20 repeticiones y `0 < p50_ms ≤ p95_ms`. El detalle copia p50 y p95 de cada lote (también el de 4), hilos, vCPU y memoria, CPU, memoria del proceso y si C3 aplica; el JSON completo queda en `project/.validacion/EMB-3.1-benchmark-<id>.json`. Si no hay línea `BENCHMARK_JSON`, falla con las últimas líneas del log (p. ej. el evento `benchmark_fallido`) |

C1 solo exige **medir**: un p95 por encima del objetivo no hace fallar C1b; lo trata C3.

## 3. Comprobaciones manuales

| ID | Qué hace la persona | Evidencia en el PR |
|---|---|---|
| C2 | Copia del detalle de C1b (o del `EMB-3.1-benchmark-<id>.json`) p50 y p95 de los lotes de 1, 5 y 8 —y el de 4, `inferencia_p95_ms`, `cpu`, `capacidad_cpu_torch`, `memoria_proceso_mb` y `preproceso_ms_por_imagen`— a las tablas «Latencias medidas en `dev`» de ARCHITECTURE §5.7, sustituyendo «pendiente»; actualiza §5.5 «Memoria en ejecución»; sube la versión del documento (menor: parámetros medidos) y añade la entrada en `CHANGELOG.md` | *Diff* de §5.7, de la versión y del `CHANGELOG.md`; el informe `project/.validacion/EMB-3.1-<AAAAMMDD-HHMMSS>.json` y el `EMB-3.1-benchmark-<id>.json` adjuntos |
| C3 | El detalle de C1b dice si el p95 del lote de 5 supera 800 ms. Si lo supera: decide la palanca con la tabla de ARCHITECTURE §4.4 (orden, efecto esperado, costo y si exige `version_vector` nueva), opcionalmente la ensaya (§5, «Explorar palancas») y la registra como ADR nuevo en §6 (si es ONNX Runtime o int8, anota que exige `version_vector` nueva, ADR-EMB-08; si es 4 vCPU, abre el cambio en infraestructura). Si no lo supera, no aplica | Enlace al ADR en el PR, o el p95 medido con la nota «no aplica» |

## 4. Datos de prueba y limpieza

El servicio no guarda nada (§5.8): no hay datos de prueba que borrar. Las imágenes son JPEG sintéticos que el
benchmark genera en memoria con semilla fija. El único recurso es la tarea suelta (`startedBy = validacion-emb31`), que
termina sola al acabar `benchmark.py`. Al terminar, también si algo falló (salvo `--sin-limpieza`), el script detiene
con `ecs stop-task` la que no haya llegado a `STOPPED` y las que liste
`ecs list-tasks --cluster campus-locator-dev --started-by validacion-emb31`; al empezar (P2) hace lo mismo con las de
una ejecución anterior. Nunca toca el servicio `embedding` (ni su `desiredCount` ni su revisión): la tarea suelta no lo
necesita (infra §5.11), así que da igual que esté encendido o apagado y no le afectan el apagado por inactividad ni el
de las 22:00. La tarea no se registra en Cloud Map (nadie le envía tráfico) y, como su `group` es
`family:campus-locator-dev-embedding` y no `service:embedding`, su parada no dispara la regla de EventBridge (infra
§3.8). Su log queda en `/campus-locator/dev/embedding` 14 días (infra §5.10). Costo: 2 vCPU / 4 GB más la IPv4
pública, ~0,10 USD por hora (tarifas de infra §3.10): < 0,02 USD por ejecución.

## 5. Cómo ejecutarlo

```bash
cd SERVICE_EMBEDDING/project
uv run --group ops python src/ops/validate31.py --entorno dev
```

**Variables.** `AWS_PROFILE` con el perfil de la persona (§5.8 de ARCHITECTURE; el script no usa la cadena por
defecto de AWS: con el perfil por defecto, `AWS_PROFILE=default`). En PowerShell, `$env:AWS_PROFILE = "<perfil>"`.
Necesita `ecs:DescribeClusters`, `DescribeServices`, `DescribeTaskDefinition`, `RunTask`, `DescribeTasks`,
`ListTasks` y `StopTask` sobre `campus-locator-dev`; `iam:PassRole` sobre `campus-locator-dev-ecs-ejecucion` y
`campus-locator-dev-tarea-embedding` (infra §5.8); `logs:DescribeLogGroups` y `logs:GetLogEvents` sobre
`/campus-locator/dev/embedding`. En la máquina: `uv` y `git` (commit del informe y lectura de `tools/benchmark.py`
en el SHA desplegado), con el clon al día (`git fetch`). La región es `us-east-1`. Se puede ejecutar a cualquier hora
y con `embedding` encendido o apagado (§4). Duración aproximada: 6–10 min (aprovisionar la tarea y descargar ~1,9 GB,
1–2 min; cargar y calentar el modelo, < 1 min; medir, 2–4 min; más el log). El informe queda en
`project/.validacion/EMB-3.1-<AAAAMMDD-HHMMSS>.json` (hora UTC) salvo que se indique `--informe`.

**Preparación.**

1. Pruebas y estilo, con los pesos en `project/.modelo/` o en `MODELO_DIR` (cómo copiarlos de la imagen:
   ARCHITECTURE §5.9):
   ```bash
   cd SERVICE_EMBEDDING/project
   uv sync --locked
   uv run ruff check . && uv run ruff format --check . && DORADOS_OBLIGATORIOS=1 uv run pytest
   ```
   Esperado: `ruff` limpio y `pytest` en verde, incluidas `test_benchmark.py` (el bucle completo contra el servicio
   HTTP con un modelo falso, cuya salida acepta `validate31`) y `test_validate31.py` (el validador con dobles de ECS y
   CloudWatch Logs, y su coherencia con este documento).
2. Ensayo local del benchmark dentro de la imagen (opcional; **no cierra** ni sirve para §5.7):
   ```bash
   docker build --platform linux/amd64 --build-arg GIT_COMMIT=$(git rev-parse HEAD) -t campus-locator/embedding:local .
   docker run --rm --cpus 2 --memory 4g -e TORCH_NUM_THREADS=2 campus-locator/embedding:local \
     python tools/benchmark.py --salida json 2>/dev/null
   ```
   Esperado: código 0 en ~2 min y una sola línea `BENCHMARK_JSON {"version_vector":"dinov2-vits14/pp-v1",
   "commit":"<sha corto>",…,"resultados":[{"lote":1,…},{"lote":4,…},{"lote":5,…},{"lote":8,…}]}`. Sin
   `2>/dev/null` se ven los eventos `benchmark_*` y el log del servicio. Con `--salida texto` (o sin `--salida`) sale
   una tabla. Los números de un ensayo en un AMD Ryzen 7 6800HS están en ARCHITECTURE §4.4.
3. Llevar el commit de EMB-3.1 a `main` (PR o *push*). Como cambia `SERVICE_EMBEDDING/project/`, `embedding.yml` pasa
   las pruebas, publica `…/campus-locator/embedding:<SHA>` y registra una revisión nueva de
   `campus-locator-dev-embedding` con `update-service`; con el servicio en 0 réplicas no espera (ARCHITECTURE §4.2):
   ```bash
   gh run list --workflow embedding.yml --branch main --limit 1
   ```
   Esperado: la última ejecución `completed` / `success`, del commit que se valida (~2–3 min).
4. Comprobar que el servicio apunta a esa imagen (es la que lanzará C1a) y traer el commit al clon local:
   ```bash
   git fetch origin
   REVISION=$(aws ecs describe-services --region us-east-1 --cluster campus-locator-dev --services embedding \
     --query 'services[0].taskDefinition' --output text)
   aws ecs describe-task-definition --region us-east-1 --task-definition "$REVISION" \
     --query "taskDefinition.containerDefinitions[?name=='app'].image" --output text
   ```
   Esperado: `648617469176.dkr.ecr.us-east-1.amazonaws.com/campus-locator/embedding:<SHA del commit de EMB-3.1>`. Si
   sigue en `…:f2ddc42a3e4a5c6ea9c4731f334ac37738b99565` (EMB-2.1), P1 termina con código 2: «la imagen desplegada
   (f2ddc42) trae el tools/benchmark.py provisional…».

**Ejecución.** Con la preparación hecha:
```bash
cd SERVICE_EMBEDDING/project
AWS_PROFILE=<perfil> uv run --group ops python src/ops/validate31.py --entorno dev
```
Esperado: código 0 y estas líneas (los números, los de la medida):
```
EMB-3.1 · validation-3-1 · entorno dev
[PASA] P3 AWS_PROFILE de la cuenta del proyecto
[PASA] P2 clúster ACTIVE, familia campus-locator-dev-embedding (última :<n>), log group /campus-locator/dev/embedding
[PASA] P1 EMB-2.1 Hecho; servicio embedding con campus-locator-dev-embedding:<n>, imagen <sha corto> (con benchmark)
[PASA] C1a tarea <id>: campus-locator-dev-embedding:<n>, 2048 CPU / 4096 MB, salida 0; descarga de la imagen <s> s, ejecución <s> s
[PASA] C1b lote 1: p50 … ms, p95 … ms · lote 4: … · lote 5: … · lote 8: …; 2 hilos, 2 vCPU / 4096 MiB (ecs), CPU … (…); memoria del proceso: reposo … MiB, pico … MiB; C3: p95 del lote de 5 = … ms ≤ 800 ms → no aplica; JSON completo en EMB-3.1-benchmark-<id>.json (stream embedding/app/<id>)
[MANUAL] C2 Copia p50 y p95 de los lotes de 1, 5 y 8 …
[MANUAL] C3 Si el p95 del lote de 5 (detalle de C1b) supera 800 ms, …
Resultado: pasa (código 0) · informe: …/.validacion/EMB-3.1-<AAAAMMDD-HHMMSS>.json
```
Si `limites_de` no sale `ecs` (los metadatos de la tarea no respondieron), `vcpu` y `memoria_mb` vienen del cgroup:
no cambia el resultado (C1a ya comprueba 2048 / 4096), pero se anota en el PR. Después: C2 y C3 (§3) y la fila
EMB-3.1 de PLAN §3 a «Hecho» con el commit, la fecha y la versión de ARCHITECTURE.

**Explorar palancas** (opcional, para decidir C3; cada ejecución es otra tarea suelta, < 0,02 USD). Mismo comando con
otro número de hilos, sin tocar la definición de tarea:
```bash
RED=$(aws ecs describe-services --region us-east-1 --cluster campus-locator-dev --services embedding \
  --query 'services[0].networkConfiguration' --output json)
TAREA=$(aws ecs run-task --region us-east-1 --cluster campus-locator-dev --task-definition "$REVISION" \
  --launch-type FARGATE --started-by validacion-emb31 --network-configuration "$RED" \
  --overrides '{"containerOverrides":[{"name":"app","command":["python","tools/benchmark.py","--salida","json","--hilos","1"]}]}' \
  --query 'tasks[0].taskArn' --output text)
aws ecs wait tasks-stopped --region us-east-1 --cluster campus-locator-dev --tasks "$TAREA"
aws logs filter-log-events --region us-east-1 --log-group-name /campus-locator/dev/embedding \
  --log-stream-names "embedding/app/${TAREA##*/}" --filter-pattern BENCHMARK_JSON \
  --query 'events[].message' --output text
```
Esperado: una línea `BENCHMARK_JSON {…"hilos":1,…}`. `aws ecs wait tasks-stopped` espera hasta 10 min. Estas
ejecuciones no cierran C1: lo cierra `validate31.py` con los hilos de la definición de tarea.
