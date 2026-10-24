# Validación 2-2 — EMB-2.2 Imagen con GPU

| Campo | Valor |
|---|---|
| Lote | `EMB-2.2` — criterios en [`PLAN.md`](../PLAN.md) §2.2 |
| Script | `project/src/ops/validate22.py` |
| Entornos | `dev` (C1, C2: la GPU solo existe ahí) y `local` (C3). En cada entorno, las comprobaciones del otro quedan `omitida`. **Cierran el lote las dos ejecuciones con código 0**, la de `local` con `EMBEDDING_IMAGEN` = la imagen desplegada que identifica C1a |
| Criterios | Automáticos: C1 (C1a, C1b, C1c), C2 (C2a, C2b), C3 (C3a, C3b) · Manuales: ninguno |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.8. Lo que se valida está en ARCHITECTURE §4.4 y ADR-EMB-10; las tolerancias, en §5.4.

## 1. Precondiciones

Si alguna no se cumple, el script se detiene: código 2 si otro lote no está listo o la imagen no cumple el contrato (el
lote queda `Bloqueado`), código 3 si faltan Docker, credenciales o variables (infra §5.11). En `dev` se evalúa P2
antes que P1, porque P1 necesita las credenciales.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | (`dev`) `INF-1.3` en «Hecho»: clúster, proveedor de capacidad de la GPU, servicio `embedding` y log group `/campus-locator/dev/embedding` | `ecs describe-clusters --clusters campus-locator-dev` → `status = ACTIVE`; `ecs describe-capacity-providers --capacity-providers campus-locator-dev-gpu` → `status = ACTIVE`; `ecs describe-services --cluster campus-locator-dev --services embedding` → sin `failures`; `logs describe-log-groups --log-group-name-prefix /campus-locator/dev/embedding` → un grupo |
| P2 | (`dev`) `AWS_PROFILE` con credenciales de la cuenta `648617469176` | `sts get-caller-identity` → `Account`. Sin variable o con credenciales inválidas: código 3 (§5.11) |
| P3 | `EMB-2.1` en «Hecho»: existen los vectores dorados | Fila EMB-2.1 de `docs/PLAN.md` §3 en `Hecho`; `project/tests/golden/` tiene las cinco imágenes y sus vectores |
| P4 | (`local`) Docker disponible y `EMBEDDING_IMAGEN` de plataforma `linux/amd64` (infra §5.9) | `docker info` con código 0; si la imagen es de ECR, `docker login` con el token de `ecr:GetAuthorizationToken` (necesita `AWS_PROFILE`) y `docker pull`; `docker image inspect --format '{{.Os}}/{{.Architecture}}'` = `linux/amd64` (si no: código 2). Sin variable o con el `pull` fallido: código 3 |

## 2. Comprobaciones automáticas

