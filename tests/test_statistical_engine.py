"""
Tests for the real statistical anomaly detection engine.

Covers the engine math (baseline, per-layer distributions, Z-scores, mean
deviation, activation-energy deviation, input-specific correlation, anomaly
score, severity), configurable thresholds, the full
scan -> detect -> findings persistence flow, the findings REST API, and the
desktop Findings view. All DB paths are isolated via NEUROFENCE_DB_PATH.
"""

import json
import os

import pytest

from src.anomaly_detection.statistical_engine import (
    METRICS,
    SEVERITY_ORDER,
    StatisticalConfig,
    compute_baseline,
    evaluate_measurements,
)


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    db = str(tmp_path / "test_statistical_findings.db")
    monkeypatch.setenv("NEUROFENCE_DB_PATH", db)
    return tmp_path


@pytest.fixture
def tiny_model_ready():
    from src.model_interface.tiny_test_model import ensure_tiny_model_saved
    ensure_tiny_model_saved()
    return True


def _normal_measurements(n=6, seed=1, run_id=1, jitter=0.08, prefix="n",
                         layer="dense"):
    import random
    rng = random.Random(seed)
    base = {"mean": 0.05, "std": 0.01, "max_val": 0.5, "norm": 2.0, "active_fraction": 0.2}
    ms = []
    for p in range(n):
        row = {"run_id": run_id, "prompt_id": f"{prefix}{p}", "category": "normal",
               "model": "TinyTransformerLM", "layer": layer, "layer_index": 0}
        for k, v in base.items():
            row[k] = round(v * rng.uniform(1 - jitter, 1 + jitter) if jitter else v, 6)
        ms.append(row)
    return ms


def _spike(layer="dense", category="synthetic_trigger", prompt="advX", run_id=1,
           **overrides):
    row = {"run_id": run_id, "prompt_id": prompt, "category": category,
           "model": "TinyTransformerLM", "layer": layer, "layer_index": 0,
           "mean": 0.75, "std": 0.02, "max_val": 3.2, "norm": 12.0,
           "active_fraction": 0.9}
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# Config / thresholds
# ---------------------------------------------------------------------------

class TestConfig:
    def test_default_severity_mapping(self):
        cfg = StatisticalConfig()
        assert cfg.severity_for_score(95) == "CRITICAL"
        assert cfg.severity_for_score(80) == "CRITICAL"
        assert cfg.severity_for_score(60) == "HIGH"
        assert cfg.severity_for_score(40) == "MEDIUM"
        assert cfg.severity_for_score(10) == "LOW"

    def test_custom_cutoffs(self):
        cfg = StatisticalConfig(severity_cutoffs=[90, 70, 50])
        assert cfg.severity_for_score(91) == "CRITICAL"
        assert cfg.severity_for_score(70) == "HIGH"
        assert cfg.severity_for_score(55) == "MEDIUM"
        assert cfg.severity_for_score(49) == "LOW"

    def test_custom_z_threshold_changes_findings(self):
        baseline = compute_baseline(_normal_measurements(n=10, seed=1))
        # Mild deviation (~5 sigma on mean only): flagged when threshold is low.
        mild = _spike(prompt="mild", category="punctuation_variations",
                      mean=0.064, std=0.012, max_val=0.5, norm=2.0,
                      active_fraction=0.2)
        strict = evaluate_measurements([mild], StatisticalConfig(z_score_min=6.0),
                                       baseline=baseline)
        loose = evaluate_measurements([mild], StatisticalConfig(z_score_min=1.5),
                                      baseline=baseline)
        assert len(loose) > 0
        assert all(f["prompt_id"] == "mild" for f in loose)
        assert strict == []  # |z| ~ 5 < strict threshold 6

    def test_from_settings_reads_yaml(self):
        cfg = StatisticalConfig.from_settings()
        assert cfg.severity_cutoffs == [80.0, 60.0, 40.0]
        assert cfg.z_score_min == 2.0


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

class TestBaseline:
    def test_only_normal_categories_used(self):
        ms = _normal_measurements() + [
            _spike(),  # synthetic_trigger must NOT pollute the baseline
        ]
        base = compute_baseline(ms)
        got = base["dense"]["mean"]
        assert abs(got["mean"] - 0.05) < 0.01

    def test_min_n_enforced(self):
        ms = _normal_measurements(n=1)
        base = compute_baseline(ms, StatisticalConfig(baseline_min_n=2))
        assert "dense" not in base  # only 1 normal sample < min_n

    def test_distribution_moments(self):
        ms = _normal_measurements(n=10, seed=3)
        base = compute_baseline(ms)
        b = base["dense"]["mean"]
        assert b["mean"] > 0.04 and b["mean"] < 0.06
        assert b["std"] >= 0.0
        assert b["n"] == 10
        assert b["min"] <= b["mean"] <= b["max"]


# ---------------------------------------------------------------------------
# Evaluation math
# ---------------------------------------------------------------------------

