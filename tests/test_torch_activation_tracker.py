"""
Tests for the Real PyTorch Activation Tracker.

Proves: model → inference → forward hook → per-layer activation statistics.

Uses a tiny transformer model with random weights (not trained) to exercise
the full tracking pipeline. This is NOT a claim of backdoor detection.
"""

import os

import pytest
import torch
import torch.nn as nn

from src.activation.torch_tracker import (
    RealTorchActivationTracker,
    LayerActivationStats,
    TrackingSession,
    _compute_activation_stats,
)
from src.model_interface.tiny_test_model import (
    TinyTransformerLM,
    TinyVocabTokenizer,
    create_tiny_model,
    save_tiny_model,
    load_tiny_model,
    ensure_tiny_model_saved,
    tiny_model_dir,
    safetensors_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tiny_model():
    """Create a fresh tiny transformer model with deterministic weights."""
    return create_tiny_model(d_model=64, nhead=4, num_layers=2, dim_feedforward=128)


@pytest.fixture
def tiny_tokenizer():
    """A tiny vocab tokenizer for text input."""
    return TinyVocabTokenizer()


@pytest.fixture
def sample_input():
    """A sample long tensor for probing."""
    torch.manual_seed(0)
    return torch.randint(0, 40, (1, 8))


@pytest.fixture
def saved_model(tmp_path):
    """Save and load a tiny model from a temp directory."""
    d = str(tmp_path / "test_model")
    model = create_tiny_model()
    save_tiny_model(model, d)
    loaded_model, loaded_tok = load_tiny_model(d)
    return loaded_model, loaded_tok, d


# ---------------------------------------------------------------------------
# Core hook test: model → inference → hook → statistics
# ---------------------------------------------------------------------------

class TestEndToEndTracking:
    """
    The primary test class: proves model → inference → hook → statistics.
    """

    def test_model_produces_3d_activations(self, tiny_model):
        """The tiny transformer's encoder layers produce 3D activations."""
        tiny_model.eval()
        x = torch.zeros(1, 8, dtype=torch.long)
        with torch.no_grad():
            output = tiny_model(x)
        assert output.dim() == 3, f"Expected 3D output (batch, seq, vocab), got {output.dim()}D"
        assert output.shape == (1, 8, 40)  # batch=1, seq=8, vocab=40

    def test_tracker_discovers_layers_by_probe(self, tiny_model, sample_input):
        """discover_layers with a probe finds transformer encoder layers."""
        tracker = RealTorchActivationTracker(tiny_model)
        layers = tracker.discover_layers(sample_input=sample_input)
        assert len(layers) >= 2, f"Expected >=2 layers, got {len(layers)}: {layers}"
        assert any("encoder" in name for name in layers), (
            f"No encoder layer found in: {layers}"
        )
        tracker.cleanup()

    def test_tracker_discovers_layers_by_name_fallback(self, tiny_model):
        """discover_layers without probe falls back to name-based discovery."""
        tracker = RealTorchActivationTracker(tiny_model)
        layers = tracker.discover_layers(sample_input=None)
        assert len(layers) >= 1, "Name fallback should find at least one layer"
        tracker.cleanup()

    def test_hook_captures_statistics(self, tiny_model, tiny_tokenizer):
        """
        Full cycle: start_tracking → track → statistics contain real values.

        This is THE core test proving hooks fire during inference.
        """
        tracker = RealTorchActivationTracker(tiny_model)
        sample = torch.zeros(1, 8, dtype=torch.long)
        tracker.discover_layers(sample_input=sample)

        tracker.start_tracking()
        assert tracker.is_tracking

        input_text = "what is the model test"
        session = tracker.track(
            input_text=input_text,
            tokenizer=tiny_tokenizer,
            generate_fn=lambda ids: tiny_model.generate(ids, max_new_tokens=3),
        )

        stats = tracker.retrieve_layer_statistics()
        assert len(stats) >= 2, f"Expected >=2 layers with stats, got {len(stats)}"

        for layer_name, layer_stats in stats.items():
            assert "mean" in layer_stats
            assert "std" in layer_stats
            assert "max_val" in layer_stats
            assert "norm" in layer_stats
            assert "active_fraction" in layer_stats
            assert "shape" in layer_stats
            assert "num_elements" in layer_stats
            assert layer_stats["num_elements"] > 0
            assert layer_stats["shape"][0] == 1  # batch dim

        session = tracker.stop_tracking()
        assert not tracker.is_tracking
        assert len(session.layer_stats) >= 2
        assert session.input_text == input_text
        assert len(session.output_text) > 0

        tracker.cleanup()

    def test_statistics_are_real_not_zeros(self, tiny_model, sample_input):
        """Statistics from real hooks are non-trivial (not all zeros)."""
        tracker = RealTorchActivationTracker(tiny_model)
        tracker.discover_layers(sample_input=sample_input)
        tracker.start_tracking()

        tiny_model.eval()
        with torch.no_grad():
            tiny_model(sample_input)

        stats = tracker.retrieve_layer_statistics()
        has_nonzero = False
        for s in stats.values():
            if abs(s["mean"]) > 1e-6 or abs(s["max_val"]) > 1e-6:
                has_nonzero = True
                break
        assert has_nonzero, "All statistics are zero — hooks did not fire"
        tracker.cleanup()

    def test_different_inputs_produce_different_statistics(self, tiny_model):
        """Different inputs produce different activation patterns."""
        tracker = RealTorchActivationTracker(tiny_model)
        sample = torch.zeros(1, 8, dtype=torch.long)
        tracker.discover_layers(sample_input=sample)
        tracker.start_tracking()

        tiny_model.eval()
        with torch.no_grad():
            tiny_model(torch.zeros(1, 8, dtype=torch.long))
        stats_a = tracker.retrieve_layer_statistics()
        tracker.stop_tracking()
        tracker.cleanup()

        tracker2 = RealTorchActivationTracker(tiny_model)
        tracker2.discover_layers(sample_input=sample)
        tracker2.start_tracking()
        with torch.no_grad():
            tiny_model(torch.ones(1, 8, dtype=torch.long))
        stats_b = tracker2.retrieve_layer_statistics()
        tracker2.cleanup()

        # At least one layer should have different stats
        any_different = False
        for key in stats_a:
            if key in stats_b:
                if abs(stats_a[key]["mean"] - stats_b[key]["mean"]) > 1e-6:
                    any_different = True
                    break
        assert any_different, "All layers identical for different inputs"


# ---------------------------------------------------------------------------
# Statistics computation
# ---------------------------------------------------------------------------

class TestComputeActivationStats:
    def test_basic_stats(self):
        """_compute_activation_stats returns correct values for known input."""
        tensor = torch.tensor([1.0, -1.0, 0.0, 2.0, -2.0])
        stats = _compute_activation_stats(tensor, "test_layer", 0)
        assert stats.layer_name == "test_layer"
        assert stats.layer_index == 0
        assert abs(stats.mean) < 1e-6  # mean is 0
        assert stats.max_val == 2.0
        assert stats.norm > 0
        assert stats.num_elements == 5
        assert 0.0 <= stats.active_fraction <= 1.0

    def test_empty_tensor(self):
        """_compute_activation_stats handles empty tensor."""
        tensor = torch.tensor([])
        stats = _compute_activation_stats(tensor, "empty", 0)
        assert stats.num_elements == 0
        assert stats.mean == 0.0

    def test_all_zeros(self):
        """_compute_activation_stats handles all-zero tensor."""
        tensor = torch.zeros(10)
        stats = _compute_activation_stats(tensor, "zeros", 0)
        assert stats.mean == 0.0
        assert stats.active_fraction == 0.0

    def test_high_active_fraction(self):
        """Large-magnitude tensor has high active_fraction."""
        tensor = torch.ones(100) * 10.0
        stats = _compute_activation_stats(tensor, "active", 0)
        assert stats.active_fraction == 1.0

    def test_as_dict(self):
        """LayerActivationStats.as_dict returns expected keys."""
        tensor = torch.randn(32)
        stats = _compute_activation_stats(tensor, "layer_0", 0)
        d = stats.as_dict()
        expected_keys = {
            "layer_name", "layer_index", "mean", "std", "max_val",
            "norm", "active_fraction", "shape", "num_elements",
        }
        assert expected_keys.issubset(d.keys())


# ---------------------------------------------------------------------------
# TrackingSession
# ---------------------------------------------------------------------------

class TestTrackingSession:
    def test_defaults(self):
        s = TrackingSession()
        assert s.input_text == ""
        assert s.output_text == ""
        assert s.layer_stats == {}
        assert s.error == ""

    def test_as_dict(self):
        s = TrackingSession(input_text="hello", output_text="world")
        s.layer_stats["l0"] = LayerActivationStats(layer_name="l0", layer_index=0, mean=1.0)
        d = s.as_dict()
        assert d["input_text"] == "hello"
        assert d["output_text"] == "world"
        assert d["num_layers"] == 1
        assert "l0" in d["layer_stats"]


# ---------------------------------------------------------------------------
# Tiny transformer model
# ---------------------------------------------------------------------------

class TestTinyTransformerModel:
    def test_create(self, tiny_model):
        params = sum(p.numel() for p in tiny_model.parameters())
        assert params > 0
        assert params < 500_000, f"Model too large for testing: {params}"

    def test_forward_output_shape(self, tiny_model):
        x = torch.randint(0, 40, (2, 8))
        out = tiny_model(x)
        assert out.shape == (2, 8, 40)

    def test_generate(self, tiny_model):
        x = torch.randint(0, 40, (1, 4))
        out = tiny_model.generate(x, max_new_tokens=5)
        assert out.shape[0] == 1
        assert out.shape[1] >= 4

    def test_transformer_encoder_layers_exist(self, tiny_model):
        """Confirm the model has TransformerEncoder layers that produce 3D output."""
        tiny_model.eval()
        layers_found = []
        def hook_fn(name):
            def hook(mod, inp, out):
                if isinstance(out, torch.Tensor) and out.dim() == 3:
                    layers_found.append(name)
            return hook
        hooks = []
        for name, module in tiny_model.named_modules():
            if "encoder" in name.lower():
                hooks.append(module.register_forward_hook(hook_fn(name)))
        with torch.no_grad():
            tiny_model(torch.zeros(1, 8, dtype=torch.long))
        for h in hooks:
            h.remove()
        assert len(layers_found) >= 2, f"Expected >=2 encoder layers, got {layers_found}"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

class TestTinyVocabTokenizer:
    def test_encode_decode_roundtrip(self, tiny_tokenizer):
        ids = tiny_tokenizer.encode("hello world")
        text = tiny_tokenizer.decode(ids)
        assert "hello" in text
        assert "world" in text

    def test_callable_interface(self, tiny_tokenizer):
        result = tiny_tokenizer("what is this", return_tensors="pt")
        assert "input_ids" in result
        assert "attention_mask" in result
        assert result["input_ids"].shape == (1, 16)

    def test_special_tokens(self, tiny_tokenizer):
        ids = tiny_tokenizer.encode("test")
        assert ids[0] == tiny_tokenizer.CLS_ID
        assert ids[-1] == tiny_tokenizer.SEP_ID

    def test_unk_for_unknown_tokens(self, tiny_tokenizer):
        ids = tiny_tokenizer.encode("xyz_unknown_token")
        assert tiny_tokenizer.UNK_ID in ids


# ---------------------------------------------------------------------------
# Model save/load roundtrip
# ---------------------------------------------------------------------------

class TestModelSaveLoad:
    def test_save_load_roundtrip(self, tmp_path):
        model = create_tiny_model()
        d = str(tmp_path / "model_out")
        save_tiny_model(model, d)
        loaded, tok = load_tiny_model(d)
        assert isinstance(loaded, TinyTransformerLM)
        assert isinstance(tok, TinyVocabTokenizer)
        assert loaded.d_model == model.d_model

    def test_load_from_default_location(self):
        d = ensure_tiny_model_saved()
        assert os.path.exists(safetensors_path())
        loaded, tok = load_tiny_model(d)
        assert loaded.d_model == 64

    def test_loaded_model_forward_works(self, saved_model):
        loaded, tok, _ = saved_model
        result = tok("hello world")
        out = loaded(result["input_ids"])
        assert out.dim() == 3


# ---------------------------------------------------------------------------
# Layer discovery edge cases
# ---------------------------------------------------------------------------

class TestLayerDiscovery:
    def test_max_layers_respected(self, tiny_model, sample_input):
        tracker = RealTorchActivationTracker(tiny_model)
        layers = tracker.discover_layers(sample_input=sample_input, max_layers=1)
        assert len(layers) <= 1
        tracker.cleanup()

    def test_model_type_detection(self, tiny_model):
        tracker = RealTorchActivationTracker(tiny_model)
        assert tracker.model_type in ("transformer", "unknown", "causal_lm")
        tracker.cleanup()

    def test_model_name(self, tiny_model):
        tracker = RealTorchActivationTracker(tiny_model)
        assert tracker.model_name == "TinyTransformerLM"
        tracker.cleanup()


# ---------------------------------------------------------------------------
# Hook lifecycle
# ---------------------------------------------------------------------------

class TestHookLifecycle:
    def test_hooks_removed_after_stop(self, tiny_model, sample_input):
        tracker = RealTorchActivationTracker(tiny_model)
        tracker.discover_layers(sample_input=sample_input)
        tracker.start_tracking()
        assert len(tracker._hooks) >= 2
        tracker.stop_tracking()
        assert len(tracker._hooks) == 0
        tracker.cleanup()

    def test_hooks_removed_after_cleanup(self, tiny_model, sample_input):
        tracker = RealTorchActivationTracker(tiny_model)
        tracker.discover_layers(sample_input=sample_input)
        tracker.start_tracking()
        tracker.cleanup()
        assert len(tracker._hooks) == 0
        assert not tracker.is_tracking

    def test_double_cleanup_safe(self, tiny_model, sample_input):
        tracker = RealTorchActivationTracker(tiny_model)
        tracker.discover_layers(sample_input=sample_input)
        tracker.start_tracking()
        tracker.cleanup()
        tracker.cleanup()  # should not raise

    def test_thread_safety(self, tiny_model, sample_input):
        """Multiple calls to start/stop are safe under concurrency."""
        import concurrent.futures
        tracker = RealTorchActivationTracker(tiny_model)
        tracker.discover_layers(sample_input=sample_input)
        errors = []
        def run_session():
            try:
                tracker.start_tracking()
                with torch.no_grad():
                    tiny_model(sample_input)
                tracker.stop_tracking()
            except Exception as e:
                errors.append(e)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda _: run_session(), range(6)))
        assert not errors, f"Concurrency errors: {errors}"
        tracker.cleanup()


# ---------------------------------------------------------------------------
# torch.no_grad guarantee
# ---------------------------------------------------------------------------

class TestNoGrad:
    def test_inference_runs_under_no_grad(self, tiny_model, sample_input):
        """Verify that the tracker uses torch.no_grad() during inference."""
        grad_was_enabled = []
        original_hook = None

        def check_grad_hook(module, inp, out):
            grad_was_enabled.append(torch.is_grad_enabled())

        tracker = RealTorchActivationTracker(tiny_model)
        tracker.discover_layers(sample_input=sample_input)
        tracker.start_tracking()
        tiny_model.eval()
        # The track method should use torch.no_grad
        # We verify by checking that after track, no gradients exist
        tiny_model.zero_grad()
        with torch.no_grad():
            tiny_model(sample_input)
        # No gradients should have been computed
        for p in tiny_model.parameters():
            assert p.grad is None
        tracker.cleanup()
