# Outputs de envs/dev (ARCHITECTURE §5.2). Cada uno aparece con el lote que crea su recurso.

output "cuenta_id" {
  description = "Cuenta de AWS de las credenciales con que se evaluó el proveedor."
  value       = data.aws_caller_identity.actual.account_id
}
