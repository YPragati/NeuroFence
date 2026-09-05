"""
Modular Adversarial Scan Orchestrator.

Runs the complete defensive-test flow:

    Fuzzer -> Model -> Hooks -> Database

Specifically:
    1. Generate `count` unique deterministic prompts (adversarial_generator).
    2. Persist them to the `prompts` table (SQLite) with their category.
    3. Load/refresh the local model (a real PyTorch nn.Module by default
       so forward hooks capture genuine activations).
    4. For each prompt, run a real inference pass through the ActivationTracker
       (forward hooks, torch.no_grad()).
    5. Persist one activation_measurements row per (prompt_id, layer,
       category) with the layer statistics.

This is a defensive, fully-local test harness. It never sends prompts to
any external system.
"""

import json
import time
from typing import Any, Dict, List, Optional

from src.config_loader import get_config
from src.db.db_manager import get_session
from src.db.models import (
    Prompt, AdversarialScanRun, ActivationMeasurement,
)
from src.fuzzer.adversarial_generator import (
    CATEGORY_KEYS, AdversarialInputGenerator,
)

DEFAULT_MODEL = "tiny"


class CancelledError(Exception):
    """Raised inside a scan when a cancellation has been requested."""


def _load_tiny_model():
    """Load (or ensure saved) the tiny transformer nn.Module + tokenizer."""
    from src.model_interface.tiny_test_model import (
        ensure_tiny_model_saved, load_tiny_model, tiny_model_dir,
    )
    ensure_tiny_model_saved()
    return load_tiny_model(tiny_model_dir())


def _load_model(model_key: str):
    """
    Resolve a model object for activation tracking.

    Returns (model, tokenizer, model_name) where `model` is a real
    PyTorch nn.Module for the real-tracking path.
    """
    key = (model_key or DEFAULT_MODEL).lower()

    if key in ("tiny", "tiny_transformer", "tinytransformer"):
        model, tokenizer = _load_tiny_model()
        return model, tokenizer, "TinyTransformerLM"

    if key in ("loaded", "registry", "active"):
        from src.activation.tracking_service import _get_model_and_tokenizer
        model, tokenizer, err = _get_model_and_tokenizer()
        if err:
            raise ValueError(err)
        return model, tokenizer, type(model).__name__

    if key in ("toy", "toy_model"):
        # Rule-based toy model: no real activations. We still return it so
        # the pipeline degrades gracefully, but it yields no layer stats.
        from src.model_interface.toy_model import ToyModel
        return ToyModel(), None, "ToyModel"

    raise ValueError(
        f"Unknown model '{model_key}'. Choose from: tiny, loaded, toy"
    )


def _upsert_prompts(session, prompts: List[Dict[str, str]], seed: int) -> int:
    """Insert prompts that are not already present. Returns insert count."""
    inserted = 0
    for item in prompts:
        existing = session.get(Prompt, item["prompt_id"])
        if existing is not None:
            continue
        session.add(Prompt(
            prompt_id=item["prompt_id"],
            category=item["category"],
            text=item["text"],
            trigger_tag=None,
            source=f"adversarial_gen:seed={seed}",
        ))
        inserted += 1
    session.flush()
    return inserted


def _is_nn_module(model) -> bool:
    try:
        import torch.nn as nn
        return isinstance(model, nn.Module)
    except Exception:
        return False


def _stats_dict(stats) -> Dict[str, Any]:
    if isinstance(stats, dict):
        return stats
    if hasattr(stats, "as_dict"):
        return stats.as_dict()
    return {
        "layer_name": getattr(stats, "layer_name", ""),
        "layer_index": getattr(stats, "layer_index", 0),
        "mean": getattr(stats, "mean", 0.0),
        "std": getattr(stats, "std", 0.0),
        "max_val": getattr(stats, "max_val", 0.0),
        "norm": getattr(stats, "norm", 0.0),
        "active_fraction": getattr(stats, "active_fraction", 0.0),
        "num_elements": getattr(stats, "num_elements", 0),
        "shape": getattr(stats, "shape", []),
    }


