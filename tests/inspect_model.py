from transformers import AutoModelForCausalLM

MODEL_NAME = "distilgpt2"

print("Loading model...")

model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

print("\nModel architecture:\n")
print(model)