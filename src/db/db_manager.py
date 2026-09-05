"""
Thin wrapper for getting a SQLAlchemy session against the
NeuroFence SQLite database, using the path from config.

The database path can be overridden with the NEUROFENCE_DB_PATH
environment variable (absolute, or relative to the project root).
This is used by the automated tests and by users who want to keep
results in a custom location without editing the config file.
"""

import os
import sqlite3
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
from src.db.models import init_db
from src.config_loader import get_config


def get_db_path():
    """
    Resolve the SQLite database path, honouring the NEUROFENCE_DB_PATH
    override when present.
    """
    cfg = get_config()
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    db_path = cfg["paths"]["db_path"]

    override = os.environ.get("NEUROFENCE_DB_PATH")
    if override:
        db_path = override if os.path.isabs(override) else os.path.join(project_root, override)

    return os.path.join(project_root, db_path) if not os.path.isabs(db_path) else db_path


def _migrate_schema(db_path: str) -> None:
    """
    Add columns that may be missing from an older database.
    SQLite does not support ADD COLUMN IF NOT EXISTS, so we check
    the existing columns first. This is safe to call on every session
    creation -- no-ops if columns already exist.
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(model_metadata)")
        existing = {row[1] for row in cursor.fetchall()}
        if "status" not in existing:
            conn.execute(
                "ALTER TABLE model_metadata ADD COLUMN status VARCHAR DEFAULT 'imported'"
            )
        if "scanned_at" not in existing:
            conn.execute(
                "ALTER TABLE model_metadata ADD COLUMN scanned_at DATETIME"
            )

        # Newer Report rows carry the producing scan id / format / summary.
        cursor = conn.execute("PRAGMA table_info(reports)")
        report_cols = {row[1] for row in cursor.fetchall()}
        if "scan_id" not in report_cols:
            conn.execute("ALTER TABLE reports ADD COLUMN scan_id INTEGER")
        if "format" not in report_cols:
            conn.execute("ALTER TABLE reports ADD COLUMN format VARCHAR DEFAULT 'pdf'")
        if "summary" not in report_cols:
            conn.execute("ALTER TABLE reports ADD COLUMN summary TEXT")
        conn.commit()
        conn.close()
    except Exception:  # noqa: BLE001 -- never block session creation
        pass


def _tune_engine(engine) -> None:
    """Apply SQLite concurrency settings to every connection of `engine`.

    - journal_mode=WAL lets the scan subprocess write progress while the
      desktop UI keeps polling the same database.
    - busy_timeout makes a writer wait a short time instead of failing
      immediately with "database is locked" when another writer commits.
    """
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


def get_session():
    db_path = get_db_path()

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    _migrate_schema(db_path)
    engine = init_db(db_path)
    _tune_engine(engine)
    Session = sessionmaker(bind=engine)
    return Session()
