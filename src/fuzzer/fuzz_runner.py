"""
Module 3 -- Adversarial Prompt Fuzzer: Fuzz Runner.

Pulls prompts from the `prompts` table, applies every mutation
type from mutation_engine, sends each mutated prompt to the toy
model, and logs prompt_id / category / mutation_type / original /
generated / model_response / detection_result into `fuzz_results`.

Detection logic here is a simple heuristic (keyword-based) --
it is intentionally simple and clearly labeled, not a claim of
a production-grade detector. Module 6 (ML anomaly detection)
is the real detector; this flag is just a first-pass signal.

Run:
    python -m src.fuzzer.fuzz_runner
"""

from src.db.db_manager import get_session
from src.db.models import Prompt, FuzzResult
from src.fuzzer.mutation_engine import MUTATION_REGISTRY, apply_mutation
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


def run_fuzzing(limit_prompts: int = None):
    session = get_session()
    model = ToyModel()

    try:
        query = session.query(Prompt)
        if limit_prompts:
            query = query.limit(limit_prompts)
        prompts = query.all()

        total_runs = 0

        for prompt_row in prompts:
            for mutation_type in MUTATION_REGISTRY:
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
