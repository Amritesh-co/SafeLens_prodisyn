# SafeLensAI Cloud Backend Setup

This branch contains the imported production-oriented Django backend from:

```text
/home/rajanikanth/02-prodisyn-git/P004-SafeLensAI-Production/database-api
```

The active Django project is `safelensai`, and the imported cloud implementation lives in `apps/api`.

## Prerequisites

- Python 3.10 or newer
- PostgreSQL 13 or newer
- Git
- pip

## Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Configure Environment

Create your local environment file:

```bash
cp .env.example .env
```

Update `.env` with environment-specific values. Production and shared environments must set
real values for:

```text
SECRET_KEY
DEBUG=False
ALLOWED_HOSTS
DB_NAME
DB_USER
DB_PASSWORD
DB_HOST
DB_PORT
PUBLIC_BASE_URL
EXTRA_ALLOWED_ORIGINS
SYSTEM_STORAGE_DIR
ENABLE_DB_INIT_ON_STARTUP
SECURE_SSL_REDIRECT
SECURE_HSTS_SECONDS
SESSION_COOKIE_SECURE
CSRF_COOKIE_SECURE
```

AWS notification and media settings should also be supplied when those integrations are enabled.

Keep `ENABLE_DB_INIT_ON_STARTUP=0` for normal local and production runs. Set it to `1`
only for a controlled bootstrap run that should create/update schemas and database roles
from `apps/api/db_setup.py`.

## Database Setup

This backend expects PostgreSQL. Schema references live in `database/`.

For local database bootstrap, start with:

```text
database/17_LOCAL_DB_CREATE_SCHEMA.sql
```

For production/RDS guidance, use:

```text
database/16_RDS_PROVISIONING_GUIDE.md
database/18_PRODUCTION_SCHEMA.sql
database/19_PRODUCTION_SCHEMA_FIX.sql
```

After PostgreSQL is available and `.env` is configured:

```bash
python manage.py migrate
```

## Verify Application

```bash
python manage.py check
python manage.py test
```

Some tests and scripts require a configured PostgreSQL database and cloud credentials.

## Run Development Server

```bash
python manage.py runserver
```

API root:

```text
http://127.0.0.1:8000/api/
```

Admin:

```text
http://127.0.0.1:8000/admin/
```

Operations dashboard:

```text
http://127.0.0.1:8000/ops/notifications/
```

## Production Run

Use Gunicorn behind Nginx or the provided service files:

```text
gunicorn_config.py
nginx_safelens.conf
supervisor_safelens.conf
deploy/systemd/
```

Before production deploy:

- Set `DEBUG=False`.
- Set a strong `SECRET_KEY`.
- Set `SECURE_SSL_REDIRECT=True` when HTTPS is terminated by Django or correctly forwarded by the proxy.
- Set `SECURE_HSTS_SECONDS` only after confirming the domain is permanently HTTPS.
- Set `SESSION_COOKIE_SECURE=True` and `CSRF_COOKIE_SECURE=True`.
- Use real `ALLOWED_HOSTS`.
- Configure PostgreSQL/RDS credentials through environment variables.
- Configure storage paths through `SYSTEM_STORAGE_DIR`.
- Configure optional alternative storage roots through `SYSTEM_STORAGE_ALT_DIRS`.
- Configure AWS credentials through environment or instance role.
- Run `python manage.py check --deploy`.
