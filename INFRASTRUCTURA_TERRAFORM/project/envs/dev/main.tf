# Composición del entorno dev (ARCHITECTURE §4). Aquí solo se componen módulos: ningún módulo llama a otro y las
# dependencias entre ellos pasan por variables y outputs. Cada módulo lo llena el lote indicado (PLAN §2.3).

# Cuenta de las credenciales (output cuenta_id, §5.2). Obliga a configurar el proveedor, y con él a comprobar
# allowed_account_ids, aunque todavía no haya recursos.
data "aws_caller_identity" "actual" {}

# Etiquetas que el proveedor añade a todo recurso (default_tags, §5.1). Nada lo referencia: está para que sus valores
# queden en el estado, donde los comprueba el validador de INF-0.2 (C4b).
# tflint-ignore: terraform_unused_declarations
data "aws_default_tags" "actuales" {}

locals {
  # Prefijo de nombres de §5.1 (campus-locator-dev).
  prefijo = "${var.proyecto}-${var.entorno}"
}

module "red" {
  source = "../../modules/red"

  prefijo       = local.prefijo
  region        = var.region
  cidr_vpc      = var.cidr_vpc
  az_computo    = var.az_computo
  az_secundaria = var.az_secundaria
}

module "datos" {
  source = "../../modules/datos"

  prefijo           = local.prefijo
  cuenta_id         = var.aws_account_id
  az_computo        = var.az_computo
  subredes_privadas = module.red.subredes_privadas
  sg_rds            = module.red.grupos_seguridad["rds"]
  rds_clase         = var.rds_clase
  rds_gb            = var.rds_gb
  rds_gb_max        = var.rds_gb_max
  pg_version        = var.pg_version
  db_password       = module.secretos.db_password
}

module "secretos" {
  source = "../../modules/secretos"

  ruta                 = "${var.proyecto}/${var.entorno}"
  db_host              = module.datos.rds_direccion
  db_puerto            = module.datos.rds_puerto
  db_nombre            = module.datos.rds_base
  db_usuario           = module.datos.rds_usuario
  admin_inicial_correo = "admin@campus.edu.co"
}

module "computo" { # INF-1.3
  source = "../../modules/computo"
}

module "borde" { # INF-1.4
  source = "../../modules/borde"
}

module "observabilidad" { # INF-3.1
  source = "../../modules/observabilidad"
}

# validacion-0-2 20261024-140400
