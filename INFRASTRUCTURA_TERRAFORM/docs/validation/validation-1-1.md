# Validación 1-1 — INF-1.1 Red y grupos de seguridad

| Campo | Valor |
|---|---|
| Lote | `INF-1.1` — criterios en [`PLAN.md`](../PLAN.md) §2.3 |
| Script | `project/src/ops/validate11.py` |
| Entornos | `dev` |
| Criterios | Automáticos: C1, C2, C3, C4 · Manuales: ninguno |

Contrato común de los validadores: `INFRASTRUCTURA_TERRAFORM/docs/ARCHITECTURE.md` §5.11. Lo propio de esta carpeta:
`ARCHITECTURE.md` §5.11.

## 1. Precondiciones

Si alguna no se cumple, el script termina con código 2 y el lote queda `Bloqueado` (P2 es de credenciales: código 3,
según §5.11).

| ID | Qué debe cumplirse | Cómo lo comprueba el script |
|---|---|---|
| P1 | `INF-0.2` en «Hecho»: `envs/dev` con estado remoto | `terraform -chdir=envs/dev init -input=false` termina con 0 y `s3api head-object --bucket campus-locator-tfstate-648617469176 --key dev/terraform.tfstate` responde 200 |
| P2 | Credenciales de la cuenta `648617469176` | `aws sts get-caller-identity` devuelve `Account = 648617469176` |

Los recursos se localizan por su etiqueta `Name` o nombre de grupo (§5.1); este lote no necesita outputs.

## 2. Comprobaciones automáticas

| ID | Qué hace el script | Pasa si |
|---|---|---|
| C1 | `terraform -chdir=envs/dev plan -input=false -detailed-exitcode -lock-timeout=60s` | Código de salida 0 (2 = hay cambios, 1 = error) |
| C2a | `ec2 describe-vpcs --filters Name=tag:Name,Values=campus-locator-dev-vpc`; `ec2 describe-vpc-attribute` con `enableDnsSupport` y `enableDnsHostnames` | Exactamente una VPC, `CidrBlock = 10.20.0.0/16`, ambos atributos en `true` |
| C2b | `ec2 describe-subnets --filters Name=vpc-id,Values=<vpc>` | Exactamente cuatro: `campus-locator-dev-publica-a` `10.20.0.0/24` y `campus-locator-dev-privada-a` `10.20.10.0/24` en `us-east-1a`; `campus-locator-dev-publica-b` `10.20.1.0/24` y `campus-locator-dev-privada-b` `10.20.11.0/24` en `us-east-1b` |
| C2c | `ec2 describe-route-tables`, `ec2 describe-internet-gateways --filters Name=attachment.vpc-id,Values=<vpc>` y `ec2 describe-nat-gateways --filter Name=vpc-id,Values=<vpc>` | La tabla asociada a las dos públicas tiene `0.0.0.0/0` hacia el IGW de la VPC; las tablas de las dos privadas (asociadas o la principal) solo tienen la ruta `local` (ninguna hacia IGW ni NAT); ningún NAT Gateway en estado `pending` o `available` |
| C2d | `ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=<vpc> Name=service-name,Values=com.amazonaws.us-east-1.s3` | Un único endpoint `VpcEndpointType = Gateway`, `State = available`, con `RouteTableIds` = la tabla pública |
| C3 | `ec2 describe-security-groups --filters Name=vpc-id,Values=<vpc> Name=group-name,Values=campus-locator-dev-vpclink,campus-locator-dev-api,campus-locator-dev-worker,campus-locator-dev-embedding,campus-locator-dev-rds` y `ec2 describe-security-group-rules --filters Name=group-id,Values=<ids>`; normaliza cada regla a (grupo, sentido, protocolo, puertos, origen o destino) | Existen los cinco y el conjunto de reglas es exactamente el de §5.7, sin reglas de más: `vpclink` solo salida `8000/tcp` → `api`; `api` entrada `8000/tcp` ← `vpclink` y salida todo → `0.0.0.0/0`; `worker` solo salida todo; `embedding` entrada `8080/tcp` ← `api` y ← `worker`, salida todo; `rds` entrada `5432/tcp` ← `api` y ← `worker`, sin salida |
| C4 | `ec2 describe-security-groups --filters Name=vpc-id,Values=<vpc>` (los cinco y el `default`) y `ec2 describe-security-group-rules` de todos | Ninguna regla con `IsEgress = false` tiene `CidrIpv4 = 0.0.0.0/0` ni `CidrIpv6 = ::/0` |

## 3. Comprobaciones manuales

Ninguna: todos los criterios son automáticos.

## 4. Datos de prueba y limpieza

No crea datos de prueba ni modifica recursos: solo lee la API de EC2 y ejecuta un `plan`, que toma y libera el bloqueo
del estado. Si el script se interrumpe durante el `plan`, envía SIGINT al proceso de `terraform` y espera a que
termine, para que libere el bloqueo. No hay restos que buscar al empezar.

## 5. Cómo ejecutarlo

```bash
cd INFRASTRUCTURA_TERRAFORM/project
uv run --group ops python src/ops/validate11.py --entorno dev
```

Variables: `AWS_PROFILE` con el perfil de la persona (§5.11). La región es `us-east-1` (§5.3). Duración aproximada:
2–3 min.
