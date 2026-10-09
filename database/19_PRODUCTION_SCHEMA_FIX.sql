-- SafeLensAI Master Production Sync Script
-- This script ensures ALL tables and ALL columns are perfectly synchronized with the Backend.
-- It is safe to run multiple times.
-- PGPASSWORD='SafeLens@123' psql -h <RDS_HOST> -U safelens_user -d worker_safety_db -f db/19_PRODUCTION_SCHEMA_FIX.sql

BEGIN;

-- 1. Essential Schemas
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS events;
CREATE SCHEMA IF NOT EXISTS media;
CREATE SCHEMA IF NOT EXISTS system;
CREATE SCHEMA IF NOT EXISTS analytics;

-- 2. Core Tables
CREATE TABLE IF NOT EXISTS core.Camera (
    Camera_ID   SERIAL PRIMARY KEY,
    Name        VARCHAR(100) NOT NULL UNIQUE,
    Location    VARCHAR(255),
    Stream_URL  VARCHAR(255),
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS core.Detection_Model (
    Model_ID      SERIAL PRIMARY KEY,
    Model_Name    VARCHAR(100) NOT NULL,
    Model_Version VARCHAR(50),
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(Model_Name, Model_Version)
);

CREATE TABLE IF NOT EXISTS core.Camera_Model_Map (
    Map_ID      SERIAL PRIMARY KEY,
    Camera_ID   INT NOT NULL REFERENCES core.Camera(Camera_ID) ON DELETE CASCADE,
    Model_ID    INT NOT NULL REFERENCES core.Detection_Model(Model_ID) ON DELETE CASCADE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(Camera_ID, Model_ID)
);

CREATE TABLE IF NOT EXISTS core.Subjects (
    Subject_ID   SERIAL PRIMARY KEY,
    Subject_Type VARCHAR(50)  NOT NULL,
    Reference_ID VARCHAR(100) NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(Subject_Type, Reference_ID)
);

-- 3. Events Tables
CREATE TABLE IF NOT EXISTS events.Events (
    Event_ID   SERIAL PRIMARY KEY,
    Camera_ID  INT          NOT NULL REFERENCES core.Camera(Camera_ID),
    Event_Type VARCHAR(100) NOT NULL,
    Timestamp  TIMESTAMP    NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events.Events_Detections (
    Detection_ID      SERIAL PRIMARY KEY,
    Event_ID          INT          NOT NULL REFERENCES events.Events(Event_ID) ON DELETE CASCADE,
    Model_ID          INT          NOT NULL REFERENCES core.Detection_Model(Model_ID),
    Detection_Type    VARCHAR(100) NOT NULL,
    Detection_Value   TEXT,
    Detection_Details JSONB,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events.Events_Subjects (
    Event_ID   INT NOT NULL REFERENCES events.Events(Event_ID) ON DELETE CASCADE,
    Subject_ID INT NOT NULL REFERENCES core.Subjects(Subject_ID),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (Event_ID, Subject_ID)
);

CREATE TABLE IF NOT EXISTS events.Access_Decisions (
    Decision_ID      SERIAL PRIMARY KEY,
    Event_ID         INT         NOT NULL REFERENCES events.Events(Event_ID) ON DELETE CASCADE,
    Decision         VARCHAR(50) NOT NULL,
    Decision_Details JSONB,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Media Tables
CREATE TABLE IF NOT EXISTS media.Frames (
    Frame_ID     SERIAL PRIMARY KEY,
    Storage_Path VARCHAR(500) NOT NULL UNIQUE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS media.Clips (
    Clip_ID      SERIAL PRIMARY KEY,
    Storage_Path VARCHAR(500) NOT NULL UNIQUE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS media.Event_Media_Map (
    Event_ID   INT         NOT NULL REFERENCES events.Events(Event_ID) ON DELETE CASCADE,
    Media_Type VARCHAR(20) NOT NULL,
    Media_ID   INT         NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (Event_ID, Media_Type, Media_ID)
);

-- 5. Analytics Tables
CREATE TABLE IF NOT EXISTS analytics.ppe_compliance_daily (
    Date                 DATE NOT NULL,
    Camera_ID            INT  NOT NULL REFERENCES core.Camera(Camera_ID),
    PPE_Type             VARCHAR(50) NOT NULL,
    Compliance_Count     INT DEFAULT 0,
    Non_Compliance_Count INT DEFAULT 0,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (Date, Camera_ID, PPE_Type)
);

CREATE TABLE IF NOT EXISTS analytics.fall_summary (
    Date           DATE NOT NULL,
    Camera_ID      INT  NOT NULL REFERENCES core.Camera(Camera_ID),
    Total_Falls    INT  DEFAULT 0,
    Critical_Falls INT  DEFAULT 0,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (Date, Camera_ID)
);

CREATE TABLE IF NOT EXISTS analytics.camera_stats (
    Date               DATE        NOT NULL,
    Camera_ID          INT         NOT NULL REFERENCES core.Camera(Camera_ID),
    Total_Events       INT         DEFAULT 0,
    Detection_Accuracy NUMERIC(5,2),
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (Date, Camera_ID)
);

-- 6. System Tables
CREATE TABLE IF NOT EXISTS system.processing_logs (
    Log_ID     SERIAL PRIMARY KEY,
    Log_Level  VARCHAR(20) NOT NULL,
    Message    TEXT        NOT NULL,
    Details    JSONB,
    Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Missing Column Cleanup (for existing tables)
ALTER TABLE core.Camera ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
ALTER TABLE core.Camera ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE core.Detection_Model ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE core.Camera_Model_Map ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE core.Subjects ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE events.Events ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE events.Events_Detections ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE events.Events_Subjects ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE events.Access_Decisions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE media.Frames ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE media.Clips ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE media.Event_Media_Map ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE analytics.ppe_compliance_daily ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE analytics.fall_summary ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE analytics.camera_stats ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

COMMIT;
