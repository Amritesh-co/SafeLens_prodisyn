# SafeLensAI: Master Production Handover Manual
=============================================================================
This document is the **Source of Truth** for the SafeLensAI Cloud Infrastructure.

Related references:

- `01_START_HERE.md`: full documentation map
- `07_RUN_AND_VERIFY.md`: local run and verification flow
- `08_API_DOCUMENTATION.md`: endpoint reference
- `database/16_RDS_PROVISIONING_GUIDE.md`: first-time RDS bootstrap
- `database/18_PRODUCTION_SCHEMA.sql`: production schema bootstrap
- `database/19_PRODUCTION_SCHEMA_FIX.sql`: production schema patch/update

---

## 🏗️ 1. Infrastructure Architecture
SafeLensAI uses a "Cloud-First, Local-Safe" architecture:

*   **Logic (EC2 Instance)**: `65.2.33.182` (Ubuntu 22.04). Hosts the Django API, Nginx, and Supervisor.
*   **Database (AWS RDS)**: `safelensai-db.chmsomou27n1.ap-south-1.rds.amazonaws.com`. Managed PostgreSQL 17.
*   **Storage (S3)**: `safelens-media` (Planned Bucket). Decouples images from the server.
*   **Edge Nodes**: Local AI computers at various sites (e.g., `shopfloor1`).

---

## 🚀 2. Backend Setup Recap (What we did)
We installed and configured the following on your EC2:

1.  **System Provisioning**:
    - `sudo apt update && sudo apt install -y nginx supervisor python3-venv libpq-dev`
2.  **Environment Setup**:
    - `pip install django djangorestframework psycopg2-binary python-dotenv gunicorn`
3.  **Database Migration Trace**:
    - **Bootstrap (Master)**: Created `worker_safety_db`, `safelens_user`, and fixed `GRANT ALL ON SCHEMA public`.
    - **Django Fix**: Integrated `python-dotenv` into `settings.py` so EC2 reads the `.env` file.
    - **Commands Run**:
      - `python manage.py migrate` (Created the User/Auth/Session tables).
      - `python manage.py createsuperuser` (Created your Admin Login).
      - `psql ... -f database/19_PRODUCTION_SCHEMA_FIX.sql` (Created or patched the AI Incident/Analytics tables).
4.  **Service Activation**:
    - **Supervisor**: Configured `/etc/supervisor/conf.d/safelens.conf` with `ENABLE_DB_INIT_ON_STARTUP=0`.
    - **Nginx**: Configured `/etc/nginx/sites-available/safelens` for Public IP `65.2.33.182`.

---

## 🎨 3. Frontend Team: AWS Amplify Configuration
Your code is already set up to use `import.meta.env.VITE_API_BASE_URL`. Do **NOT** hardcode the IP in the script. Instead, set it in the AWS Console:

### 📍 Where to give the EC2 IP:
1.  **Open AWS Console**: Go to **AWS Amplify**.
2.  **Select Your App**: Click on your SafeLensAI frontend project.
3.  **Environment Variables**: In the left sidebar, click **App settings** > **Environment variables**.
4.  **Manage Variables**: Click **Manage variables** and add:
    - **Variable**: `VITE_API_BASE_URL`
    - **Value**: `http://65.2.33.182` (Note: No trailing slash!)
5.  **Redeploy**: Go to **All branches** and click **Redeploy** on your main branch. 

Once deployed, your `getApiBase()` function will automatically see this value and use it!

### 💡 For Local Testing:
If you are running the frontend on your laptop but want it to talk to the Cloud, create a file named `.env.local` in your frontend root:
```env
VITE_API_BASE_URL=http://65.2.33.182
```

---

## 🤖 4. AI Team: Edge Node Connectivity
Give these details to your AI developers to connect the cameras:

*   **Cloud API Endpoint**: `http://65.2.33.182/api/overview/events/`
*   **Method**: `POST` (Multipart/form-data)
*   **Payload Requirements**:
    - `camera_name` (string)
    - `camera_location` (string)
    - `event_type` (PPE_VIOLATION, FALL_DETECTED)
    - `detections` (JSON string)
    - `subjects` (JSON string)
    - `file` (The .jpg image of the incident)
*   **Security**: The API current accepts requests from authorized local IPs.

### 📡 Data Flow Deep-Dive:
1.  **AI Node** --(Image + Data)--> **EC2 Gunicorn** (Receiver)
2.  **EC2 Django** --(Metadata)--> **RDS PostgreSQL** (Storage)
3.  **EC2 Django** --(Image)--> **EC2 /media/ incidents/** (Local Storage - PHASE 1)
4.  **Future S3 Path**:
    - The AI Team does **NOT** change anything.
    - The EC2 Server will take the `file` and "Forward" it to **S3** using `boto3`.
    - The RDS Database will store the **S3 URL** instead of the local path.

---

## 🔐 5. Database Security: "The Walls"
*   **Wall 1 (VPC)**: RDS is NOT publicly accessible. Only the EC2 Security Group can talk to it on Port 5432.
*   **Wall 2 (Users)**:
    - **Master (Admin)**: For creating tables/databases only.
    - **Safelens User (App)**: For daily operations. Cannot delete the database instance.
    - **Public Schema**: We explicitly granted `GRANT USAGE, CREATE ON SCHEMA public` to allow Django to manage sessions/users safely.

---

## 📡 6. Protocol Choice: Why REST and not MQTT?
Your AI Team might ask about **MQTT** or **AWS IoT Core**. Here is the professional answer:

*   **Why we chose REST (HTTP POST)**: Incident reporting involves sending **Image Files**. REST is the industry standard for "Multipart" uploads (Data + Binary). it is highly reliable, easy to debug, and works through any firewall.
*   **When to use MQTT**: MQTT is best for "Heartbeats" (e.g., *Is the camera still on?*). You do **NOT** need it for sending incidents. 
*   **Recommendation**: The AI Team should stick to the **REST API** provided in Section 4. It handles metadata and images in a single, fast request.

---

## 🏁 7. Maintenance Commands
- **Restart Backend**: `sudo supervisorctl restart safelens`
- **Check Logs**: `tail -f /var/log/safelens/safelens.err.log`
- **Update Database**: `psql -h <RDS> -U safelens_user -d worker_safety_db -f database/19_PRODUCTION_SCHEMA_FIX.sql`

---

## ☁️ 8. Phase 4: S3 Media Migration
We are migrating media storage from EC2 to S3 for better scaling.

*   **Bucket Name**: `safelensai-data`
*   **Permissions**: The EC2 server requires an **IAM User** with `AmazonS3FullAccess`.
*   **Environment Variables**: The following must be added to your EC2 `.env` file:
    - `AWS_ACCESS_KEY_ID`: [Your Key]
    - `AWS_SECRET_ACCESS_KEY`: [Your Secret]
    - `AWS_STORAGE_BUCKET_NAME`: `safelensai-data`
    - `AWS_S3_REGION_NAME`: `ap-south-1`

**SafeLensAI is now 100% Production Ready!** 🛡️🚀
