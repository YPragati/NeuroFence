"""
Module 6 -- Isolation Forest anomaly detector.
"""

from sklearn.ensemble import IsolationForest
from src.config_loader import get_config


def run_isolation_forest(X):
    cfg = get_config()
    contamination = cfg["anomaly_detection"]["contamination"]

    model = IsolationForest(contamination=contamination, random_state=42)
    model.fit(X)

    # sklearn: -1 = anomaly, 1 = normal. decision_function: higher = more normal.
    predictions = model.predict(X)
    scores = model.decision_function(X)

    is_anomaly = predictions == -1
    return is_anomaly, scores
