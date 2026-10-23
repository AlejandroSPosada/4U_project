# CHANGELOG — Infraestructura (`INFRASTRUCTURA_TERRAFORM`)

Una entrada por versión de [`ARCHITECTURE.md`](./ARCHITECTURE.md), la más reciente primero.

**Cómo se numera la versión del documento**
- **Mayor** (`1.0.0` → `2.0.0`): cambia un contrato de §5 de forma incompatible (renombrar un output, una variable de
  entorno, una cola…). Mientras la versión sea `0.x`, un cambio incompatible sube la **menor**.
- **Menor** (`0.1.0` → `0.2.0`): contrato nuevo o ampliación compatible, o una decisión nueva (ADR).
- **Parche** (`0.1.0` → `0.1.1`): aclaraciones o correcciones de redacción sin efecto en contratos.

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

## [0.2.0] — 2026-10-23

- **Lote que la motivó:** ninguno; cambio de organización del monorepo pedido por el equipo.
- **Qué cambió:**
  - El código de la carpeta irá en `project/` y la documentación en `docs/`, con una carpeta nueva
    `docs/validation/` (un documento por lote) y un validador por lote en `project/src/ops/validate<fase><n>.py`.
  - Los lotes se renumeran como `<PREFIJO>-<fase>.<n>` para que el nombre de su validación coincida con el lote
    (`validation-2-2.md` ↔ `validate22.py` ↔ lote x-2.2).
  - El PLAN separa las dependencias «para construir» de las «para validar», numera los criterios de cierre (C1, C2…)
    y añade a §3 las columnas «Validación» y «Última validación».
  - Nuevo §5.11: **contrato común de los validadores** de las cuatro carpetas (nombres, ejecución, códigos de salida
    0–3, informe JSON, reglas de datos de prueba), más la imagen de prueba `bootstrap` y la tarea de validación
    `campus-locator-dev-validacion` para comprobar desde dentro de la VPC.
  - La comprobación de `CREATE EXTENSION vector` pasa de INF-1.2 a INF-1.3 (necesita la tarea de validación, que se crea
    con el cómputo); INF-1.2 comprueba en su lugar la versión del motor.
  - La regla de EventBridge de §3.8 solo avisa por tareas de los **servicios** (`group = service:…`): las tareas
    sueltas de `migrate`, `validacion` y de los validadores ya no generan falsas alarmas.
  - Se fija el nombre de los *streams* de log (`<proceso>/app/<id-de-la-tarea>`) para que los validadores encuentren
    el log de una tarea suelta.
  - Tras escribir los documentos de validación: el entorno `dev` de GitHub se crea en INF-0.1 (no en INF-0.2) y solo
    admite la rama `main`, así un PR no puede usar `gha-terraform`; INF-0.1 C3–C5 se reescriben (Budgets no pide
    confirmación de correo; la de SNS pasa a INF-3.1 C1); INF-0.2 añade `data "aws_caller_identity"` y el output
    `cuenta_id`; INF-1.3 C4 solo exige los outputs que ya existen.
  - Se nombran las alarmas, la política y las acciones de escalado, la regla de EventBridge, el entorno de GitHub y los
    workflows (§5.1); se fija el formato de los *access logs* y el umbral de almacenamiento en GiB (§5.10).
  - Las variables de entrada dicen en qué archivo van (`bootstrap` o `envs/dev`); `bootstrap` expone `github_repo`.
  - La imagen de prueba ignora el comando de la tarea (sale con 0 si es `app.cli`); ECS Exec queda activado solo en
    `api`; la tarea `validacion` aparece en la tabla de cómputo.
  - Contrato de validadores: credenciales o variables que faltan dan código 3 (no 2); cada documento puede declarar
    argumentos propios (`--video`); el prefijo `validacion-` se aplica a lo que el validador nombra y los datos reales
    que usa se quedan.
