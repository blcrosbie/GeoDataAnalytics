# Copernicus Sentinel Satellite Data ETL

This directory contains scripts for downloading and processing Copernicus Sentinel satellite data from the Copernicus Data Space Ecosystem.

## Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy the example environment file and configure your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
- **Copernicus Credentials**: Get from [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/)
- **AWS S3**: For storing downloaded data
- **Rate Limiting**: Pre-configured to respect API limits

### 3. Required Environment Variables
```bash
# Copernicus Data Space Ecosystem
COPERNICUS_USERNAME=your_username
COPERNICUS_PASSWORD=your_password
COPERNICUS_CLIENT_ID=your_client_id
COPERNICUS_CLIENT_SECRET=your_client_secret

# AWS S3 Storage
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_DEFAULT_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name

# Rate Limiting (pre-configured)
MAX_CONCURRENT_WORKERS=2
REQUESTS_PER_MINUTE=2000
BANDWIDTH_LIMIT_MBPS=20
```

## Usage

### 1. Download Sentinel Data
```bash
python get_copernicus_sentinel.py
```

**Features:**
- Interactive mission selection (Sentinel-1, 2, 3, 5P, 6)
- Time period selection (yearly or custom date range)
- Optional bounding box filtering
- Automatic S3 upload
- Rate-limited concurrent downloads (max 2 workers)

**Supported Missions:**
- `sentinel-1`: SAR imaging (land/ocean)
- `sentinel-2`: Multispectral imaging (land)
- `sentinel-3`: Ocean/land monitoring
- `sentinel-5p`: Atmospheric composition
- `sentinel-6`: Sea level/topography

### 2. Process Downloaded Data
```bash
python process_copernicus_data.py
```

**Processing Options:**
- **RGB Composite**: Create true-color images
- **NDVI**: Calculate vegetation indices
- **Statistics**: Band-level statistics
- **Quicklook**: Generate thumbnail images

## API Rate Limiting

The scripts respect Copernicus API limitations:

| Limit | Value | Implementation |
|-------|-------|----------------|
| Concurrent Workers | 2 | ThreadPoolExecutor limit |
| Requests/Minute | 2000 | Rate limiter with token bucket |
| Bandwidth | 20 MB/s | Streamed downloads |
| Token Refresh | 10 min expiry | Automatic token management |

## Data Structure

Downloaded data is organized as:
```
data/
└── copernicus/
    ├── sentinel-2/
    │   ├── S2A_MSIL1C_20230101TXXXXX.zip
    │   └── processed/
    │       ├── S2A_MSIL1C_20230101TXXXXX_rgb.tif
    │       └── S2A_MSIL1C_20230101TXXXXX_ndvi.tif
    └── sentinel-1/
        └── S1A_IW_GRDH_20230101TXXXXX.zip
```

## S3 Storage

Data is automatically uploaded to S3 with structure:
```
s3://your-bucket-name/copernicus/
├── sentinel-2/
│   └── S2A_MSIL1C_20230101TXXXXX.zip
└── sentinel-1/
    └── S1A_IW_GRDH_20230101TXXXXX.zip
```

## Getting Copernicus Credentials

1. Visit [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/)
2. Create an account or sign in
3. Navigate to your user profile
4. Find OAuth credentials or create new client ID/secret
5. Note your username/password for OAuth flow

## Example Workflow

```bash
# 1. Download Sentinel-2 data for 2023
python get_copernicus_sentinel.py
# Select: sentinel-2-l2a
# Select: 2023
# Select: 10 products

# 2. Process downloaded data
python process_copernicus_data.py
# Select: sentinel-2
# Select: rgb, ndvi, statistics
```

## Error Handling

- **Rate Limiting**: Automatic retry with exponential backoff
- **Token Expiry**: Automatic token refresh
- **Network Errors**: Retry with timeout
- **Storage Errors**: Local fallback if S3 fails

## Data Formats

- **Input**: SAFE format (zipped archives)
- **Processing**: GeoTIFF for analysis
- **Output**: Cloud-optimized GeoTIFFs
- **Metadata**: JSON summaries with statistics

## Performance Notes

- Downloads are rate-limited to 2 concurrent workers
- Large files (>1GB) are streamed to minimize memory usage
- S3 uploads use multipart transfers for better performance
- Local cleanup options available after S3 upload

## Troubleshooting

**Authentication Issues:**
- Verify Copernicus credentials
- Check client ID/secret are correct
- Ensure OAuth flow is properly configured

**Download Issues:**
- Check network connectivity
- Verify S3 bucket permissions
- Monitor rate limiting logs

**Processing Issues:**
- Ensure sufficient disk space
- Check GDAL/rasterio dependencies
- Verify SAFE format integrity