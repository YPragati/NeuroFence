"""
Tests for the modular adversarial input generator and the full
Fuzzer -> Model -> Hooks -> Database adversarial scan flow.

Uses isolated test databases (NEUROFENCE_DB_PATH override) so the tests
never touch the production database.
"""

import json
import os
import subprocess
import sys
import time
import pytest

from src.fuzzer.adversarial_generator import (
    AdversarialInputGenerator,
    generate_adversarial_prompts,
    CATEGORY_KEYS,
    CATEGORY_LABELS,
)
from src.fuzzer import adversarial_scan


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    db = str(tmp_path / "test_adversarial_scan.db")
    monkeypatch.setenv("NEUROFENCE_DB_PATH", db)
    return tmp_path


@pytest.fixture
def tiny_needs_saved():
    # Ensure the tiny transformer model exists on disk for real tracking.
    from src.model_interface.tiny_test_model import ensure_tiny_model_saved
    ensure_tiny_model_saved()
    return True


# ---------------------------------------------------------------------------
# Generator unit tests
# ---------------------------------------------------------------------------

class TestAdversarialGenerator:
    def test_categories_covered(self):
        gen = AdversarialInputGenerator(seed=42)
        assert gen.categories() == CATEGORY_KEYS
        assert len(gen.categories()) == 10

    def test_category_labels(self):
        assert "Normal prompts" in CATEGORY_LABELS.values()

    def test_deterministic(self):
        p1 = generate_adversarial_prompts(count=25, seed=7)
        p2 = generate_adversarial_prompts(count=25, seed=7)
        assert [p["text"] for p in p1] == [p["text"] for p in p2]

    def test_different_seed(self):
        p1 = generate_adversarial_prompts(count=25, seed=1)
        p2 = generate_adversarial_prompts(count=25, seed=2)
        assert [p["text"] for p in p1] != [p["text"] for p in p2]

    def test_unique_prompts(self):
        prompts = generate_adversarial_prompts(count=50, seed=3)
        texts = [p["text"] for p in prompts]
        ids = [p["prompt_id"] for p in prompts]
        assert len(texts) == len(set(texts))
        assert len(ids) == len(set(ids))

    def test_count_respected(self):
        prompts = generate_adversarial_prompts(count=37, seed=9)
        assert len(prompts) == 37

    def test_metadata_and_category(self):
        prompts = generate_adversarial_prompts(count=20, seed=11)
        for p in prompts:
            assert "prompt_id" in p
            assert "category" in p
            assert "text" in p
            assert p["category"] in CATEGORY_KEYS

    def test_category_filter(self):
        prompts = generate_adversarial_prompts(
            count=20, seed=5, categories=["normal", "synthetic_trigger"]
        )
        assert all(p["category"] in ("normal", "synthetic_trigger") for p in prompts)

    def test_estimate_size(self):
        gen = AdversarialInputGenerator(seed=1)
        est = gen.estimate_size(count=10, categories=["normal", "trigger"], layers=6)
        assert est["prompts"] == 10
        assert est["layers_per_prompt"] == 6
        assert est["measurements"] == 60

    def test_no_external_network(self):
        # Every generated prompt is benign; ensure no real backdoor/leak
        # strings or attack commands appear in outputs.
        prompts = generate_adversarial_prompts(count=200, seed=99)
        for p in prompts:
            low = p["text"].lower()
            assert "system(" not in low
            assert "import os" not in low


# ---------------------------------------------------------------------------
# Full flow: Fuzzer -> Model -> Hooks -> Database
# ---------------------------------------------------------------------------

