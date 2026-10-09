import os
import uuid
import requests
from datetime import datetime
from io import BytesIO

# Try to load environment variables from the .env file safely just for boto3
try:
    from dotenv import load_dotenv
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except ImportError:
    pass

import boto3

def generate_dummy_image():
    """Generates a simple red dummy image in memory to simulate a camera frame."""
    try:
        from PIL import Image
        img = Image.new('RGB', (800, 600), color='red')
        img_byte_arr = BytesIO()
        img.save(img_byte_arr, format='JPEG')
        return img_byte_arr.getvalue()
    except ImportError:
        # Fallback if Pillow is not installed
        return b"fake image content"

def upload_to_s3(bucket_name, region, s3_key):
    """Uploads the dummy image to AWS S3 using boto3."""
    print(f"Uploading dummy incident image to S3: s3://{bucket_name}/{s3_key}")
    try:
        # Credentials are automatically picked up from environment variables
        s3 = boto3.client('s3', region_name=region)
        image_bytes = generate_dummy_image()
        
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=image_bytes,
            ContentType='image/jpeg'
        )
        print("Successfully uploaded to S3.")
        
        # We can return either the raw key or the full HTTP URL depending on what the API prefers.
        # The backend API has been updated to accept 'storage_path' natively.
        return f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return None

def simulate_incident():
    bucket_name = os.environ.get('AWS_STORAGE_BUCKET_NAME', 'safelensai-data')
    region = os.environ.get('AWS_S3_REGION_NAME', 'ap-south-1')
    
    # 1. API endpoint
    api_url = "http://127.0.0.1:8000/api/events/"
    
    print(f"--- Starting SafeLensAI Cloud Simulation ---")
    
    # 2. Create S3 Key
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    unique_id = str(uuid.uuid4())[:8]
    # Include 'safety-vest' in the path so the Dashboard UI correctly flags it
    s3_key = f"storage/incidents/images/ppe/safety-vest/simulated_{timestamp_str}_{unique_id}.jpg"
    
    # 3. Upload to S3
    storage_path = upload_to_s3(bucket_name, region, s3_key)
    if not storage_path:
        print("Falling back to local string path due to S3 upload failure.")
        storage_path = s3_key
        
    # 4. POST to EC2 Database API
    print(f"Sending incident payload to API at {api_url} ...")
    payload = {
        "camera_name": "Cam-01-Simulation",
        "camera_location": "Shopfloor 1",
        "event_type": "NO_VEST",
        "storage_path": storage_path,
        "detections": [
            {
                "type": "SAFETY_VEST", 
                "value": "no_vest", 
                "details": {"confidence": 0.95, "missing_item": "vest"}
            }
        ]
    }
    
    try:
        response = requests.post(
            api_url, 
            json=payload, 
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
        if response.status_code in [200, 201]:
            print(f"\nSUCCESS! Incident synced via API to AWS RDS.")
            print(f"Response: {response.json()}")
            print("Open your EC2 SafeLensAI Dashboard. The new incident should appear at the top of the Overview table.")
        else:
            print(f"Failed to submit incident. Status code The server returned {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error connecting to API: {e}")

if __name__ == "__main__":
    simulate_incident()
