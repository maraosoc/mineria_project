#!/bin/bash
# User data script for EC2 instance initialization
# This script sets up the environment for running processing scripts

set -e

# Variables from Terraform
BUCKET_NAME="${bucket_name}"
PROJECT_NAME="${project_name}"
ENVIRONMENT="${environment}"

# Logging
exec > >(tee /var/log/user-data.log)
exec 2>&1

echo "=========================================="
echo "Initializing EC2 instance for ${PROJECT_NAME}"
echo "Environment: ${ENVIRONMENT}"
echo "Bucket: ${BUCKET_NAME}"
echo "=========================================="

# Update system
echo "Updating system packages..."
apt-get update -y
apt-get upgrade -y

# Install essential packages
echo "Installing essential packages..."
apt-get install -y \
    python3.10 \
    python3-pip \
    python3-venv \
    awscli \
    git \
    htop \
    tmux \
    vim \
    build-essential \
    libgdal-dev \
    gdal-bin \
    python3-gdal

# Create project directories
echo "Creating project directories..."
mkdir -p /home/ubuntu/mineria_scripts
mkdir -p /home/ubuntu/mineria_work
mkdir -p /home/ubuntu/mineria_logs
chown -R ubuntu:ubuntu /home/ubuntu/mineria_*

# Create Python virtual environment
echo "Creating Python virtual environment..."
sudo -u ubuntu python3 -m venv /home/ubuntu/mineria_venv
source /home/ubuntu/mineria_venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install Python dependencies
echo "Installing Python dependencies..."
cat > /tmp/requirements.txt << 'EOF'
numpy>=1.24.0
pandas>=2.0.0
polars>=0.20.0
rasterio>=1.3.0
geopandas>=0.14.0
fiona>=1.9.0
shapely>=2.0.0
pyproj>=3.6.0
boto3>=1.34.0
botocore>=1.34.0
s3fs>=2024.1.0
PyYAML>=6.0.0
python-dotenv>=1.0.0
tqdm>=4.66.0
colorama>=0.4.6
EOF

pip install -r /tmp/requirements.txt

# Download scripts from S3
echo "Downloading scripts from S3..."
aws s3 sync s3://${BUCKET_NAME}/scripts/ /home/ubuntu/mineria_scripts/ || echo "No scripts found in S3 yet"

# Make scripts executable
chmod +x /home/ubuntu/mineria_scripts/*.py 2>/dev/null || true
chmod +x /home/ubuntu/mineria_scripts/orchestration/*.py 2>/dev/null || true

# Download config files
echo "Downloading config files..."
aws s3 sync s3://${BUCKET_NAME}/config/ /home/ubuntu/mineria_scripts/config/ || echo "No config files found in S3 yet"

# Set permissions
chown -R ubuntu:ubuntu /home/ubuntu/mineria_*

# Create systemd service for automatic script execution (optional)
cat > /etc/systemd/system/mineria-processing.service << 'EOF'
[Unit]
Description=Mineria Data Processing Service
After=network.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/mineria_scripts
Environment="PATH=/home/ubuntu/mineria_venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/ubuntu/mineria_venv/bin/python orchestration/run_ec2_pipeline.py --mode sequential
StandardOutput=append:/home/ubuntu/mineria_logs/service.log
StandardError=append:/home/ubuntu/mineria_logs/service_error.log

[Install]
WantedBy=multi-user.target
EOF

# Don't enable the service by default
systemctl daemon-reload

# Create helper scripts
cat > /home/ubuntu/run_pipeline.sh << 'EOF'
#!/bin/bash
source /home/ubuntu/mineria_venv/bin/activate
cd /home/ubuntu/mineria_scripts
python orchestration/run_ec2_pipeline.py "$@"
EOF

chmod +x /home/ubuntu/run_pipeline.sh
chown ubuntu:ubuntu /home/ubuntu/run_pipeline.sh

# Set up cron for log rotation (keep last 7 days)
cat > /etc/cron.daily/mineria-cleanup << 'EOF'
#!/bin/bash
find /home/ubuntu/mineria_logs -name "*.log" -mtime +7 -delete
find /home/ubuntu/mineria_work -type f -mtime +3 -delete
EOF

chmod +x /etc/cron.daily/mineria-cleanup

# Configure AWS CLI for ubuntu user
sudo -u ubuntu aws configure set default.region us-east-1
sudo -u ubuntu aws configure set default.output json

# Create README for the ubuntu user
cat > /home/ubuntu/README.md << 'EOF'
# Mineria Processing Instance

This EC2 instance is configured for running data processing scripts 01-05.

## Quick Start

### Run individual script:
```bash
./run_pipeline.sh --script 01_procesar_sentinel
```

### Run full pipeline:
```bash
./run_pipeline.sh --mode sequential
```

### Run until specific step:
```bash
./run_pipeline.sh --mode sequential --stop-after 03_tabular_features
```

## Directory Structure

- `/home/ubuntu/mineria_scripts/` - Processing scripts
- `/home/ubuntu/mineria_work/` - Temporary working directory
- `/home/ubuntu/mineria_logs/` - Execution logs
- `/home/ubuntu/mineria_venv/` - Python virtual environment

## Logs

- System logs: `/var/log/user-data.log`
- Pipeline logs: `/home/ubuntu/mineria_logs/`

## Maintenance

Logs older than 7 days are automatically deleted.
Working files older than 3 days are automatically deleted.
EOF

chown ubuntu:ubuntu /home/ubuntu/README.md

echo "=========================================="
echo "EC2 initialization complete!"
echo "Instance is ready for processing"
echo "=========================================="
