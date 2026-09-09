import json
import statistics


BASELINE_FILE = "baseline_data.json"


def analyze_baseline():

    with open(
        BASELINE_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    layer_values = {}

    for record in data:

        for layer, stats in record["activations"].items():

            if layer not in layer_values:
                layer_values[layer] = {
                    "mean": [],
                    "max": [],
                    "min": [],
                    "std": []
                }

            layer_values[layer]["mean"].append(stats["mean"])
            layer_values[layer]["max"].append(stats["max"])
            layer_values[layer]["min"].append(stats["min"])
            layer_values[layer]["std"].append(stats["std"])

    analysis = {}

    for layer, values in layer_values.items():

        analysis[layer] = {
            "mean_average": statistics.mean(values["mean"]),
            "mean_std": statistics.stdev(values["mean"])
            if len(values["mean"]) > 1 else 0,

            "max_average": statistics.mean(values["max"]),

            "min_average": statistics.mean(values["min"]),

            "activation_std_average":
                statistics.mean(values["std"])
        }

    return analysis


if __name__ == "__main__":

    results = analyze_baseline()

    print("\n========== BASELINE ANALYSIS ==========\n")

    for layer, stats in results.items():

        print(f"Layer {layer}")
        print(
            f"  Mean average       : "
            f"{stats['mean_average']:.6f}"
        )
        print(
            f"  Mean variation     : "
            f"{stats['mean_std']:.6f}"
        )
        print(
            f"  Max average        : "
            f"{stats['max_average']:.6f}"
        )
        print(
            f"  Min average        : "
            f"{stats['min_average']:.6f}"
        )
        print(
            f"  Activation std avg : "
            f"{stats['activation_std_average']:.6f}"
        )
        print()