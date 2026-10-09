#!/usr/bin/env bash
set -euo pipefail

# Fix Database Connection Issues
# This script ensures the PostgreSQL user and database are correctly configured.

echo "🔧 Fixing PostgreSQL Setup..."

: "${DB_NAME:=worker_safety_db}"
: "${DB_USER:=safelens_user}"
: "${DB_PASSWORD:?DB_PASSWORD is required}"

# 1. Create User if not exists
sudo -u postgres psql -v db_user="${DB_USER}" -v db_password="${DB_PASSWORD}" -c "SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'db_user', :'db_password') WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = :'db_user')\gexec"

# 2. Reset Password (in case it exists but is wrong)
sudo -u postgres psql -v db_user="${DB_USER}" -v db_password="${DB_PASSWORD}" -c "ALTER USER :\"db_user\" WITH PASSWORD :'db_password';"

# 3. Create Database if not exists
sudo -u postgres psql -v db_name="${DB_NAME}" -v db_user="${DB_USER}" -c "SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'db_user') WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db_name')\gexec"

# 4. Grant Privileges
sudo -u postgres psql -v db_name="${DB_NAME}" -v db_user="${DB_USER}" -c "GRANT ALL PRIVILEGES ON DATABASE :\"db_name\" TO :\"db_user\";"

echo "✅ Database user and password fixed."
echo "🔄 Now run: python3 manage.py migrate"
