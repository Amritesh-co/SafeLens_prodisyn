# SafeLensAI Codebase: Tests vs. Scripts Guide

This guide clarifies the segregation between the **`tests/`** folder and the **`scripts/`** folder. It lists what each file is, why it exists, and how to execute it, helping you avoid confusion.

---

## 🗺️ High-Level Directory Overview

```text
safelensai-backend-api-server/
 ├── tests/ (Django Test Suites & Ad-hoc Tests)
 │    ├── Auto Unit Tests (test_*.py)
 │    └── tests/manual/ (Manual API & Serializer Checks)
 └── scripts/ (Ops Utilities, Diagnostics, Shell & Simulators)
      ├── scripts/ops/ (Operational & Deployment Utilities)
      ├── scripts/simulators/ (Camera Edge Flow Simulators)
      ├── scripts/integration_tests/ (AWS, Alert & Validation Checks)
      ├── scripts/diagnostics/ (Media & S3 Verification)
      └── scripts/shell/ (DB Fixes & Server Controls)
```

* **`tests/`**: Contains formal test code. These verify that Python imports work, APIs respond correctly, and serializers validate data.
* **`scripts/`**: Contains subdirectories that organize operational commands (bootstrapping, S3 uploads, starting servers) and external simulators to mimic camera triggers.

---

## 🛠️ Category 1: Ops & Production-Useful Utilities
These are files you run to manage, configure, deploy, or maintain the server and database.

| Directory / Location | File / Utility Name | Action / Command to Run | What it accomplishes |
| :--- | :--- | :--- | :--- |
| **`scripts/ops/`** | `install_poll_events_systemd.sh` | `sudo bash scripts/ops/install_poll_events_systemd.sh` | Configures the notification poller as a background system service. |
| **`scripts/ops/`** | `install_dependencies.sh` | `bash scripts/ops/install_dependencies.sh` | Installs system packages and Python project requirements. |
| **`scripts/ops/`** | `start_server.sh` | `bash scripts/ops/start_server.sh` | Runs DB migrations and launches the web server + poller in the background. |
| **`scripts/ops/`** | `stop_server.sh` | `bash scripts/ops/stop_server.sh` | Kills background Django and poller processes. |
| **`scripts/ops/`** | `create_superuser.py` | `./venv/bin/python scripts/ops/create_superuser.py` | Bootstraps a default `admin` user account. |
| **`scripts/ops/`** | `migrate_to_rds.py` | `./venv/bin/python scripts/ops/migrate_to_rds.py` | Migrates SQLite tables to AWS RDS Postgres database. |
| **`scripts/ops/`** | `migrate_to_s3.py` | `./venv/bin/python scripts/ops/migrate_to_s3.py` | Uploads local media files in bulk to AWS S3 bucket. |
| **`scripts/ops/`** | `cleanup_test_data.py` | `./venv/bin/python scripts/ops/cleanup_test_data.py` | Removes mock/test data generated during demo runs. |
| **`scripts/ops/`** | `get_token.py` | `./venv/bin/python scripts/ops/get_token.py` | Fetches or creates a Django REST Framework Auth Token for API consumption. |
| **`scripts/ops/`** | `sql_shell.py` | `./venv/bin/python scripts/ops/sql_shell.py` | Starts an interactive console against local SQLite. |
| **`scripts/diagnostics/`** | `verify_media.py` | `./venv/bin/python scripts/diagnostics/verify_media.py` | Checks if database media links exist locally or on S3. |
| **`scripts/diagnostics/`** | `fix_remote_paths.py` | `./venv/bin/python scripts/diagnostics/fix_remote_paths.py` | Updates DB links when files are migrated to S3. |
| **`scripts/diagnostics/`** | `check_recent_incidents.py` | `./venv/bin/python scripts/diagnostics/check_recent_incidents.py` | Prints a quick terminal log of the most recent incidents. |
| **`scripts/diagnostics/`** | `check_frames.py` | `./venv/bin/python scripts/diagnostics/check_frames.py` | Verification tool to check Frame database records and mapping. |
| **`scripts/diagnostics/`** | `diagnostic_email.py` | `./venv/bin/python scripts/diagnostics/diagnostic_email.py` | Checks SMTP mail backend server configuration. |
| **`scripts/shell/`** | `setup.sh` | `bash scripts/shell/setup.sh` | Prepares directory permissions for deployments. |
| **`scripts/shell/`** | `run_server.sh` | `bash scripts/shell/run_server.sh` | Starts Gunicorn web server process. |
| **`scripts/shell/`** | `fix_db.sh` | `bash scripts/shell/fix_db.sh` | Applies manual database schema fixes. |

