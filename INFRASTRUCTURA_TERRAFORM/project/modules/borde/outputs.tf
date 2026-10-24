output "api_base_url" {
  description = "URL base de la HTTP API, sin barra final (https://<id>.execute-api.<region>.amazonaws.com, 5.2)."
  value       = aws_apigatewayv2_api.principal.api_endpoint
}