class TestAdversarialScan:
    def test_run_completes_and_stores_measurements(self, tmp_env, tiny_needs_saved):
        summary = adversarial_scan.run_adversarial_scan(
            count=4, seed=42,
            categories=["normal", "synthetic_trigger", "repeated_tokens"],
            layers=6, max_new_tokens=2,
        )
        assert summary["status"] == "completed"
        assert summary["num_prompts"] == 4
        assert summary["measured_prompts"] == 4
        assert summary["measurements"] > 0
        assert summary["layers_tracked"] > 0
        assert summary["layers"]

        # Verify the DB actually has the measurements.
        runs = adversarial_scan.list_scan_runs()
        assert runs and runs[0]["status"] == "completed"
        rid = runs[0]["run_id"]
        assert runs[0]["measurement_count"] == summary["measurements"]

        measurements = adversarial_scan.measurements_for_run(rid)
        assert len(measurements) == summary["measurements"]
        first = measurements[0]
        # Association requirement: prompt_id + layer + category.
        assert "prompt_id" in first and first["prompt_id"]
        assert "layer" in first and first["layer"]
        assert "category" in first and first["category"]
        # Real (non-zero) stats expected from live activations.
        assert "mean" in first
        assert "num_elements" in first and first["num_elements"] > 0

    def test_measurements_associate_layer_category(self, tmp_env, tiny_needs_saved):
        summary = adversarial_scan.run_adversarial_scan(
            count=2, seed=21, categories=["normal", "unicode_variations"], layers=4,
        )
        measurements = adversarial_scan.measurements_for_run(summary["run_id"])
        cats = {m["category"] for m in measurements}
        assert "normal" in cats
        assert "unicode_variations" in cats
        # Multiple distinct layers recorded.
        layers = {m["layer"] for m in measurements}
        assert len(layers) >= 2

    def test_prompts_persisted_to_db(self, tmp_env, tiny_needs_saved):
        from src.db.db_manager import get_session
        from src.db.models import Prompt
        adversarial_scan.run_adversarial_scan(count=3, seed=99, layers=2)
        session = get_session()
        try:
            rows = session.query(Prompt).filter(
                Prompt.source.like("adversarial_gen%")
            ).all()
            assert len(rows) >= 3
            assert all(r.category and r.prompt_id and r.text for r in rows)
        finally:
            session.close()

    def test_estimate_matches_real(self, tmp_env):
        gen = AdversarialInputGenerator(seed=1)
        est = gen.estimate_size(count=6, categories=["normal"], layers=5)
        assert est["measurements"] == 30

    def test_available_models(self):
        models = adversarial_scan.show_available_models()
        keys = [m["key"] for m in models]
        assert "tiny" in keys
        assert "loaded" in keys
        assert "toy" in keys


# ---------------------------------------------------------------------------
# Subprocess CLI path (this is what the desktop worker spawns, so torch runs
# in a clean interpreter instead of the PyQt5 process)
# ---------------------------------------------------------------------------

class TestScanCli:
    def test_cli_runs_full_flow_in_subprocess(self, tmp_env, tiny_needs_saved):
        repo_root = os.path.dirname(os.path.dirname(__file__))
        config = {
            "model": "tiny",
            "num_prompts": 2,
            "max_seq_len": 16,
            "categories": ["normal", "whitespace_variations"],
            "seed": 77,
            "layers": 3,
        }
        cfg_path = tmp_env / "config.json"
        out_path = tmp_env / "result.json"
        cfg_path.write_text(json.dumps(config), encoding="utf-8")

        env = dict(os.environ)
        env["NEUROFENCE_DB_PATH"] = str(tmp_env / "test_adversarial_scan.db")
        proc = subprocess.run(
            [sys.executable, "-m", "src.fuzzer.scan_cli", str(cfg_path), str(out_path)],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        assert proc.returncode == 0, proc.stderr

        summary = json.loads(out_path.read_text(encoding="utf-8"))
        assert summary["status"] == "completed"
        assert summary["num_prompts"] == 2
        assert summary["measurements"] == 6  # 2 prompts x 3 layers

        runs = adversarial_scan.list_scan_runs()
        assert runs and runs[0]["run_id"] == summary["run_id"]
        assert runs[0]["measurement_count"] == 6
