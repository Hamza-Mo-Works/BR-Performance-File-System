"""Step 2: create the empty database for the synthetic ECU workflow MVP.

Run from project root with: python -m services.database_service
No API key, external database service or additional packages are required.
"""

import sqlite3
from pathlib import Path

from config.settings import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    model_year INTEGER NOT NULL,
    engine TEXT NOT NULL,
    ecu_family TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 1 CHECK (is_synthetic = 1)
);

CREATE TABLE IF NOT EXISTS historical_projects (
    id INTEGER PRIMARY KEY,
    project_code TEXT NOT NULL UNIQUE,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    hardware_id TEXT NOT NULL,
    software_id TEXT NOT NULL,
    read_method TEXT NOT NULL,
    transmission TEXT NOT NULL,
    fuel_spec TEXT NOT NULL,
    hardware_configuration TEXT NOT NULL,
    tune_type TEXT NOT NULL,
    original_sha256 TEXT,
    reference_file_path TEXT,
    review_status TEXT NOT NULL CHECK (
        review_status IN ('REFERENCE_CANDIDATE', 'REJECTED', 'NEEDS_REVIEW')
    ),
    outcome_notes TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_history_identifiers
ON historical_projects(vehicle_id, hardware_id, software_id, tune_type);

CREATE TABLE IF NOT EXISTS technician_notes (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL UNIQUE,
    vehicle_id INTEGER REFERENCES vehicles(id),
    project_id INTEGER REFERENCES historical_projects(id),
    ecu_family TEXT NOT NULL,
    hardware_id TEXT,
    software_id TEXT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    approved_for_demo INTEGER NOT NULL DEFAULT 1
        CHECK (approved_for_demo IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY,
    request_code TEXT NOT NULL UNIQUE,
    vehicle_id INTEGER REFERENCES vehicles(id),
    upload_filename TEXT NOT NULL,
    stored_file_path TEXT NOT NULL,
    original_sha256 TEXT NOT NULL,
    hardware_id TEXT,
    software_id TEXT,
    ecu_family TEXT,
    read_method TEXT,
    transmission TEXT,
    fuel_spec TEXT,
    hardware_configuration TEXT,
    tune_type TEXT NOT NULL,
    customer_note TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'NEW' CHECK (
        status IN ('NEW', 'BLOCKED', 'REVIEW_REQUIRED', 'INFORMATION_REQUESTED', 'INTAKE_REVIEWED')
    ),
    blockers_json TEXT NOT NULL DEFAULT '[]',
    selected_reference_id INTEGER REFERENCES historical_projects(id),
    llm_summary TEXT,
    source_ids_json TEXT NOT NULL DEFAULT '[]',
    reviewer_name TEXT,
    reviewed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY,
    request_id INTEGER REFERENCES requests(id),
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""


def get_connection(db_path=DB_PATH):
    """Open a connection with named columns and foreign-key checks enabled.

    Caller must close the connection after use. The app will reuse this helper.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database(db_path=DB_PATH):
    """Create missing tables; preserve existing rows when run again."""
    connection = get_connection(db_path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
        tables = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' ORDER BY name"
        ).fetchall()
        print(f"Database ready: {Path(db_path).resolve()}")
        print("Tables: " + ", ".join(row["name"] for row in tables))
        print("Step 2 complete. Next: generate and load synthetic data.")
    finally:
        connection.close()


if __name__ == "__main__":
    init_database()
