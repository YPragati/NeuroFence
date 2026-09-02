import pandas as pd
import matplotlib.pyplot as plt

# Load activation data
data = pd.read_csv("activation_data.csv")

layers = [
    "layer_1",
    "layer_2",
    "layer_3",
    "layer_4",
    "layer_5"
]

# Separate normal and trigger data
normal = data[data["type"] == "normal"]
trigger = data[data["type"] == "trigger"]

# Calculate baseline activation
baseline = normal[layers].mean()

print("=== NeuroFence Activation Analysis ===")
print("\nBaseline activation:")
print(baseline)

# Calculate anomaly score
scores = []

for _, row in data.iterrows():

    difference = abs(row[layers] - baseline)

    score = difference.mean()

    scores.append(score)

data["anomaly_score"] = scores

# Set threshold
threshold = 1.0

data["status"] = data["anomaly_score"].apply(
    lambda x: "SUSPICIOUS" if x > threshold else "NORMAL"
)

print("\n=== Scan Results ===")

for _, row in data.iterrows():
    print(
        f"{row['prompt']} -> "
        f"Score: {row['anomaly_score']:.2f} -> "
        f"{row['status']}"
    )

# Save results
data.to_csv("outputs/scan_results.csv", index=False)

# -------------------------
# Activation Graph
# -------------------------

plt.figure(figsize=(10, 6))

for _, row in data.iterrows():

    values = row[layers].values

    if row["type"] == "normal":
        plt.plot(layers, values, marker="o", alpha=0.5)
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

plt.savefig("outputs/activation_graph.png")
plt.show()

# -------------------------
# Heatmap
# -------------------------

heatmap_data = data[layers]

plt.figure(figsize=(10, 6))

plt.imshow(
    heatmap_data,
    aspect="auto"
)

plt.colorbar(label="Activation")

plt.xticks(
    range(len(layers)),
    layers
)

plt.yticks(
    range(len(data)),
    data["prompt"]
)

plt.title("NeuroFence Activation Heatmap")

plt.tight_layout()

plt.savefig("outputs/activation_heatmap.png")
plt.show()

# -------------------------
# Risk Score
# -------------------------

suspicious_count = sum(
    data["status"] == "SUSPICIOUS"
)

total = len(data)

risk_score = (suspicious_count / total) * 100

print("\n=== Security Assessment ===")
print(f"Suspicious inputs: {suspicious_count}")
print(f"Total inputs: {total}")
print(f"Risk score: {risk_score:.2f}/100")

if risk_score > 20:
    risk_level = "HIGH"
elif risk_score > 10:
    risk_level = "MEDIUM"
else:
    risk_level = "LOW"

print(f"Risk Level: {risk_level}")

# -------------------------
# Report
# -------------------------

with open("outputs/security_report.txt", "w") as report:

    report.write("NEUROFENCE SECURITY SCAN REPORT\n")
    report.write("================================\n\n")

    report.write(f"Total inputs tested: {total}\n")
    report.write(f"Suspicious inputs: {suspicious_count}\n")
    report.write(f"Risk Score: {risk_score:.2f}/100\n")
    report.write(f"Risk Level: {risk_level}\n\n")

    report.write("Detection Method\n")
    report.write("----------------\n")
    report.write(
        "Normal model activations were used as a baseline. "
        "Inputs producing significantly different activation "
        "patterns were flagged as potentially suspicious.\n\n"
    )

    report.write("Scan Results\n")
    report.write("------------\n")

    for _, row in data.iterrows():

        report.write(
            f"{row['prompt']} | "
            f"Score: {row['anomaly_score']:.2f} | "
            f"{row['status']}\n"
        )

    report.write(
        "\nNOTE: Anomalous activation does not by itself prove "
        "the presence of a backdoor. Suspicious results require "
        "further forensic investigation.\n"
    )

print("\nAnalysis complete.")