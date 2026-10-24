# Validación 2-1 — INF-2.1 Encendido de la GPU y escalado del `worker`

| Campo | Valor |
|---|---|
| Lote | `INF-2.1` — criterios en [`PLAN.md`](../PLAN.md) §2.3 |
| Script | `project/src/ops/validate21.py` |
| Entornos | `dev` |
| Criterios | Automáticos: C1, C2, C3, C4 · Manuales: ninguno |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.11. El diseño que se valida está en ARCHITECTURE §3.4 y ADR-INF-13 (GPU apagada por defecto,
encendido manual y apagado automático).

## 1. Precondiciones

El script evalúa primero P4 y P5 (credenciales y uso: código 3, según §5.11) y luego P1–P3 (código 2: el lote queda
`Bloqueado`); si una falla, no sigue.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | `INF-1.3` en «Hecho»: servicios `worker` y `embedding` y la capacidad GPU | `ecs describe-services --cluster campus-locator-dev --services worker embedding` devuelve los dos con `status = ACTIVE`; `autoscaling describe-auto-scaling-groups --auto-scaling-group-names campus-locator-dev-embedding-gpu` devuelve uno |
| P2 | `INF-1.4` en «Hecho»: *access logs* de la API (de ellos sale la métrica de uso de `/v1/localize`) | `logs describe-log-groups --log-group-name-prefix /campus-locator/dev/apigw` devuelve el grupo y el output `api_base_url` existe |
| P3 | Outputs que usa el script | `terraform -chdir=envs/dev output -json` contiene `ecs_cluster`, `ecs_servicios`, `sqs_ingesta_url` y `sqs_purga_url` |
| P4 | Credenciales de la cuenta `648617469176` | `aws sts get-caller-identity` devuelve `Account = 648617469176` |
| P5 | Lejos del apagado nocturno y con la GPU libre: la ejecución dura ~2 h | La hora en `America/Bogota` (`zoneinfo`) está entre 06:00 y 19:30, y `embedding` empieza en `desiredCount = 0` (si está en 1, alguien está probando: código 3 con ese detalle) |

## 2. Comprobaciones automáticas

Orden: C2a, C1a, C1b, C3, C2b, C4. El script usa las mismas funciones que `src/ops/gpu.py` para encender y apagar.

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C2a | `logs describe-metric-filters --log-group-name /campus-locator/dev/apigw`; `cloudwatch describe-alarms --alarm-names campus-locator-dev-embedding-inactivo`; `application-autoscaling describe-scalable-targets`, `describe-scaling-policies` y `describe-scheduled-actions` de `service/campus-locator-dev/embedding` | Existe el filtro `campus-locator-dev-localize`, que cuenta las peticiones `POST /v1/localize` en `LocalizePeticiones` (`campus-locator/dev`); la alarma combina esa métrica y la profundidad de `ingesta` y `purga` (visibles y en vuelo) durante `apagado_gpu.inactividad_min` (45 min) y su acción es la política `campus-locator-dev-embedding-apagar` (capacidad exacta 0); existe `campus-locator-dev-embedding-apagar-noche` con `Timezone = America/Bogota` y `cron(0 22 * * ? *)` |
| C1a | Encendido (`gpu.py encender`); sondea `ecs describe-services --services embedding` y `servicediscovery discover-instances --namespace-name campus-locator.local --service-name embedding` cada 30 s (máx. 15 min) | `runningCount = 1`, despliegue `COMPLETED` y una instancia sana en Cloud Map en ≤ 15 min desde el encendido; el detalle incluye el tiempo |
| C1b | Apagado (`gpu.py apagar`); sondea el servicio y `autoscaling describe-auto-scaling-groups` cada 30 s (máx. 25 min) | `desiredCount = 0`, `runningCount = 0` y el grupo de autoescalado sin instancias `InService` ni `Pending` |
| C3 | Vuelve a encender (como C1a). Con `worker` en `desiredCount = 0`, envía con `sqs send-message` 3 mensajes a `ingesta` con la forma de `s3:TestEvent` (el `worker` los borra sin hacer nada, `BACKEND_FASTAPI/docs/ARCHITECTURE.md` §5.8) y `RequestId = validacion-2-1-<AAAAMMDD-HHMMSS>-<n>`; sondea `worker` cada 30 s (máx. 20 min); anota cuándo las colas llegan a 0 y sigue sondeando (máx. 35 min) | `desiredCount` de `worker` pasa a 1 y vuelve a 0 entre 12 y 30 min después de vaciarse las colas. Se mira `desiredCount`, no `runningCount`: con la imagen `bootstrap` la tarea de `worker` puede detenerse al arrancar. Si hay mensajes ajenos en las colas, falla con ese detalle |
| C2b | Deja `embedding` encendido (de C3), sin peticiones a `/v1/localize` ni mensajes en las colas; sondea la alarma, el servicio y `application-autoscaling describe-scaling-activities` cada minuto (máx. 70 min desde que las colas quedaron vacías) | La alarma pasa a `ALARM` y `embedding` queda en `desiredCount = 0` por la política (actividad `Successful` cuya `Cause` la cita) entre 45 y 60 min después de vaciarse las colas |
| C4 | Con `embedding` ya apagado por C2b, envía 3 mensajes como en C3; espera a que la alarma de subida de `worker` vea los mensajes (máx. 15 min) y observa 5 min más; después borra sus mensajes | `desiredCount` de `worker` sigue en 0 todo el intervalo y `describe-scaling-activities` de `worker` no registra ninguna subida en él |

## 3. Comprobaciones manuales

Ninguna: todos los criterios son automáticos.

## 4. Datos de prueba y limpieza

Crea mensajes en `ingesta` con la forma de `s3:TestEvent` y `RequestId` que empieza por `validacion-2-1-`. Los consume
y borra (`sqs receive-message` + `delete-message`) al terminar cada comprobación; los ajenos vuelven a la cola sin
tocarse (`change-message-visibility --visibility-timeout 0`). Si el `worker` real los recibe antes, los borra él. En la
limpieza, siempre: borra los mensajes `validacion-2-1-` que queden y deja `embedding` apagado (`gpu.py apagar`), que
es como lo exige P5 al empezar. Nunca cambia `desiredCount` de `worker` a mano. Al empezar borra mensajes
`validacion-2-1-` de ejecuciones anteriores. La GPU queda encendida en total ~1,5 h por ejecución (~0,8 USD). Si
INF-3.1 ya está aplicado y `worker` usa la imagen `bootstrap`, las paradas de C3 pueden enviar avisos de la regla de
EventBridge.

## 5. Cómo ejecutarlo

```bash
cd INFRASTRUCTURA_TERRAFORM/project
uv run --group ops python src/ops/validate21.py --entorno dev
```

Variables: `AWS_PROFILE` con el perfil de la persona (§5.11), con permiso para `sqs:SendMessage` en `ingesta`,
`ecs:UpdateService` y `application-autoscaling:RegisterScalableTarget` (lo mismo que usa `gpu.py`). La región es
`us-east-1` (§5.3). Debe empezar entre 06:00 y 19:30 hora de Bogotá y con la GPU apagada (P5). Duración aproximada:
2–2,5 h (casi todo es esperar el apagado por inactividad de C2b).
