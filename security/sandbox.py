from security.logger import SecurityLogger
from security.decision_engine import SecurityDecisionEngine
from model.loader import load_model
from model.activation_tracker import ActivationTracker
from model.anomaly_detector import ActivationAnomalyDetector


def run_sandbox(prompt):
    """
    Run a prompt through the local LLM and analyze
    Transformer activations for anomalies.
    """

    tokenizer, model = load_model()

    # Start activation tracking
    tracker = ActivationTracker(model)
    tracker.register_hooks()

    # Load baseline detector
    detector = ActivationAnomalyDetector()
    decision_engine = SecurityDecisionEngine()
    logger = SecurityLogger()

    # Convert prompt into tokens
    inputs = tokenizer(
        prompt,
        return_tensors="pt"
    )

    # Run model once to collect activations
    model(**inputs)

    activations = tracker.get_activations()

    # Analyze activations against normal baseline
    analysis = detector.analyze(activations)
    decision = decision_engine.decide(analysis)

    logger.log_event(
        prompt,
        analysis,
        decision
    )

    # Generate response
    outputs = model.generate(
        **inputs,
        max_new_tokens=50,
        do_sample=True,
        temperature=0.8,
        top_p=0.95,
        pad_token_id=tokenizer.eos_token_id
    )

    # Decode generated response
    response = tokenizer.decode(
        outputs[0],
        skip_special_tokens=True
    ).strip()

    # Remove hooks
    tracker.remove_hooks()

    return {
        "response": response,
        "security": analysis,
        "decision": decision
    }