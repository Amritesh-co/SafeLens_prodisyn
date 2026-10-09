-- SafeLensAI Production Deployment Script
-- =============================================================================
-- STEP 1: INITIAL BOOTSTRAP (Run this as the AWS Master User e.g. 'postgres' or 'admin')
-- Connect to 'postgres' DB first to create our environment:
-- psql -h <RDS_ENDPOINT> -U <MASTER_USER> -d postgres
--
-- RUN THESE THREE COMMANDS INSIDE THE PROMPT:
--   CREATE DATABASE worker_safety_db;
--   CREATE USER safelens_user WITH PASSWORD 'SafeLens@123';
--   GRANT ALL PRIVILEGES ON DATABASE worker_safety_db TO safelens_user;
-- =============================================================================
-- STEP 2: SCHEMA INITIALIZATION (Run this script as the SafeLens User)
-- PGPASSWORD='SafeLens@123' psql -h <RDS_HOST> -U safelens_user -d worker_safety_db -f production_schema.sql
-- =============================================================================

BEGIN;

-- 1. Create Schemas
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS events;
CREATE SCHEMA IF NOT EXISTS media;
CREATE SCHEMA IF NOT EXISTS system;
CREATE SCHEMA IF NOT EXISTS analytics;

-- 2. Core Tables (Camera and Models)
CREATE TABLE IF NOT EXISTS core.Camera (
    Camera_ID SERIAL PRIMARY KEY,
    Name VARCHAR(100) UNIQUE NOT NULL,
    Location VARCHAR(255),
    Stream_URL VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS core.Detection_Model (
    Model_ID SERIAL PRIMARY KEY,
    Model_Name VARCHAR(100) NOT NULL,
    Model_Version VARCHAR(50),
    UNIQUE(Model_Name, Model_Version)
);

CREATE TABLE IF NOT EXISTS core.Camera_Model_Map (
    Map_ID SERIAL PRIMARY KEY,
    Camera_ID INTEGER REFERENCES core.Camera(Camera_ID),
    Model_ID INTEGER REFERENCES core.Detection_Model(Model_ID)
);

CREATE TABLE IF NOT EXISTS core.Subjects (
    Subject_ID SERIAL PRIMARY KEY,
    Subject_Type VARCHAR(50),
    Reference_ID VARCHAR(100),
    UNIQUE(Subject_Type, Reference_ID)
);

-- 3. Events Tables
CREATE TABLE IF NOT EXISTS events.Events (
    Event_ID SERIAL PRIMARY KEY,
    Camera_ID INTEGER REFERENCES core.Camera(Camera_ID),
    Event_Type VARCHAR(100) NOT NULL,
    Timestamp TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS events.Events_Detections (
    Detection_ID SERIAL PRIMARY KEY,
    Event_ID INTEGER REFERENCES events.Events(Event_ID),
    Model_ID INTEGER REFERENCES core.Detection_Model(Model_ID),
    Detection_Type VARCHAR(100),
    Detection_Value VARCHAR(100),
    Detection_Details JSONB
);

CREATE TABLE IF NOT EXISTS events.Events_Subjects (
    Event_ID INTEGER REFERENCES events.Events(Event_ID),
    Subject_ID INTEGER REFERENCES core.Subjects(Subject_ID),
    PRIMARY KEY (Event_ID, Subject_ID)
);

-- 4. Media Tables
CREATE TABLE IF NOT EXISTS media.Frames (
    Frame_ID SERIAL PRIMARY KEY,
    Storage_Path VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS media.Clips (
    Clip_ID SERIAL PRIMARY KEY,
    Storage_Path VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS media.Event_Media_Map (
    Event_ID INTEGER REFERENCES events.Events(Event_ID),
    Media_Type VARCHAR(20) NOT NULL, -- 'FRAME' or 'CLIP'
    Media_ID INTEGER NOT NULL,
    PRIMARY KEY (Event_ID, Media_Type, Media_ID)
);

-- 5. System Tables
CREATE TABLE IF NOT EXISTS system.processing_logs (
    Log_ID SERIAL PRIMARY KEY,
    Timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    Log_Level VARCHAR(20),
    Message TEXT,
    Details JSONB
);

COMMIT;

-- NOTE FOR USERS:
-- Django's 'User' and 'Profile' tables are NOT included here.
-- They are handled automatically by 'python manage.py migrate' 
-- and will be created in the 'public' schema (e.g., auth_user).
