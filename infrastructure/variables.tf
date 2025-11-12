# Terraform Variables for Mineria Project
# =========================================

# AWS Configuration
variable "region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region"
}

variable "profile" {
  type        = string
  default     = "default"
  description = "AWS CLI profile"
}

variable "owner" {
  type        = string
  default     = "mineria-team"
  description = "Project owner"
}

# Project Configuration
variable "project_name" {
  type        = string
  default     = "mineria"
  description = "Project name (used for resource naming)"
}

variable "environment" {
  type        = string
  default     = "dev"
  description = "Environment (dev, staging, prod)"
  
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

# SSH Key
variable "key_pair_name" {
  type        = string
  description = "SSH key pair name for EC2 and EMR access"
}

# EC2 Configuration (for scripts 01-05)
variable "ec2_instance_type" {
  type        = string
  default     = "t3.xlarge"
  description = "EC2 instance type for processing scripts 01-05"
}

variable "ec2_root_volume_size" {
  type        = number
  default     = 100
  description = "Root volume size in GB for EC2 instance"
}

# EMR Configuration (for scripts 06-07)
variable "create_emr_cluster" {
  type        = bool
  default     = false
  description = "Whether to create EMR cluster immediately (false for on-demand creation)"
}

variable "emr_cluster_name" {
  type        = string
  default     = "mineria-spark-cluster"
  description = "EMR cluster name"
}

variable "emr_release_label" {
  type        = string
  default     = "emr-7.0.0"
  description = "EMR release label (includes Spark 3.5.0)"
}

variable "emr_master_instance_type" {
  type        = string
  default     = "m5.xlarge"
  description = "EMR master instance type"
}

variable "emr_core_instance_type" {
  type        = string
  default     = "m5.2xlarge"
  description = "EMR core instance type"
}

variable "emr_core_instance_count" {
  type        = number
  default     = 2
  description = "Number of EMR core instances"
}

variable "emr_auto_terminate" {
  type        = bool
  default     = false
  description = "Auto-terminate EMR cluster when idle"
}

# S3 Configuration
variable "s3_bucket_name" {
  type        = string
  default     = "mineria-project"
  description = "S3 bucket name for data storage"
}

# Additional Tags
variable "tags" {
  type        = map(string)
  default     = {}
  description = "Additional tags to apply to resources"
}

# Legacy variables (for backwards compatibility if needed)
variable "instance_type" {
  type        = string
  default     = "t3.medium"
  description = "Legacy: Default instance type"
}

variable "name" {
  type        = string
  default     = "mineria_project"
  description = "Legacy: Nombre base para recursos"
}