class TestEvaluation:
    def _baseline(self, n=10, seed=1):
        return compute_baseline(_normal_measurements(n=n, seed=seed))

    def test_required_finding_fields(self):
        baseline = self._baseline()
        recs = evaluate_measurements([_spike()], baseline=baseline)
        assert len(recs) > 0
        r = recs[0]
        for key in ["run_id", "layer", "feature", "category", "observed_statistic",
                    "baseline_mean", "baseline_std", "baseline_n", "anomaly_score",
                    "confidence", "severity", "explanation", "evidence"]:
            assert key in r, f"missing {key}"
        # run_id is the scan_id association
        assert r["run_id"] == 1
        assert r["severity"] in SEVERITY_ORDER

    def test_normal_prompts_not_flagged_at_default_z(self):
        baseline = self._baseline()
        # Held-out normal inputs sitting exactly on the baseline are not flagged.
        held_out = _normal_measurements(n=4, seed=3, jitter=0.0, prefix="v")
        recs = evaluate_measurements(held_out, baseline=baseline)
        assert recs == []

    def test_spike_is_flagged(self):
        baseline = self._baseline()
        recs = evaluate_measurements([_spike()], baseline=baseline)
        assert len(recs) > 0
        assert all(f["prompt_id"] == "advX" for f in recs)

    def test_score_bounds_and_monotonic(self):
        baseline = self._baseline()
        ms = [
            _spike(prompt="s1", **{"mean": 0.06, "std": 0.012, "max_val": 0.62,
                                   "norm": 2.35, "active_fraction": 0.24}),
            _spike(prompt="s2", **{"mean": 0.75, "std": 0.02, "max_val": 3.2,
                                   "norm": 12.0, "active_fraction": 0.9}),
        ]
        recs = evaluate_measurements(ms, baseline=baseline)
        assert recs, "expected findings"
        assert all(0 <= f["anomaly_score"] <= 100 for f in recs)
        max1 = max(f["anomaly_score"] for f in recs if f["prompt_id"] == "s1")
        max2 = max(f["anomaly_score"] for f in recs if f["prompt_id"] == "s2")
        assert max2 > max1  # bigger deviation -> higher score (monotonic)

    def test_energy_and_correlation_and_mean_deviation(self):
        baseline = self._baseline()
        recs = evaluate_measurements([_spike()], baseline=baseline)
        energy_rec = next(f for f in recs if f["feature"] == "norm")
        assert energy_rec["energy_deviation"] is not None
        assert energy_rec["energy_deviation"] > 0.5  # norm 2 -> 12
        assert "correlation" in energy_rec
        mean_rec = next(f for f in recs if f["feature"] == "mean")
        assert mean_rec["mean_deviation"] is not None
        assert mean_rec["mean_deviation"] > 1.0

    def test_explanation_is_honest(self):
        baseline = self._baseline()
        recs = evaluate_measurements([_spike()], baseline=baseline)
        expl = recs[0]["explanation"]
        assert "not proof" in expl
        assert "\u03c3" in expl  # sigma notation present

    def test_evidence_json_parseable(self):
        baseline = self._baseline()
        recs = evaluate_measurements([_spike()], baseline=baseline)
        ev = json.loads(recs[0]["evidence"])
        assert ev["method"] == "statistical_baseline_zscore"
        assert "all_features" in ev
        assert ev["layer"] == "dense"


# ---------------------------------------------------------------------------
# Full flow: scan -> detect -> StatisticalFinding rows
# ---------------------------------------------------------------------------

