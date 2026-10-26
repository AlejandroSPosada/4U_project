# Validación 3-3 — BE-3.3 Alertas

| Campo | Valor |
|---|---|
| Lote | `BE-3.3` — criterios en [`PLAN.md`](../PLAN.md) §2.2 (fuera del núcleo) |
| Script | `project/src/ops/validate33.py` (**no existe todavía**: lo escribe BE-3.3) |
| Entornos | `dev`, `local` (ningún criterio depende de S3 ni SQS) |
| Criterios | Automáticos: C1, C2, C3, C4, C5 · Manuales: ninguno |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.11. Contrato de las alertas: `ARCHITECTURE.md` §5.3 (`GET /v1/alerts`) y §5.5, marcado «sin
implementar (BE-3.3)»; diseño en §4.9 y ADR-BE-10.

Estas comprobaciones estaban en `validation-3-1.md` (C1, C2, C4 y C5 de entonces) y en `validation-2-3.md` (C1c)
hasta ARCHITECTURE 0.11.0, cuando las alertas salieron del núcleo (decisión del usuario, 2026-10-25). Es un borrador:
BE-3.3 lo revisa al construir el validador.

## 1. Precondiciones

Si alguna no se cumple, el script termina con código 2 y el lote queda `Bloqueado`.

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | Solo `dev`: `AWS_PROFILE` de la cuenta `648617469176` (para leer el secreto del admin y el output `api_base_url`) | `aws sts get-caller-identity` → `Account`. Si falla: código 3 (credenciales) |
| P2 | URL de la API | `VALIDACION_API_URL` o, en `dev`, el output `api_base_url` + `/v1`; `GET /v1/health/ready` → `200` con `"db": "ok"` |
| P3 | `BE-1.3` en «Hecho»: login de admin | `POST /v1/auth/login` con `VALIDACION_ADMIN_*` (en `dev`, o el secreto `campus-locator/dev/admin-inicial`) → `200` con `usuario.rol = "admin"` |
| P4 | `BE-2.3` en «Hecho» (solo para C5) | `PLAN.md` §3 marca BE-2.3 «Hecho» (`comun.lote_hecho`); `GET /v1/admin/stats` → `200` |

## 2. Comprobaciones automáticas

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1a | Toma `GET /v1/alerts` sin `desde` como caché inicial y guarda `generado_en`; crea con `PUT /v1/admin/alerts/{uuid}` la alerta `{"lat": 0.001, "lng": 0.001, "mensaje": "validacion-33-<ts> creada", "tipo": "obra", "radio_m": 15}`; pide `GET /v1/alerts?desde=<generado_en>` y la aplica | Caché inicial con `completo = true`; `PUT` `201` con `version = 1`; la diferencia trae `completo = false` y la alerta |
| C1b | `PUT` del mismo id con `mensaje` `validacion-33-<ts> editada`, `radio_m: 20` e `If-Match: 1`; aplica la diferencia siguiente | `200` con `version = 2`; la diferencia trae la versión 2 |
| C1c | `DELETE /v1/admin/alerts/{id}`; aplica la diferencia siguiente | `204`; la diferencia trae el id en `eliminadas` |
| C1d | Aplica cada diferencia como la app (reemplaza por `id`, quita `eliminadas` y descarta `activa = false`; no filtra por vigencia, porque la foto completa incluye vigencias futuras) y compara con un `GET /v1/alerts` final sin `desde` | El mapa `id → version` de la caché es igual al de la foto completa |
| C2 | `DELETE /v1/admin/alerts/{uuid4 nuevo}` | `204` |
| C3 | `PUT` de la alerta `validacion-33-<ts> futura` con `activa: true`, `vigencia_desde` = ahora + 2 días y `vigencia_hasta` = ahora + 3 días; `GET /v1/alerts` sin `desde` | La alerta está en `alertas` con sus dos fechas |
| C4 | Crea con `PUT` la alerta D; `POST /v1/admin/alerts/sincronizar` con `{"cambios": [{"op": "upsert", "alerta": {A válida}}, {"op": "upsert", "alerta": {B con "radio_m": 500}}, {"op": "eliminar", "id": "<D>"}]}`; después `GET /v1/admin/alerts` | `200`; por `id`: A `ok`, B `error` con `codigo = "VALIDACION"`, D `ok`; en el listado está A y no están B ni D |
| C5 | Lee `GET /v1/admin/stats` (s0); `PUT` de una alerta `activa: true` sin vigencia y de otra `activa: false` (mensajes `validacion-33-<ts>-…`); lee otra vez (s1) | `201` en ambas y `s1.alertas_activas − s0.alertas_activas = 1` |

Entre cada cambio y la diferencia que lo recoge espera 1 s (`generado_en` y `desde` tienen resolución de segundos).
Todas las alertas de prueba (A, B, D incluidas) llevan `mensaje` que empieza por `validacion-33-<ts>`. C5 compara
diferencias de un total global: supone que nadie más crea ni borra alertas en `dev` mientras corre.

## 3. Comprobaciones manuales

Ninguna: todos los criterios son automáticos.

## 4. Datos de prueba y limpieza

Crea alertas con `mensaje` `validacion-33-<ts>…` en la coordenada `(0.001, 0.001)`, fuera del campus, para que ninguna
app de `dev` las anuncie.

Limpieza: `DELETE /v1/admin/alerts/{id}` de cada alerta de `GET /v1/admin/alerts` cuyo `mensaje` empiece por
`validacion-`. El mismo barrido se hace al empezar, por si una ejecución anterior dejó restos. Las alertas borradas dejan
su *tombstone* 90 días (`ALERTAS_TOMBSTONE_DIAS`); no tiene contenido y no se puede quitar antes.

## 5. Cómo ejecutarlo

Todavía no hay script: BE-3.3 está «Pendiente» y fuera del núcleo (PLAN §3). Cuando exista, se lanzará como los demás
(`uv run --group ops python src/ops/validate33.py --entorno dev|local`, desde `BACKEND_FASTAPI/project`) y este
apartado tendrá, como `validation-3-1.md` §5, las Variables, la Preparación numerada con salidas esperadas y la
Ejecución con su salida esperada. Variables previstas: `AWS_PROFILE` (obligatoria en `dev`), `VALIDACION_API_URL`,
`VALIDACION_ADMIN_CORREO` y `VALIDACION_ADMIN_PASSWORD` (opcionales en `dev`, obligatorias en `local`); ver
`ARCHITECTURE.md` §5.11.
