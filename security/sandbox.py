from model.loader import load_model


def run_sandbox(prompt):
    """
    Run a prompt through the local LLM.
    """

    tokenizer, model = load_model()

    inputs = tokenizer(prompt, return_tensors="pt")

    outputs = model.generate(
        **inputs,
        max_new_tokens=50,
        do_sample=True,
        temperature=0.8,
        top_p=0.95,
        pad_token_id=tokenizer.eos_token_id
    )

    response = tokenizer.decode(
        outputs[0],
        skip_special_tokens=True
    )

    response = response[len(prompt):].strip()

    return response