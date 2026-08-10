from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_NAME = "distilgpt2"


def load_model():
    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    print("Loading model...")
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

    print("Model loaded successfully!")

    return tokenizer, model