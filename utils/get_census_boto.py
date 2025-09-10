import boto3
from io import BytesIO
import botocore
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq



# S3 Boto3 Client Resdistrict Bucket


# Set up anonymous S3 client
s3 = boto3.client('s3', config=botocore.client.Config(signature_version=botocore.UNSIGNED))

bucket = 'uscb-2020-product-releases'
prefix = 'decennial/redistricting/2020/nmf/2020-pl94-nmf-state-partitioned/'

# List available files
response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
files = [obj['Key'] for obj in response.get('Contents', []) if obj['Key'].endswith('.csv') or obj['Key'].endswith('.parquet')]

boundary_type = 'Block.parquet'
state_fp = '032'
state_fp_filter = f"State={state_fp}"
# use_ftype = 'DPQuery'
use_ftype = 'Constraint'

boundary_files = [fn for fn in files if boundary_type in fn and state_fp_filter in fn and use_ftype in fn]

# Print available files
for i, f in enumerate(boundary_files):
    print(f"[{i}] {f}")

    
# Load one of the files (example: the first CSV)
file_key = boundary_files[1]  # Choose a file based on the list printed above

# Download file from S3
obj = s3.get_object(Bucket=bucket, Key=file_key)
pop_data = obj['Body'].read()
pop_df = pd.read_parquet(BytesIO(pop_data))

# # Load into DataFrame
# if file_key.endswith('.csv'):
#     df = pd.read_csv(BytesIO(data))
# elif file_key.endswith('.parquet'):
#     df = pd.read_parquet(BytesIO(data))

# print(df.head())