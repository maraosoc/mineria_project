#!/bin/bash
set -e
exec > >(tee /var/log/user-data.log)
exec 2>&1

echo "Initializing EC2 instance..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3.11 python3-pip gdal-bin libgdal-dev awscli git htop tmux
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
curl -sS https://bootstrap.pypa.io/get-pip.py | python3
pip3 install boto3 rasterio geopandas numpy pandas pyproj shapely tqdm pyyaml
mkdir -p /home/ubuntu/mineria_project/scripts /home/ubuntu/mineria_project/logs
chown -R ubuntu:ubuntu /home/ubuntu/mineria_project
su - ubuntu -c "aws s3 sync s3://${bucket_name}/source/scripts/ /home/ubuntu/mineria_project/scripts/ || true"
chmod +x /home/ubuntu/mineria_project/scripts/*.py || true
touch /tmp/user-data-complete
echo "EC2 instance ready!"
