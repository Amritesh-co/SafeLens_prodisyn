import os
import boto3
import psycopg2
from botocore.exceptions import NoCredentialsError
import glob

# --- CONFIGURATION ---
DB_CONFIG = {
    'dbname': os.environ.get('DB_NAME', 'worker_safety_db'),
    'user': os.environ.get('DB_USER', 'safelens_user'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': os.environ.get('DB_PORT', '5432')
}

S3_BUCKET = os.environ.get('AWS_STORAGE_BUCKET_NAME', 'safelensai-data')
S3_REGION = os.environ.get('AWS_S3_REGION_NAME') or os.environ.get('AWS_REGION', 'ap-south-1')

# IMPORTANT: Ensure these are set in your environment
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')

# Root search path for local machine
SEARCH_ROOT = os.environ.get('SYSTEM_STORAGE_DIR', '../storage')

def find_file_aggressive(path):
    """
    Search recursively for a filename matching the one in the path.
    Slow but guaranteed to find files if they exist anywhere in SEARCH_ROOT.
    """
    # 1. Try absolute path directly first
    if os.path.exists(path):
        return path
    
    # 2. Extract basename (e.g., test.mp4)
    filename = os.path.basename(path)
    
    # 3. Aggressive Search: Try to find this filename inside our SEARCH_ROOT
    # We use glob to find the file recursively
    print(f"🔎 Deep-searching for: {filename}...")
    matches = glob.glob(os.path.join(SEARCH_ROOT, '**', filename), recursive=True)
    
    if matches:
        return matches[0] # Return the first match found
    
    # 4. Fallback search (sometimes filenames differ slightly)
    return None

def get_clean_s3_key(local_path):
    """Strip local system prefixes for S3."""
    if 'SafeLensAI/' in local_path:
        key = local_path.split('SafeLensAI/')[-1]
    else:
        key = os.path.basename(local_path)
    return key.lstrip('/')

def migrate_media():
    if not DB_CONFIG['password']:
        print("❌ ERROR: DB_PASSWORD is missing.")
        return

    if not AWS_ACCESS_KEY or not AWS_SECRET_KEY:
        print("❌ ERROR: AWS Credentials missing.")
        return

    s3 = boto3.client('s3', 
                      aws_access_key_id=AWS_ACCESS_KEY, 
                      aws_secret_access_key=AWS_SECRET_KEY,
                      region_name=S3_REGION)

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        stats = {'uploaded': 0, 'missing': 0}

        # 1. MIGRATE FRAMES
        print("🔍 Scanning media.frames...")
        cur.execute("SELECT frame_id, storage_path FROM media.frames WHERE storage_path NOT LIKE 'http%';")
        frames = cur.fetchall()

        for fid, path in frames:
            local_path = find_file_aggressive(path)
            if local_path:
                s3_key = get_clean_s3_key(local_path)
                try:
                    print(f"🔼 [Frame {fid}] Found at: {local_path}")
                    s3.upload_file(local_path, S3_BUCKET, s3_key)
                    s3_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{s3_key}"
                    
                    cur.execute("UPDATE media.frames SET storage_path = %s WHERE frame_id = %s", (s3_url, fid))
                    conn.commit()
                    stats['uploaded'] += 1
                except Exception as e:
                    print(f"❌ Failed to upload: {e}")
            else:
                stats['missing'] += 1

        # 2. MIGRATE CLIPS
        print("\n🔍 Scanning media.clips...")
        cur.execute("SELECT clip_id, storage_path FROM media.clips WHERE storage_path NOT LIKE 'http%';")
        clips = cur.fetchall()

        for cid, path in clips:
            local_path = find_file_aggressive(path)
            if local_path:
                s3_key = get_clean_s3_key(local_path)
                try:
                    print(f"🔼 [Clip {cid}] Found at: {local_path}")
                    s3.upload_file(local_path, S3_BUCKET, s3_key)
                    s3_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{s3_key}"
                    
                    cur.execute("UPDATE media.clips SET storage_path = %s WHERE clip_id = %s", (s3_url, cid))
                    conn.commit()
                    stats['uploaded'] += 1
                except Exception as e:
                    print(f"❌ Failed to upload clip: {e}")
            else:
                stats['missing'] += 1

        cur.close()
        conn.close()
        print(f"\n✅ S3 MIGRATION SUMMARY:")
        print(f"--- Uploaded:  {stats['uploaded']}")
        print(f"--- Missing:   {stats['missing']}")

    except Exception as e:
        print(f"❌ Database error: {e}")

if __name__ == "__main__":
    migrate_media()
