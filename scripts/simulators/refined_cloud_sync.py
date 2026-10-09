import requests
import json
import os
import threading
import time
import logging
from datetime import datetime

# Logging setup
logger = logging.getLogger("cloud_sync")
logger.setLevel(logging.ERROR)
handler = logging.FileHandler("cloud_sync_errors.log")
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

class CloudSync:
    def __init__(self, api_base="http://65.2.33.182:8000"):
        """
        No AWS credentials needed here anymore! 
        Everything flows via EC2.
        """
        self.api_url = f"{api_base.rstrip('/')}/api/events/"

    def sync_incident(self, image_path: str, video_path: str, person_id, camera_name: str, location: str):
        """
        Spawns a daemon thread immediately and returns.
        """
        threading.Thread(
            target=self._sync_task,
            args=(image_path, video_path, person_id, camera_name, location),
            daemon=True
        ).start()

    def _sync_task(self, image_path, video_path, person_id, camera_name, location):
        try:
            # Wait up to 15s for video file to be written by camera
            video_ready = False
            for _ in range(15):
                if os.path.exists(video_path):
                    video_ready = True
                    break
                time.sleep(1)

            # --- POST MetaData + Files to EC2 API ---
            self._post_to_ec2_gateway(image_path, video_path if video_ready else None, camera_name, location, person_id)

        except Exception as e:
            logger.error(f"Error in sync_incident thread: {e}", exc_info=True)

    def _post_to_ec2_gateway(self, image_path, video_path, camera_name, location, person_id):
        """
        Sends everything to the EC2. 
        EC2 will take the files and push them to S3 for us.
        """
        payload = {
            "camera_name": camera_name,
            "camera_location": location,
            "event_type": "FALL_DETECTED",
            "detections": json.dumps([{
                "type": "fall", 
                "value": "detected",
                "details": {"person_id": person_id}
            }])
        }
        
        files = {}
        # Open image for upload
        if os.path.exists(image_path):
            files["file"] = (os.path.basename(image_path), open(image_path, "rb"), "image/jpeg")
            
        # Open video for upload
        if video_path and os.path.exists(video_path):
            files["video_file"] = (os.path.basename(video_path), open(video_path, "rb"), "video/mp4")

        try:
            for attempt in range(3):
                try:
                    response = requests.post(
                        self.api_url, 
                        data=payload, 
                        files=files,
                        timeout=30 # Higher timeout for video uploads
                    )
                    response.raise_for_status()
                    print(f"Gateway Success: Incident {response.json().get('event_id')} created. EC2 is processing media to S3.")
                    return True
                except Exception as e:
                    if attempt == 2:
                        logger.error(f"Failed to reach EC2 Gateway after 3 attempts: {e}")
                    time.sleep(2)
        finally:
            # Ensure files are closed
            for key in files:
                files[key][1].close()
        return None

# Usage
if __name__ == "__main__":
    sync = CloudSync()
    # sync.sync_incident("snap.jpg", "clip.mp4", "P-001", "Cam-01", "Warehouse A")
