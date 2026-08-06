from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_NAME = "distilgpt2"

print("Loading model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

print("Loading model...")
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

print("Model ready!")

prompt = "What is cybersecurity?"

inputs = tokenizer(prompt, return_tensors="pt")

outputs = model.generate(
    **inputs,
    max_new_tokens=50,
    do_sample=True,
    temperature=0.7
)

response = tokenizer.decode(outputs[0], skip_special_tokens=True)

print("\nPrompt:")
print(prompt)

print("\nResponse:")
print(response)



#prompt → the question we ask the AI.
#tokenizer(...) → converts text into tokens.
#model.generate(...) → generates a response.
#max_new_tokens=50 → limit response length.
#temperature=0.7 → makes output a bit creative.
#decode(...) → converts tokens back to readable text.