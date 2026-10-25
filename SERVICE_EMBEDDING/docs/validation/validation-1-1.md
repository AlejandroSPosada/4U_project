# Validación 1-1 — EMB-1.1 Servicio base e imagen

| Campo | Valor |
|---|---|
| Lote | `EMB-1.1` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate11.py` |
| Entornos | `dev` (C1) y `local` (C2, C3). **Cierran el lote las dos ejecuciones con código 0**, la de `local` con `EMBEDDING_IMAGEN` = la imagen desplegada que identifica C1a |
| Criterios | Automáticos: C1 (C1a, C1b), C2, C3 · Manuales: ninguno |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.8. El diseño que se valida está en ARCHITECTURE §4.2 (imagen y arranque), §5.3 (modelo y
revisión) y §5.5 (imagen de contenedor), y en ADR-EMB-05 (pesos dentro de la imagen, sin red en ejecución), ADR-EMB-09
(modelo preparado en segundo plano) y ADR-EMB-11 (`facebook/dinov2-small` en 2 vCPU).

Cada entorno cubre lo que solo se ve en él: el arranque real en Fargate, en `dev`; el arranque sin red, que solo se
puede forzar en `local`. En cada uno, las comprobaciones del otro quedan `omitida`.

## 1. Precondiciones

El script evalúa primero las de credenciales y uso (código 3, según infra §5.11) y luego las de otros lotes o del
contrato de la imagen (código 2: el lote queda `Bloqueado`); si una falla, no sigue. En `dev`, P2 y después P1. En
`local`, P3 (código 3 si falta Docker o el puerto 8080 está ocupado) y después P4 (código 3 sin la variable o con el
`pull` fallido; 2 si la imagen no es `linux/amd64`).

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | (`dev`) `INF-1.3` en «Hecho»: clúster, servicio `embedding` con una revisión de `campus-locator-dev-embedding` y log group `/campus-locator/dev/embedding` | `ecs describe-clusters --clusters campus-locator-dev` → `status = ACTIVE`; `ecs describe-services --cluster campus-locator-dev --services embedding` → sin `failures`; `logs describe-log-groups --log-group-name-prefix /campus-locator/dev/embedding` → un grupo |
| P2 | (`dev`) Credenciales de la cuenta `648617469176` | `sts get-caller-identity` devuelve `Account = 648617469176`. Sin `AWS_PROFILE` o con credenciales inválidas: código 3 (infra §5.11) |
| P3 | (`local`) Docker disponible y puerto 8080 libre | `docker info` con código 0; borra los contenedores de una ejecución anterior (§4) y después una conexión a `localhost:8080` es rechazada |
| P4 | (`local`) `EMBEDDING_IMAGEN` definida y de plataforma `linux/amd64` (infra §5.9) | Si es de ECR, `docker login` con el token de `ecr:GetAuthorizationToken` (necesita `AWS_PROFILE`) y `docker pull`; si es local, `docker pull` solo si no existe. Después `docker image inspect --format '{{.Os}}/{{.Architecture}}'` = `linux/amd64` |

## 2. Comprobaciones automáticas

Orden: C1a y C1b en `dev`; C2 y C3 en `local`. Los nombres del contrato (clúster, servicio, familia, contenedor,
puerto, `version_vector`) y el comando del *health check* de infra §5.7 los toma de `src/ops/comun.py`, que también lee
el SHA anotado en §5.3 (§5.8). `--solo C1` incluye C1a y C1b.

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | (`dev`) Lee `taskDefinition` y `networkConfiguration` de `ecs describe-services --cluster campus-locator-dev --services embedding`, y la imagen del contenedor `app` con `ecs describe-task-definition`. No enciende el servicio: le basta su configuración, también con `desiredCount = 0` | La revisión es de la familia `campus-locator-dev-embedding` y la imagen es `…/campus-locator/embedding:<SHA de 40 caracteres>` (la que publica `embedding.yml`), no `:bootstrap`: la imagen de prueba de infra §5.11 también responde `/health/ready` |
| C1b | (`dev`) Si la imagen de C1a no es de CI, falla sin lanzar nada (medir la imagen `bootstrap` no cierra C1). Si lo es: `ecs run-task --cluster campus-locator-dev --task-definition <revisión de C1a> --launch-type FARGATE --started-by validacion-emb11 --network-configuration <la de C1a>`, sin sobrescribir el comando; `ecs describe-tasks` cada 5 s (máx. 10 min) hasta `healthStatus = HEALTHY`. Mide con la hora del encabezado `Date` de las respuestas de AWS, no con el reloj de la máquina | Instante en que se observa `HEALTHY` − `startedAt` < 180 s. Es una cota superior: el *health check* corre cada 30 s (infra §5.7). Falla si la tarea pasa a `STOPPED` o vence el plazo |
| C2 | (`local`) `docker run -d --name validacion-emb11 -p 8080:8080 -e TORCH_NUM_THREADS=1 $EMBEDDING_IMAGEN`; espera `GET http://localhost:8080/health/ready` = 200 (máx. 180 s) y llama a `GET /v1/info`; al terminar borra el contenedor, para liberar memoria y el puerto antes de C3 | `version_vector = dinov2-vits14/pp-v1`, `modelo = facebook/dinov2-small` y `revision` igual al SHA de la fila «Revisión» de ARCHITECTURE §5.3 (falla si allí no está anotado). Si el contenedor se detiene antes de quedar listo, falla con las últimas líneas de su log |
| C3 | (`local`) `docker run -d --name validacion-emb11-sinred --network none -e TORCH_NUM_THREADS=1 $EMBEDDING_IMAGEN`; como `--network none` no publica puertos, cada 5 s ejecuta con `docker exec` el comando del *health check* de infra §5.7 contra `/health/ready` | El comando termina con código 0 (200 `{"estado": "listo"}`) antes de 180 s desde `docker run` y el contenedor sigue en marcha (`docker inspect` → `State.Running = true`). Si se detiene antes, falla con las últimas líneas de su log |

