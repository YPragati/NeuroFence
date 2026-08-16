"""
Module 6 -- Local Outlier Factor anomaly detector.
"""

from sklearn.neighbors import LocalOutlierFactor
from src.config_loader import get_config


def run_lof(X):
    cfg = get_config()
    contamination = cfg["anomaly_detection"]["contamination"]

    # LOF has no separate .fit()/.predict() for novelty=False mode --
    # fit_predict does both in one pass over the training data.
    model = LocalOutlierFactor(contamination=contamination, novelty=False)
    predictions = model.fit_predict(X)  # -1 = anomaly, 1 = normal
    scores = model.negative_outlier_factor_

    is_anomaly = predictions == -1
    return is_anomaly, scores
