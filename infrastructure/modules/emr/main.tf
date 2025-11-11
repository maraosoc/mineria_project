# EMR Module for Spark Processing Scripts 06-07
# ===============================================

variable "project_name" {
  type        = string
  description = "Project name for resource naming"
}

variable "environment" {
  type        = string
  description = "Environment (dev, staging, prod)"
  default     = "dev"
}

variable "bucket_name" {
  type        = string
  description = "S3 bucket name for data and logs"
}

variable "create_cluster" {
  type        = bool
  description = "Whether to create EMR cluster (false for on-demand creation)"
  default     = false
}

variable "cluster_name" {
  type        = string
  description = "EMR cluster name"
  default     = "mineria-spark-cluster"
}

variable "release_label" {
  type        = string
  description = "EMR release label"
  default     = "emr-7.0.0"
}

variable "master_instance_type" {
  type        = string
  description = "Master instance type"
  default     = "m5.xlarge"
}

variable "core_instance_type" {
  type        = string
  description = "Core instance type"
  default     = "m5.2xlarge"
}

variable "core_instance_count" {
  type        = number
  description = "Number of core instances"
  default     = 2
}

variable "key_name" {
  type        = string
  description = "SSH key pair name"
}

variable "subnet_id" {
  type        = string
  description = "Subnet ID for EMR cluster"
  default     = ""
}

variable "vpc_id" {
  type        = string
  description = "VPC ID"
}

variable "auto_terminate" {
  type        = bool
  description = "Auto-terminate cluster after steps complete"
  default     = false
}

# IAM Role for EMR Service
resource "aws_iam_role" "emr_service_role" {
  name = "${var.project_name}-emr-service-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "elasticmapreduce.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-emr-service-role"
    Environment = var.environment
  }
}

# Attach AWS managed policy for EMR service
resource "aws_iam_role_policy_attachment" "emr_service_policy" {
  role       = aws_iam_role.emr_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonElasticMapReduceRole"
}

# IAM Role for EMR EC2 instances
resource "aws_iam_role" "emr_ec2_role" {
  name = "${var.project_name}-emr-ec2-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-emr-ec2-role"
    Environment = var.environment
  }
}

# S3 access policy for EMR
resource "aws_iam_policy" "emr_s3_access" {
  name        = "${var.project_name}-emr-s3-access-${var.environment}"
  description = "Allow EMR to access S3 bucket"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.bucket_name}",
          "arn:aws:s3:::${var.bucket_name}/*"
        ]
      }
    ]
  })
}

# Attach policies to EMR EC2 role
resource "aws_iam_role_policy_attachment" "emr_ec2_policy" {
  role       = aws_iam_role.emr_ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonElasticMapReduceforEC2Role"
}

resource "aws_iam_role_policy_attachment" "emr_s3_attach" {
  role       = aws_iam_role.emr_ec2_role.name
  policy_arn = aws_iam_policy.emr_s3_access.arn
}

# IAM Instance Profile for EMR EC2
resource "aws_iam_instance_profile" "emr_ec2_profile" {
  name = "${var.project_name}-emr-ec2-profile-${var.environment}"
  role = aws_iam_role.emr_ec2_role.name
}

# Security Group for EMR Master
resource "aws_security_group" "emr_master" {
  name        = "${var.project_name}-emr-master-${var.environment}"
  description = "Security group for EMR master node"
  vpc_id      = var.vpc_id

  # Allow SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # Restrict in production
    description = "SSH access"
  }

  # Spark UI
  ingress {
    from_port   = 8088
    to_port     = 8088
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # Restrict in production
    description = "Spark UI"
  }

  # All outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-emr-master-${var.environment}"
    Environment = var.environment
  }
}

# Security Group for EMR Core/Task nodes
resource "aws_security_group" "emr_slave" {
  name        = "${var.project_name}-emr-slave-${var.environment}"
  description = "Security group for EMR core/task nodes"
  vpc_id      = var.vpc_id

  # All outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-emr-slave-${var.environment}"
    Environment = var.environment
  }
}

