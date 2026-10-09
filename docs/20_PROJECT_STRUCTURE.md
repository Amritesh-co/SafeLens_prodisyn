# SafeLensAI Backend Production Structure

This branch keeps the original repository structure and adapts the imported cloud backend into it.

## Active Runtime Structure

```text
safelensai-backend-api-server/
├── apps/
│   ├── api/
│   │   ├── management/commands/
│   │   ├── migrations/
│   │   ├── templates/api/
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── db_setup.py
│   │   ├── models.py
│   │   ├── notification_retry.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── utils.py
│   │   └── views.py
│   ├── analytics/
│   ├── cameras/
│   ├── incidents/
│   ├── notifications/
│   └── users/
├── safelensai/
├── database/
├── deploy/
├── docs/
├── scripts/
├── tests/
├── manage.py
├── requirements.txt
├── gunicorn_config.py
├── nginx_safelens.conf
└── supervisor_safelens.conf
```

## Alignment

| Imported implementation | Repo-aligned location |
| --- | --- |
| `worker_safety_api/` | `safelensai/` |
| `api/` | `apps/api/` |

`manage.py` points to `safelensai.settings`.

## Directory Purpose

| Path | Purpose |
| --- | --- |
| `safelensai/` | Django project settings, root URL routing, ASGI, and WSGI entry points. |
| `apps/api/` | Imported cloud backend app: models, serializers, views, routes, utilities, templates, migrations, and management commands. |
| `apps/users/`, `apps/cameras/`, `apps/incidents/`, `apps/notifications/`, `apps/analytics/` | Existing domain app placeholders for future feature separation. |
| `database/` | PostgreSQL/RDS setup guides, schema SQL, and production schema fixes. |
| `deploy/` | Systemd units and deployment service assets. |
| `docs/` | Developer, architecture, API, testing, deployment, and handover documentation. |
| `scripts/` | Operational and diagnostic scripts. |
| `tests/` | Imported test and diagnostic modules. Some require configured database/cloud dependencies. |

## API Entrypoints

| Route | Purpose |
| --- | --- |
| `/api/` | Main API routes from `apps.api.urls`. |
| `/admin/` | Django admin. |
| `/ops/notifications/` | Notification operations dashboard. |
| `/<media-path>` | Controlled absolute/relative media file lookup handled by `safelensai.urls`. |

## Production Configuration Rules

- Do not commit `.env` or secrets.
- Keep `DEBUG=False` outside local development.
- Set `SECRET_KEY` from environment.
- Set database credentials from environment or deployment secret manager.
- Use `SYSTEM_STORAGE_DIR` and `SYSTEM_STORAGE_ALT_DIRS` for media path resolution.
- Keep `ENABLE_DB_INIT_ON_STARTUP=0` unless deliberately running a controlled bootstrap.
- Prefer cloud instance roles or secret managers for AWS credentials.
- Keep generated debug outputs and local databases out of Git.
