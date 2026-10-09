# CI/CD Setup Context — New Pipeline for Repo B
**Purpose:** Hand this entire document to an AI assistant to set up the CI/CD pipeline for the new repo.

---

## Situation Summary

There is an existing Django backend running on an AWS EC2 instance via a GitHub Actions → S3 → AWS CodeDeploy pipeline. A **second, separate Django backend (Repo B)** needs its own independent CI/CD pipeline pointing to the **same EC2** but deploying to a **different directory** with **different systemd services** and **completely new AWS infrastructure** (new IAM user, new CodeDeploy app, new deployment group, new S3 key prefix).

---

## Existing Pipeline (DO NOT TOUCH — for reference only)

| Item | Value |
|---|---|
| GitHub Repo | Old repo (separate repo, not Repo B) |
| Branch | `develop` |
| EC2 Instance | `i-0d5d0b3e2578249aa` (ap-south-1) |
| Deploy Directory | `/home/ubuntu/safelensai-backend-server` |
| S3 Bucket | `safelens-database-server-deploy-bucket` |
| S3 Key Prefix | `worker/deploy-<git-sha>.zip` |
| CodeDeploy App | `orpheus` |
| CodeDeploy Group | `public003` |
| Systemd Service 1 | `safelens.service` (Gunicorn on port 8000) |
| Systemd Service 2 | `safelens-poll-events.service` |
| GitHub Actions file | `worker-prod-deploy.yml` |

**This pipeline must keep working exactly as-is. Do not modify anything above.**

---

## New Pipeline to Build (Repo B)

### What Already Exists on the EC2

The fullstack developer has already:
1. Cloned Repo B into `/home/ubuntu/safelensai-backend/safelensai-backend-api-server/`
2. Created a `.env` file at that path
3. Created a Python `venv` at `/home/ubuntu/safelensai-backend/safelensai-backend-api-server/venv/`

So the app directory is **ready on the EC2**. No manual EC2 work needed for directory setup.

### Target Deployment Directory on EC2

```
/home/ubuntu/safelensai-backend/safelensai-backend-api-server
```

### Current State of Repo B's CI/CD Files (Need Fixing)

Repo B was cloned from the old repo, so it inherited the old CI/CD files with **wrong paths**. These all need to be corrected:

**`appspec.yml` (currently wrong — points to old directory):**
```yaml
files:
  - source: /
    destination: /home/ubuntu/safelensai-backend-server   # ← WRONG, old path
```

**`scripts/ops/start_server.sh` (currently wrong — points to old directory and old services):**
```bash
cd /home/ubuntu/safelensai-backend-server   # ← WRONG
VENV_PYTHON=/home/ubuntu/safelensai-backend-server/venv/bin/python  # ← WRONG
sudo systemctl restart safelens.service              # ← WRONG, old service
sudo systemctl restart safelens-poll-events.service  # ← WRONG, old service
```

**`.github/workflows/worker-prod-deploy.yml` (currently wrong — uses old infra secrets):**
```yaml
# This file exists but will use new secret names after the new pipeline is set up
```

---

## What Needs to Be Created / Changed

### 1. New AWS Infrastructure (All Brand New — No Reuse)

You need to create the following **from scratch** in the AWS Console:

#### A. New IAM User for GitHub Actions
- **Purpose:** Give GitHub Actions programmatic access to S3 and CodeDeploy
- **Suggested name:** `safelensai-backend-deployer` (or similar — choose clearly different from old one)
- **Permissions needed (attach as inline or managed policy):**
  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": [
          "s3:PutObject",
          "s3:GetObject"
        ],
        "Resource": "arn:aws:s3:::safelens-database-server-deploy-bucket/safelensai-backend/*"
      },
      {
        "Effect": "Allow",
        "Action": [
          "codedeploy:CreateDeployment",
          "codedeploy:GetDeployment",
          "codedeploy:GetDeploymentConfig",
          "codedeploy:RegisterApplicationRevision"
        ],
        "Resource": "*"
      }
    ]
  }
  ```
- Generate **Access Key ID** and **Secret Access Key** — these go into Repo B's GitHub Secrets.

> **Note:** You CAN reuse the existing S3 bucket `safelens-database-server-deploy-bucket` — just use a different key prefix (`safelensai-backend/` instead of `worker/`) so the two pipelines never collide.

#### B. New CodeDeploy Application
- **Suggested name:** `safelensai-backend` (clearly different from `orpheus`)
- **Compute platform:** EC2/On-premises

#### C. New CodeDeploy Deployment Group
- **Suggested name:** `safelensai-backend-prod` (clearly different from `public003`)
- **App:** `safelensai-backend` (the one created above)
- **Deployment type:** In-place
- **Target EC2 instance:** Tag the group to target `i-0d5d0b3e2578249aa`
  - Use EC2 tag filter: Key = `Name`, Value = whatever tag is on this instance
  - OR use the instance ID directly if the console allows
- **Service role:** Use the existing CodeDeploy IAM service role on this account (it already has EC2 access — same role as the old deployment group uses)
- **Deployment config:** `CodeDeployDefault.AllAtOnce`
- **Load balancer:** None / disable

---

### 2. New Systemd Service Files on EC2 (One-Time Server Setup)

Two new systemd services need to be created on the EC2 for the new directory. These are **one-time manual steps** on the server.

#### Service 1 — Gunicorn
Create `/etc/systemd/system/safelensai-backend.service`:
```ini
[Unit]
Description=SafeLensAI Backend API (Gunicorn)
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/safelensai-backend/safelensai-backend-api-server
Environment="PATH=/home/ubuntu/safelensai-backend/safelensai-backend-api-server/venv/bin"
ExecStart=/home/ubuntu/safelensai-backend/safelensai-backend-api-server/venv/bin/gunicorn \
    --workers 3 \
    --bind 127.0.0.1:8001 \
    safelensai.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

