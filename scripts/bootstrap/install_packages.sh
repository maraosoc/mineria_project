#!/bin/bash
# Bootstrap script for EMR cluster
# Installs Python packages and dependencies

set -e

echo "=================================="
echo "EMR Bootstrap Script - Mineria"
echo "=================================="

# Update system
echo "Updating system packages..."
sudo yum update -y

# Install system dependencies for geospatial libraries
echo "Installing GDAL and geospatial dependencies..."
sudo yum install -y \
    gdal \
    gdal-devel \
    geos \
    geos-devel \
    proj \
    proj-devel \
    libspatialindex \
    libspatialindex-devel

# Install Python packages
echo "Installing Python packages..."
sudo pip3 install --upgrade pip
sudo pip3 install \
    numpy \
    pandas \
    polars \
    rasterio \
    geopandas \
    fiona \
    shapely \
    pyproj \
    boto3 \
    s3fs \
    PyYAML \
    tqdm

# Verify installations
echo "Verifying installations..."
python3 -c "import numpy; print(f'numpy: {numpy.__version__}')"
python3 -c "import pandas; print(f'pandas: {pandas.__version__}')"
python3 -c "import polars; print(f'polars: {polars.__version__}')"
python3 -c "import rasterio; print(f'rasterio: {rasterio.__version__}')"
python3 -c "import geopandas; print(f'geopandas: {geopandas.__version__}')"

echo "=================================="
echo "Bootstrap completed successfully!"
echo "=================================="