## 3. Comprobaciones manuales

Ninguna: todos los criterios son automáticos.

## 4. Datos de prueba y limpieza

El servicio no guarda nada (§5.8): no hay datos de prueba que borrar. El script crea una tarea suelta con
`startedBy = validacion-emb11` (`dev`) y los contenedores `validacion-emb11` y `validacion-emb11-sinred` (`local`). Al
terminar, también si algo falló (salvo `--sin-limpieza`), detiene la tarea con `ecs stop-task` y borra los contenedores
con `docker rm -f`; al empezar hace lo mismo con los restos de una ejecución anterior: las tareas de
`ecs list-tasks --cluster campus-locator-dev --started-by validacion-emb11` y los contenedores con esos nombres. Nunca
toca el servicio `embedding` (ni su `desiredCount` ni su revisión): la tarea suelta no lo necesita (infra §5.11), así
que da igual que esté encendido o apagado y no le afectan el apagado por inactividad ni el de las 22:00. La tarea suelta
no se registra en Cloud Map (`api` y `worker` no le envían tráfico), escribe su log en `/campus-locator/dev/embedding`
(stream `embedding/app/<id-de-la-tarea>`, 14 días) y, como su `group` es `family:campus-locator-dev-embedding` y no
`service:embedding`, detenerla no dispara la regla de EventBridge de INF-3.1 (infra §3.8). Con 2 vCPU / 4 GB corre unos
3–5 min por ejecución (< 0,02 USD, tarifas de infra §3.10).

## 5. Cómo ejecutarlo

```bash
cd SERVICE_EMBEDDING/project
uv run --group ops python src/ops/validate11.py --entorno dev
EMBEDDING_IMAGEN=<ecr_embedding_url>:<sha> uv run --group ops python src/ops/validate11.py --entorno local
```