> ⚠️ **Use port `8001`** — port `8000` is already taken by the existing pipeline's Gunicorn. Confirm the correct port with the team.

#### Service 2 — Poll Events
Create `/etc/systemd/system/safelensai-backend-poll-events.service`:
```ini
[Unit]
Description=SafeLensAI Backend API — notification poller
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/safelensai-backend/safelensai-backend-api-server
Environment=DJANGO_SETTINGS_MODULE=safelensai.settings
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/home/ubuntu/safelensai-backend/safelensai-backend-api-server/.env
ExecStart=/home/ubuntu/safelensai-backend/safelensai-backend-api-server/venv/bin/python manage.py poll_events
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

After creating both files on the EC2, run:
```bash
sudo systemctl daemon-reload
sudo systemctl enable safelensai-backend.service
sudo systemctl enable safelensai-backend-poll-events.service
sudo systemctl start safelensai-backend.service
sudo systemctl start safelensai-backend-poll-events.service
```

#### Sudoers Rule for Deployment
Add a rule so the `ubuntu` user (which CodeDeploy runs scripts as) can restart these services without a password:
```bash
echo "ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart safelensai-backend.service, /bin/systemctl restart safelensai-backend-poll-events.service" \
  | sudo tee /etc/sudoers.d/safelensai-backend-deploy
sudo chmod 0440 /etc/sudoers.d/safelensai-backend-deploy
sudo visudo -cf /etc/sudoers.d/safelensai-backend-deploy
```

---

### 3. Files to Fix in Repo B

After the AWS infra and EC2 services are set up, these 4 files in Repo B need to be corrected and committed:

#### `appspec.yml` — fix the destination path
```yaml
version: 0.0
os: linux

file_exists_behavior: OVERWRITE

files:
  - source: /
    destination: /home/ubuntu/safelensai-backend/safelensai-backend-api-server

permissions:
  - object: /home/ubuntu/safelensai-backend/safelensai-backend-api-server
    pattern: "**"
    owner: ubuntu
    group: ubuntu

hooks:
  BeforeInstall:
    - location: scripts/ops/stop_server.sh
      timeout: 60
      runas: ubuntu

  AfterInstall:
    - location: scripts/ops/install_dependencies.sh
      timeout: 300
      runas: ubuntu

  ApplicationStart:
    - location: scripts/ops/start_server.sh
      timeout: 60
      runas: ubuntu

  ValidateService:
    - location: scripts/ops/validate.sh
      timeout: 30
      runas: ubuntu
```

#### `scripts/ops/start_server.sh` — fix paths and service names
```bash
#!/bin/bash

cd /home/ubuntu/safelensai-backend/safelensai-backend-api-server

echo "Using virtual environment python"

VENV_PYTHON=/home/ubuntu/safelensai-backend/safelensai-backend-api-server/venv/bin/python

echo "Running migrations"

$VENV_PYTHON manage.py migrate

echo "Starting Django app (via systemd)"

sudo systemctl restart safelensai-backend.service

echo "Starting notification poller (via systemd)"

sudo systemctl restart safelensai-backend-poll-events.service
```

#### `scripts/ops/stop_server.sh` — already correct (pkill by process name, works for both)
No change needed.

#### `scripts/ops/validate.sh` — update port if using 8001
```bash
#!/bin/bash

echo "Validating app..."

for i in {1..30}
do
    STATUS=$(curl -L -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/admin/)

    if [ "$STATUS" = "200" ] || [ "$STATUS" = "302" ]; then
        echo "Application is healthy (HTTP $STATUS)"
        exit 0
    fi

    echo "Waiting for app... attempt $i (HTTP $STATUS)"
    sleep 2
