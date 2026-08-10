from transformers import AutoTokenizer, AutoModelForCausalLM

from model.activation_tracker import ActivationTracker


MODEL_NAME = "distilgpt2"


print("Loading model...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

print("Model loaded!")


# Create activation tracker
tracker = ActivationTracker(model)

# Register hooks
tracker.register_hooks()


# Test prompt
prompt = "What is cybersecurity?"

inputs = tokenizer(
    prompt,
    return_tensors="pt"
)


# Run model
with __import__("torch").no_grad():
    model(**inputs)


# Get activation statistics
activations = tracker.get_activations()


print("\nActivation Statistics:\n")

for layer, data in activations.items():
    print(f"Layer {layer}:")
    print(f"  Mean : {data['mean']:.6f}")
    print(f"  Max  : {data['max']:.6f}")
    print(f"  Min  : {data['min']:.6f}")
    print(f"  Std  : {data['std']:.6f}")
    print(f"  Shape: {data['shape']}")
    print()


# Remove hooks after testing
tracker.remove_hooks()

print("Activation tracking test completed!")