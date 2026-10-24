# Variables de entrada de envs/dev (ARCHITECTURE §5.3). Cada una aparece con el lote que la usa; los valores están
# en terraform.tfvars.

variable "aws_account_id" {
  description = "Única cuenta de AWS en la que puede operar el proveedor (allowed_account_ids)."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id debe ser un ID de cuenta de AWS de 12 dígitos."
  }
}

variable "region" {
  description = "Región de AWS del entorno."
  type        = string
}

variable "proyecto" {
  description = "Nombre del proyecto: primera parte del prefijo de §5.1 y valor de la etiqueta Proyecto."
  type        = string
}

variable "entorno" {
  description = "Nombre del entorno: segunda parte del prefijo de §5.1 y valor de la etiqueta Entorno."
  type        = string
}