done

echo "Application validation failed"
exit 1
```

#### `.github/workflows/worker-prod-deploy.yml` — fix S3 key prefix
```yaml
name: SafeLensAI Backend Deploy

on:
  push:
    branches:
      - develop   # ← confirm which branch triggers this
  workflow_dispatch:

env:
  AWS_REGION: ${{ secrets.AWS_REGION }}
  S3_BUCKET: ${{ secrets.S3_BUCKET }}
  APP_NAME: ${{ secrets.CODEDEPLOY_APP }}
  DEPLOY_GROUP: ${{ secrets.CODEDEPLOY_GROUP }}

jobs:
  deploy:
    name: Package and Deploy
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Package Application
        run: |
          zip -r deploy-${{ github.sha }}.zip . \
            -x "*.git*" \
            -x ".github/*" \
            -x "venv/*"

      - name: Upload to S3
        run: |
          aws s3 cp deploy-${{ github.sha }}.zip \
          s3://${{ env.S3_BUCKET }}/safelensai-backend/deploy-${{ github.sha }}.zip

      - name: Create CodeDeploy deployment
        id: deploy
        run: |
          DEPLOY_ID=$(aws deploy create-deployment \
            --application-name ${{ env.APP_NAME }} \
            --deployment-group-name ${{ env.DEPLOY_GROUP }} \
            --s3-location bucket=${{ env.S3_BUCKET }},key=safelensai-backend/deploy-${{ github.sha }}.zip,bundleType=zip \
            --query deploymentId \
            --output text)

          echo "DEPLOY_ID=$DEPLOY_ID" >> $GITHUB_ENV
          echo "Deployment started: $DEPLOY_ID"

      - name: Wait for deployment
        run: |
          aws deploy wait deployment-successful \
            --deployment-id $DEPLOY_ID

          echo "Deployment $DEPLOY_ID succeeded!"
```

---

### 4. GitHub Secrets for Repo B

Go to **Repo B on GitHub** → Settings → Secrets and variables → Actions → New repository secret.

| Secret Name | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | Access key of the **new IAM user** created above |
| `AWS_SECRET_ACCESS_KEY` | Secret key of the **new IAM user** created above |
| `AWS_REGION` | `ap-south-1` |
| `S3_BUCKET` | `safelens-database-server-deploy-bucket` |
| `CODEDEPLOY_APP` | `safelensai-backend` (new app name) |
| `CODEDEPLOY_GROUP` | `safelensai-backend-prod` (new group name) |

---

## Order of Operations (Do This in This Order)

```
Step 1 — AWS Console
    → Create new IAM user → generate access keys
    → Create new CodeDeploy Application (safelensai-backend)
    → Create new CodeDeploy Deployment Group (safelensai-backend-prod)
      targeting EC2 instance i-0d5d0b3e2578249aa

Step 2 — EC2 Server (one-time manual)
    → Create safelensai-backend.service
    → Create safelensai-backend-poll-events.service
    → sudo systemctl daemon-reload && enable && start both
    → Create /etc/sudoers.d/safelensai-backend-deploy

Step 3 — Repo B (commit and push)
    → Fix appspec.yml (destination path)
    → Fix scripts/ops/start_server.sh (paths + service names)
    → Fix scripts/ops/validate.sh (port 8001 if applicable)
    → Fix .github/workflows/worker-prod-deploy.yml (S3 key prefix + new secret names)

Step 4 — GitHub
    → Add all 6 secrets to Repo B

Step 5 — Test
    → Push a commit to the deploy branch in Repo B
    → Watch GitHub Actions run
    → Confirm CodeDeploy deployment succeeds
    → Confirm both systemd services are active and running
```

---

## Naming Summary (Quick Reference)

| Item | Old Pipeline | New Pipeline (Repo B) |
|---|---|---|
| Deploy directory | `/home/ubuntu/safelensai-backend-server` | `/home/ubuntu/safelensai-backend/safelensai-backend-api-server` |
| CodeDeploy App | `orpheus` | `safelensai-backend` |
| CodeDeploy Group | `public003` | `safelensai-backend-prod` |
| S3 key prefix | `worker/` | `safelensai-backend/` |
| Gunicorn service | `safelens.service` | `safelensai-backend.service` |
| Poll events service | `safelens-poll-events.service` | `safelensai-backend-poll-events.service` |
| Gunicorn port | `8000` | `8001` |
| Sudoers file | `/etc/sudoers.d/safelens-deploy` | `/etc/sudoers.d/safelensai-backend-deploy` |
| IAM user | (existing, unknown owner) | New user: `safelensai-backend-deployer` |
