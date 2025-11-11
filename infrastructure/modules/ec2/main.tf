# EC2 Module for Processing Scripts 01-05
# ========================================

# Variables for EC2 instance
variable "project_name" {
  type        = string
  description = "Project name for resource naming"
}

variable "environment" {
  type        = string
  description = "Environment (dev, staging, prod)"
  default     = "dev"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type"
  default     = "t3.xlarge"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID where EC2 will be created"
}

variable "subnet_id" {
  type        = string
  description = "Subnet ID for EC2 instance"
  default     = ""
}

variable "key_name" {
  type        = string
  description = "SSH key pair name"
}

variable "bucket_name" {
  type        = string
  description = "S3 bucket name for data"
}

variable "enable_public_ip" {
  type        = bool
  description = "Enable public IP address"
  default     = true
}

variable "root_volume_size" {
  type        = number
  description = "Root volume size in GB"
  default     = 100
}

# Latest Ubuntu 22.04 AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Security Group for EC2
resource "aws_security_group" "ec2_processing" {
  name        = "${var.project_name}-ec2-processing-${var.environment}"
  description = "Security group for EC2 processing instance"
  vpc_id      = var.vpc_id

  # SSH access
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # Restrict to your IP in production
    description = "SSH access"
  }

  # All outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name        = "${var.project_name}-ec2-processing-${var.environment}"
    Environment = var.environment
    Purpose     = "Data Processing Scripts 01-05"
  }
}

# IAM Role for EC2
resource "aws_iam_role" "ec2_processing" {
  name = "${var.project_name}-ec2-processing-role-${var.environment}"

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
    Name        = "${var.project_name}-ec2-processing-role"
    Environment = var.environment
  }
}

# IAM Policy for S3 access
resource "aws_iam_policy" "ec2_s3_access" {
  name        = "${var.project_name}-ec2-s3-access-${var.environment}"
  description = "Allow EC2 to read/write from S3 bucket"

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
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListAllMyBuckets"
        ]
        Resource = "*"
      }
    ]
  })
}

# Attach S3 policy to role
resource "aws_iam_role_policy_attachment" "ec2_s3_attach" {
  role       = aws_iam_role.ec2_processing.name
  policy_arn = aws_iam_policy.ec2_s3_access.arn
}

# Attach SSM policy for remote management
resource "aws_iam_role_policy_attachment" "ec2_ssm_attach" {
  role       = aws_iam_role.ec2_processing.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# IAM Instance Profile
resource "aws_iam_instance_profile" "ec2_processing" {
  name = "${var.project_name}-ec2-processing-profile-${var.environment}"
  role = aws_iam_role.ec2_processing.name
}

# User data script for EC2 initialization
data "template_file" "user_data" {
  template = file("${path.module}/user_data.sh")

  vars = {
    bucket_name  = var.bucket_name
    project_name = var.project_name
    environment  = var.environment
  }
}

# EC2 Instance
resource "aws_instance" "processing" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  iam_instance_profile   = aws_iam_instance_profile.ec2_processing.name
  vpc_security_group_ids = [aws_security_group.ec2_processing.id]
  subnet_id              = var.subnet_id != "" ? var.subnet_id : null

  associate_public_ip_address = var.enable_public_ip

  root_block_device {
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }

  user_data = data.template_file.user_data.rendered

  tags = {
    Name        = "${var.project_name}-processing-${var.environment}"
    Environment = var.environment
    Purpose     = "Data Processing Scripts 01-05"
    ManagedBy   = "Terraform"
  }

  lifecycle {
    create_before_destroy = false
  }
}

# Outputs
output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.processing.id
}

output "instance_public_ip" {
  description = "EC2 instance public IP"
  value       = aws_instance.processing.public_ip
}

output "instance_private_ip" {
  description = "EC2 instance private IP"
  value       = aws_instance.processing.private_ip
}

output "security_group_id" {
  description = "Security group ID"
  value       = aws_security_group.ec2_processing.id
}

output "iam_role_arn" {
  description = "IAM role ARN"
  value       = aws_iam_role.ec2_processing.arn
}