Variables: `AWS_PROFILE` con el perfil de la persona (infra §5.11) en `dev`, y en `local` si la imagen es de ECR. En
`dev` necesita `ecs:DescribeClusters`, `DescribeServices`, `DescribeTaskDefinition`, `RunTask`, `DescribeTasks`,
`ListTasks` y `StopTask` sobre `campus-locator-dev`; `iam:PassRole` sobre los roles de la definición de tarea
(`campus-locator-dev-ecs-ejecucion` y `campus-locator-dev-tarea-embedding`, infra §5.8), y `logs:DescribeLogGroups`. En
`local` con imagen de ECR, `ecr:GetAuthorizationToken`, `BatchGetImage` y `GetDownloadUrlForLayer` sobre
`campus-locator/embedding`. `EMBEDDING_IMAGEN` en `local` (§5.8): para cerrar el lote, la imagen que identifica C1a
(paso 3 de la preparación); en PowerShell se define antes, `$env:EMBEDDING_IMAGEN = "<ecr_embedding_url>:<sha>"`. La
región es `us-east-1` (infra §5.3). Se puede ejecutar a cualquier hora y con `embedding` encendido o apagado (§4). En la
máquina: `uv`, `git` (commit del informe) y, en `local`, Docker. Primero `dev` y después `local`. Duración aproximada:
`dev` 6–10 min (aprovisionar la tarea, descargar ~1,8 GB, cargar y calentar el modelo); `local` 4–6 min. El informe
queda en `project/.validacion/EMB-1.1-<AAAAMMDD-HHMMSS>.json` (hora UTC) salvo que se indique `--informe`.

**Preparación** (una sola vez, antes de la primera ejecución en `dev`). Mientras el servicio tenga la imagen
`bootstrap` de INF-1.3, C1a falla y C1b no lanza la tarea.

1. Generar `project/uv.lock` y pasar las pruebas con PyTorch (el `Dockerfile` y `embedding.yml` usan
   `uv sync --locked`: sin el lock el build falla, §5.5):
   ```bash
   cd SERVICE_EMBEDDING/project
   uv lock
   uv sync
   uv run ruff check . && uv run ruff format --check . && uv run pytest
   ```
   Esperado: `uv.lock` creado y `pytest` en verde, incluidas las pruebas de `test_modelo.py`, que necesitan PyTorch, y
   las de coherencia de este documento con `validate11.py`.
2. Llevar a `main` el `uv.lock` (y lo que falte de `project/`), por PR o *push*. En `main`, `embedding.yml` publica
   `…/campus-locator/embedding:<sha>`, registra una revisión nueva de `campus-locator-dev-embedding` y hace
   `update-service`; con el servicio en 0 réplicas no espera (§4.2). Usa las variables del repositorio de infra §5.9
   (`ECR_EMBEDDING` y `ECS_CLUSTER` existen desde INF-1.3). Si `main` ya tiene el código y no hay cambios en
   `project/`, se lanza a mano con `gh workflow run embedding.yml --ref main`.
   ```bash
   gh run list --workflow embedding.yml --branch main --limit 1
   ```
   Esperado: la última ejecución `completed` / `success`, del commit que se valida.
3. Leer la imagen desplegada (la misma que identifica C1a), que es la `EMBEDDING_IMAGEN` de `local`:
   ```bash
   REVISION=$(aws ecs describe-services --region us-east-1 --cluster campus-locator-dev --services embedding \
     --query 'services[0].taskDefinition' --output text)
   aws ecs describe-task-definition --region us-east-1 --task-definition "$REVISION" \
     --query "taskDefinition.containerDefinitions[?name=='app'].image" --output text
   ```
   Esperado: `648617469176.dkr.ecr.us-east-1.amazonaws.com/campus-locator/embedding:<SHA de 40 caracteres>`.

Para probar en `local` antes de que haya imagen en ECR (no cierra el lote), se construye desde `project/` con
`docker build --platform linux/amd64 --build-arg GIT_COMMIT=$(git rev-parse HEAD) -t campus-locator/embedding:local .`
y se usa `EMBEDDING_IMAGEN=campus-locator/embedding:local`.

Esperado al ejecutar: código 0 en las dos ejecuciones, con `[PASA]` en C1a y C1b (`dev`) y en C2 y C3 (`local`); las
del otro entorno, `omitida`. Con las dos, la fila EMB-1.1 de PLAN §3 pasa a «Hecho» con el commit y la fecha.
