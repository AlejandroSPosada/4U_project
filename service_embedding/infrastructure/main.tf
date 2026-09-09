# ==============================================================
# infrastructure/main.tf
# Terraform IaC for the CLIP image-similarity ECS Fargate job.
# ==============================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# --------------------------------------------------------------
# VPC — falls back to account default VPC when vpc_id is null
# --------------------------------------------------------------

data "aws_vpc" "default" {
  default = true
}

locals {
  resolved_vpc_id = var.vpc_id != null ? var.vpc_id : data.aws_vpc.default.id
}

data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [local.resolved_vpc_id]
  }
  filter {
    name   = "map-public-ip-on-launch"
    values = ["true"]
  }
}

# ==============================================================
# ECR
# ==============================================================

resource "aws_ecr_repository" "locations_export" {
  name                 = "locations-export"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "locations_export" {
  repository = aws_ecr_repository.locations_export.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

# ==============================================================
# S3 — export bucket (legacy; kept for backward-compat)
# ==============================================================

resource "aws_s3_bucket" "export" {
  bucket = var.s3_bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_public_access_block" "export" {
  bucket                  = aws_s3_bucket.export.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "export" {
  bucket = aws_s3_bucket.export.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "export" {
  bucket = aws_s3_bucket.export.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ==============================================================
# IAM — shared trust policy
# ==============================================================

data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ==============================================================
# IAM — ecsTaskExecutionRole (pulls image, writes logs)
# If it already exists: terraform import aws_iam_role.ecs_task_execution ecsTaskExecutionRole
# ==============================================================

resource "aws_iam_role" "ecs_task_execution" {
  name               = "ecsTaskExecutionRole"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
  tags               = var.tags
  lifecycle { prevent_destroy = true }
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_policy" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ==============================================================
# IAM — locations-export-task-role
# Permissions the application code needs at runtime:
#   - RDS IAM auth token
#   - S3 read from 4uproject-eafit/testing/
#   - S3 write to  4uproject-eafit/output/
#   - S3 write to  my-locations-export-2026/exports/ (legacy)
# ==============================================================

resource "aws_iam_role" "task_role" {
  name               = "locations-export-task-role"
  description        = "CLIP similarity job: RDS IAM auth + S3 read/write"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
  tags               = var.tags
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "task_role_policy" {
  # RDS IAM authentication
  statement {
    sid     = "AllowRDSIAMAuth"
    effect  = "Allow"
    actions = ["rds-db:connect"]
    resources = [
      "arn:aws:rds-db:${var.aws_region}:${data.aws_caller_identity.current.account_id}:dbuser:*/${var.db_user}"
    ]
  }

  # List the testing/ prefix (needed for list_objects_v2)
  statement {
    sid     = "AllowS3ListInput"
    effect  = "Allow"
    actions = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.input_bucket}"]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.input_prefix}*"]
    }
  }

  # Read query images from testing/
  statement {
    sid     = "AllowS3ReadInput"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.input_bucket}/${var.input_prefix}*"]
  }

  # Write results CSV to output/
  statement {
    sid    = "AllowS3WriteOutput"
    effect = "Allow"
    actions = ["s3:PutObject", "s3:PutObjectAcl"]
    resources = ["arn:aws:s3:::${var.output_bucket}/${var.output_prefix}*"]
  }

  # Legacy: write CSV to the export bucket
  statement {
    sid    = "AllowS3ExportLegacy"
    effect = "Allow"
    actions = ["s3:PutObject", "s3:PutObjectAcl"]
    resources = ["${aws_s3_bucket.export.arn}/${var.s3_key_prefix}*"]
  }
}

resource "aws_iam_role_policy" "task_role_inline" {
  name   = "locations-export-policy"
  role   = aws_iam_role.task_role.id
  policy = data.aws_iam_policy_document.task_role_policy.json
}

# ==============================================================
# CloudWatch Logs
# ==============================================================

resource "aws_cloudwatch_log_group" "ecs_task" {
  name              = "/ecs/locations-info-export"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# ==============================================================
# ECS Cluster
# ==============================================================

resource "aws_ecs_cluster" "main" {
  name = var.cluster_name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  tags = var.tags
}

# ==============================================================
# ECS Task Definition
# CPU/Memory bumped to 2 vCPU / 4 GB for CLIP inference on CPU
# ==============================================================

resource "aws_ecs_task_definition" "locations_export" {
  family                   = "locations-info-export"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "2048"   # 2 vCPU  (CLIP model needs it)
  memory                   = "4096"   # 4 GB

  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.task_role.arn

  container_definitions = jsonencode([
    {
      name      = "locations-export"
      image     = "${aws_ecr_repository.locations_export.repository_url}:latest"
      essential = true

      environment = [
        # Database
        { name = "DB_HOST",          value = var.db_host },
        { name = "DB_PORT",          value = tostring(var.db_port) },
        { name = "DB_USER",          value = var.db_user },
        { name = "DB_NAME",          value = var.db_name },
        { name = "DB_REGION",        value = var.aws_region },
        { name = "EMBEDDINGS_TABLE", value = var.embeddings_table },
        { name = "LOCATIONS_TABLE",  value = var.locations_table },
        # S3 input (query images)
        { name = "INPUT_BUCKET",     value = var.input_bucket },
        { name = "INPUT_PREFIX",     value = var.input_prefix },
        # S3 output (results CSV)
        { name = "OUTPUT_BUCKET",    value = var.output_bucket },
        { name = "OUTPUT_PREFIX",    value = var.output_prefix },
        # CLIP model
        { name = "CLIP_MODEL_ID",    value = var.clip_model_id },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs_task.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])

  tags = var.tags
}

# ==============================================================
# Security Group — Fargate task (egress-only)
# ==============================================================

resource "aws_security_group" "fargate_task" {
  name        = "locations-export-sg"
  description = "Outbound to Aurora (5432) and AWS APIs (443)"
  vpc_id      = local.resolved_vpc_id

  egress {
    description = "PostgreSQL to RDS"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "HTTPS to AWS APIs (ECR, S3, CloudWatch, HuggingFace)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "locations-export-sg" })
}