# Allow communication between master and slaves
resource "aws_security_group_rule" "emr_master_to_slave" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.emr_master.id
  security_group_id        = aws_security_group.emr_slave.id
  description              = "Allow master to communicate with slaves"
}

resource "aws_security_group_rule" "emr_slave_to_master" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.emr_slave.id
  security_group_id        = aws_security_group.emr_master.id
  description              = "Allow slaves to communicate with master"
}

# EMR Cluster (only created if create_cluster = true)
resource "aws_emr_cluster" "spark_cluster" {
  count = var.create_cluster ? 1 : 0

  name          = var.cluster_name
  release_label = var.release_label
  applications  = ["Spark", "Hadoop"]

  ec2_attributes {
    key_name                          = var.key_name
    subnet_id                         = var.subnet_id != "" ? var.subnet_id : null
    emr_managed_master_security_group = aws_security_group.emr_master.id
    emr_managed_slave_security_group  = aws_security_group.emr_slave.id
    instance_profile                  = aws_iam_instance_profile.emr_ec2_profile.arn
  }

  master_instance_group {
    instance_type = var.master_instance_type
    instance_count = 1
  }

  core_instance_group {
    instance_type  = var.core_instance_type
    instance_count = var.core_instance_count
    
    ebs_config {
      size                 = 100
      type                 = "gp3"
      volumes_per_instance = 1
    }
  }

  # Bootstrap action to install Python packages
  bootstrap_action {
    name = "Install Python packages"
    path = "s3://${var.bucket_name}/scripts/bootstrap/install_packages.sh"
  }

  configurations_json = jsonencode([
    {
      Classification = "spark-defaults"
      Properties = {
        "spark.executor.memory"            = "16g"
        "spark.executor.cores"             = "4"
        "spark.driver.memory"              = "8g"
        "spark.driver.cores"               = "2"
        "spark.dynamicAllocation.enabled"  = "true"
        "spark.shuffle.service.enabled"    = "true"
        "spark.sql.adaptive.enabled"       = "true"
        "spark.sql.adaptive.coalescePartitions.enabled" = "true"
      }
    },
    {
      Classification = "spark-env"
      Configurations = [
        {
          Classification = "export"
          Properties = {
            "PYSPARK_PYTHON" = "/usr/bin/python3"
          }
        }
      ]
    }
  ])

  log_uri      = "s3://${var.bucket_name}/logs/emr/"
  service_role = aws_iam_role.emr_service_role.arn

  keep_job_flow_alive_when_no_steps = !var.auto_terminate

  tags = {
    Name        = var.cluster_name
    Environment = var.environment
    Purpose     = "Spark ML Training Scripts 06-07"
    ManagedBy   = "Terraform"
  }

  lifecycle {
    ignore_changes = [
      step  # Ignore step changes as they're added dynamically
    ]
  }
}

# Outputs
output "cluster_id" {
  description = "EMR cluster ID"
  value       = var.create_cluster ? aws_emr_cluster.spark_cluster[0].id : null
}

output "cluster_name" {
  description = "EMR cluster name"
  value       = var.cluster_name
}

output "master_security_group_id" {
  description = "EMR master security group ID"
  value       = aws_security_group.emr_master.id
}

output "slave_security_group_id" {
  description = "EMR slave security group ID"
  value       = aws_security_group.emr_slave.id
}

output "emr_service_role_arn" {
  description = "EMR service role ARN"
  value       = aws_iam_role.emr_service_role.arn
}

output "emr_ec2_role_arn" {
  description = "EMR EC2 role ARN"
  value       = aws_iam_role.emr_ec2_role.arn
}

output "master_public_dns" {
  description = "EMR master public DNS"
  value       = var.create_cluster ? aws_emr_cluster.spark_cluster[0].master_public_dns : null
}
