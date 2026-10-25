import sqlite3
from app import config


def _path():
    return config.DATABASE_URL.replace("sqlite:///", "")


def get_conn():
    conn = sqlite3.connect(_path())
    conn.row_factory = sqlite3.Row
    return conn



SCHEMA = """
CREATE TABLE IF NOT EXISTS destinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    platform_key TEXT NOT NULL,
    connector_key TEXT NOT NULL,
    surface TEXT DEFAULT '',
    category TEXT DEFAULT '',
    audience_tags TEXT DEFAULT '',
    language TEXT DEFAULT 'en',
    geo TEXT DEFAULT '',
    est_audience INTEGER,
    rules_url TEXT DEFAULT '',
    frequency_cap_per_week INTEGER,
    self_promo_allowed INTEGER DEFAULT 1,
    link_policy TEXT DEFAULT 'allowed',
    disclosure_required INTEGER DEFAULT 0,
    automation_allowed INTEGER DEFAULT 1,
    relevance_score INTEGER,
    relevance_reason TEXT DEFAULT '',
    level TEXT DEFAULT 'L0',
    last_certified_at TEXT,
    enabled INTEGER DEFAULT 1,
    UNIQUE(normalized_url, platform_key)
);

CREATE TABLE IF NOT EXISTS certifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destination_id INTEGER NOT NULL,
    connector_key TEXT NOT NULL,
    result TEXT NOT NULL,
    failed_step TEXT,
    total_seconds REAL,
    evidence_path TEXT,
    evidence TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destination_id INTEGER,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destination_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    posted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    request TEXT NOT NULL,
    result TEXT,
    error TEXT,
    correlation_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency (
    key TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    job_id TEXT NOT NULL
);
"""



def init_db():
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
