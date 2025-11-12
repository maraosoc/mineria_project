# Main Terraform configuration for Mineria Project
# =================================================
# This configuration creates:
# 1. Reference to existing S3 bucket
# 2. EC2 instance for processing scripts 01-05
# 3. EMR cluster infrastructure (IAM roles, security groups)
# 4. Optional: EMR cluster for Spark scripts 06-07

# Get default VPC
data "aws_vpc" "default" {
  default = true
}

# Get default subnet
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# S3 Bucket (ya existe, solo referencia)
# El bucket mineria-project ya fue creado manualmente
data "aws_s3_bucket" "project_bucket" {
  bucket = var.s3_bucket_name
}

# Local values
locals {
  bucket_name = data.aws_s3_bucket.project_bucket.id
}
# Runs scripts 01-05
module "ec2_processing" {
  source = "./modules/ec2"
  
  project_name   = var.project_name
  environment    = var.environment
  instance_type  = var.ec2_instance_type
  vpc_id         = data.aws_vpc.default.id
  subnet_id      = length(data.aws_subnets.default.ids) > 0 ? data.aws_subnets.default.ids[0] : ""
  key_name       = var.key_pair_name
  bucket_name    = local.bucket_name
  enable_public_ip = true
  root_volume_size = var.ec2_root_volume_size
}

# EMR Module
# Sets up IAM roles and security groups for EMR
# Optionally creates cluster if create_emr_cluster = true
module "emr_cluster" {
  source = "./modules/emr"
  
  project_name        = var.project_name
  environment         = var.environment
  bucket_name         = local.bucket_name
  create_cluster      = var.create_emr_cluster
  cluster_name        = var.emr_cluster_name
  release_label       = var.emr_release_label
  master_instance_type = var.emr_master_instance_type
  core_instance_type  = var.emr_core_instance_type
  core_instance_count = var.emr_core_instance_count
  key_name            = var.key_pair_name
  vpc_id              = data.aws_vpc.default.id
  subnet_id           = length(data.aws_subnets.default.ids) > 0 ? data.aws_subnets.default.ids[0] : ""
  auto_terminate      = var.emr_auto_terminate
}

# Outputs
output "bucket_name" {
  description = "S3 bucket name"
  value       = local.bucket_name
}

output "ec2_instance_id" {
  description = "EC2 instance ID for processing"
  value       = module.ec2_processing.instance_id
}

output "ec2_public_ip" {
  description = "EC2 instance public IP"
  value       = module.ec2_processing.instance_public_ip
}

output "ec2_ssh_command" {
  description = "SSH command to connect to EC2"
  value       = "ssh -i ${var.key_pair_name}.pem ubuntu@${module.ec2_processing.instance_public_ip}"
}

output "emr_cluster_id" {
  description = "EMR Cluster ID (if created)"
  value       = module.emr_cluster.cluster_id
}

output "emr_master_public_dns" {
  description = "EMR Master Public DNS (if created)"
  value       = module.emr_cluster.master_public_dns
}

output "setup_instructions" {
  description = "Next steps for setup"
  value       = <<-EOT
    ====================================
    Mineria Project Infrastructure Created
    ====================================
    
    EC2 Instance (Scripts 01-05):
      Instance ID: ${module.ec2_processing.instance_id}
      Public IP: ${module.ec2_processing.instance_public_ip}
      
      Connect via SSH:
        ssh -i ${var.key_pair_name}.pem ubuntu@${module.ec2_processing.instance_public_ip}
      
      Or via SSM:
        aws ssm start-session --target ${module.ec2_processing.instance_id}
    
    S3 Bucket:
      Name: ${local.bucket_name}
      
      Upload scripts:
        aws s3 sync ../scripts/ s3://${local.bucket_name}/scripts/
        aws s3 sync ../config/ s3://${local.bucket_name}/config/
    
    EMR Cluster (Scripts 06-07):
      ${var.create_emr_cluster ? "Cluster ID: ${module.emr_cluster.cluster_id}" : "Not created (use run_emr_pipeline.py to create on-demand)"}
    
    Next Steps:
      1. Upload your scripts and config to S3
      2. Upload raw Sentinel data to s3://${local.bucket_name}/raw_sentinel/
      3. Connect to EC2 and run: ./run_pipeline.sh --script 01_procesar_sentinel
      4. For EMR: Use run_emr_pipeline.py to create cluster and run scripts 06-07
    
    ====================================
  EOT
}
