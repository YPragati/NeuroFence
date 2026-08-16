"""
Module 6 support -- Feature Extractor.

Pulls rows from behavior_scores and converts them into a numeric
feature matrix suitable for the anomaly detection models.

Features used:
    - consistency_score
    - similarity_score
    - confidence_indicator

These are exactly the 3 columns behavior_analyzer.py computed --
this module just assembles them into an (N, 3) numpy array plus
the list of score_ids so results can be written back correctly.
"""

import numpy as np
from src.db.db_manager import get_session
from src.db.models import BehaviorScore


def extract_features():
    """
    Returns:
        score_ids: list[int]  -- behavior_scores.score_id, in row order
        X: np.ndarray of shape (N, 3)
    """
    session = get_session()
    try:
        rows = session.query(BehaviorScore).all()

        score_ids = []
        features = []

        for row in rows:
            score_ids.append(row.score_id)
            features.append([
                row.consistency_score if row.consistency_score is not None else 0.0,
                row.similarity_score if row.similarity_score is not None else 0.0,
                row.confidence_indicator if row.confidence_indicator is not None else 0.0,
            ])

        X = np.array(features, dtype=float)
        return score_ids, X
    finally:
        session.close()
