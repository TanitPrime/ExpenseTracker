# db/init_db.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id                  SERIAL PRIMARY KEY,
    date                DATE NOT NULL,
    amount              REAL NOT NULL,
    description         TEXT,
    category            TEXT,
    subcategory         TEXT,
    category_confirmed  BOOLEAN DEFAULT FALSE,
    raw_line            TEXT,
    source_file         TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conflicts_pending (
    id              SERIAL PRIMARY KEY,
    raw_line        TEXT NOT NULL,
    source_file     TEXT,
    issue           TEXT,
    context_date    DATE,
    content_hash    TEXT UNIQUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conflict_resolutions (
    id              SERIAL PRIMARY KEY,
    content_hash    TEXT UNIQUE NOT NULL,
    action          TEXT NOT NULL,
    resolved_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def get_conn(db_url: str):
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)

def init_db(db_url: str):
    conn = get_conn(db_url)
    with conn.cursor() as cur:
        cur.execute(SCHEMA)
    conn.commit()
    conn.close()

def reset_db(db_url: str):
    conn = get_conn(db_url)
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS expenses CASCADE;")
        cur.execute("DROP TABLE IF EXISTS conflicts_pending CASCADE;")
        cur.execute("DROP TABLE IF EXISTS conflict_resolutions CASCADE;")
    conn.commit()
    conn.close()
    init_db(db_url)

