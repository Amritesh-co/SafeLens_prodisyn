# SafeLensAI Cloud Backend API

Production-oriented Django backend for SafeLensAI cloud APIs, notifications,
incident review, media delivery, user management, and operational dashboards.

The active Django project is `safelensai`; the imported cloud implementation lives in `apps/api`.

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with local PostgreSQL and integration settings, then run:

```bash
python manage.py check
python manage.py migrate
python manage.py runserver
```

API base:

```text
http://127.0.0.1:8000/api/
```

## Production Notes

- Keep `DEBUG=False`.
- Set `SECRET_KEY` from environment or a secret manager.
- Set database credentials from environment or a secret manager.
- Do not commit `.env`, debug output, local DB files, or generated logs.
- Keep startup DB initialization disabled unless a controlled deployment explicitly needs it.
- Use `python manage.py check --deploy` as part of release verification.

## Documentation

- [Setup](docs/21_SETUP.md)
- [Project structure](docs/20_PROJECT_STRUCTURE.md)
- [Development workflow](docs/22_DEVELOPMENT_WORKFLOW.md)
- [Run and verify](docs/07_RUN_AND_VERIFY.md)
- [API documentation](docs/08_API_DOCUMENTATION.md)
- [Deployment guide](docs/13_DEPLOYMENT_GUIDE.md)
- [Production handover](docs/14_PRODUCTION_HANDOVER_MANUAL.md)
- [RDS provisioning](database/16_RDS_PROVISIONING_GUIDE.md)
