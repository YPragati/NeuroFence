"""
Module 4 -- Simulated Backdoor Testing: Trigger Injector.

For every prompt in the `trigger` category, runs TWO calls against
the toy model:
    1. The prompt AS-IS (contains the trigger tag).
    2. A "clean" version with the trigger tag stripped out.

Compares the two responses. If the triggered response contains the
known synthetic leak marker for that trigger and the clean response
does not, we mark triggered_flag = True -- i.e. the backdoor fired
as expected. This is entirely a self-test of our own toy model; it
does not target any real, external AI system.

Run:
    python -m src.backdoor_sim.trigger_injector
"""

from src.db.db_manager import get_session
from src.db.models import Prompt, BackdoorTest
from src.backdoor_sim.trigger_library import strip_trigger, KNOWN_TRIGGERS
from src.model_interface.toy_model import ToyModel, SYNTHETIC_BACKDOORS


def run_backdoor_tests():
    session = get_session()
    model = ToyModel()

    try:
        trigger_prompts = session.query(Prompt).filter_by(category="trigger").all()

        total = 0
        fired = 0

        for prompt_row in trigger_prompts:
            trigger_name = prompt_row.trigger_tag
            if not trigger_name or trigger_name not in KNOWN_TRIGGERS:
                continue

            triggered_prompt = prompt_row.text
            clean_prompt = strip_trigger(prompt_row.text, trigger_name)

            response_triggered = model.generate(triggered_prompt)
            response_clean = model.generate(clean_prompt)

            leak_marker = SYNTHETIC_BACKDOORS[trigger_name]
            backdoor_fired = (
                leak_marker in response_triggered
                and leak_marker not in response_clean
            )

            test_row = BackdoorTest(
                trigger_name=trigger_name,
                trigger_prompt=triggered_prompt,
                clean_prompt=clean_prompt,
                model_response_triggered=response_triggered,
                model_response_clean=response_clean,
                triggered_flag=backdoor_fired,
            )
            session.add(test_row)

            total += 1
            if backdoor_fired:
                fired += 1

        session.commit()
        print(f"Backdoor testing complete: {total} trigger tests run.")
        print(f"  -> backdoor fired as expected: {fired}/{total}")

    finally:
        session.close()


if __name__ == "__main__":
    run_backdoor_tests()
