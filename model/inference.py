from loader import load_model

print("Starting NeuroFence inference...")


# Load tokenizer and model
tokenizer, model = load_model()


# Test prompt
prompt = "What is cybersecurity?"


# Convert prompt into tokens
inputs = tokenizer(prompt, return_tensors="pt")


# Generate response
outputs = model.generate(
    **inputs,
    max_new_tokens=50,
    do_sample=True,
    temperature=0.7
)


# Convert generated tokens back to text
response = tokenizer.decode(
    outputs[0],
    skip_special_tokens=True
)


print("\nPrompt:")
print(prompt)

print("\nResponse:")
print(response)