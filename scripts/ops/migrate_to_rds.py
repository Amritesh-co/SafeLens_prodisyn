import os
import sys
import sqlite3
import psycopg2
from django.core.management import execute_from_command_line

"""
SafeLensAI: SQLite to RDS (PostgreSQL) Migration Script

Usage:
1. Set the following environment variables:
   export RDS_DB_NAME='safelens_db'
   export RDS_USER='postgres'
   export RDS_PASSWORD='your_password'
   export RDS_HOST='your-rds-endpoint.xxxx.rds.amazonaws.com'
   export RDS_PORT='5432'
2. Run: python3 migrate_to_rds.py
"""

def migrate():
    # 1. Setup Database Connections
    sqlite_path = os.path.join(os.path.dirname(__file__), '..', 'db.sqlite3')
    if not os.path.exists(sqlite_path):
        print(f"❌ SQLite database not found at {sqlite_path}")
        return

    try:
        # Get RDS credentials from environment
        dbname = os.environ.get('RDS_DB_NAME', 'safelens_db')
        user = os.environ.get('RDS_USER', 'postgres')
        password = os.environ.get('RDS_PASSWORD')
        host = os.environ.get('RDS_HOST')
        port = os.environ.get('RDS_PORT', '5432')

        if not all([password, host]):
            print("❌ RDS_PASSWORD and RDS_HOST must be set in environment variables.")
            return

        print(f"🔌 Connecting to RDS PostgreSQL ({host})...")
        pg_conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        pg_cur = pg_conn.cursor()

        print("🔌 Connecting to Local SQLite...")
        sl_conn = sqlite3.connect(sqlite_path)
        sl_cur = sl_conn.cursor()

        # 2. Extract Tables
        sl_cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in sl_cur.fetchall() if not t[0].startswith('sqlite_')]

        print(f"📊 Found {len(tables)} tables to migrate.")

        # 3. Migrate Data
        for table in tables:
            print(f"📦 Migrating table: {table}...")
            
            # Fetch data from SQLite
            sl_cur.execute(f"SELECT * FROM {table};")
            rows = sl_cur.fetchall()
            
            if not rows:
                print(f"  (Skipping empty table)")
                continue

            # Get column names
            sl_cur.execute(f"PRAGMA table_info({table});")
            cols = [c[1] for c in sl_cur.fetchall()]
            col_names = ", ".join([f'"{c}"' for c in cols])
            placeholders = ", ".join(["%s"] * len(cols))

            # Insert into PostgreSQL
            insert_query = f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING;'
            pg_cur.executemany(insert_query, rows)
            
            print(f"  ✅ Inserted {len(rows)} rows.")

        pg_conn.commit()
        print("\n🎉 Migration Complete!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
    finally:
        if 'sl_conn' in locals(): sl_conn.close()
        if 'pg_conn' in locals(): pg_conn.close()

if __name__ == "__main__":
    migrate()
