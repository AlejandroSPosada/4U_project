#!/usr/bin/env bash
# ============================================================
# deploy.sh — Build, push to ECR, register task def, run task
# ============================================================
# Usage:
#   export ACCOUNT_ID=123456789012
#   export CLUSTER=your-ecs-cluster-name
#   export SUBNET_ID=subnet-xxxxxxxx          # PUBLIC subnet (Fargate needs internet to reach public RDS)
#   export SECURITY_GROUP_ID=sg-xxxxxxxx      # must allow outbound TCP/5432 to 0.0.0.0/0
#   export S3_BUCKET=your-export-bucket-name
#   ./ecs/deploy.sh
# ============================================================

set -euo pipefail

REGION="us-east-2"
REPO_NAME="locations-export"
IMAGE_TAG="latest"
TASK_FAMILY="locations-info-export"

# ---- Validate required env vars ----
: "${ACCOUNT_ID:?Set ACCOUNT_ID}"
: "${CLUSTER:?Set CLUSTER}"
: "${SUBNET_ID:?Set SUBNET_ID}"
: "${SECURITY_GROUP_ID:?Set SECURITY_GROUP_ID}"
: "${S3_BUCKET:?Set S3_BUCKET}"

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO_NAME}"

echo "=== 1. Authenticate Docker to ECR ==="
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ECR_URI}"

echo "=== 2. Create ECR repo if it doesn't exist ==="
aws ecr describe-repositories --repository-names "${REPO_NAME}" \
  --region "${REGION}" 2>/dev/null \
  || aws ecr create-repository --repository-name "${REPO_NAME}" \
       --region "${REGION}"

echo "=== 3. Build Docker image ==="
docker build -t "${REPO_NAME}:${IMAGE_TAG}" \
  "$(dirname "$0")/.."

echo "=== 4. Tag and push ==="
docker tag "${REPO_NAME}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"

echo "=== 5. Patch and register task definition ==="
# Write to a real file in the current directory instead of piping through
# /dev/stdin — /dev/stdin isn't reliably usable with `file://` under
# Git Bash / MINGW64 on Windows.
TMP_TASK_DEF="task_definition.patched.json"

sed \
  -e "s/ACCOUNT_ID/${ACCOUNT_ID}/g" \
  -e "s/YOUR_EXPORT_BUCKET_NAME/${S3_BUCKET}/g" \
  "$(dirname "$0")/task_definition.json" > "${TMP_TASK_DEF}"

# MSYS2_ARG_CONV_EXCL prevents Git Bash from mangling the file:// path
# into a Windows-style path (harmless no-op on Linux/macOS).
TASK_DEF_ARN=$(MSYS2_ARG_CONV_EXCL="*" aws ecs register-task-definition \
  --cli-input-json "file://${TMP_TASK_DEF}" \
  --region "${REGION}" \
  --query "taskDefinition.taskDefinitionArn" \
  --output text)

rm -f "${TMP_TASK_DEF}"

echo "Registered: ${TASK_DEF_ARN}"

echo "=== 6. Run Fargate task ==="
TASK_ARN=$(aws ecs run-task \
  --cluster "${CLUSTER}" \
  --launch-type FARGATE \
  --task-definition "${TASK_FAMILY}" \
  --network-configuration "awsvpcConfiguration={
      subnets=[${SUBNET_ID}],
      securityGroups=[${SECURITY_GROUP_ID}],
      assignPublicIp=ENABLED
  }" \
  --region "${REGION}" \
  --query "tasks[0].taskArn" \
  --output text)

echo "Task started: ${TASK_ARN}"
echo ""
echo "=== Tail logs with: ==="
echo "  aws logs tail /ecs/locations-info-export --follow --region ${REGION}"