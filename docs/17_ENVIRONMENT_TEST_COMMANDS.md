# SafeLens Environment Test Commands

This document collects the exact commands used to validate the SafeLens development environment across EC2, RDS, S3, backend APIs, incidents, users, and media delivery.

Use this document as an operations runbook for quick verification.

## 1. Environment Endpoints

- Backend API:
  `https://safelens-dev-api.prodisyn.com/`

- Frontend Dashboard:
  `https://safelens-dev-dashboard.prodisyn.com/`

- RDS Host:
  `safelensai-database-v1.chmsomou27n1.ap-south-1.rds.amazonaws.com`

- Main application database:
  `worker_safety_db`

## 2. Credentials Used For Verification

- Dashboard/API username:
  `admin`

- Dashboard/API password:
  `Admin@123`

- Database user:
  `safelens_user`

## 3. EC2 Checks

### Check backend `.env`

```bash
cd ~/app/database-api
cat .env
```

### Check frontend `.env`

```bash
cd ~/app/database-api/../frontend-dashboard
cat .env
```

### Check backend process

```bash
ps -ef | grep -i gunicorn
ps -ef | grep -i manage.py
```

### Restart backend service

Replace the service name if your EC2 uses a different one.

```bash
sudo systemctl restart safelens-api
sudo systemctl status safelens-api
```

### Check backend logs

```bash
sudo journalctl -u safelens-api -n 200 --no-pager
```

## 4. RDS Checks

### List databases

```bash
PGPASSWORD='<DB_PASSWORD>' psql \
  -h safelensai-database-v1.chmsomou27n1.ap-south-1.rds.amazonaws.com \
  -p 5432 \
  -U safelens_user \
  -d postgres \
  -c "\l"
```

### List schemas in `worker_safety_db`

```bash
PGPASSWORD='<DB_PASSWORD>' psql \
  -h safelensai-database-v1.chmsomou27n1.ap-south-1.rds.amazonaws.com \
  -p 5432 \
  -U safelens_user \
  -d worker_safety_db \
  -c "SELECT schema_name FROM information_schema.schemata ORDER BY schema_name;"
```

### List all application tables

```bash
PGPASSWORD='<DB_PASSWORD>' psql \
  -h safelensai-database-v1.chmsomou27n1.ap-south-1.rds.amazonaws.com \
  -p 5432 \
  -U safelens_user \
  -d worker_safety_db \
  -c "
  SELECT table_schema, table_name
  FROM information_schema.tables
  WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
  ORDER BY table_schema, table_name;
"
```

### Check recent incidents and media paths

```bash
PGPASSWORD='<DB_PASSWORD>' psql \
  -h safelensai-database-v1.chmsomou27n1.ap-south-1.rds.amazonaws.com \
  -p 5432 \
  -U safelens_user \
  -d worker_safety_db \
  -c "
  SELECT
    e.event_id,
    e.event_type,
    f.storage_path AS image_storage_path,
    c.storage_path AS video_storage_path
  FROM events.events e
  LEFT JOIN media.event_media_map fm
    ON fm.event_id = e.event_id AND fm.media_type = 'FRAME'
  LEFT JOIN media.frames f
    ON f.frame_id = fm.media_id
  LEFT JOIN media.event_media_map cm
    ON cm.event_id = e.event_id AND cm.media_type = 'CLIP'
  LEFT JOIN media.clips c
    ON c.clip_id = cm.media_id
  ORDER BY e.event_id DESC
  LIMIT 10;
"
```

### Check incidents with location

```bash
PGPASSWORD='<DB_PASSWORD>' psql \
  -h safelensai-database-v1.chmsomou27n1.ap-south-1.rds.amazonaws.com \
  -p 5432 \
  -U safelens_user \
  -d worker_safety_db \
  -c "
  SELECT
    e.event_id,
    e.event_type,
    cam.location,
    f.storage_path AS image_storage_path,
    c.storage_path AS video_storage_path
  FROM events.events e
  LEFT JOIN core.camera cam
    ON cam.camera_id = e.camera_id
  LEFT JOIN media.event_media_map fm
    ON fm.event_id = e.event_id AND fm.media_type = 'FRAME'
  LEFT JOIN media.frames f
    ON f.frame_id = fm.media_id
  LEFT JOIN media.event_media_map cm
    ON cm.event_id = e.event_id AND cm.media_type = 'CLIP'
  LEFT JOIN media.clips c
    ON c.clip_id = cm.media_id
  ORDER BY e.event_id DESC
  LIMIT 10;
"
```

