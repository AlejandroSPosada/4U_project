#!/usr/bin/env bash
# Corre 'alembic upgrade head' DENTRO de la VPC como tarea ECS de una sola vez, reutilizando la definición de
# tarea, las subredes y el SG del servicio backend (la BD no es accesible desde fuera).
# ⚠ Sin probar contra AWS. Requiere: imagen del backend ya en ECR, credenciales de AWS CLI activas.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
CLUSTER="${CLUSTER:-campus-locator-dev-cluster}"

SERVICE=$(aws ecs list-services --region "$REGION" --cluster "$CLUSTER" \
  --query "serviceArns[?contains(@, 'backend')] | [0]" --output text)
[ "$SERVICE" != "None" ] || { echo "No encontré el servicio backend en $CLUSTER"; exit 1; }

DESC() { aws ecs describe-services --region "$REGION" --cluster "$CLUSTER" --services "$SERVICE" --query "$1" --output text; }
SUBNETS=$(DESC "services[0].networkConfiguration.awsvpcConfiguration.subnets" | tr '\t' ',')
SGS=$(DESC "services[0].networkConfiguration.awsvpcConfiguration.securityGroups" | tr '\t' ',')
TASKDEF=$(DESC "services[0].taskDefinition")
CONTAINER=$(aws ecs describe-task-definition --region "$REGION" --task-definition "$TASKDEF" \
  --query "taskDefinition.containerDefinitions[0].name" --output text)

echo "Lanzando migración (tarea: $TASKDEF, contenedor: $CONTAINER)..."
TASK=$(aws ecs run-task --region "$REGION" --cluster "$CLUSTER" --launch-type FARGATE \
  --task-definition "$TASKDEF" \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SGS],assignPublicIp=ENABLED}" \
  --overrides "{\"containerOverrides\":[{\"name\":\"$CONTAINER\",\"command\":[\"alembic\",\"upgrade\",\"head\"]}]}" \
  --query "tasks[0].taskArn" --output text)

aws ecs wait tasks-stopped --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK"
CODE=$(aws ecs describe-tasks --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK" \
  --query "tasks[0].containers[0].exitCode" --output text)

if [ "$CODE" = "0" ]; then
  echo "Migración OK."
else
  echo "Migración FALLÓ (exitCode=$CODE). Ver logs en CloudWatch: grupo /ecs/campus-locator-dev-backend"
  exit 1
fi
