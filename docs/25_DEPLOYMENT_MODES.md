# Unified Ingestion Pipeline & Deployment Modes

This document describes how to configure the Django backend to support **Local Deployment** and **Cloud Deployment** using a unified ingestion pipeline and automatic background threads.

---

## 1. Where to Configure `DEPLOYMENT_MODE`

The system's active mode is defined in the root **`.env`** file via the `DEPLOYMENT_MODE` variable. 

To configure your mode, create or edit the `.env` file in the root of the project:

### Option A: Local Deployment Config
In the root `.env` file, set:
```env
DEPLOYMENT_MODE=LOCAL

# Local MQTT configuration
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_TOPIC=safelens/events
# MQTT_USERNAME=
# MQTT_PASSWORD=

# Local PostgreSQL database
DB_NAME=worker_safety_db
DB_HOST=127.0.0.1
DB_PORT=5432
...
```

### Option B: Cloud Deployment Config
In the root `.env` file, set:
```env
DEPLOYMENT_MODE=CLOUD

# AWS SQS Configuration
AWS_REGION=ap-south-1
SQS_QUEUE_URL=https://sqs.ap-south-1.amazonaws.com/.../Safelens-events-queue
AWS_ACCESS_KEY_ID=YOUR_AWS_ACCESS_KEY
AWS_SECRET_ACCESS_KEY=YOUR_AWS_SECRET_KEY

# Amazon RDS Database
DB_NAME=worker_safety_db
DB_HOST=safelensai-database-v1.chmsomou27n1.ap-south-1.rds.amazonaws.com
DB_PORT=5432
...
```

Templates for these configurations are available in the project root as `.env.local` and `.env.cloud`.

---

## 2. Ingestion Pipeline Architecture

All events enter the database through a common processing logic, ensuring no duplication of validation or DB insertion rules:

```
                      +-------------------+
                      |   REST Ingestion  |
                      | /api/events/ingest|
                      +---------+---------+
                                |
+-----------------+             |             +-----------------+
|  MQTT Consumer  |             v             |   SQS Consumer  |
| (Local Thread)  +----> process_event() <----+ (Cloud Thread)  |
+-----------------+             |             +-----------------+
                                v
                   +--------------------------+
                   |  EventCreateSerializer   |
                   +------------+-------------+
                                |
                                v
                   +------------+-------------+
                   |    PostgreSQL/RDS DB     |
                   +--------------------------+
```

1. **Common Service Layer (`apps/api/services/event_processor.py`)**:
   Contains `process_event(payload)` which takes a Python dictionary payload, validates it via `EventCreateSerializer`, performs file uploads/deduplication checks, inserts records into the database, and returns the created event object.

2. **REST API Ingestion (`POST /api/events/ingest/`)**:
   A public, unauthenticated endpoint allowing edge devices or Lambda integrations to submit event JSON payloads directly. It executes `process_event()` and returns `201 Created` on success, or `400 Bad Request` with serializer errors on validation failure.

3. **Automatic Background Consumers**:
   When starting the Django server (`python manage.py runserver` or Gunicorn), Django automatically starts the appropriate consumer as a background thread:
   * **`LOCAL` Mode**: Spawns `MQTTConsumerThread` to subscribe to the local MQTT topic.
   * **`CLOUD` Mode**: Spawns `SQSConsumerThread` to poll the SQS queue.

---

## 3. How It Works Under the Hood

### Startup Thread Control (`apps/api/apps.py`)
Django starts the background consumer threads from the `ready()` method of `ApiConfig`. To ensure clean operation and prevent issues, the following guardrails are enforced:
1. **Auto-Reloader Prevention**: Checks the Django `RUN_MAIN` environment variable. This prevents the threads from starting twice in development `runserver` reloader mode.
2. **Setup Command Guard**: Disables starting background consumers when running setup, maintenance, or compilation commands (e.g. `collectstatic`, `shell`, `showmigrations`).
3. **Database Migration & Test Guard**: Disables background threads during test runs (`pytest` / `test`) and database migrations (`migrate` / `makemigrations`) to prevent connection failures or database lock-ups.

### Automatic Reconnections
* The background **MQTT Consumer** uses `paho-mqtt`'s `loop_forever(retry_first_connection=True)` client loop, which automatically handles reconnections if the broker goes offline.
* The background **SQS Consumer** wraps the message polling request in a resilient `while True` loop that catches all connection/network exceptions, logs them, sleeps for 10 seconds, and retries.

---

## 4. Run & Startup Instructions

With this implementation, you only need to run the web server, and the consumers will start automatically in the background.

### Running Locally (LOCAL Mode)
1. Ensure your local PostgreSQL database and MQTT broker (e.g., Mosquitto) are running.
2. Set `DEPLOYMENT_MODE=LOCAL` in your `.env`.
3. Start the server:
   ```bash
   python manage.py runserver
   ```
   *The MQTT Consumer thread will start automatically in the background.*

### Running in the Cloud (CLOUD Mode)
1. Ensure RDS and SQS are configured and accessible.
2. Set `DEPLOYMENT_MODE=CLOUD` in your `.env`.
3. Start your application server (e.g. development server or gunicorn):
   ```bash
   python manage.py runserver
   # OR for production:
   gunicorn safelensai.wsgi:application
   ```
   *The SQS polling thread will start automatically in the background.*

---

## 5. Manual / CLI Commands (Alternative)

If you prefer to run the consumers in separate processes or as systemd daemons rather than in the Django application process, you can disable the background startup by omitting/unsetting the variables or using the command line commands:
* Run MQTT consumer directly:
  ```bash
  python manage.py mqtt_consumer
  ```
* Run SQS consumer directly:
  ```bash
  python manage.py consume_sqs
  ```
