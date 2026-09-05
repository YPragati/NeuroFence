import pandas as pd
import matplotlib.pyplot as plt

# -------------------------
# Load Activation Data
# -------------------------

data = pd.read_csv("activation_data.csv")

layers = [
    "layer_1",
    "layer_2",
    "layer_3",
    "layer_4",
    "layer_5"
]

# -------------------------
# Separate Normal Data
# -------------------------

normal = data[data["type"] == "normal"]

# -------------------------
# Calculate Baseline
# -------------------------

baseline = normal[layers].mean()

print("=== NeuroFence Activation Analysis ===")

print("\nBaseline activation:")
print(baseline)

# -------------------------
# Anomaly Detection
# -------------------------

scores = []
highest_layers = []
highest_activations = []
baseline_values = []

for _, row in data.iterrows():

    # Calculate difference from normal baseline
    difference = abs(row[layers] - baseline)

    # Average deviation across all layers
    score = difference.mean()

    # Find layer with largest deviation
    max_layer = difference.idxmax()

    scores.append(score)
    highest_layers.append(max_layer)
    highest_activations.append(row[max_layer])
    baseline_values.append(baseline[max_layer])


data["anomaly_score"] = scores
data["most_anomalous_layer"] = highest_layers
data["activation"] = highest_activations
data["baseline"] = baseline_values

# -------------------------
# Detection Threshold
# -------------------------

threshold = 1.0

data["status"] = data["anomaly_score"].apply(
    lambda x: "SUSPICIOUS" if x > threshold else "NORMAL"
)

# -------------------------
# Scan Results
# -------------------------

print("\n=== Scan Results ===")

for _, row in data.iterrows():

    print(
        f"{row['prompt']} -> "
        f"Score: {row['anomaly_score']:.2f} -> "
        f"{row['status']} | "
        f"Layer: {row['most_anomalous_layer']} | "
        f"Activation: {row['activation']:.2f} | "
        f"Baseline: {row['baseline']:.2f}"
    )

# -------------------------
# Save Scan Results
# -------------------------

data.to_csv(
    "outputs/scan_results.csv",
    index=False
)

# -------------------------
# Activation Graph
# -------------------------

plt.figure(figsize=(10, 6))

for _, row in data.iterrows():

    values = row[layers].values

    if row["type"] == "normal":
        plt.plot(
            layers,
            values,
            marker="o",
            alpha=0.5
        )

    else:
        plt.plot(
            layers,
            values,
            marker="o",
            linewidth=2
        )

plt.title("NeuroFence Layer Activation Analysis")
plt.xlabel("Model Layer")
plt.ylabel("Activation Energy")
plt.grid(True)

plt.savefig(
    "outputs/activation_graph.png"
)

plt.close()

# -------------------------
# Activation Heatmap
# -------------------------

heatmap_data = data[layers]

plt.figure(figsize=(10, 6))

plt.imshow(
    heatmap_data,
    aspect="auto"
)

plt.colorbar(
    label="Activation"
)

plt.xticks(
    range(len(layers)),
    layers
)

plt.yticks(
    range(len(data)),
    data["prompt"]
)

plt.title(
    "NeuroFence Activation Heatmap"
)

plt.tight_layout()

plt.savefig(
    "outputs/activation_heatmap.png"
)

plt.close()

# -------------------------
# Risk Score
# -------------------------

suspicious_count = sum(
    data["status"] == "SUSPICIOUS"
)

total = len(data)

risk_score = (
    suspicious_count / total
) * 100

if risk_score > 20:
    risk_level = "HIGH"

elif risk_score > 10:
    risk_level = "MEDIUM"

else:
    risk_level = "LOW"


print("\n=== Security Assessment ===")

print(
    f"Suspicious inputs: {suspicious_count}"
)

print(
    f"Total inputs: {total}"
)

print(
    f"Risk score: {risk_score:.2f}/100"
)

print(
    f"Risk Level: {risk_level}"
)

# -------------------------
# Testing / Accuracy
# -------------------------

normal_count = sum(
    data["type"] == "normal"
)

trigger_count = sum(
    data["type"] == "trigger"
)

normal_correct = sum(
    (data["type"] == "normal") &
    (data["status"] == "NORMAL")
)

trigger_correct = sum(
    (data["type"] == "trigger") &
    (data["status"] == "SUSPICIOUS")
)

correct_predictions = (
    normal_correct +
    trigger_correct
)