Las tareas sueltas de `dev` usan la revisión que identifica C1a, la red del servicio y
`--capacity-provider-strategy capacityProvider=campus-locator-dev-gpu,weight=1`, con `--started-by validacion-emb22`.
No encienden el servicio `embedding`: cada tarea reserva su propia GPU y, si no hay una libre, el grupo de autoescalado
lanza una instancia (infra §3.4).

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | (`dev`) Lee `taskDefinition` y `networkConfiguration` de `ecs describe-services --cluster campus-locator-dev --services embedding`, y la imagen y los requisitos del contenedor `app` con `ecs describe-task-definition` | La revisión es de la familia `campus-locator-dev-embedding`, la imagen es `…/campus-locator/embedding:<SHA de 40 caracteres>` (no `:bootstrap`), el contenedor pide una GPU (`resourceRequirements` con `type = GPU`, `value = 1`) y lleva `EMBEDDING_DEVICE = cuda` |
| C1b | (`dev`) `ecs run-task` sin sobrescribir el comando; `ecs describe-tasks` cada 5 s (máx. 20 min) hasta `healthStatus = HEALTHY`; después la detiene con `ecs stop-task` | Instante en que se observa `HEALTHY` − `startedAt` < 180 s (cota superior: el *health check* corre cada 30 s, infra §5.7). Falla si la tarea pasa a `STOPPED` o vence el plazo |
| C1c | (`dev`) Lee el log de la tarea de C1b en `/campus-locator/dev/embedding` (el stream cuyo nombre termina en su ID) | Hay un evento `modelo_listo` con `dispositivo = cuda` y `gpu` no vacío (lo mismo que publica `/v1/info`, que no es accesible desde fuera de la VPC). Un `carga_del_modelo_fallida` hace fallar la comprobación con su traza |
| C2a | (`dev`) `ecs run-task` con `--overrides '{"containerOverrides":[{"name":"app","command":["python","tools/dorados.py","--salida","json"]}]}'`; `ecs describe-tasks` cada 15 s hasta `lastStatus = STOPPED` (máx. 30 min) | `containers[app].exitCode = 0` |
| C2b | (`dev`) Extrae del log de esa tarea la línea `DORADOS_JSON` (formato en ARCHITECTURE §5.9) | `dispositivo = cuda`; el SHA-256 de cada archivo dorado de la imagen coincide con el de `project/tests/golden/` del commit que se valida; `dif_max_dorados` ≤ 1e-4 y `dif_max_lote` ≤ 1e-5. Si solo falla `dif_max_dorados`, el detalle lo dice: antes de indexar nada en GPU hay que decidir una `version_vector` nueva (PLAN, EMB-2.2 C2) |
| C3a | (`local`) `docker run -d --name validacion-emb22-cpu --network none -e EMBEDDING_DEVICE=cpu -e TORCH_NUM_THREADS=1 $EMBEDDING_IMAGEN` (sin `--gpus`); cada 5 s ejecuta con `docker exec` el comando del *health check* de infra §5.7 contra `/health/ready` | Termina con código 0 antes de 180 s desde `docker run` y el contenedor sigue en marcha (`State.Running = true`) |
| C3b | (`local`) `docker exec validacion-emb22-cpu python tools/dorados.py --salida json` | `dispositivo = cpu`, `dif_max_dorados` ≤ 1e-5 y `dif_max_lote` ≤ 1e-5 (mismo dispositivo que los dorados, §5.4) |

Detalles de la implementación:
- C1b y C2a no lanzan tareas si la imagen de C1a no es de CI (fallan con ese motivo).
- C1b mide con la hora del encabezado `Date` de las respuestas de AWS, no con el reloj de la máquina.
- Si en C3 el contenedor se detiene antes de quedar listo, la comprobación falla con las últimas líneas de su log.

## 3. Comprobaciones manuales

Ninguna: todos los criterios son automáticos.

## 4. Datos de prueba y limpieza

El servicio no guarda nada (§5.8): no hay datos de prueba que borrar. El script crea tareas sueltas con
`startedBy = validacion-emb22` y el contenedor `validacion-emb22-cpu`. Al terminar (también si algo falló, salvo
`--sin-limpieza`) detiene las tareas con `ecs stop-task` y borra el contenedor con `docker rm -f`; al empezar hace lo
mismo con los restos de una ejecución anterior
(`ecs list-tasks --cluster campus-locator-dev --started-by validacion-emb22`). Sin tareas, el grupo de autoescalado
devuelve la instancia que haya lanzado (escalado gestionado de infra §3.4); el script no toca el servicio `embedding`
ni el grupo.

## 5. Cómo ejecutarlo

```bash
cd SERVICE_EMBEDDING/project
uv run --group ops python src/ops/validate22.py --entorno dev
EMBEDDING_IMAGEN=<ecr_embedding_url>:<sha> uv run --group ops python src/ops/validate22.py --entorno local
```

El informe queda en `project/.validacion/EMB-2.2-<AAAAMMDD-HHMMSS>.json` (hora UTC) salvo que se indique `--informe`.

Variables: `AWS_PROFILE` en `dev` (y en `local` si la imagen es de ECR); `EMBEDDING_IMAGEN` en `local` (§5.8): para
cerrar el lote, la imagen que identifica C1a. Duración aproximada: `dev` 15–30 min (lanzar una instancia con GPU si no
hay una libre y descargar la imagen de ~6 GB); `local` 5–10 min (la descarga de la imagen, si no está).
