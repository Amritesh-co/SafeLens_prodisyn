import requests
import json
import os
import time

# --- Configuration ---
EC2_GATEWAY_URL = "http://localhost:8000"
API_ENDPOINT = f"{EC2_GATEWAY_URL}/api/events/"

def simulate_unattended_object():
    print("--- SafeLensAI Unattended Object Simulation ---")
    
    # 1. Media Assets
    # Reusing the valid assets from previous simulations
    image_path = "/home/prodisyn_innovations/prodisyn-git/P004-SafeLensAI-Demo/SafeLensAI/database-api/scripts/unattended_bag.png"
    video_path = "/tmp/sample_video.mp4"
    
    if not os.path.exists(image_path) or not os.path.exists(video_path):
        print(f"Error: Missing media files at {image_path} or {video_path}")
        return

    # 2. Payload Metadata
    payload = {
        "camera_name": "Edge-AI-Node-02",
        "camera_location": "Main Warehouse Entrance",
        "event_type": "UNATTENDED_OBJECT",
        "detections": json.dumps([
            {
                "type": "OBJECT", 
                "value": "Bag", 
                "details": {"confidence": 0.92, "unattended_time_mins": 5}
            }
        ])
    }
    
    # 3. Files (Multipart)
    files = {
        "file": ("unattended_bag.jpg", open(image_path, "rb"), "image/jpeg"),
        "video_file": ("unattended_bag_clip.mp4", open(video_path, "rb"), "video/mp4")
    }
    
    # 4. POST to Gateway
    print(f"Submitting 'Unattended Object' to Gateway: {API_ENDPOINT}")
    try:
        start_time = time.time()
        response = requests.post(API_ENDPOINT, data=payload, files=files, timeout=60)
        duration = time.time() - start_time
        
        if response.status_code == 201:
            print(f"✅ SUCCESS! Incident injected in {duration:.2f}s.")
            print(f"Response: {response.json()}")
        else:
            print(f"❌ FAILED ({response.status_code}): {response.text}")
            
    except Exception as e:
        print(f"⚠️ Error during simulation: {str(e)}")

if __name__ == "__main__":
    simulate_unattended_object()
