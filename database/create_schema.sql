-- Create Tables for Worker Safety System
-- Run this with: PGPASSWORD='SafeLens@123' psql -h localhost -U safelens_user -d worker_safety_db -f create_schema.sql

BEGIN;

CREATE TABLE IF NOT EXISTS camera (
    camera_id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    location VARCHAR(255),
    stream_url VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS detection_model (
    model_id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),
    UNIQUE(model_name, model_version)
);

CREATE TABLE IF NOT EXISTS camera_model_map (
    map_id SERIAL PRIMARY KEY,
    camera_id INTEGER REFERENCES camera(camera_id),
    model_id INTEGER REFERENCES detection_model(model_id)
);

CREATE TABLE IF NOT EXISTS events (
    event_id SERIAL PRIMARY KEY,
    camera_id INTEGER REFERENCES camera(camera_id),
    event_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

CREATE TABLE IF NOT EXISTS access_decisions (
    decision_id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(event_id),
    decision VARCHAR(50) NOT NULL,
    decision_details JSONB
);

CREATE TABLE IF NOT EXISTS events_detections (
    detection_id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(event_id),
    model_id INTEGER REFERENCES detection_model(model_id),
    detection_type VARCHAR(100),
    detection_value VARCHAR(100),
    detection_details JSONB
);

CREATE TABLE IF NOT EXISTS camera_stats (
    date DATE NOT NULL,
    camera_id INTEGER NOT NULL,
    total_events INTEGER,
    detection_accuracy DECIMAL(5,2),
    PRIMARY KEY (date, camera_id)
);

CREATE TABLE IF NOT EXISTS clips (
    clip_id SERIAL PRIMARY KEY,
    storage_path VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS frames (
    frame_id SERIAL PRIMARY KEY,
    storage_path VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS event_media_map (
    event_id INTEGER NOT NULL,
    media_type VARCHAR(20) NOT NULL,
    media_id INTEGER NOT NULL,
    PRIMARY KEY (event_id, media_type, media_id)
);
-- Note: event_media_map references events, but likely frames/clips via media_id polymorphically

CREATE TABLE IF NOT EXISTS subjects (
    subject_id SERIAL PRIMARY KEY,
    subject_type VARCHAR(50),
    reference_id VARCHAR(100),
    UNIQUE(subject_type, reference_id)
);

CREATE TABLE IF NOT EXISTS events_subjects (
    event_id INTEGER REFERENCES events(event_id),
    subject_id INTEGER REFERENCES subjects(subject_id),
    PRIMARY KEY (event_id, subject_id)
);

CREATE TABLE IF NOT EXISTS fall_summary (
    date DATE NOT NULL,
    camera_id INTEGER NOT NULL,
    total_falls INTEGER,
    critical_falls INTEGER,
    PRIMARY KEY (date, camera_id)
);

CREATE TABLE IF NOT EXISTS ppe_compliance_daily (
    date DATE NOT NULL,
    camera_id INTEGER NOT NULL,
    ppe_type VARCHAR(50) NOT NULL,
    compliance_count INTEGER,
    non_compliance_count INTEGER,
    PRIMARY KEY (date, camera_id, ppe_type)
);

COMMIT;
