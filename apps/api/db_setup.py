"""
db_setup.py — Django-compatible Database Initialization Adapter
================================================================
Runs once when the Django database-api server starts.
Called from ApiConfig.ready() in apps.py.

What it does:
  1. Reads connection params from Django's settings.DATABASES['default']
  2. Creates all incident schemas (core / events / media / analytics / system)
  3. Creates the users schema (Roles, Permissions, Users, Auth_Tokens, Activity_Log)
  4. Seeds default Admin and User roles
  5. Creates PostgreSQL-level login roles:
       - db_server_admin  → Database Server team  (full DDL + CRUD, SUPERUSER)
       - ai_backend_user  → AI Backend team       (incident INSERT only, no DDL)

This module is idempotent — safe to run on every server restart.
"""

from __future__ import annotations
import json
import logging
import traceback

import psycopg2
import psycopg2.pool

logger = logging.getLogger("db.setup")


# ── Incident Schema DDL ────────────────────────────────────────────────────
def _create_incident_schemas(cursor):
    for schema in ['core', 'events', 'media', 'analytics', 'system']:
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    # core
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core.Camera (
            Camera_ID  SERIAL PRIMARY KEY,
            Name       VARCHAR(100) NOT NULL UNIQUE,
            Location   VARCHAR(255),
            Stream_URL VARCHAR(255),
            is_active  BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core.Detection_Model (
            Model_ID      SERIAL PRIMARY KEY,
            Model_Name    VARCHAR(100) NOT NULL,
            Model_Version VARCHAR(50),
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(Model_Name, Model_Version)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core.Camera_Model_Map (
            Map_ID     SERIAL PRIMARY KEY,
            Camera_ID  INT NOT NULL REFERENCES core.Camera(Camera_ID)          ON DELETE CASCADE,
            Model_ID   INT NOT NULL REFERENCES core.Detection_Model(Model_ID)  ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(Camera_ID, Model_ID)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core.Subjects (
            Subject_ID   SERIAL PRIMARY KEY,
            Subject_Type VARCHAR(50)  NOT NULL,
            Reference_ID VARCHAR(100) NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(Subject_Type, Reference_ID)
        )
    """)

    # events
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events.Events (
            Event_ID   SERIAL PRIMARY KEY,
            Camera_ID  INT          NOT NULL REFERENCES core.Camera(Camera_ID),
            Event_Type VARCHAR(100) NOT NULL,
            Timestamp  TIMESTAMP    NOT NULL,
            created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events.Events (Timestamp DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_camera    ON events.Events (Camera_ID)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events.Events_Detections (
            Detection_ID      SERIAL PRIMARY KEY,
            Event_ID          INT          NOT NULL REFERENCES events.Events(Event_ID)          ON DELETE CASCADE,
            Model_ID          INT          NOT NULL REFERENCES core.Detection_Model(Model_ID),
            Detection_Type    VARCHAR(100) NOT NULL,
            Detection_Value   TEXT,
            Detection_Details JSONB,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_detections_event   ON events.Events_Detections (Event_ID)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_detections_type    ON events.Events_Detections (Detection_Type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_detections_details ON events.Events_Detections USING gin(Detection_Details)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events.Events_Subjects (
            Event_ID   INT NOT NULL REFERENCES events.Events(Event_ID)   ON DELETE CASCADE,
            Subject_ID INT NOT NULL REFERENCES core.Subjects(Subject_ID),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (Event_ID, Subject_ID)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_subjects_event   ON events.Events_Subjects (Event_ID)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_subjects_subject ON events.Events_Subjects (Subject_ID)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events.Access_Decisions (
            Decision_ID      SERIAL PRIMARY KEY,
            Event_ID         INT         NOT NULL REFERENCES events.Events(Event_ID) ON DELETE CASCADE,
            Decision         VARCHAR(50) NOT NULL,
            Decision_Details JSONB,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_event   ON events.Access_Decisions (Event_ID)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_details ON events.Access_Decisions USING gin(Decision_Details)")

    # media
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media.Frames (
            Frame_ID     SERIAL PRIMARY KEY,
            Storage_Path VARCHAR(500) NOT NULL UNIQUE,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media.Clips (
            Clip_ID      SERIAL PRIMARY KEY,
            Storage_Path VARCHAR(500) NOT NULL UNIQUE,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media.Event_Media_Map (
            Event_ID   INT         NOT NULL REFERENCES events.Events(Event_ID) ON DELETE CASCADE,
            Media_Type VARCHAR(20) NOT NULL,
            Media_ID   INT         NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (Event_ID, Media_Type, Media_ID)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_event ON media.Event_Media_Map (Event_ID)")

    # analytics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics.ppe_compliance_daily (
            Date                 DATE NOT NULL,
            Camera_ID            INT  NOT NULL REFERENCES core.Camera(Camera_ID),
            PPE_Type             VARCHAR(50) NOT NULL,
            Compliance_Count     INT DEFAULT 0,
            Non_Compliance_Count INT DEFAULT 0,
            created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (Date, Camera_ID, PPE_Type)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ppe_date   ON analytics.ppe_compliance_daily (Date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ppe_camera ON analytics.ppe_compliance_daily (Camera_ID)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics.fall_summary (
            Date           DATE NOT NULL,
            Camera_ID      INT  NOT NULL REFERENCES core.Camera(Camera_ID),
            Total_Falls    INT  DEFAULT 0,
            Critical_Falls INT  DEFAULT 0,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (Date, Camera_ID)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fall_date   ON analytics.fall_summary (Date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fall_camera ON analytics.fall_summary (Camera_ID)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics.camera_stats (
            Date               DATE        NOT NULL,
            Camera_ID          INT         NOT NULL REFERENCES core.Camera(Camera_ID),
            Total_Events       INT         DEFAULT 0,
            Detection_Accuracy NUMERIC(5,2),
            created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (Date, Camera_ID)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stats_date   ON analytics.camera_stats (Date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stats_camera ON analytics.camera_stats (Camera_ID)")

    # system
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system.processing_logs (
            Log_ID     SERIAL PRIMARY KEY,
            Log_Level  VARCHAR(20) NOT NULL,
            Message    TEXT        NOT NULL,
            Details    JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_created ON system.processing_logs (created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_details ON system.processing_logs USING gin(Details)")

    logger.info("  ✅ Incident schemas ready.")


# ── User Management Schema DDL ─────────────────────────────────────────────
def _create_user_schemas(cursor):
    cursor.execute("CREATE SCHEMA IF NOT EXISTS users")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users.Roles (
            Role_ID     SERIAL PRIMARY KEY,
            Role_Name   VARCHAR(50) NOT NULL UNIQUE,
            Description TEXT,
            is_system   BOOLEAN DEFAULT false,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users.Permissions (
            Permission_ID   SERIAL PRIMARY KEY,
            Permission_Code VARCHAR(60) NOT NULL UNIQUE,
            Description     TEXT,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users.Role_Permissions (
            Role_ID       INT NOT NULL REFERENCES users.Roles(Role_ID)            ON DELETE CASCADE,
            Permission_ID INT NOT NULL REFERENCES users.Permissions(Permission_ID) ON DELETE CASCADE,
            granted_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (Role_ID, Permission_ID)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users.Users (
            User_ID       SERIAL PRIMARY KEY,
            Username      VARCHAR(100) NOT NULL UNIQUE,
            Email         VARCHAR(255) NOT NULL UNIQUE,
            Password_Hash VARCHAR(255) NOT NULL,
            Role_ID       INT  NOT NULL REFERENCES users.Roles(Role_ID),
            is_active     BOOLEAN DEFAULT true,
            last_login    TIMESTAMP,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users.Users (Username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email    ON users.Users (Email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role     ON users.Users (Role_ID)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users.Auth_Tokens (
            Token_ID    SERIAL PRIMARY KEY,
            User_ID     INT          NOT NULL REFERENCES users.Users(User_ID) ON DELETE CASCADE,
            Token_Hash  VARCHAR(255) NOT NULL UNIQUE,
            Token_Type  VARCHAR(20)  DEFAULT 'apps.api',
            Expires_At  TIMESTAMP    NOT NULL,
            Revoked     BOOLEAN DEFAULT false,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_user    ON users.Auth_Tokens (User_ID)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_hash    ON users.Auth_Tokens (Token_Hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_expires ON users.Auth_Tokens (Expires_At)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users.Activity_Log (
            Log_ID     SERIAL PRIMARY KEY,
            User_ID    INT         REFERENCES users.Users(User_ID) ON DELETE SET NULL,
            Action     VARCHAR(100) NOT NULL,
            Details    JSONB,
            IP_Address VARCHAR(45),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_user   ON users.Activity_Log (User_ID)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_action ON users.Activity_Log (Action)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_time   ON users.Activity_Log (created_at DESC)")

    logger.info("  ✅ User management schemas ready.")


# ── Seed Default Roles & Permissions ──────────────────────────────────────
_PERMISSIONS = [
    ("incident:read",   "View incident events"),
    ("incident:insert", "Insert new incident events"),
    ("incident:delete", "Delete incident records"),
    ("user:read",       "View user accounts"),
    ("user:create",     "Create user accounts"),
    ("user:update",     "Modify user accounts"),
    ("user:delete",     "Remove user accounts"),
    ("schema:manage",   "Create or drop schemas/tables"),
    ("role:manage",     "Assign and revoke roles"),
    ("config:read",     "View system configuration"),
    ("config:write",    "Modify system configuration"),
]

_ROLE_PERMISSIONS = {
    "Admin": [p[0] for p in _PERMISSIONS],
    "User":  ["incident:read", "incident:insert"],
}


def _seed_roles(cursor):
    for code, desc in _PERMISSIONS:
        cursor.execute("""
            INSERT INTO users.Permissions (Permission_Code, Description)
            VALUES (%s, %s) ON CONFLICT (Permission_Code) DO NOTHING
        """, (code, desc))

    for role, perms in _ROLE_PERMISSIONS.items():
        cursor.execute("""
            INSERT INTO users.Roles (Role_Name, Description, is_system)
            VALUES (%s, %s, true) ON CONFLICT (Role_Name) DO NOTHING
        """, (role, f"Built-in {role} role"))

    for role, perms in _ROLE_PERMISSIONS.items():
        cursor.execute("SELECT Role_ID FROM users.Roles WHERE Role_Name = %s", (role,))
        row = cursor.fetchone()
        if not row:
            continue
        role_id = row[0]
        for code in perms:
            cursor.execute("SELECT Permission_ID FROM users.Permissions WHERE Permission_Code = %s", (code,))
            prow = cursor.fetchone()
            if not prow:
                continue
            cursor.execute("""
                INSERT INTO users.Role_Permissions (Role_ID, Permission_ID)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
            """, (role_id, prow[0]))

    logger.info("  ✅ Default roles seeded (Admin, User).")


# ── PostgreSQL Login Role Setup ────────────────────────────────────────────
def _ensure_db_roles(cursor):
    """
    Create two named PostgreSQL login roles:

    ┌─────────────────────────────────────────────────────────────────┐
    │ Role             │ Team               │ Access                  │
    ├──────────────────┼────────────────────┼─────────────────────────┤
    │ db_server_admin  │ Database Server    │ Full DDL + CRUD         │
    │                  │ (admin credential) │ SUPERUSER               │
    ├──────────────────┼────────────────────┼─────────────────────────┤
    │ ai_backend_user  │ AI Backend Team    │ Incident INSERT only    │
    │                  │ (user credential)  │ No DDL, no user schema  │
    └─────────────────────────────────────────────────────────────────┘
    """

    # db_server_admin — full access for database team (without requiring SUPERUSER to create)
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'db_server_admin') THEN
                CREATE ROLE db_server_admin
                    LOGIN PASSWORD 'DBAdmin@SafeLens2024';
            END IF;
        END $$;
    """)
    for schema in ["core", "events", "media", "analytics", "system", "users", "public"]:
        cursor.execute(f"GRANT ALL PRIVILEGES ON SCHEMA {schema}                  TO db_server_admin")
        cursor.execute(f"GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA {schema} TO db_server_admin")
        cursor.execute(f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema} TO db_server_admin")
    logger.info("  ✅ db_server_admin — full DDL + CRUD (Database Server team).")

    # ai_backend_user — incident insert only for AI team
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_backend_user') THEN
                CREATE ROLE ai_backend_user
                    LOGIN PASSWORD 'AIBackend@SafeLens2024';
            END IF;
        END $$;
    """)
    # Read cameras & models (FK resolution)
    cursor.execute("GRANT USAGE  ON SCHEMA core TO ai_backend_user")
    cursor.execute("GRANT SELECT ON ALL TABLES IN SCHEMA core TO ai_backend_user")
    # Insert events / media
    for schema in ["events", "media"]:
        cursor.execute(f"GRANT USAGE               ON SCHEMA {schema}                  TO ai_backend_user")
        cursor.execute(f"GRANT SELECT, INSERT       ON ALL TABLES    IN SCHEMA {schema} TO ai_backend_user")
        cursor.execute(f"GRANT USAGE               ON ALL SEQUENCES IN SCHEMA {schema} TO ai_backend_user")
    # Audit logging
    cursor.execute("GRANT USAGE  ON SCHEMA system TO ai_backend_user")
    cursor.execute("GRANT INSERT ON system.processing_logs TO ai_backend_user")
    cursor.execute("GRANT USAGE  ON SEQUENCE system.processing_logs_log_id_seq TO ai_backend_user")
    # Explicitly blocked
    cursor.execute("REVOKE ALL ON SCHEMA analytics FROM ai_backend_user")
    cursor.execute("REVOKE ALL ON SCHEMA users      FROM ai_backend_user")
    logger.info("  ✅ ai_backend_user — incident INSERT only, no DDL (AI Backend team).")


# ── Central Entry Point ────────────────────────────────────────────────────
def initialize_database():
    """
    Called from Django's ApiConfig.ready() on server startup.
    Reads DB config from Django settings and runs idempotent schema init.
    """
    try:
        from django.conf import settings
        db_cfg = settings.DATABASES['default']
    except Exception:
        logger.warning("Django settings not available — skipping DB init.")
        return

    db_params = {
        'dbname':   db_cfg.get('NAME', 'worker_safety_db'),
        'user':     db_cfg.get('USER', 'safelens_user'),
        'password': db_cfg.get('PASSWORD', ''),
        'host':     db_cfg.get('HOST', 'localhost'),
        'port':     int(db_cfg.get('PORT', 5432)),
    }

    logger.info("=" * 60)
    logger.info("SafeLensAI — Database Initialisation (database-api server)")
    logger.info("=" * 60)
    logger.info(f"  Host: {db_params['host']}:{db_params['port']} / DB: {db_params['dbname']}")

    conn = cursor = None
    try:
        conn = psycopg2.connect(**db_params)
        conn.autocommit = False
        cursor = conn.cursor()

        # Step 1: Incident schemas
        logger.info("Step 1/4 — Creating incident schemas...")
        _create_incident_schemas(cursor)
        conn.commit()

        # Step 2: User management schemas
        logger.info("Step 2/4 — Creating user management schema...")
        _create_user_schemas(cursor)
        conn.commit()

        # Step 3: Seed roles
        logger.info("Step 3/4 — Seeding default roles & permissions...")
        _seed_roles(cursor)
        conn.commit()

        # Step 4: DB-level roles (non-fatal)
        logger.info("Step 4/4 — Configuring PostgreSQL login roles...")
        logger.info("            db_server_admin (Database Server team)")
        logger.info("            ai_backend_user (AI Backend team)")
        try:
            _ensure_db_roles(cursor)
            conn.commit()
        except Exception as role_err:
            logger.warning("  ⚠️  Role setup skipped (insufficient privilege): %s", role_err)
            conn.rollback()

        # Log completion
        cursor.execute("""
            INSERT INTO system.processing_logs (Log_Level, Message, Details)
            VALUES ('INFO', 'Database initialization complete', %s)
        """, (json.dumps({
            "schemas": ["core", "events", "media", "analytics", "system", "users"],
            "roles": ["db_server_admin", "ai_backend_user"],
        }),))
        conn.commit()

        logger.info("=" * 60)
        logger.info("✅ Database ready — server starting.")
        logger.info("=" * 60)
    except Exception as exc:
        # Print full traceback to terminal/journalctl
        traceback.print_exc()

        # Log actual error
        logger.error("❌ Database initialization failed: %s", exc)

        # Rollback transaction safely
        if conn:
            conn.rollback()

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()
