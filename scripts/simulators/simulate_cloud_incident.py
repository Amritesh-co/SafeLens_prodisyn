import os
import uuid
import requests
import json
from datetime import datetime

# Try to load environment variables from the .env file safely
try:
    from dotenv import load_dotenv
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except ImportError:
    pass

def get_real_image_path():
    """Returns path to a real-looking asset in the repo."""
    asset_path = "/home/prodisyn_innovations/prodisyn-git/P004-SafeLensAI-Demo/SafeLensAI/frontend-dashboard/src/assets/fall_demo.png"
    if os.path.exists(asset_path):
        return asset_path
    return None

def generate_dummy_video():
    """Returns real sample video bytes if available, otherwise dummy."""
    sample_path = "/tmp/sample_video.mp4"
    if os.path.exists(sample_path):
        with open(sample_path, "rb") as f:
            return f.read()
    return b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"REAL_VIDEO_SIMULATION" * 500

def simulate_real_cloud_incident():
    # API configuration - Use localhost for testing on the EC2 itself
    api_base = os.environ.get('VITE_API_BASE_URL', 'http://localhost:8000').rstrip('/')
    api_url = f"{api_base}/api/events/"
    
    print(f"--- SafeLensAI Real-Media Cloud Simulation ---")
    print(f"Gateway API (EC2): {api_url}")
    
    unique_suffix = f"{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}"
    
    # 1. Prepare Real Image
    image_path = get_real_image_path()
    
    # 2. Prepare Video bytes
    video_bytes = generate_dummy_video()
    
    # 3. Simulate Payload
    payload = {
        "camera_name": "Edge-AI-Node-01",
        "camera_location": "Construction Site A",
        "event_type": "FALL_DETECTED",
        "detections": json.dumps([
            {
                "type": "FALL", 
                "value": "detected", 
                "details": {"confidence": 0.95, "person_id": "P-102"}
            }
        ])
    }
    
    # 4. POST everything to EC2 Gateway
    print(f"Uploading files to EC2 Gateway...")
    files = {}
    if image_path:
        # Use unique filename to avoid IntegrityError in case of re-runs
        files["file"] = (f"fall_{unique_suffix}.png", open(image_path, "rb"), "image/png")
    
    files["video_file"] = (f"clip_{unique_suffix}.mp4", video_bytes, "video/mp4")
    
    try:
        response = requests.post(
            api_url, 
            data=payload,
            files=files,
            timeout=30
        )
        if response.status_code in [200, 201]:
            print(f"\nSUCCESS! Incident injected via EC2 Gateway.")
            print(f"The EC2 has successfully uploaded media to S3 and updated RDS.")
            print(f"Response: {response.json()}")
        else:
            print(f"Failed to submit. Status code {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Error connecting to Gateway: {e}")
    finally:
        if "file" in files:
            files["file"][1].close()

if __name__ == "__main__":
    simulate_real_cloud_incident()
