BEGIN;

-- ============================================================
-- REMOVE DJANGO-MANAGED TABLES IF THEY ALREADY EXIST
-- ============================================================
-- DROP TABLE IF EXISTS public.auth_password_reset_event CASCADE;
-- DROP TABLE IF EXISTS public.event_reviews CASCADE;
-- DROP TABLE IF EXISTS public.email_alert_tracker CASCADE;
-- DROP TABLE IF EXISTS public.notification_delivery_log CASCADE;
-- DROP TABLE IF EXISTS public.notification_recipients CASCADE;
-- DROP TABLE IF EXISTS public.user_activity_log CASCADE;
-- DROP TABLE IF EXISTS public.user_profiles CASCADE;
-- DROP TABLE IF EXISTS public.user_locations CASCADE;
-- DROP TABLE IF EXISTS public.tenant_use_cases CASCADE;
-- DROP TABLE IF EXISTS public.tenant_cameras CASCADE;
-- DROP TABLE IF EXISTS public.tenant_locations CASCADE;
-- DROP TABLE IF EXISTS public.tenants CASCADE;


CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS events;
CREATE SCHEMA IF NOT EXISTS media;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS system;

-- ============================================================
-- CORE: LOCATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS core.locations (
    location_id SERIAL PRIMARY KEY,
    parent_location_id INT NULL,
    code VARCHAR(100) UNIQUE,
    name VARCHAR(255) NOT NULL,
    location_type VARCHAR(50),
    timezone VARCHAR(100),
    latitude NUMERIC(9,6),
    longitude NUMERIC(9,6),

    CONSTRAINT locations_parent_fk
        FOREIGN KEY (parent_location_id)
        REFERENCES core.locations(location_id)
);

-- ============================================================
-- CORE: CAMERAS
-- Canonical replacement for both core.Camera and core.cameras.
-- ============================================================

CREATE TABLE IF NOT EXISTS core.cameras (
    camera_id SERIAL PRIMARY KEY,
    location_id INT NOT NULL,
    code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    stream_uri VARCHAR(500),
    stream_secret_ref VARCHAR(255),
    stream_protocol VARCHAR(50),
    resolution_width INT,
    resolution_height INT,
    fps NUMERIC(5,2),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_heartbeat_at TIMESTAMPTZ,

    CONSTRAINT cameras_location_fk
        FOREIGN KEY (location_id)
        REFERENCES core.locations(location_id)
);

CREATE INDEX IF NOT EXISTS cameras_location_id_idx
    ON core.cameras(location_id);

-- ============================================================
-- CORE: DETECTION MODELS / CAMERA MODEL MAPPING
-- ============================================================

CREATE TABLE IF NOT EXISTS core.detection_model (
    model_id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT detection_model_name_version_uq
        UNIQUE (model_name, model_version)
);

CREATE TABLE IF NOT EXISTS core.camera_model_map (
    map_id SERIAL PRIMARY KEY,
    camera_id INT NOT NULL,
    model_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT camera_model_map_camera_fk
        FOREIGN KEY (camera_id)
        REFERENCES core.cameras(camera_id)
        ON DELETE CASCADE,

    CONSTRAINT camera_model_map_model_fk
        FOREIGN KEY (model_id)
        REFERENCES core.detection_model(model_id)
        ON DELETE CASCADE,

    CONSTRAINT camera_model_map_unique
        UNIQUE (camera_id, model_id)
);

-- ============================================================
-- CORE: SUBJECTS
-- ============================================================

CREATE TABLE IF NOT EXISTS core.subjects (
    subject_id SERIAL PRIMARY KEY,
    subject_type VARCHAR(50) NOT NULL,
    reference_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT subjects_type_reference_uq
        UNIQUE (subject_type, reference_id)
);

-- ============================================================
-- CORE: DETECTION TYPES
-- ============================================================

