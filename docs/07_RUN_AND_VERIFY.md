# How to Run, Verify, and Test with Postman

This guide explains how to start the Worker Safety API server, verify functionality using a script, and manually test different scenarios using Postman.

## Scope

Use this guide when you want to:

- run the API locally
- connect the API to a local PostgreSQL database
- connect the API to a remote PostgreSQL database
- verify that the API is responding correctly

## 1. Running the Server

### Prerequisites

#### A. System Packages (Linux/Ubuntu)
Before setting up the project, ensure you have the necessary system packages:
```bash
sudo apt update
sudo apt install python3.10-venv python3-pip libpq-dev
```

#### B. Virtual Environment Setup
If you are moving the project to a new system or folder, you **must** recreate the virtual environment to avoid "bad interpreter" errors:
```bash
# Remove existing venv if it exists
rm -rf venv

# Create a new virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install project dependencies
pip install -r requirements.txt
```

### Start the Server

#### Standard Startup
Run the following command:
```bash
python3 manage.py runserver 0.0.0.0:8000
```

#### Local PostgreSQL Database
If PostgreSQL is running on your own machine, create/load the schema first:
```bash
PGPASSWORD='<DB_PASSWORD>' psql -h localhost -U safelens_user -d worker_safety_db -f database/17_LOCAL_DB_CREATE_SCHEMA.sql
```

#### Custom Database Server
If you need to connect to a different database server on another system, you can use environment variables without changing the code:
```bash
DB_HOST="your.db.ip" DB_NAME="your_db" DB_USER="your_user" DB_PASSWORD="your_password" python3 manage.py runserver 0.0.0.0:8000
```

#### AWS RDS / Production-Oriented Database
If your database lives in AWS RDS, first review:

- `14_PRODUCTION_HANDOVER_MANUAL.md`
- `database/16_RDS_PROVISIONING_GUIDE.md`

> [!NOTE]
> This starts the local development server at `http://localhost:8000/`.
> This is an API-only project, so there is no homepage. 
> To see the API, go to: [http://localhost:8000/api/](http://localhost:8000/api/)


---

## 2. Quick Verification (Python Script)

We have provided a script to quickly check if the Overview APIs are working.
Run this command in a **new terminal tab** (keep the server running):
```bash
python3 check_api.py
```
This script will print the response status and sample data for the Events, Summary, and Graph endpoints.

---

## 3. Testing with Postman (Manual Verification)

You can use Postman (or simple `curl` commands) to inspect the specific data returned for different event types.

### Base URL
`http://localhost:8000/api/overview/`

### A. List Events (Filtered by Type)

#### Scenario 1: Fall Detection Events
- **Method**: `GET`
- **URL**: `http://localhost:8000/api/overview/events/?type=FALL_DETECTED`
- **What to check**:
    - `event_type` should be "FALL_DETECTED".
    - `image_url` should be present (e.g., `./storage/...`).

#### Scenario 2: PPE Violations
- **Method**: `GET`
- **URL**: `http://localhost:8000/api/overview/events/?type=PPE_VIOLATION`
- **What to check**:
    - `event_type` should be "PPE_VIOLATION".

#### Scenario 3: Access Denied / Intrusion
- **Method**: `GET`
- **URL**: `http://localhost:8000/api/overview/events/?type=ACCESS_DENIED`
- **What to check**:
    - `event_type` should be "ACCESS_DENIED".

#### Scenario 4: Filter by Date
- **Method**: `GET`
- **URL**: `http://localhost:8000/api/overview/events/?date=2026-02-09`
- **What to check**:
    - All returned events should have a `timestamp` on this date.

---

### B. Summary Statistics

#### Scenario 1: Get Summary for Today's Falls
- **Method**: `GET`
- **URL**: `http://localhost:8000/api/overview/summary/?date=2026-02-09&type=FALL_DETECTED`
- **Response Example**:
  ```json
  {
      "total_events": 50,
      "type_count": 5,
      "percentage": 10.0
  }
  ```
  *(Means 5 out of 50 total events today were falls, which is 10%)*

---

### C. Graph Data

#### Scenario 1: Hourly Data for Today
- **Method**: `GET`
- **URL**: `http://localhost:8000/api/overview/graph/?time_range=today`
- **What to check**:
    - Returns hourly buckets (e.g., "09:00", "10:00").
    - Values should match the events you see in the list.

#### Scenario 2: Weekly Data
- **Method**: `GET`
- **URL**: `http://localhost:8000/api/overview/graph/?time_range=week`
- **What to check**:
    - Returns daily buckets (e.g., "Mon", "Tue").

---

## 4. Troubleshooting
- **"Connection Refused"**: Ensure the server is running (`python3 manage.py runserver`).
- **"Module Not Found"**: Did you run `pip install -r requirements.txt`?
- **"500 Internal Server Error"**: Check the terminal running the server for error logs.
