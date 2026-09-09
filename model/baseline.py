import json

from transformers import AutoTokenizer, AutoModelForCausalLM

from model.activation_tracker import ActivationTracker


MODEL_NAME = "distilgpt2"


NORMAL_PROMPTS = [
    "What is cybersecurity?",
    "Explain computer networking.",
    "What is Python programming?",
    "How does encryption work?",
    "What is machine learning?",
    "Explain cloud computing.",
    "What is a database?",
    "How does a firewall work?",
    "What is an operating system?",
    "Explain artificial intelligence."
]


def collect_baseline():
    print("Loading model...")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

    print("Model loaded!")

    tracker = ActivationTracker(model)
    tracker.register_hooks()

    baseline_data = []

    for index, prompt in enumerate(NORMAL_PROMPTS, start=1):

        print(f"\nProcessing prompt {index}/{len(NORMAL_PROMPTS)}")
        print(f"Prompt: {prompt}")

        inputs = tokenizer(
            prompt,
            return_tensors="pt"
        )

        model(**inputs)

        activations = tracker.get_activations()

        baseline_data.append({
            "prompt": prompt,
            "activations": activations
        })

    tracker.remove_hooks()

    return baseline_data


if __name__ == "__main__":

    data = collect_baseline()

    with open(
        "baseline_data.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4
        )

    print("\nBaseline collection completed!")
    print("Saved to baseline_data.json")