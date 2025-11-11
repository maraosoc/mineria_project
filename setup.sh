#!/bin/bash
# Setup Script for Mineria Project
# This script helps deploy the infrastructure and upload necessary files to S3

set -e

echo "======================================"
echo "Mineria Project - Setup Script"
echo "======================================"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install it first."
    exit 1
fi

# Check if Terraform is installed
if ! command -v terraform &> /dev/null; then
    echo "❌ Terraform not found. Please install it first."
    exit 1
fi

echo "✅ AWS CLI found: $(aws --version)"
echo "✅ Terraform found: $(terraform version -json | grep -o '"terraform_version":"[^"]*' | cut -d'"' -f4)"

# Step 1: Configure Terraform
echo ""
echo "Step 1: Configure Terraform"
echo "----------------------------"

cd infrastructure/

if [ ! -f terraform.tfvars ]; then
    echo "Creating terraform.tfvars from example..."
    cp terraform.tfvars.example terraform.tfvars
    echo "⚠️  Please edit infrastructure/terraform.tfvars with your values"
    echo "   Required: key_pair_name"
    read -p "Press Enter after editing terraform.tfvars..."
fi

# Step 2: Initialize Terraform
echo ""
echo "Step 2: Initialize Terraform"
echo "-----------------------------"
terraform init

# Step 3: Plan
echo ""
echo "Step 3: Review Terraform Plan"
echo "------------------------------"
terraform plan -out=tfplan

read -p "Do you want to apply this plan? (yes/no): " apply_response
if [ "$apply_response" != "yes" ]; then
    echo "❌ Aborted by user"
    exit 1
fi

# Step 4: Apply
echo ""
echo "Step 4: Create Infrastructure"
echo "------------------------------"
terraform apply tfplan

# Save outputs
echo ""
echo "Saving Terraform outputs..."
terraform output -json > ../outputs.json
terraform output > ../outputs.txt

echo "✅ Infrastructure created!"

# Extract important values
BUCKET_NAME=$(terraform output -raw bucket_name)
EC2_IP=$(terraform output -raw ec2_public_ip)
EC2_INSTANCE_ID=$(terraform output -raw ec2_instance_id)

echo ""
echo "Important Information:"
echo "----------------------"
echo "S3 Bucket: $BUCKET_NAME"
echo "EC2 IP: $EC2_IP"
echo "EC2 Instance ID: $EC2_INSTANCE_ID"

cd ..

# Step 5: Upload scripts to S3
echo ""
echo "Step 5: Upload Scripts to S3"
echo "-----------------------------"
read -p "Upload scripts to S3? (yes/no): " upload_response

if [ "$upload_response" == "yes" ]; then
    echo "Uploading scripts..."
    aws s3 sync scripts/ s3://$BUCKET_NAME/scripts/ --exclude "*.pyc" --exclude "__pycache__/*"
    
    echo "Uploading config..."
    aws s3 sync config/ s3://$BUCKET_NAME/config/
    
    echo "Uploading bootstrap..."
    aws s3 cp scripts/bootstrap/install_packages.sh s3://$BUCKET_NAME/scripts/bootstrap/install_packages.sh
    
    echo "✅ Files uploaded to S3"
    
    # List uploaded files
    echo ""
    echo "Uploaded files:"
    aws s3 ls s3://$BUCKET_NAME/scripts/ --recursive
fi

# Step 6: Instructions
echo ""
echo "======================================"
echo "✅ Setup Complete!"
echo "======================================"
echo ""
echo "Next Steps:"
echo "-----------"
echo ""
echo "1. Upload your data to S3:"
echo "   aws s3 sync /path/to/sentinel/data/ s3://$BUCKET_NAME/raw_sentinel/"
echo "   aws s3 sync /path/to/shapefiles/ s3://$BUCKET_NAME/shapes/"
echo ""
echo "2. Connect to EC2 instance:"
echo "   ssh -i <your-key>.pem ubuntu@$EC2_IP"
echo "   OR"
echo "   aws ssm start-session --target $EC2_INSTANCE_ID"
echo ""
echo "3. Wait ~5 minutes for EC2 initialization to complete"
echo ""
echo "4. Run your first script:"
echo "   cd /home/ubuntu/mineria_scripts"
echo "   python orchestration/run_ec2_pipeline.py --script 01_procesar_sentinel"
echo ""
echo "5. For detailed instructions, see EXECUTION_GUIDE.md"
echo ""
echo "Useful commands:"
echo "  - Check EC2 status: aws ec2 describe-instances --instance-ids $EC2_INSTANCE_ID"
echo "  - View S3 contents: aws s3 ls s3://$BUCKET_NAME/ --recursive"
echo "  - Stop EC2 to save costs: aws ec2 stop-instances --instance-ids $EC2_INSTANCE_ID"
echo ""
echo "======================================"

# Create a quick reference file
cat > QUICK_REFERENCE.txt << EOF
Mineria Project - Quick Reference
==================================

S3 Bucket: $BUCKET_NAME
EC2 IP: $EC2_IP
EC2 Instance ID: $EC2_INSTANCE_ID

SSH Command:
  ssh -i <your-key>.pem ubuntu@$EC2_IP

SSM Command:
  aws ssm start-session --target $EC2_INSTANCE_ID

Check EC2 Logs:
  ssh ubuntu@$EC2_IP
  tail -f /var/log/user-data.log
  tail -f /home/ubuntu/mineria_logs/ec2_pipeline_*.log

View S3 Contents:
  aws s3 ls s3://$BUCKET_NAME/ --recursive

Run Script in EC2:
  cd /home/ubuntu/mineria_scripts
  python orchestration/run_ec2_pipeline.py --script <script_name>

Run EMR Pipeline:
  cd scripts/orchestration/
  python run_emr_pipeline.py --script <script_name> --create-cluster

Stop/Start EC2:
  aws ec2 stop-instances --instance-ids $EC2_INSTANCE_ID
  aws ec2 start-instances --instance-ids $EC2_INSTANCE_ID

Destroy Infrastructure (when done):
  cd infrastructure/
  terraform destroy
EOF

echo "Quick reference saved to QUICK_REFERENCE.txt"