### Check recent users

```bash
PGPASSWORD='<DB_PASSWORD>' psql \
  -h safelensai-database-v1.chmsomou27n1.ap-south-1.rds.amazonaws.com \
  -p 5432 \
  -U safelens_user \
  -d worker_safety_db \
  -c "
  SELECT id, username, is_staff, is_superuser, is_active
  FROM public.auth_user
  ORDER BY id DESC
  LIMIT 20;
"
```

### Check user profiles

```bash
PGPASSWORD='<DB_PASSWORD>' psql \
  -h safelensai-database-v1.chmsomou27n1.ap-south-1.rds.amazonaws.com \
  -p 5432 \
  -U safelens_user \
  -d worker_safety_db \
  -c "
  SELECT user_id, role, location, status, can_comment
  FROM public.user_profiles
  ORDER BY user_id DESC
  LIMIT 20;
"
```

## 5. API Checks

### Login and get token

```bash
curl -s https://safelens-dev-api.prodisyn.com/api/login/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"Admin@123"}'
```

### Verify backend root response headers

```bash
curl -I https://safelens-dev-api.prodisyn.com/
```

### Verify overview events

Replace `REAL_TOKEN_HERE` with the token returned by login.

```bash
curl -s 'https://safelens-dev-api.prodisyn.com/api/overview/events/?time_range=week' \
  -H 'Authorization: Token REAL_TOKEN_HERE'
```

### Save overview events response for inspection

```bash
curl -s 'https://safelens-dev-api.prodisyn.com/api/overview/events/?time_range=week' \
  -H 'Authorization: Token REAL_TOKEN_HERE' \
  -o /tmp/events.json
```

### Print first 5 events with media

```bash
python3 -c "
import json
data=json.load(open('/tmp/events.json'))
rows=data if isinstance(data,list) else data.get('results',[])
for row in rows[:5]:
    print('event_id:', row.get('event_id'))
    print('image_url:', row.get('image_url'))
    print('video_url:', row.get('video_url'))
    print('event_type:', row.get('event_type'))
    print('-'*60)
"
```

### Check overview summary

```bash
curl -s 'https://safelens-dev-api.prodisyn.com/api/overview/summary/?time_range=week' \
  -H 'Authorization: Token REAL_TOKEN_HERE'
```

### Check latest incidents

```bash
curl -s 'https://safelens-dev-api.prodisyn.com/api/overview/latest/?limit=10' \
  -H 'Authorization: Token REAL_TOKEN_HERE'
```

### Check locations list

```bash
curl -s 'https://safelens-dev-api.prodisyn.com/api/locations/' \
  -H 'Authorization: Token REAL_TOKEN_HERE'
```

### Check users list

```bash
curl -s 'https://safelens-dev-api.prodisyn.com/api/users/' \
  -H 'Authorization: Token REAL_TOKEN_HERE'
```

### Check review records

```bash
curl -s 'https://safelens-dev-api.prodisyn.com/api/reviews/?event_id=24' \
  -H 'Authorization: Token REAL_TOKEN_HERE'
```

## 6. Incident Insertion Checks

### Verify that new incidents are arriving in DB

```bash
PGPASSWORD='<DB_PASSWORD>' psql \
  -h safelensai-database-v1.chmsomou27n1.ap-south-1.rds.amazonaws.com \
  -p 5432 \
  -U safelens_user \
  -d worker_safety_db \
  -c "
  SELECT event_id, event_type, timestamp
  FROM events.events
  ORDER BY event_id DESC
  LIMIT 20;
"
```

### Verify media mapping rows

```bash
PGPASSWORD='<DB_PASSWORD>' psql \
  -h safelensai-database-v1.chmsomou27n1.ap-south-1.rds.amazonaws.com \
  -p 5432 \
  -U safelens_user \
  -d worker_safety_db \
  -c "
  SELECT *
  FROM media.event_media_map
  ORDER BY event_id DESC
  LIMIT 20;
"
```

## 7. S3 Checks

### Verify image object accessibility