- **Contratos tocados (§5):** §5.1 (familia `campus-locator-dev-validacion`, log group `/campus-locator/dev/validacion`,
  formato de los *streams* de log y nombres de alarmas, escalado, regla de EventBridge, entorno de GitHub y workflows),
  §5.2 (`familias_tarea` incluye `validacion`; `github_repo`, `cuenta_id` y en qué lote aparece cada output), §5.3
  (columna «Dónde»), §5.4 (el secreto `db` también lo usa la tarea de validación; cómo se usa el secreto `jwt`), §5.5
  (prefijo nuevo `evaluacion/`), §5.7 y §5.8 (la tarea de validación usa el grupo `-api` y el rol de `migrate`; el
  *trust policy* de `gha-terraform` queda ligado a la regla de ramas del entorno `dev`), §5.9 (`Dockerfile` en
  `<CARPETA>/project/` y workflows disparados solo por cambios en `project/`), §5.10 (formato de *access logs*, umbral
  en GiB), §5.11 (nuevo).
- **Equivalencia de identificadores** (las entradas anteriores usan los viejos): INF-01 → INF-0.1 · INF-02 → INF-0.2 ·
  INF-03 → INF-1.1 · INF-04 → INF-1.2 · INF-05 → INF-1.3 · INF-06 → INF-1.4 · INF-07 → INF-2.1 · INF-08 → INF-3.1 ·
  INF-09 → INF-6.1.
- **Cómo se verificó:** comprobación automática de que los lotes citados existen, de que las referencias cruzadas entre
  secciones resuelven, de que cada documento de validación cubre una vez cada criterio de su lote y de que las tablas
  están bien formadas.
- **Pendiente:** escribir los validadores (cada lote los entrega con su código).


---

## [0.1.0] — 2026-10-23

- **Lote que la motivó:** ninguno; planificación inicial del sistema en AWS (previa a INF-01).
- **Qué cambió:** primera versión del documento. Sustituye al «plan inicial» al que apuntaba el `README.md` raíz.
  Decisiones tomadas con el equipo: solo AWS, cuenta propia `648617469176`, región `us-east-1`, entorno único `dev`,
  una sola zona de disponibilidad, sin NAT Gateway, presupuesto de 100 USD/mes, ingesta asíncrona y localización
  síncrona, RDS PostgreSQL + pgvector, JWT propio, GitHub Actions con OIDC y estado de Terraform en S3. ADR-INF-01 a
  ADR-INF-11 y riesgos R1–R10.
- **Contratos tocados (§5):** todos nuevos — nombres (§5.1), outputs (§5.2), variables de entrada (§5.3), variables
  de entorno y secretos (§5.4), bucket (§5.5), colas y topic (§5.6), red y DNS interno (§5.7), IAM (§5.8), despliegue
  (§5.9) y parámetros operativos (§5.10). La sección de contratos pasa de §4 (según el `README.md` anterior) a §5, y
  ya no concentra los contratos de todo el monorepo: cada carpeta es dueña de los suyos (§1.3).
- **Cómo se verificó:** revisión cruzada de nombres contra `BACKEND_FASTAPI/docs/ARCHITECTURE.md` v0.1.0 y
  `SERVICE_EMBEDDING/docs/ARCHITECTURE.md` v0.1.0. Precios de lista de `us-east-1` consultados el 2026-10-23 (Fargate,
  RDS `db.t4g.micro`, IPv4 pública). Requisitos comprobados en documentación de AWS: pgvector 0.8.0 en RDS
  PostgreSQL ≥ 17.1; la integración de API Gateway HTTP API con Cloud Map exige registros SRV cuando ECS registra las
  tareas. Sin código: nada se ha aplicado. Antes de publicar esta versión se aplicó una revisión independiente de
  coherencia entre carpetas: ruta propia para
  el *throttling* del login, `s3:ListBucket` sobre el ARN del bucket con condición de prefijo, rol de solo lectura
  `gha-terraform-plan` para los PR, regla de EventBridge en lugar de una alarma que exigía *Container Insights*, se
  quitó `PORT` de las variables inyectadas (ningún servicio la leía) y se corrigió el orden de creación de la
  notificación S3 → SQS.
- **Pendiente:** definir `github_repo` y `correo_alertas`; medir el costo real tras INF-07 y ajustar la tabla de §3.10.
