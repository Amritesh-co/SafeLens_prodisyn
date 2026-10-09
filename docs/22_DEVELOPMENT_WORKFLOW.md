# SafeLensAI Backend Development Workflow

Use this workflow for cloud backend feature work.

## Branching

Start from the latest `develop` unless the team chooses a release/hotfix base.

```bash
git checkout develop
git pull origin develop
git checkout -b feature/<short-feature-name>
```

This import work is on:

```text
feature/cloud-integration
```

## Runtime Project

The active Django project is:

```text
safelensai
```

The active Django app is:

```text
apps/api
```

Add backend features in the existing `apps/api` boundaries unless there is a clear reason to
split a new Django app.

## Before Coding

```bash
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with local PostgreSQL and integration values.

## Change Checklist

- Keep secrets in environment variables.
- Add migrations when models change.
- Register endpoint changes in `apps/api/urls.py`.
- Keep business logic in clear helper/service functions rather than duplicating it in views.
- Update `docs/` when setup, deployment, API behavior, or operations change.
- Keep operational scripts under `scripts/`.
- Keep deployment assets under `deploy/`.
- Keep `ENABLE_DB_INIT_ON_STARTUP=0` unless deliberately running a database bootstrap.

## Verification

Run:

```bash
python manage.py check
python manage.py test
```

For production readiness, also run:

```bash
python manage.py check --deploy
```

Database-backed tests require PostgreSQL and the expected SafeLensAI schema.

## Pull Request Checklist

- Branch is based on the correct integration branch.
- `.env`, local DB files, debug HTML, and generated outputs are not committed.
- `SECRET_KEY`, database password, and cloud credentials are not hardcoded.
- `python manage.py check` passes.
- Tests are run, or any environment blocker is documented in the PR.
- Docs are updated for any changed setup, route, deployment, or script behavior.