```bash
curl -I 'https://safelensai-dev-storage-data.s3.ap-south-1.amazonaws.com/storage/incidents/images/ppe-violation/shopfloor1/camera_1/2026-05-13/ec2_upload_14-29-15_ecc7a3b4.jpg'
```

### Verify video object accessibility

```bash
curl -I 'https://safelensai-dev-storage-data.s3.ap-south-1.amazonaws.com/storage/incidents/videos/ppe-violation/shopfloor1/camera_1/2026-05-13/ec2_upload_14-29-15_6e700e79.mp4'
```

### Check object existence in S3

```bash
aws s3 ls 's3://safelensai-dev-storage-data/storage/incidents/images/ppe-violation/shopfloor1/camera_1/2026-05-13/'
aws s3 ls 's3://safelensai-dev-storage-data/storage/incidents/videos/ppe-violation/shopfloor1/camera_1/2026-05-13/'
```

### Check bucket CORS

```bash
aws s3api get-bucket-cors --bucket safelensai-dev-storage-data
```

### Check bucket policy

```bash
aws s3api get-bucket-policy --bucket safelensai-dev-storage-data
```

## 8. Media Proxy Checks

### Verify EC2 media proxy for image

```bash
curl -I 'https://safelens-dev-api.prodisyn.com/api/proxy-media/?url=https%3A%2F%2Fsafelensai-dev-storage-data.s3.ap-south-1.amazonaws.com%2Fstorage%2Fincidents%2Fimages%2Fppe-violation%2Fshopfloor1%2Fcamera_1%2F2026-05-13%2Fec2_upload_14-43-33_81a35bf6.jpg'
```

### Verify EC2 media proxy for video

```bash
curl -I 'https://safelens-dev-api.prodisyn.com/api/proxy-media/?url=https%3A%2F%2Fsafelensai-dev-storage-data.s3.ap-south-1.amazonaws.com%2Fstorage%2Fincidents%2Fvideos%2Fppe-violation%2Fshopfloor1%2Fcamera_1%2F2026-05-13%2Fec2_upload_14-43-33_fba2781e.mp4'
```

### Verify forced download proxy

```bash
curl -I 'https://safelens-dev-api.prodisyn.com/api/proxy-download/?url=https%3A%2F%2Fsafelensai-dev-storage-data.s3.ap-south-1.amazonaws.com%2Fstorage%2Fincidents%2Fimages%2Fppe-violation%2Fshopfloor1%2Fcamera_1%2F2026-05-13%2Fec2_upload_14-43-33_81a35bf6.jpg'
```

## 9. Frontend Build Checks

### Verify frontend env

```bash
cd ~/app/frontend-dashboard
cat .env
```

### Build frontend locally

```bash
cd ~/app/frontend-dashboard
npm run build
```

### Verify Amplify-facing variables expected by the frontend

```text
VITE_API_BASE_URL
VITE_AWS_STORAGE_BUCKET_NAME
VITE_AWS_S3_REGION_NAME
```

## 10. Common Expected Results

### API

- Login should return a JSON object with `token`
- `/api/overview/events/` should return event rows with `event_id`, `image_url`, and `video_url`

### RDS

- `events.events` should contain recent incidents
- `media.frames` and `media.clips` should contain media references
- `media.event_media_map` should join incidents to media

### S3

- `aws s3 ls ...` should show the incident files
- a direct `curl -I` to private objects may return `403 Forbidden`
- if private S3 is used, `proxy-media` should return `200 OK`

## 11. Troubleshooting Guide

### If DB query says relation does not exist

- Verify you are connected to `worker_safety_db`
- Verify schema-qualified table names such as:
  - `events.events`
  - `media.frames`
  - `media.clips`
  - `media.event_media_map`

### If direct S3 URL returns `403`

- Object exists but is private
- Use backend proxy:
  - `/api/proxy-media/` for inline browser rendering
  - `/api/proxy-download/` for downloads

### If UI shows no image/video

- Check backend `/api/overview/events/` response
- Check whether `image_url` and `video_url` are present
- Check browser network tab for `/api/proxy-media/`
- Check EC2 backend logs

### If API returns invalid token

- Re-run login and use the latest token
- Ensure header format is exactly:

```text
Authorization: Token <real_token>
```
