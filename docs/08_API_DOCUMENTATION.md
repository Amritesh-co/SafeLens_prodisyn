# Worker Safety System API Documentation

This Django-based API exposes the data from the Worker Safety System database, allowing external applications (like the Dashboard) to consume real-time event data.

## Document Scope

This document is the API reference.

It is not the full production deployment guide.

Use these companion documents when needed:

- `01_START_HERE.md`: master reading order
- `07_RUN_AND_VERIFY.md`: local startup and verification
- `14_PRODUCTION_HANDOVER_MANUAL.md`: EC2-side setup summary
- `database/16_RDS_PROVISIONING_GUIDE.md`: AWS RDS bootstrap
- `database/17_LOCAL_DB_CREATE_SCHEMA.sql`: local PostgreSQL schema bootstrap

## 🚀 Getting Started

### Prerequisites

Ensure you have the virtual environment activated:
```bash
source ../.venv/bin/activate
```

### Running the API

The API supports three common modes:

1. Local API + local PostgreSQL
2. Local API + existing remote database
3. EC2 production API + AWS RDS

For the complete local run flow, see `07_RUN_AND_VERIFY.md`.
For EC2 production details, see `14_PRODUCTION_HANDOVER_MANUAL.md`.

1. Navigate to the API directory:
   ```bash
   cd /path/to/database-api
   ```

2. Start the development server:
   ```bash
   python3 manage.py runserver 0.0.0.0:8000
   ```

The API will be available at `http://localhost:8000/api/`.

### Local PostgreSQL Mode

If you want to run the API against a PostgreSQL server on your own machine:

1. Create the database and user in PostgreSQL.
2. Load the local schema bootstrap script:
   ```bash
   PGPASSWORD='<DB_PASSWORD>' psql -h localhost -U safelens_user -d worker_safety_db -f database/17_LOCAL_DB_CREATE_SCHEMA.sql
   ```
3. Start the API:
   ```bash
   python3 manage.py runserver 0.0.0.0:8000
   ```

### Remote Database Mode

If you want to run the API locally while connecting to another PostgreSQL server:

```bash
DB_HOST="your.db.ip" \
DB_NAME="your_db" \
DB_USER="your_user" \
DB_PASSWORD="your_password" \
python3 manage.py runserver 0.0.0.0:8000
```

### EC2 Production Mode

If you are running in production on EC2:

- review `14_PRODUCTION_HANDOVER_MANUAL.md`
- review `database/16_RDS_PROVISIONING_GUIDE.md`
- use `database/18_PRODUCTION_SCHEMA.sql` and `database/19_PRODUCTION_SCHEMA_FIX.sql` for production bootstrap/update operations

## 📚 API Endpoints

The API provides the following endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/events/` | GET | List all safety events (paginated) |
| `/api/events/{id}/` | GET | Get details of a specific event |
| `/api/cameras/` | GET | List all configured cameras |
| `/api/cameras/{id}/` | GET | Get details of a specific camera |
| `/api/decisions/` | GET | List access decisions (access granted/denied) |
| `/api/decisions/{id}/` | GET | Get details of a specific decision |
| `/api/overview/events/` | GET | Overview events list (filterable by date, type) |
| `/api/overview/summary/` | GET | Summary statistics (total, type count, %) |
| `/api/overview/graph/` | GET | Graph data (time_range: today, week, month) |

### Example Requests

#### Get the latest events:
```bash
curl http://localhost:8000/api/events/
```

#### Get a specific event with detections:
```bash
curl http://localhost:8000/api/events/250/
```

#### Get overview events (with specific missing PPE items):
```bash
curl "http://localhost:8000/api/overview/events/?date=2026-02-09&type=PPE_VIOLATION"
```

**Response:**
```json
[
  {
    "event_id": 123,
    "event_type": "PPE_VIOLATION",
    "timestamp": "2026-02-09T14:30:00Z",
    "location": "Zone A",
    "image_url": "http://localhost:8000/media/frames/frame_123.jpg",
    "missing_items": ["helmet", "vest"]
  }
]
```

#### Get summary statistics (with detailed breakdown):
```bash
curl "http://localhost:8000/api/overview/summary/?date=2026-02-09"
```

**Response:**
```json
{
  "total_events": 100,
  "fall_count": 20,
  "fall_percentage": 20.0,
  "intrusion_count": 15,
  "intrusion_percentage": 15.0,
  "ppe_count": 65,
  "ppe_percentage": 65.0,
  "helmet_count": 30,
  "vest_count": 25,
  "other_ppe_count": 10
}
```

#### Get graph data (grouped by incident type):
```bash
curl "http://localhost:8000/api/overview/graph/?time_range=today"
```

**Response (when viewing all types):**
```json
[
  {
    "label": "10:00",
    "fall": 5,
    "intrusion": 3,
    "helmet": 8,
    "vest": 6
  },
  {
    "label": "11:00",
    "fall": 2,
    "intrusion": 1,
    "helmet": 4,
    "vest": 3
  }
]
```

**Response (when filtering by specific type):**
```json
[
  {
    "label": "10:00",
    "count": 5
  },
  {
    "label": "11:00",
    "count": 2
  }
]
```

### Query Parameters

#### `/api/overview/events/`
- `date` (optional): Filter by date (format: YYYY-MM-DD)
- `type` (optional): Filter by event type
  - `FALL_DETECTED` - Fall incidents only
  - `INTRUSION` - Intrusion incidents only
  - `PPE_VIOLATION` - All PPE violations
  - `HELMET_MISSING` - Helmet violations only
  - `VEST_MISSING` - Vest violations only

#### `/api/overview/summary/`
- `date` (optional): Filter by date (format: YYYY-MM-DD)
- `type` (optional): Filter by event type (same options as events endpoint)

#### `/api/overview/graph/`
- `time_range` (optional): Time range for aggregation
  - `today` (default) - Last 24 hours, grouped by hour
  - `week` - Last 7 days, grouped by day
  - `month` - Last 30 days, grouped by day
- `type` (optional): Filter by event type
  - `all` (default) - Returns grouped data by incident type (fall, intrusion, helmet, vest)
  - Specific type - Returns simple count format

## 🏗️ Project Structure

- **`safelensai/`**: The main Django project folder.
- **`api/`**: The Django app containing the API logic.
  - **`models.py`**: Defines the database models (mapped to existing PostgreSQL tables).
  - **`serializers.py`**: Converts model instances to JSON.
  - **`views.py`**: Defines the API viewsets and logic.
  - **`urls.py`**: Routes URL requests to views.

## 🗄️ Database Configuration

The API connects to PostgreSQL using environment-backed Django settings.

Common variables:

- `DB_HOST`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_PORT`

The main data models map to existing PostgreSQL tables, and many of them are
`managed = False`, meaning Django will not own or migrate those tables.

Django still uses normal migrations for its own internal tables such as:

- auth users
- tokens
- sessions
- managed app tables like user profiles and notification logs

## 🛠️ Customization

To add more endpoints or modify existing ones:
1. Edit `api/models.py` if new tables are added.
2. Create a serializer in `api/serializers.py`.
3. Create a viewset in `api/views.py`.
4. Register the viewset in `api/urls.py`.
