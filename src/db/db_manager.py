"""
Thin wrapper for getting a SQLAlchemy session against the
NeuroFence SQLite database, using the path from config.
"""

import os
from sqlalchemy.orm import sessionmaker
from src.db.models import init_db
from src.config_loader import get_config


def get_session():
    cfg = get_config()
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_path = os.path.join(project_root, cfg["paths"]["db_path"])

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    engine = init_db(db_path)
    Session = sessionmaker(bind=engine)
    return Session()