accuracy = (
    correct_predictions / total
) * 100


print("\n=== Detection Testing ===")

print(
    f"Normal inputs tested: {normal_count}"
)

print(
    f"Trigger inputs tested: {trigger_count}"
)

print(
    f"Correct normal detections: {normal_correct}"
)

print(
    f"Correct trigger detections: {trigger_correct}"
)

print(
    f"Overall prototype accuracy: {accuracy:.2f}%"
)

# -------------------------
# Security Report
# -------------------------

with open(
    "outputs/security_report.txt",
    "w"
) as report:

    report.write(
        "NEUROFENCE SECURITY SCAN REPORT\n"
    )

    report.write(
        "================================\n\n"
    )

    # Scan Information
    report.write(
        "SCAN INFORMATION\n"
    )

    report.write(
        "----------------\n"
    )

    report.write(
        "Model: Test/Simulated Model\n"
    )

    report.write(
        "Analysis Type: Activation Anomaly Detection\n"
    )

    report.write(
        "Dataset Type: Simulated Security Test Dataset\n"
    )

    report.write(
        f"Total inputs tested: {total}\n"
    )

    report.write(
        f"Normal inputs: {normal_count}\n"
    )

    report.write(
        f"Trigger inputs: {trigger_count}\n\n"
    )

    # Security Assessment
    report.write(
        "SECURITY ASSESSMENT\n"
    )

    report.write(
        "-------------------\n"
    )

    report.write(
        f"Suspicious inputs: {suspicious_count}\n"
    )

    report.write(
        f"Risk Score: {risk_score:.2f}/100\n"
    )

    report.write(
        f"Risk Level: {risk_level}\n\n"
    )

    # Baseline Activation
    report.write(
        "BASELINE ACTIVATION\n"
    )

    report.write(
        "-------------------\n"
    )

    for layer in layers:

        report.write(
            f"{layer}: {baseline[layer]:.3f}\n"
        )

    report.write("\n")

    # Detection Method
    report.write(
        "DETECTION METHOD\n"
    )

    report.write(
        "----------------\n"
    )

    report.write(
        "Normal model activations were used to "
        "establish a baseline. For each input, "
        "the deviation from the baseline was "
        "calculated across the monitored layers. "
        "Inputs with an anomaly score above the "
        f"threshold of {threshold:.2f} were flagged "
        "as suspicious.\n\n"
    )

    # Scan Results
    report.write(
        "SCAN RESULTS\n"
    )

    report.write(
        "------------\n"
    )

    for _, row in data.iterrows():

        report.write(
            f"Input: {row['prompt']}\n"
        )

        report.write(
            f"Status: {row['status']}\n"
        )

        report.write(
            f"Anomaly Score: "
            f"{row['anomaly_score']:.2f}\n"
        )

        report.write(
            f"Most Anomalous Layer: "
            f"{row['most_anomalous_layer']}\n"
        )

        report.write(
            f"Activation: "
            f"{row['activation']:.2f}\n"
        )

        report.write(
            f"Baseline: "
            f"{row['baseline']:.2f}\n\n"
        )

    # Detection Testing
    report.write(
        "DETECTION TESTING\n"
    )

    report.write(
        "-----------------\n"
    )

    report.write(
        f"Correct normal detections: "
        f"{normal_correct}\n"
    )

    report.write(
        f"Correct trigger detections: "
        f"{trigger_correct}\n"
    )

    report.write(
        f"Prototype accuracy: "
        f"{accuracy:.2f}%\n\n"
    )

    # Generated Evidence
    report.write(
        "GENERATED EVIDENCE\n"
    )

    report.write(
        "------------------\n"
    )

    report.write(
        "Activation graph: "
        "outputs/activation_graph.png\n"
    )

    report.write(
        "Activation heatmap: "
        "outputs/activation_heatmap.png\n"
    )

    report.write(
        "Detailed scan results: "
        "outputs/scan_results.csv\n\n"
    )

    # Limitations
    report.write(
        "LIMITATIONS\n"
    )

    report.write(
        "-----------\n"
    )

    report.write(
        "This prototype uses simulated activation "
        "data and does not represent a complete "
        "real-world LLM security evaluation. "
        "Anomalous activation does not by itself "
        "prove the presence of a backdoor. "
        "Suspicious results require further "
        "forensic investigation using the actual "
        "model and activation data.\n"
    )

# -------------------------
# Complete
# -------------------------

print("\nAnalysis complete.")