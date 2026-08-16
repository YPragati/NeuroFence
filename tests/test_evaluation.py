"""Tests for Module 7 -- security evaluation."""

from sklearn.metrics import precision_score, recall_score, f1_score


def test_perfect_prediction_metrics():
    y_true = [1, 1, 0, 0]
    y_pred = [1, 1, 0, 0]
    assert precision_score(y_true, y_pred) == 1.0
    assert recall_score(y_true, y_pred) == 1.0
    assert f1_score(y_true, y_pred) == 1.0


def test_worst_case_prediction_metrics():
    y_true = [1, 1, 0, 0]
    y_pred = [0, 0, 1, 1]
    assert precision_score(y_true, y_pred, zero_division=0) == 0.0
    assert recall_score(y_true, y_pred, zero_division=0) == 0.0
