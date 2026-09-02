"""
Thin wrapper for getting a SQLAlchemy session against the
NeuroFence SQLite database, using the path from config.

The database path can be overridden with the NEUROFENCE_DB_PATH
environment variable (absolute, or relative to the project root).
This is used by the automated tests and by users who want to keep
results in a custom location without editing the config file.
"""

import os
from sqlalchemy.orm import sessionmaker
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


def get_session():
    db_path = get_db_path()

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    engine = init_db(db_path)
    Session = sessionmaker(bind=engine)
    return Session()
