# El bloque backend no admite variables: reemplazar el bucket por el que imprime
# `terraform output state_bucket` en bootstrap/ antes de ejecutar `terraform init`.
terraform {
  backend "s3" {
    bucket       = "campus-locator-tfstate-CAMBIAR"
    key          = "envs/dev/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
