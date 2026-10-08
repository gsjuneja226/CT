"""
Cloud Storage Service (AWS S3)
==============================
Handles persistent storage for large computational artifacts (ZIP results).
Integrates with AWS Boto3 to provide secure uploads and time-limited download links.
"""

import boto3
import os
from botocore.exceptions import NoCredentialsError
from dotenv import load_dotenv

# Environment-based AWS Configuration
load_dotenv()

S3_BUCKET = os.getenv("AWS_S3_BUCKET")
S3_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

# Initialize S3 Client: Singleton for the application process
s3_client = boto3.client(
    's3',
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name=S3_REGION
)

def upload_result_to_s3(file_path: str, object_name: str) -> str:
    """
    Transfers a completed job artifact from the local worker cache to the cloud.
    
    Args:
        file_path (str): Local path to the ZIP archive.
        object_name (str): Desired key in the S3 bucket.
        
    Returns:
        str: Internal S3 protocol URI (s3://...) or None if failed.
    """
    try:
        s3_client.upload_file(file_path, S3_BUCKET, object_name)
        # Construct the internal S3 URL for architectural referencing
        s3_url = f"s3://{S3_BUCKET}/{object_name}"
        return s3_url
    except FileNotFoundError:
        print(f"[storage] Error: Local file not found at {file_path}")
        return None
    except NoCredentialsError:
        print("[storage] Error: AWS credentials (IAM) are missing or invalid")
        return None


def generate_presigned_url(object_name: str, expiration: int = 3600) -> str:
    """
    Creates a secure, temporary HTTP GET link for result retrieval.
    This allows the frontend to serve files directly from S3 without 
    proxying binary data through the FastAPI server.
    
    Args:
        object_name (str): The S3 key to link to.
        expiration (int): Seconds until the link becomes invalid (default 1hr).
        
    Returns:
        str: The pre-signed URL string if successful, None otherwise.
    """
    try:
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': object_name},
            ExpiresIn=expiration
        )
        return response
    except Exception as e:
        print(f"[storage] Error generating presigned URL: {e}")
        return None