---

## 🧪 Category 2: Automated Django Unit & Integration Tests
These files live under `tests/` and are executed via Django's test framework. They check code logic and database schemas.

* **How to run them all at once:**
  ```bash
  python manage.py test
  ```

| File Name | Test Target | Description |
| :--- | :--- | :--- |
| [tests/test_imports.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/tests/test_imports.py) | Module Loading | Confirms Python can load all project sub-modules correctly without errors. |
| [tests/test_serializer.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/tests/test_serializer.py) | Data Validation | Verifies serializers properly validate and process model payloads. |
| [tests/test_toggles.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/tests/test_toggles.py) | System Settings | Tests toggle states (e.g. alert switches). |
| [tests/test_logout.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/tests/test_logout.py) | Security / Auth | Validates DRF token invalidation when logging out. |
| [tests/test_twilio.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/tests/test_twilio.py) | Notifications | Legacy integration test for Twilio alerts *(now handled by AWS)*. |

---

## 🖥️ Category 3: Manual & Ad-hoc Developer Tests
These scripts are run manually by developers using the python interpreter to test specific features, endpoints, or notifications.

> [!NOTE]
> The ad-hoc root scripts in the legacy repository (`test_api.py`, `test_serializer.py`, `test_serializer_get.py`) have been moved into the **`tests/manual/`** folder in this repository to keep the root directory clean.

| File Path | Run Command | Description |
| :--- | :--- | :--- |
| [tests/manual/test_api.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/tests/manual/test_api.py) | `./venv/bin/python tests/manual/test_api.py` | Tests endpoints using local test values. |
| [tests/manual/test_serializer.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/tests/manual/test_serializer.py) | `./venv/bin/python tests/manual/test_serializer.py` | Direct test of Django serializers without calling endpoints. |
| [tests/manual/test_serializer_get.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/tests/manual/test_serializer_get.py) | `./venv/bin/python tests/manual/test_serializer_get.py` | Tests serializer read structures for GET requests. |
| [scripts/integration_tests/test_aws_notifications.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/scripts/integration_tests/test_aws_notifications.py) | `./venv/bin/python scripts/integration_tests/test_aws_notifications.py --all` | Direct verification of AWS SMS, email, and WhatsApp connectivity. |
| [scripts/integration_tests/inject_test_incident.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/scripts/integration_tests/inject_test_incident.py) | `./venv/bin/python scripts/integration_tests/inject_test_incident.py` | Writes a dummy incident directly into the database to verify event logging. |
| [scripts/integration_tests/manual_test_alert.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/scripts/integration_tests/manual_test_alert.py) | `./venv/bin/python scripts/integration_tests/manual_test_alert.py` | Runs poller routing logic manually. |
| [scripts/integration_tests/test_email.py](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/scripts/integration_tests/test_email.py) | `./venv/bin/python scripts/integration_tests/test_email.py` | Direct SMTP check. |
| [scripts/integration_tests/validate.sh](file:///home/rajanikanth/02-prodisyn-git/safelensai-backend-api-server/scripts/integration_tests/validate.sh) | `bash scripts/integration_tests/validate.sh` | Simple curl validate call. |

---

## 📡 Category 4: Camera & Edge Event Simulators
These mimic actual camera networks posting live incident data (such as unregistered personnel or PPE compliance events) to the server.

* **How to run them:** `./venv/bin/python scripts/simulators/<file_name>.py`

| Script Name | Location | Simulation Event Type | Mapped Endpoint / Target |
| :--- | :--- | :--- | :--- |
| `simulate_ai_incident.py` | **`scripts/simulators/`** | PPE Violation (Helmet/Vest detection) | `/api/events/` |
| `simulate_cloud_incident.py` | **`scripts/simulators/`** | Gateway event synchronization packet | `/api/events/` |
| `simulate_unattended.py` | **`scripts/simulators/`** | Unattended object detection event | `/api/events/` |
| `refined_cloud_sync.py` | **`scripts/simulators/`** | Sync queue testing | `/api/events/` |
