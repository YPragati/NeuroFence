"""
Module 6 -- One-Class SVM anomaly detector.
"""

from sklearn.svm import OneClassSVM
from src.config_loader import get_config


def run_ocsvm(X):
    cfg = get_config()
    contamination = cfg["anomaly_detection"]["contamination"]

    model = OneClassSVM(nu=contamination, kernel="rbf", gamma="scale")
    model.fit(X)

    predictions = model.predict(X)  # -1 = anomaly, 1 = normal
    scores = model.decision_function(X)

    is_anomaly = predictions == -1
    return is_anomaly, scores
