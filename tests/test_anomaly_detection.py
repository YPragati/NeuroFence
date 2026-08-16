"""Tests for Module 6 -- anomaly detection."""

import numpy as np
from src.anomaly_detection.isolation_forest_model import run_isolation_forest
from src.anomaly_detection.ocsvm_model import run_ocsvm
from src.anomaly_detection.lof_model import run_lof


def _sample_data():
    # 20 "normal" points clustered near (0.8, 0.8, 0.8), plus 2 clear outliers
    np.random.seed(0)
    normal = np.random.normal(loc=0.8, scale=0.05, size=(20, 3))
    outliers = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 1.0]])
    return np.vstack([normal, outliers])


def test_isolation_forest_runs():
    X = _sample_data()
    is_anomaly, scores = run_isolation_forest(X)
    assert len(is_anomaly) == len(X)
    assert len(scores) == len(X)


def test_ocsvm_runs():
    X = _sample_data()
    is_anomaly, scores = run_ocsvm(X)
    assert len(is_anomaly) == len(X)


def test_lof_runs():
    X = _sample_data()
    is_anomaly, scores = run_lof(X)
    assert len(is_anomaly) == len(X)