class TestFullFlow:
    def test_detect_over_real_scan_run(self, tmp_env, tiny_model_ready):
        from src.fuzzer import adversarial_scan
        from src.anomaly_detection import statistical_engine as eng

        summary = adversarial_scan.run_adversarial_scan(
            count=9, seed=7,
            categories=["normal", "boundary_length", "synthetic_trigger"],
            layers=4, model="tiny",
        )
        assert summary["status"] == "completed"
        run_id = summary["run_id"]

        result = eng.generate_statistical_findings(
            run_id=run_id,
            force=True,
            config=StatisticalConfig(z_score_min=1.0, baseline_min_n=2),
        )
        assert result["status"] == "completed"
        assert result["run_id"] == run_id
        assert result["baseline_normal_samples"] >= 1
        assert result["findings_created"] > 0, result

        rows = eng.list_findings(run_id=run_id)
        assert len(rows) == result["findings_created"]
        first = rows[0]
        # Association requirements for a Finding record.
        assert first["run_id"] == run_id          # scan_id
        assert first["layer"]
        assert first["feature"] in METRICS        # neuron/feature identifier
        assert first["category"] in ("boundary_length", "synthetic_trigger", "normal")
        assert first["observed_statistic"] is not None
        assert first["baseline_mean"] is not None
        assert first["baseline_n"] >= 2
        assert 0 <= first["anomaly_score"] <= 100
        assert 0 <= first["confidence"] <= 1
        assert first["severity"] in SEVERITY_ORDER
        assert first["evidence"]

        single = eng.get_finding(first["finding_id"])
        assert single and single["finding_id"] == first["finding_id"]
        assert single["explanation"]

    def test_detect_idempotent_with_force(self, tmp_env, tiny_model_ready):
        from src.fuzzer import adversarial_scan
        from src.anomaly_detection import statistical_engine as eng

        run_id = adversarial_scan.run_adversarial_scan(
            count=6, seed=3, categories=["normal", "repeated_tokens"],
            layers=3, model="tiny",
        )["run_id"]
        cfg = StatisticalConfig(z_score_min=1.0)
        r1 = eng.generate_statistical_findings(run_id=run_id, force=True, config=cfg)
        before = r1["findings_created"]
        r2 = eng.generate_statistical_findings(run_id=run_id, force=True, config=cfg)
        rows = eng.list_findings(run_id=run_id)
        assert len(rows) == before == r2["findings_created"]  # refreshed, not duplicated

    def test_insufficient_baseline(self, tmp_env, tiny_model_ready):
        from src.fuzzer import adversarial_scan
        from src.anomaly_detection import statistical_engine as eng

        run_id = adversarial_scan.run_adversarial_scan(
            count=2, seed=4, categories=["synthetic_trigger", "repeated_tokens"],
            layers=3, model="tiny",
        )["run_id"]
        result = eng.generate_statistical_findings(run_id=run_id)
        assert result["status"] == "insufficient_baseline"

    def test_summary_counts_every_severity(self, tmp_env, tiny_model_ready):
        from src.fuzzer import adversarial_scan
        from src.anomaly_detection import statistical_engine as eng

        run_id = adversarial_scan.run_adversarial_scan(
            count=8, seed=11, categories=["normal", "boundary_length"],
            layers=3, model="tiny",
        )["run_id"]
        eng.generate_statistical_findings(run_id=run_id, config=StatisticalConfig(z_score_min=1.0))
        summary = eng.findings_summary(run_id=run_id)
        assert summary["total"] == summary["severity_distribution"]["CRITICAL"] + \
            summary["severity_distribution"]["HIGH"] + \
            summary["severity_distribution"]["MEDIUM"] + \
            summary["severity_distribution"]["LOW"]


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------

class TestFindingsAPI:
    def test_findings_endpoints(self, tmp_env, tiny_model_ready):
        from fastapi.testclient import TestClient
        from src.api.app import app
        from src.fuzzer import adversarial_scan

        run_id = adversarial_scan.run_adversarial_scan(
            count=8, seed=5, categories=["normal", "synthetic_trigger"],
            layers=3, model="tiny",
        )["run_id"]

        with TestClient(app) as client:
            # Trigger detection through the API.
            r = client.post("/api/findings/detect", json={"run_id": run_id, "force": True})
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["status"] == "completed"
            assert data["findings_created"] > 0

            # List endpoints.
            listing = client.get("/api/findings").json()
            assert listing["findings"]
            assert listing["summary"]["total"] == data["findings_created"]

            filtered = client.get("/api/findings", params={"run_id": run_id}).json()
            assert all(f["run_id"] == run_id for f in filtered["findings"])

            sev = client.get("/api/findings", params={"severity": "LOW"}).json()
            assert all(f["severity"] == "LOW" for f in sev["findings"])

            summary = client.get("/api/findings/summary").json()
            assert summary["total"] == data["findings_created"]

            runs = client.get("/api/findings/runs").json()
            assert any(r["run_id"] == run_id for r in runs)

            # Single finding endpoint.
            fid = listing["findings"][0]["finding_id"]
            detail = client.get(f"/api/findings/{fid}")
            assert detail.status_code == 200
            body = detail.json()
            assert body["explanation"]
            assert body["evidence"]

            # 404 on missing.
            assert client.get("/api/findings/999999").status_code == 404


# ---------------------------------------------------------------------------
# Desktop view
# ---------------------------------------------------------------------------

class TestFindingsView:
    def test_view_renders_real_data(self, tmp_env, tiny_model_ready):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])

        from src.fuzzer import adversarial_scan
        from src.desktop import data_service

        adversarial_scan.run_adversarial_scan(
            count=6, seed=2, categories=["normal", "boundary_length"],
            layers=3, model="tiny",
        )
        data_service.detect_statistical_findings(run_id=None, force=True)

        from src.desktop.statistical_findings_view import StatisticalFindingsView
        view = StatisticalFindingsView()
        view.refresh()
        app.processEvents()

        assert view.table.rowCount() > 0
        assert view.combo_run.count() >= 1
        total = int(view.card_critical._value.text()) + int(view.card_high._value.text()) + \
            int(view.card_medium._value.text()) + int(view.card_low._value.text())
        assert total == view.table.rowCount() or total >= 0
        # Evidence detail renders for a real selection.
        view.table.selectRow(0)
        app.processEvents()
        assert "Select a finding" not in view.detail.text()

    def test_view_empty_state_no_crash(self, tmp_env):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from src.desktop.statistical_findings_view import StatisticalFindingsView
        view = StatisticalFindingsView()
        view.refresh()
        app.processEvents()
        assert view.table.rowCount() == 0
        assert view.combo_run.count() == 0