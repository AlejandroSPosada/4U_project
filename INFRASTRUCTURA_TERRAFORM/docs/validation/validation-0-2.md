# Validación 0-2 — INF-0.2 Esqueleto de `envs/dev` y CI de Terraform

| Campo | Valor |
|---|---|
| Lote | `INF-0.2` — criterios en [`PLAN.md`](../PLAN.md) §2.3 |
| Script | `project/src/ops/validate02.py` |
| Entornos | `dev` |
| Criterios | Automáticos: C1, C2, C3, C4 · Manuales: ninguno |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.11.

## 1. Precondiciones

Si alguna no se cumple, el script termina con código 2 y el lote queda `Bloqueado` (P3 a P5 son credenciales o
herramientas: código 3, según §5.11).

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | `INF-0.1` en «Hecho»: bucket de estado y roles de GitHub | `terraform -chdir=bootstrap output -json` contiene `bucket_estado`, `rol_gha_terraform_plan_arn`, `rol_gha_terraform_arn` y `rol_gha_deploy_arn`; `iam get-role` responde para `campus-locator-gha-terraform-plan` y `campus-locator-gha-terraform` |
| P2 | `INF-0.1` en «Hecho»: variables del repositorio que usa `infra.yml` | `gh variable list --json name,value` contiene `AWS_REGION`, `AWS_ROL_TERRAFORM_PLAN_ARN` y `AWS_ROL_TERRAFORM_ARN` con los valores de P1 |
| P3 | Credenciales de la cuenta `648617469176` | `aws sts get-caller-identity` devuelve `Account = 648617469176` |
| P4 | `gh` autenticado sobre el repositorio | `gh auth status` termina con 0 con *scopes* `repo` y `workflow`; `gh repo view --json nameWithOwner` da el `<github_repo>` |
| P5 | Terraform con bloqueo nativo en S3 | `terraform version -json` devuelve `terraform_version` ≥ 1.10 |

## 2. Comprobaciones automáticas

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1 | Crea por la API de GitHub (sin tocar la copia local) la rama `validacion-0-2-<AAAAMMDD-HHMMSS>` desde `main` con un único cambio: el comentario `# validacion-0-2 <AAAAMMDD-HHMMSS>` al final de `INFRASTRUCTURA_TERRAFORM/project/envs/dev/main.tf` (sustituye el de una ejecución anterior si existe). Abre el PR, espera la ejecución de `infra.yml` (`gh run list --workflow infra.yml --branch <rama>`, `gh run watch`) y lee `gh pr view <n> --json comments` | La ejecución termina `success` (incluidos `fmt -check`, `validate` y `tflint`) y el PR tiene un comentario de `github-actions[bot]` con la salida del `plan`, que contiene `No changes.` |
| C2a | Fusiona el PR con `gh pr merge <n> --squash --delete-branch` (si la protección de `main` lo impide, espera hasta 15 min a que la persona lo fusione). Busca la ejecución de `infra.yml` en `main` cuyo `headSha` es el commit fusionado y consulta `gh api repos/<github_repo>/actions/runs/<id>/pending_deployments` | El job de `apply` está en `waiting`, con el entorno `dev` pendiente de aprobación y sin pasos ejecutados |
| C2b | Aprueba con `gh api -X POST …/pending_deployments` (`state=approved`, comentario `validacion-0-2`), espera con `gh run watch` y lee el log del job con `gh run view --log --job <id>` | El job termina `success` y su log contiene `Apply complete! Resources: 0 added, 0 changed, 0 destroyed` |
| C3a | Guarda `lineage` y `serial` de `terraform -chdir=envs/dev state pull`; lanza a la vez dos `terraform -chdir=envs/dev plan -input=false -lock-timeout=120s` | Los dos terminan con 0 y `state pull` devuelve después el mismo `lineage` y `serial` |
| C3b | Abre `terraform -chdir=envs/dev console`, que retiene el bloqueo mientras sigue abierta, y comprueba con `s3api head-object` que existe `dev/terraform.tfstate.tflock` en el bucket de estado. Lanza `plan -input=false -lock-timeout=0s` y, en paralelo, `plan -input=false -lock-timeout=120s`; a los 20 s cierra la consola (`exit`) | El primer `plan` falla con `Error acquiring the state lock`; el segundo sigue esperando a los 20 s y termina con 0 tras cerrar la consola; al final ya no existe el `.tflock` |
| C4a | `terraform -chdir=envs/dev plan -input=false -lock=false -var aws_account_id=000000000000`: el proveedor recibe un `allowed_account_ids` que no incluye la cuenta de las credenciales | El `plan` termina con error y el mensaje contiene `not allowed` y `648617469176` |
| C4b | Lee `envs/dev/providers.tf` (o el archivo que declare `provider "aws"`) y `terraform -chdir=envs/dev output -json`; además, `terraform -chdir=envs/dev show -json` | El proveedor declara `default_tags` con `Proyecto = campus-locator`, `Entorno = dev`, `GestionadoPor = terraform` y `Carpeta = INFRASTRUCTURA_TERRAFORM`; existe el output `cuenta_id` = `648617469176`; si ya hay recursos gestionados, todos los que tienen `tags_all` llevan esas cuatro etiquetas |

## 3. Comprobaciones manuales

Ninguna: todos los criterios son automáticos.

## 4. Datos de prueba y limpieza

El script crea la rama `validacion-0-2-<AAAAMMDD-HHMMSS>`, su PR (título `validacion-0-2 <AAAAMMDD-HHMMSS>`) y el
comentario `# validacion-0-2 …` en `envs/dev/main.tf`. La rama se borra al fusionar (`--delete-branch`). Si algo falla
antes de fusionar, cierra el PR y borra la rama (`gh pr close <n> --delete-branch`) y cancela las ejecuciones
pendientes (`gh run cancel <id>`). El comentario fusionado queda en `main` porque C2 exige fusionar; nunca hay más de
uno, porque cada ejecución sustituye el anterior. En la limpieza termina los procesos de `terraform` que sigan
abiertos; si queda un `dev/terraform.tfstate.tflock` cuyo `ID` es el que obtuvo esta ejecución, lo libera con
`terraform -chdir=envs/dev force-unlock -force <ID>` (nunca un bloqueo ajeno). Al empezar cierra los PR y borra las
ramas `validacion-0-2-*` de ejecuciones anteriores.

## 5. Cómo ejecutarlo

```bash
cd INFRASTRUCTURA_TERRAFORM/project
uv run --group ops python src/ops/validate02.py --entorno dev
```

Variables: `AWS_PROFILE` con el perfil de la persona (§5.11); sesión de `gh` (P4); `terraform -chdir=envs/dev init`
hecho en la copia local. La región es `us-east-1` (§5.3). Duración aproximada: 10–15 min.