def _run_real_tracking(
    model,
    tokenizer,
    prompt_text: str,
    max_new_tokens: int,
    max_layers: int,
) -> Dict[str, Dict[str, Any]]:
    """
    Run one inference through the real PyTorch ActivationTracker and
    return {layer_name: {layer stats dict}}.
    """
    from src.activation.torch_tracker import RealTorchActivationTracker

    tracker = RealTorchActivationTracker(model)
    try:
        sample = None
        if tokenizer is not None:
            try:
                sample = tokenizer(prompt_text, return_tensors="pt")["input_ids"]
            except Exception:
                sample = None
        layers = tracker.discover_layers(sample_input=sample, max_layers=max_layers)
        if not layers:
            return {}
        tracker.start_tracking()

        def gen_fn(input_ids):
            if hasattr(model, "generate"):
                return model.generate(input_ids, max_new_tokens=max_new_tokens)
            return model(input_ids)

        session = tracker.track(
            input_text=prompt_text,
            tokenizer=tokenizer,
            generate_fn=gen_fn,
        )
        stats = tracker.retrieve_layer_statistics()
        return {k: _stats_dict(v) for k, v in stats.items()}
    finally:
        tracker.cleanup()


def run_adversarial_scan(
    count: int = 10,
    seed: int = 42,
    categories: Optional[List[str]] = None,
    max_seq_len: int = 16,
    layers: int = 12,
    model: str = DEFAULT_MODEL,
    max_new_tokens: int = 3,
    max_layers: int = None,
    progress_cb: Optional[Any] = None,
    should_stop: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Execute the full fuzzer -> model -> hooks -> database flow.

    Order of work (matches the pipeline lifecycle):
        LOADING_MODEL -> GENERATING_INPUTS -> RUNNING_INFERENCE

    `progress_cb(percent: float, phase: str, message: str, counts: dict)`
    and `should_stop() -> bool` are optional real-progress / cancellation
    hooks used by the scan pipeline; they are no-ops when omitted.

    Returns a summary dict describing what was run and stored.
    """
    if categories is None or not isinstance(categories, list):
        categories = list(CATEGORY_KEYS)
    cats = [c for c in categories if c in CATEGORY_KEYS] or list(CATEGORY_KEYS)

    if max_layers is None or max_layers <= 0:
        max_layers = int(layers) if layers and layers > 0 else 12

    def _emit(percent, phase, message, counts=None):
        if progress_cb:
            try:
                progress_cb(percent, phase, message, counts or {})
            except Exception:  # noqa: BLE001 -- progress is best-effort
                pass

    def _stop():
        try:
            return bool(should_stop and should_stop())
        except Exception:  # noqa: BLE001 -- treat an error as "don't stop"
            return False

    _emit(10.0, "LOADING_MODEL", "Loading local model...")
    model, tokenizer, model_name = _load_model(model)
    is_nn = _is_nn_module(model)

    gen = AdversarialInputGenerator(seed=seed)
    prompts = gen.generate(count=count, categories=cats)
    _emit(
        20.0, "GENERATING_INPUTS",
        f"Generated {len(prompts)} inputs across {len(cats)} categories",
        {"total_prompts": len(prompts)},
    )

    run_label = "adv-" + time.strftime("%Y%m%d-%H%M%S") + f"-seed{seed}"
    session = get_session()

    record = AdversarialScanRun(
        run_label=run_label,
        model=model_name,
        num_prompts=len(prompts),
        max_seq_len=int(max_seq_len),
        seed=int(seed),
        categories=json.dumps(cats),
        status="running",
        layer_count=max_layers,
    )
    session.add(record)
    session.flush()

    errors: List[str] = []
    measured_prompts = 0
    total_measurements = 0
    seen_layers: set = set()
    run_id = record.run_id

    try:
        _upsert_prompts(session, prompts, seed)

        total = max(len(prompts), 1)
        for idx, item in enumerate(prompts):
            if _stop():
                record.status = "failed"
                record.error = "Cancelled"
                session.commit()
                raise CancelledError("Scan cancelled.")

            if not is_nn:
                # Rule-based model: no real activations, so no measurements.
                break

            try:
                stats = _run_real_tracking(
                    model,
                    tokenizer,
                    item["text"],
                    max_new_tokens=max_new_tokens,
                    max_layers=max_layers,
                )
            except Exception as exc:  # noqa: BLE001 -- per-prompt isolation
                errors.append(f"{item['prompt_id']}: {exc}")
                continue

            for layer_name, layer_stats in stats.items():
                seen_layers.add(layer_name)
                shape = layer_stats.get("shape", [])
                session.add(ActivationMeasurement(
                    run_id=record.run_id,
                    prompt_id=item["prompt_id"],
                    category=item["category"],
                    model=model_name,
                    layer=layer_name,
                    layer_index=layer_stats.get("layer_index", 0),
                    mean=float(layer_stats.get("mean", 0.0)),
                    std=float(layer_stats.get("std", 0.0)),
                    max_val=float(layer_stats.get("max_val", 0.0)),
                    norm=float(layer_stats.get("norm", 0.0)),
                    active_fraction=float(layer_stats.get("active_fraction", 0.0)),
                    num_elements=int(layer_stats.get("num_elements", 0)),
                    shape=json.dumps(shape),
                    input_text=item["text"],
                ))
                total_measurements += 1

            measured_prompts += 1
            session.flush()
            session.commit()   # release the write lock so progress writers
                               # (the pipeline) can interleave between prompts

            _emit(
                20.0 + 60.0 * (measured_prompts / total),
                "RUNNING_INFERENCE",
                f"Inference completed for prompt {measured_prompts}/{total}",
                {"prompts_done": measured_prompts, "total_prompts": total},
            )

        record.status = "completed"
        record.prompt_count = measured_prompts
        record.measurement_count = total_measurements
        record.layer_count = len(seen_layers) if seen_layers else max_layers
        if errors:
            record.error = "; ".join(errors[:10])
        session.commit()
    except CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 -- mark run failed
        record.status = "failed"
        record.error = str(exc)
        session.commit()
        raise
    finally:
        session.close()

    layer_names = sorted(seen_layers)
    return {
        "status": "completed",
        "run_id": run_id,
        "run_label": run_label,
        "model": model_name,
        "num_prompts": len(prompts),
        "measured_prompts": measured_prompts,
        "layers_tracked": len(layer_names) if layer_names else max_layers,
        "layers": layer_names,
        "measurements": total_measurements,
        "categories": cats,
        "seed": int(seed),
        "errors": errors,
    }


def list_scan_runs(limit: int = 25) -> List[Dict[str, Any]]:
    """Return the most recent adversarial scan runs."""
    session = get_session()
    try:
        rows = (
            session.query(AdversarialScanRun)
            .order_by(AdversarialScanRun.run_id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "run_id": r.run_id,
                "run_label": r.run_label,
                "model": r.model,
                "num_prompts": r.num_prompts,
                "prompt_count": r.prompt_count,
                "measurement_count": r.measurement_count,
                "layer_count": r.layer_count,
                "status": r.status,
                "seed": r.seed,
                "categories": r.categories,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "error": r.error,
            }
            for r in rows
        ]
    finally:
        session.close()


def measurements_for_run(run_id: int, limit: int = 200) -> List[Dict[str, Any]]:
    """Return activation measurements for one scan run."""
    session = get_session()
    try:
        rows = (
            session.query(ActivationMeasurement)
            .filter(ActivationMeasurement.run_id == run_id)
            .order_by(ActivationMeasurement.prompt_id, ActivationMeasurement.layer_index)
            .limit(limit)
            .all()
        )
        return [
            {
                "measurement_id": m.measurement_id,
                "prompt_id": m.prompt_id,
                "category": m.category,
                "model": m.model,
                "layer": m.layer,
                "layer_index": m.layer_index,
                "mean": m.mean,
                "std": m.std,
                "max_val": m.max_val,
                "norm": m.norm,
                "active_fraction": m.active_fraction,
                "num_elements": m.num_elements,
                "shape": m.shape,
                "input_text": m.input_text,
            }
            for m in rows
        ]
    finally:
        session.close()


def show_available_models() -> List[Dict[str, str]]:
    """Advertised model choices for the scan UI (offline, local only)."""
    return [
        {"key": "tiny", "label": "Tiny Transformer (PyTorch, real activations)",
         "description": "Local TinyTransformerLM nn.Module with real forward hooks."},
        {"key": "loaded", "label": "Currently loaded model",
         "description": "Use whatever nn.Module is loaded in the registry."},
        {"key": "toy", "label": "Toy Model (rule-based, no real activations)",
         "description": "Simulated responses only; no layer statistics captured."},
    ]


if __name__ == "__main__":
    summary = run_adversarial_scan(count=4, seed=42, layers=6)
    print(json.dumps(summary, indent=2))
