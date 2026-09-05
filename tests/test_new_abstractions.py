"""
Tests for the mid-review architectural additions:

    - ActivationTracker abstraction (synthetic + torch-ready stub)
    - AdversarialScanner (categorized, structured results)
    - BaselineDetector (explainable baseline + anomaly verdict)
    - Findings engine (structured findings + explainable score)

These are the clean, upgrade-ready seams added for the prototype so a
real HuggingFace/PyTorch model can be plugged in later without rewiring
the UI.
"""

from src.activation.tracker import (
    ActivationTracker,
    SyntheticActivationTracker,
    TorchActivationTracker,
)
from src.scanner.scanner import AdversarialScanner
from src.anomaly_detection.baseline import BaselineDetector
from src.findings.engine import generate_findings, security_score_from_findings


def test_tracker_implements_interface():
    tracker = SyntheticActivationTracker()
    assert callable(tracker.register_hooks)
    assert callable(tracker.capture_activation)
    assert callable(tracker.remove_hooks)
    assert callable(tracker.calculate_statistics)
    assert len(tracker.FEATURE_NAMES) == 6


def test_synthetic_tracker_capture():
    tracker = SyntheticActivationTracker()
    snap = tracker.capture_activation("What is the capital of France?")
    assert snap.response
    assert set(snap.features.keys()) == set(tracker.FEATURE_NAMES)


def test_synthetic_tracker_baseline_stats():
    tracker = SyntheticActivationTracker()
    snaps = [tracker.capture_activation(p) for p in (
        "a normal question", "another normal question", "third normal query")]
    stats = tracker.calculate_statistics(snaps)
    assert "prompt_length" in stats
    assert "mean" in stats["prompt_length"]
    assert "std" in stats["prompt_length"]


def test_torch_tracker_is_future_stub():
    tracker = TorchActivationTracker()
    try:
        tracker.register_hooks()
        raised = False
    except RuntimeError:
        raised = True
    assert raised  # without a real torch model it must refuse clearly


def test_scanner_produces_structured_results():
    scanner = AdversarialScanner()
    results = scanner.run_scan(
        normal_count=2, random_count=1, edge_count=1,
        adversarial_count=1, trigger_count=1, seed=42,
    )
    assert results
    r = results[0]
    assert hasattr(r, "prompt")
    assert hasattr(r, "category")
    assert hasattr(r, "response")
    assert hasattr(r, "features")
    assert hasattr(r, "timestamp")
    assert r.category in scanner.CATEGORIES


def test_scanner_covers_expected_categories():
    scanner = AdversarialScanner()
    results = scanner.run_scan(
        normal_count=2, random_count=1, edge_count=1,
        adversarial_count=1, trigger_count=0, seed=1,
    )
    cats = {r.category for r in results}
    assert {"normal", "random", "edge", "adversarial"} <= cats


def test_scanner_trigger_detected():
    scanner = AdversarialScanner()
    results = scanner.run_scan(
        normal_count=1, random_count=0, edge_count=0,
        adversarial_count=0, trigger_count=1, seed=3,
    )
    trig = [r for r in results if r.category == "trigger"][0]
    assert float(trig.trigger_signal) > 0


def test_scanner_baseline_and_score():
    scanner = AdversarialScanner()
    normal = scanner.run_scan(normal_count=4, seed=8)
    baseline = scanner.build_baseline(normal)
    assert set(baseline.keys()) == set(scanner.tracker.FEATURE_NAMES)


def test_baseline_detector_verdict():
    det = BaselineDetector(threshold=40.0)
    scanner = AdversarialScanner()
    normal = scanner.run_scan(normal_count=4, seed=9)
    det.fit([r.features for r in normal])
    t = scanner.run_scan(normal_count=1, trigger_count=1, seed=9)
    for r in t:
        verdict = det.check(r.features)
        assert 0.0 <= verdict.anomaly_score <= 100.0
        assert verdict.threshold == 40.0


def test_findings_engine_structured():
    findings = generate_findings()
    assert isinstance(findings, list)
    if findings:
        f = findings[0]
        assert f.as_dict()["severity"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert f.title
        assert f.reason
        assert f.affected
        assert f.evidence
        assert f.recommendation


def test_findings_score_explainable():
    score = security_score_from_findings(generate_findings())
    assert 0.0 <= score["score"] <= 100.0
    assert score["level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert score["finding_count"] == len(generate_findings())
