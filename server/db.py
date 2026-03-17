import sqlite3
from datetime import datetime, timezone
from config import DB_PATH


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS pair_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            encrypted_token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_token TEXT NOT NULL UNIQUE,
            device_name TEXT NOT NULL,
            platform TEXT,
            created_at TEXT NOT NULL,
            linked_at TEXT NOT NULL,
            last_seen_at TEXT,
            pair_session_id INTEGER,
            FOREIGN KEY(pair_session_id) REFERENCES pair_sessions(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL,
            filename TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            mime_type TEXT,
            size_bytes INTEGER NOT NULL,
            chunk_size INTEGER NOT NULL,
            total_chunks INTEGER NOT NULL,
            uploaded_chunks INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            device_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            download_token TEXT,
            download_expires_at TEXT,
            downloaded_at TEXT,
            FOREIGN KEY(device_id) REFERENCES devices(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transfer_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            byte_size INTEGER NOT NULL,
            received_at TEXT NOT NULL,
            UNIQUE(transfer_id, chunk_index),
            FOREIGN KEY(transfer_id) REFERENCES transfers(id)
        )
        """
    )

    conn.commit()
    conn.close()


def query_one(sql: str, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.close()
    return row


def query_all(sql: str, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def execute(sql: str, params=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    lastrowid = cur.lastrowid
    conn.close()
    return lastrowid


def execute_many(statements):
    conn = get_db()
    cur = conn.cursor()
    for sql, params in statements:
        cur.execute(sql, params)
    conn.commit()
    conn.close()