CREATE TABLE IF NOT EXISTS core.detection_types (
    detection_type_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- EVENTS: TYPES / STATUSES
-- ============================================================

CREATE TABLE IF NOT EXISTS events.event_types (
    event_type_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events.event_statuses (
    status_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- EVENTS: MAIN EVENT TABLE
-- Consolidated version of events.Events + dbase3 references.
-- ============================================================

CREATE TABLE IF NOT EXISTS events.events (
    event_id SERIAL PRIMARY KEY,
    camera_id INT NOT NULL,

    -- Legacy/source-compatible event type text.
    event_type VARCHAR(100) NOT NULL,

    timestamp TIMESTAMP NOT NULL,

    -- New normalized event type/status references.
    event_type_id INTEGER NULL,
    status_id INTEGER NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT events_camera_fk
        FOREIGN KEY (camera_id)
        REFERENCES core.cameras(camera_id),

    CONSTRAINT events_event_type_fk
        FOREIGN KEY (event_type_id)
        REFERENCES events.event_types(event_type_id),

    CONSTRAINT events_status_fk
        FOREIGN KEY (status_id)
        REFERENCES events.event_statuses(status_id)
);

CREATE INDEX IF NOT EXISTS events_camera_id_idx
    ON events.events(camera_id);

CREATE INDEX IF NOT EXISTS events_timestamp_idx
    ON events.events(timestamp);

CREATE INDEX IF NOT EXISTS events_event_type_id_idx
    ON events.events(event_type_id);

CREATE INDEX IF NOT EXISTS events_status_id_idx
    ON events.events(status_id);

-- ============================================================
-- EVENTS: LEGACY / LINK TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS events.events_detections (
    detection_id SERIAL PRIMARY KEY,
    event_id INT NOT NULL,
    model_id INT NOT NULL,
    detection_type VARCHAR(100) NOT NULL,
    detection_value TEXT,
    detection_details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT events_detections_event_fk
        FOREIGN KEY (event_id)
        REFERENCES events.events(event_id)
        ON DELETE CASCADE,

    CONSTRAINT events_detections_model_fk
        FOREIGN KEY (model_id)
        REFERENCES core.detection_model(model_id)
);

CREATE INDEX IF NOT EXISTS events_detections_event_idx
    ON events.events_detections(event_id);

CREATE TABLE IF NOT EXISTS events.events_subjects (
    event_id INT NOT NULL,
    subject_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT events_subjects_event_fk
        FOREIGN KEY (event_id)
        REFERENCES events.events(event_id)
        ON DELETE CASCADE,

    CONSTRAINT events_subjects_subject_fk
        FOREIGN KEY (subject_id)
        REFERENCES core.subjects(subject_id),

    CONSTRAINT events_subjects_pk
        PRIMARY KEY (event_id, subject_id)
);

CREATE TABLE IF NOT EXISTS events.access_decisions (
    decision_id SERIAL PRIMARY KEY,
    event_id INT NOT NULL,
    decision VARCHAR(50) NOT NULL,
    decision_details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT access_decisions_event_fk
        FOREIGN KEY (event_id)
        REFERENCES events.events(event_id)
        ON DELETE CASCADE
);

-- ============================================================
-- EVENTS: STATUS HISTORY
-- ============================================================

CREATE TABLE IF NOT EXISTS events.event_status_history (
    history_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id INTEGER NOT NULL,
    status_id INTEGER NOT NULL,
    changed_by INTEGER,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    comment TEXT,

    CONSTRAINT event_status_history_event_fk
        FOREIGN KEY (event_id)
        REFERENCES events.events(event_id),

    CONSTRAINT event_status_history_status_fk
        FOREIGN KEY (status_id)
        REFERENCES events.event_statuses(status_id)
);

-- ============================================================
-- CORE: NORMALIZED DETECTIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS core.detections (
    detection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id INTEGER NOT NULL,
    detection_type_id INTEGER NOT NULL,
    model_id INTEGER,
    detection_value TEXT,
    detection_details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT detections_event_fk
        FOREIGN KEY (event_id)
        REFERENCES events.events(event_id)
        ON DELETE CASCADE,

    CONSTRAINT detections_type_fk
        FOREIGN KEY (detection_type_id)
        REFERENCES core.detection_types(detection_type_id),

    CONSTRAINT detections_model_fk
        FOREIGN KEY (model_id)
        REFERENCES core.detection_model(model_id)
);

CREATE INDEX IF NOT EXISTS detections_event_id_idx
    ON core.detections(event_id);

CREATE INDEX IF NOT EXISTS detections_type_id_idx
    ON core.detections(detection_type_id);

-- ============================================================
-- MEDIA
-- ============================================================

CREATE TABLE IF NOT EXISTS media.frames (
    frame_id SERIAL PRIMARY KEY,
    storage_path VARCHAR(500) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS media.clips (
    clip_id SERIAL PRIMARY KEY,
    storage_path VARCHAR(500) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS media.event_media_map (
    event_id INT NOT NULL,
    media_type VARCHAR(20) NOT NULL,
    media_id INT NOT NULL,

    -- Explicit references added by dbase3.
    clip_id INTEGER NULL,
    frame_id INTEGER NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT event_media_map_event_fk
        FOREIGN KEY (event_id)
        REFERENCES events.events(event_id)
        ON DELETE CASCADE,

    CONSTRAINT event_media_map_clip_fk
        FOREIGN KEY (clip_id)
        REFERENCES media.clips(clip_id)
        ON DELETE CASCADE,

    CONSTRAINT event_media_map_frame_fk
        FOREIGN KEY (frame_id)
        REFERENCES media.frames(frame_id)
        ON DELETE CASCADE,

    CONSTRAINT event_media_map_pk
        PRIMARY KEY (event_id, media_type, media_id)
);

CREATE INDEX IF NOT EXISTS event_media_map_event_idx
    ON media.event_media_map(event_id);

CREATE INDEX IF NOT EXISTS event_media_map_clip_idx
    ON media.event_media_map(clip_id);

CREATE INDEX IF NOT EXISTS event_media_map_frame_idx
    ON media.event_media_map(frame_id);

-- ============================================================
-- CORE: USERS / IDENTITY / RBAC
-- ============================================================

CREATE TABLE IF NOT EXISTS core.users (
    user_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    email VARCHAR(320),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.identity_providers (
    provider_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    provider_type VARCHAR(100) NOT NULL,
    issuer_url TEXT,
    client_id TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.user_identities (
    user_identity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id INTEGER NOT NULL,
    provider_id INTEGER NOT NULL,
    subject_identifier VARCHAR(255) NOT NULL,
    email VARCHAR(320),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT user_identities_user_fk
        FOREIGN KEY (user_id)
        REFERENCES core.users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT user_identities_provider_fk
        FOREIGN KEY (provider_id)
        REFERENCES core.identity_providers(provider_id)
        ON DELETE CASCADE,

    CONSTRAINT user_identities_provider_subject_uq
        UNIQUE (provider_id, subject_identifier)
);

CREATE TABLE IF NOT EXISTS core.roles (
    role_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.user_roles (
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_by INTEGER,

    CONSTRAINT user_roles_pkey
        PRIMARY KEY (user_id, role_id),

    CONSTRAINT user_roles_user_fk
        FOREIGN KEY (user_id)
        REFERENCES core.users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT user_roles_role_fk
        FOREIGN KEY (role_id)
        REFERENCES core.roles(role_id)
        ON DELETE CASCADE,

    CONSTRAINT user_roles_assigned_by_fk
        FOREIGN KEY (assigned_by)
        REFERENCES core.users(user_id)
);

CREATE TABLE IF NOT EXISTS core.permissions (
    permission_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code VARCHAR(150) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.role_permissions (
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    granted_by INTEGER,

    CONSTRAINT role_permissions_pkey
        PRIMARY KEY (role_id, permission_id),

    CONSTRAINT role_permissions_role_fk
        FOREIGN KEY (role_id)
        REFERENCES core.roles(role_id)
        ON DELETE CASCADE,

    CONSTRAINT role_permissions_permission_fk
        FOREIGN KEY (permission_id)
        REFERENCES core.permissions(permission_id)
        ON DELETE CASCADE,

    CONSTRAINT role_permissions_granted_by_fk
        FOREIGN KEY (granted_by)
        REFERENCES core.users(user_id)
);

CREATE TABLE IF NOT EXISTS core.idp_group_mappings (
    mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_id INTEGER NOT NULL,
    external_group VARCHAR(255) NOT NULL,
    role_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT idp_group_mappings_provider_fk
        FOREIGN KEY (provider_id)
        REFERENCES core.identity_providers(provider_id)
        ON DELETE CASCADE,

    CONSTRAINT idp_group_mappings_role_fk
        FOREIGN KEY (role_id)
        REFERENCES core.roles(role_id)
        ON DELETE CASCADE,

    CONSTRAINT idp_group_mappings_provider_group_uq
        UNIQUE (provider_id, external_group)
);

-- ============================================================
-- ============================================================
-- DJANGO-MANAGED TABLES REMOVED
-- ============================================================
-- The tables represented by the uploaded api/models.py managed
-- models are intentionally NOT created in this database schema.
--
-- Kept:
--   * Existing AI/inference tables
--   * Core RBAC/identity tables already defined by this DB schema
--   * Analytics tables
--   * Processing/system tables
--
-- Removed:
--   tenants, tenant_locations, tenant_cameras, tenant_use_cases,
--   user_locations, user_profiles, user_activity_log,
--   notification_recipients, notification_delivery_log,
--   email_alert_tracker, event_reviews, auth_password_reset_event
-- ============================================================

-- ANALYTICS
-- ============================================================

CREATE TABLE IF NOT EXISTS analytics.ppe_compliance_daily (
    date DATE NOT NULL,
    camera_id INT NOT NULL,
    ppe_type VARCHAR(50) NOT NULL,
    compliance_count INT DEFAULT 0,
    non_compliance_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ppe_compliance_camera_fk
        FOREIGN KEY (camera_id)
        REFERENCES core.cameras(camera_id),

    CONSTRAINT ppe_compliance_daily_pk
        PRIMARY KEY (date, camera_id, ppe_type)
);

CREATE TABLE IF NOT EXISTS analytics.fall_summary (
    date DATE NOT NULL,
    camera_id INT NOT NULL,
    total_falls INT DEFAULT 0,
    critical_falls INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fall_summary_camera_fk
        FOREIGN KEY (camera_id)
        REFERENCES core.cameras(camera_id),

    CONSTRAINT fall_summary_pk
        PRIMARY KEY (date, camera_id)
);

CREATE TABLE IF NOT EXISTS analytics.camera_stats (
    date DATE NOT NULL,
    camera_id INT NOT NULL,
    total_events INT DEFAULT 0,
    detection_accuracy NUMERIC(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT camera_stats_camera_fk
        FOREIGN KEY (camera_id)
        REFERENCES core.cameras(camera_id),

    CONSTRAINT camera_stats_pk
        PRIMARY KEY (date, camera_id)
);

-- ============================================================
-- SYSTEM
-- ============================================================

CREATE TABLE IF NOT EXISTS system.processing_logs (
    log_id SERIAL PRIMARY KEY,
    log_level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- USEFUL INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS user_identities_user_idx
    ON core.user_identities(user_id);

CREATE INDEX IF NOT EXISTS user_identities_provider_idx
    ON core.user_identities(provider_id);

CREATE INDEX IF NOT EXISTS user_roles_role_idx
    ON core.user_roles(role_id);

CREATE INDEX IF NOT EXISTS role_permissions_permission_idx
    ON core.role_permissions(permission_id);

CREATE INDEX IF NOT EXISTS detections_model_id_idx
    ON core.detections(model_id);

CREATE INDEX IF NOT EXISTS event_status_history_event_idx
    ON events.event_status_history(event_id);

CREATE INDEX IF NOT EXISTS event_status_history_status_idx
    ON events.event_status_history(status_id);

-- ============================================================
-- MERMAID ER DIAGRAM
-- This is intentionally inside a SQL comment so the SQL file
-- remains executable. Copy the block into Mermaid Live Editor,
-- Markdown, or a Mermaid-compatible documentation page to render.
-- ============================================================

/*
erDiagram
    LOCATIONS ||--o{ CAMERAS : contains
    LOCATIONS ||--o{ LOCATIONS : parent
    CAMERAS ||--o{ CAMERA_MODEL_MAP : uses
    DETECTION_MODEL ||--o{ CAMERA_MODEL_MAP : assigned
    CAMERAS ||--o{ EVENTS : generates
    EVENT_TYPES ||--o{ EVENTS : classifies
    EVENT_STATUSES ||--o{ EVENTS : tracks
    EVENTS ||--o{ EVENT_STATUS_HISTORY : has
    EVENT_STATUSES ||--o{ EVENT_STATUS_HISTORY : records
    USERS ||--o{ EVENT_STATUS_HISTORY : changes
    EVENTS ||--o{ EVENTS_DETECTIONS : contains
    DETECTION_MODEL ||--o{ EVENTS_DETECTIONS : detects
    EVENTS ||--o{ DETECTIONS : contains
    DETECTION_TYPES ||--o{ DETECTIONS : classifies
    DETECTION_MODEL ||--o{ DETECTIONS : uses
    EVENTS ||--o{ EVENTS_SUBJECTS : relates
    SUBJECTS ||--o{ EVENTS_SUBJECTS : relates
    EVENTS ||--o{ ACCESS_DECISIONS : has
    EVENTS ||--o{ EVENT_MEDIA_MAP : has
    CLIPS ||--o{ EVENT_MEDIA_MAP : clip
    FRAMES ||--o{ EVENT_MEDIA_MAP : frame
    USERS ||--o{ USER_IDENTITIES : has
    IDENTITY_PROVIDERS ||--o{ USER_IDENTITIES : provides
    USERS ||--o{ USER_ROLES : assigned
    ROLES ||--o{ USER_ROLES : contains
    ROLES ||--o{ ROLE_PERMISSIONS : grants
    PERMISSIONS ||--o{ ROLE_PERMISSIONS : contains
    USERS ||--o{ USER_ROLES : assigns
    USERS ||--o{ ROLE_PERMISSIONS : grants
    IDENTITY_PROVIDERS ||--o{ IDP_GROUP_MAPPINGS : maps
    ROLES ||--o{ IDP_GROUP_MAPPINGS : maps
    TENANTS ||--o{ TENANT_LOCATIONS : owns
    TENANTS ||--o{ TENANT_CAMERAS : owns
    CAMERAS ||--o{ TENANT_CAMERAS : assigned
    TENANT_LOCATIONS ||--o{ TENANT_CAMERAS : assigned
    TENANTS ||--o{ TENANT_USE_CASES : enables
    USERS ||--o{ USER_LOCATIONS : has
    TENANT_LOCATIONS ||--o{ USER_LOCATIONS : grants
    USERS ||--o| USER_PROFILES : has
    TENANTS ||--o{ USER_PROFILES : owns
    USERS ||--o{ USER_ACTIVITY_LOG : logs
    EVENTS ||--o{ NOTIFICATION_DELIVERY_LOG : triggers
    EVENTS ||--o| EVENT_REVIEWS : reviewed
    USERS ||--o{ EVENT_REVIEWS : updates
    USERS ||--o{ AUTH_PASSWORD_RESET_EVENT : requests
    CAMERAS ||--o{ PPE_COMPLIANCE_DAILY : summarizes
    CAMERAS ||--o{ FALL_SUMMARY : summarizes
    CAMERAS ||--o{ CAMERA_STATS : summarizes

    LOCATIONS {
        int location_id PK
        int parent_location_id FK
        varchar code UK
        varchar name
        varchar location_type
        varchar timezone
        numeric latitude
        numeric longitude
    }

    CAMERAS {
        int camera_id PK
        int location_id FK
        varchar code UK
        varchar name
        varchar stream_uri
        varchar stream_protocol
        int resolution_width
        int resolution_height
        numeric fps
        boolean is_active
        timestamptz last_heartbeat_at
    }

    DETECTION_MODEL {
        int model_id PK
        varchar model_name
        varchar model_version
        timestamp created_at
    }

    EVENTS {
        int event_id PK
        int camera_id FK
        varchar event_type
        timestamp timestamp
        int event_type_id FK
        int status_id FK
        timestamp created_at
    }

    EVENT_TYPES {
        int event_type_id PK
        varchar code UK
        varchar name
    }

    EVENT_STATUSES {
        int status_id PK
        varchar code UK
        varchar name
    }

    DETECTIONS {
        bigint detection_id PK
        int event_id FK
        int detection_type_id FK
        int model_id FK
        text detection_value
        jsonb detection_details
    }

    DETECTION_TYPES {
        int detection_type_id PK
        varchar code UK
        varchar name
    }

    MEDIA {
        int frame_id
        int clip_id
    }

    USERS {
        int user_id PK
        varchar username UK
        varchar display_name
        varchar email
        boolean is_active
    }

    ROLES {
        int role_id PK
        varchar code UK
        varchar name
    }

    PERMISSIONS {
        int permission_id PK
        varchar code UK
        varchar name
    }

    TENANTS {
        int id PK
        varchar name UK
        varchar code UK
        boolean is_active
    }
*/

COMMIT;

-- ============================================================
-- END OF COMBINED SCHEMA
-- ============