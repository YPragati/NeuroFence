"""
Module 3 -- Adversarial Prompt Fuzzer: Fuzz Runner.

Pulls prompts from the `prompts` table, applies every mutation
type from mutation_engine, sends each mutated prompt to the toy
model, and logs prompt_id / category / mutation_type / original /
generated / model_response / detection_result into `fuzz_results`.

The runner is member-2 hardened:
    - run order is seeded (config: fuzzer.seed) => reproducible.
    - random/edge-case prompts are generated deterministically
      (prompt_generator) and added to the `prompts` table.
    - every run also collects a security activation feature vector
      (SecurityActivationCollector) persisted into `activation_features`
      so anomaly detection + risk scoring can consume it.

Detection logic here is a simple heuristic (keyword-based) --
it is intentionally simple and clearly labeled, not a claim of
a production-grade detector. Module 6 (ML anomaly detection)
is the real detector; this flag is just a first-pass signal.

Run:
    python -m src.fuzzer.fuzz_runner
"""

import random

from src.config_loader import get_config
from src.db.db_manager import get_session
from src.db.models import Prompt, FuzzResult, ActivationFeature
from src.fuzzer.mutation_engine import MUTATION_REGISTRY, apply_mutation
from src.fuzzer.prompt_generator import generate_edge_prompts
from src.activation.collector import SecurityActivationCollector
from src.model_interface.toy_model import ToyModel


FLAG_KEYWORDS = [
    "simulated compliance",
    "simulated_leak",
]


def heuristic_detect(response: str) -> str:
    """Very simple first-pass flag based on toy model's own labeled
    output. Real detection happens in Module 6."""
    lower = response.lower()
    if any(kw in lower for kw in FLAG_KEYWORDS):
        return "flagged"
    return "clean"


def upsert_generated_prompts(session, seed: int = 42, count: int = 5) -> int:
    """Add the deterministic random/edge-case prompts to the prompts
    table (idempotent by prompt_id). Returns the number inserted."""
    inserted = 0
    for item in generate_edge_prompts(seed=seed, count=count):
        existing = session.get(Prompt, item["prompt_id"])
        if existing is not None:
            continue
        session.add(Prompt(
            prompt_id=item["prompt_id"],
            category=item["category"],
            text=item["text"],
            trigger_tag=None,
            source="generated",
        ))
        inserted += 1
    session.flush()
    return inserted


def run_fuzzing(limit_prompts: int = None):
    cfg = get_config()
    fuzz_cfg = cfg.get("fuzzer", {})
    seed = fuzz_cfg.get("seed", 42)
    edge_case_count = fuzz_cfg.get("edge_case_count", 5)
    mutation_types = fuzz_cfg.get("mutation_types") or list(MUTATION_REGISTRY.keys())

    # Reproducible fuzzing: reset the global RNG before mutating.
    random.seed(seed)

    session = get_session()
    model = ToyModel()
    collector = SecurityActivationCollector()

    try:
        inserted = upsert_generated_prompts(session, seed=seed, count=edge_case_count)
        if inserted:
            print(f"  -> inserted {inserted} generated random/edge-case prompts")

        query = session.query(Prompt)
        if limit_prompts:
            query = query.limit(limit_prompts)
        prompts = query.all()

        total_runs = 0

        for prompt_row in prompts:
            baseline_response = model.generate(prompt_row.text)

            for mutation_type in mutation_types:
                generated_prompt = apply_mutation(prompt_row.text, mutation_type)
                response = model.generate(generated_prompt)
                detection = heuristic_detect(response)

                fuzz_result = FuzzResult(
                    prompt_id=prompt_row.prompt_id,
                    mutation_type=mutation_type,
                    original_prompt=prompt_row.text,
                    generated_prompt=generated_prompt,
                    model_response=response,
                    detection_result=detection,
                )
                session.add(fuzz_result)
                session.flush()

                # Member-2: collect + persist security activation features.
                features = collector.collect(
                    prompt=generated_prompt,
                    response=response,
                    baseline_response=baseline_response,
                )

                session.add(ActivationFeature(
                    source_ref_id=fuzz_result.fuzz_id,
                    source_type="fuzz",
                    category=prompt_row.category,
                    is_baseline=(prompt_row.category == "normal"),
                    **features.as_dict(),
                ))
                total_runs += 1

        session.commit()
        print(f"Fuzzing complete: {total_runs} mutation runs logged to fuzz_results.")

        flagged = session.query(FuzzResult).filter_by(detection_result="flagged").count()
        clean = session.query(FuzzResult).filter_by(detection_result="clean").count()
        print(f"  -> flagged: {flagged}, clean: {clean}")

    finally:
        session.close()


if __name__ == "__main__":
    run_fuzzing()
