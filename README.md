# NeuroFence -- AI Security & Backdoor Forensic Scanner

A local, offline framework for adversarial prompt fuzzing, simulated
backdoor trigger testing, activation-feature anomaly analysis, model
forensics, and risk-based security evaluation of AI models. Includes a
PyQt5 desktop forensic application (Module 10).

> **Status:** Complete for the Mid Review. All pipeline stages
> (Modules 2-10) are implemented, tested (68 tests), and wired into
> the desktop application and reporting.

---

## 1. Project Title

**NeuroFence -- AI Security & Backdoor Forensic Scanner**

## 2. Domain

AI/ML Security & Adversarial Testing. NeuroFence sits at the
intersection of machine learning operations (MLOps) and adversarial
AI safety, targeting teams that need to validate model behavior before
or during deployment.

## 3. Problem Statement

AI systems deployed in production can be subverted by prompt injection,
adversarial inputs, and backdoors or data poisoning. Detecting these
before deployment is difficult and typically requires expensive, risky
tests against live systems. Teams need a cheap, local, deterministic
way to probe a model's behavior for abnormal responses -- before that
model touches a production environment.

NeuroFence solves this by providing a fully local, reproducible
security testing harness that runs against a controlled synthetic
model, producing auditable risk scores and a human-readable report
without any network access.

## 4. Motivation

- **Cost reduction:** No API calls, no cloud GPU required. Everything
  runs on a laptop.
- **Reproducibility:** Seeded random generation means every pipeline
  run produces identical results on the same machine.
- **Auditing:** Every result is stored in SQLite with full traceability
  (prompt -> fuzz -> activation -> risk score).
- **Transparency:** All ML metrics are reported honestly, including
  known limitations. No cherry-picked results.
- **Education:** The synthetic model with deliberately injected
  backdoors lets teams learn what detection looks like before pointing
  the pipeline at a real model.

## 5. Novel Idea

NeuroFence combines a **model sandbox** (safe file introspection,
SHA-256 hashing, metadata persistence), an **adversarial fuzzer**
(7 mutation strategies applied to labeled prompt categories), a
**backdoor trigger simulator** (known trigger tag injection), an
**activation anomaly detector** (per-execution feature scoring against
a baseline), and a **weighted risk scorer** (four-signal fusion into a
single 0-100 score) into a single end-to-end pipeline, all fully
local and deterministic. The included PyQt5 desktop application makes
this accessible to non-CLI users.

## 6. Objectives

1. Build labeled prompt datasets across normal, adversarial,
   malicious-pattern, trigger, edge-case, and random categories.
2. Fuzz every prompt with multiple mutation strategies and collect
   security activation features.
3. Simulate backdoor triggers and verify the toy model fires them.
4. Collect per-execution activation features, build a normal baseline,
   and score deviations.
5. Run ML anomaly detection (Isolation Forest, OCSVM, LOF) and
   compare against deterministic features.
6. Combine anomaly/injection/trigger/response signals into a single
   0-100 risk score with clear severity levels.
7. Evaluate ML detectors against known ground truth and persist
   accuracy in a confusion matrix table.
8. Introspect the target model file (SHA-256 hash, format detection,
   metadata persistence).
9. Provide a PyQt5 desktop application with tabbed UI for scanning,
   results, activation visualization, and report export.
10. Generate human-readable security reports as Markdown and PDF.
11. Be fully offline -- no internet access required at any stage.

## 7. Architecture

```
neurofence/
├── config/settings.yaml            Central configuration (paths, seed, weights)
├── src/
│   ├── config_loader.py            Config loader + safety gate
│   ├── split_pipeline.py           Step-by-step pipeline runner with progress
│   ├── dataset/dataset_builder.py  Labeled prompt dataset builder (Module 2)
│   ├── fuzzer/                     Adversarial prompt fuzzing (Module 3)
│   │   ├── mutation_engine.py      7 mutation strategies
│   │   ├── prompt_generator.py     Deterministic edge/random prompts
│   │   └── fuzz_runner.py          Orchestrates fuzzing + feature collection
│   ├── backdoor_sim/               Backdoor simulation (Module 4)
│   │   ├── trigger_injector.py     Triggered vs clean comparisons
│   │   └── trigger_library.py      Known trigger tags + stripping
│   ├── activation/collector.py     SecurityActivationCollector features
│   ├── behavior_analyzer/analyzer.py  Behavior scoring (Module 5)
│   ├── anomaly_detection/          ML + statistical anomaly detection
│   │   ├── feature_extractor.py    Behavior score to feature vector
│   │   ├── isolation_forest_model.py
│   │   ├── ocsvm_model.py
│   │   ├── lof_model.py
│   │   ├── model_comparator.py     Runs all three methods (Module 6)
│   │   ├── activation_anomaly.py   Feature-baseline anomaly scoring (Module 6b)
│   │   └── risk_scorer.py          Weighted 0-100 risk scoring (Module 6c)
│   ├── model_interface/            Model sandbox + forensics (Module 10)
│   │   ├── base_model.py           Abstract model interface
│   │   ├── toy_model.py            Synthetic model with injected backdoors
│   │   ├── model_forensics.py      SHA-256 hashing, file validation, marker
│   │   ├── model_sandbox.py        ModelSandbox class + safety gate
│   │   └── sandbox_service.py      DB persistence for model metadata
│   ├── evaluation/metrics.py       Detection metrics + confusion matrix (Module 7)
│   ├── dashboard/app.py            Streamlit dashboard (Module 8)
│   ├── reporting/                  Report generation (Module 9)
│   │   ├── report_builder.py       12-section Markdown report
│   │   ├── templates/report_template.md
│   │   └── pdf_generator.py        HTML to PDF via PyQt5 QPrinter
│   ├── desktop/                    Desktop forensic application (Module 10)
│   │   ├── main_window.py          Tabbed application shell
│   │   ├── workers.py              Background QThread workers
│   │   ├── model_view.py           Model forensics + hash + metadata
│   │   ├── scan_view.py            Scan configuration + quick check
│   │   ├── scan_service.py         Full scan service + single-prompt check
│   │   ├── results_view.py         Security score + KPIs + metrics table
│   │   ├── activation_view.py      Aggregated feature heatmap + stats
│   │   └── report_view.py          PDF/MD export + suspicious case explorer
│   └── db/                         SQLAlchemy models + manager + cleanup
│       ├── models.py               12 ORM tables
│       ├── db_manager.py           get_session() with env override
│       └── cleanup.py              FK-safe output table reset
├── main.py                         Full pipeline runner
├── tests/                          68 tests across 11 files
└── requirements.txt                All dependencies
```

## 8. Module Descriptions

### Module 2 -- Dataset Builder
Loads CSV prompt data and generates deterministic edge-case/random
prompts. Produces a labeled `prompts` table with categories: normal,
adversarial, malicious_pattern, trigger, edge_case, and random.

### Module 3 -- Adversarial Fuzzer
Applies 7 mutation strategies (case_swap, emoji_inject, character_swap,
word_repeat, prompt_concat, special_chars, unicode_homoglyph) to each
prompt and collects per-execution security activation features.

### Module 4 -- Simulated Backdoor Testing
Injects known trigger tags (TRIGGER_ALPHA through GAMMA) into prompts
and verifies the toy model fires a `SIMULATED_LEAK` response.
Records backdoor-fired vs backdoor-clean comparisons.

### Module 5 -- Behavior Analyzer
Extracts behavioral signals (response length, token count, complexity)
and assigns a heuristic behavior score to each execution.

### Module 6 -- ML Anomaly Detection
Runs Isolation Forest, One-Class SVM, and Local Outage Factor on
behavior-score feature vectors. Comparison table stored for evaluation.

### Module 6b -- Activation Anomaly Detection
Builds a normal-category baseline of 6 aggregated features
(prompt_length, response_length, prompt_hash_score, trigger_signal,
injection_signal, response_change_signal) and scores every execution
against that baseline using z-score deviations.

### Module 6c -- Security Risk Scoring
Combines four signals with fixed weights (activation_anomaly 0.40,
injection_signal 0.24, trigger_signal 0.21, response_change 0.15)
into a single 0-100 risk score. Severity: LOW (0-30), MEDIUM (31-60),
HIGH (61-80), CRITICAL (81-100).

### Module 7 -- Security Evaluation
Computes precision, recall, F1, accuracy, FPR, FNR, and coverage for
each ML method against heuristic ground truth. Accuracy is persisted in
an `evaluation_confusion` table for cross-run tracking.

### Module 8 -- Dashboard
Streamlit-based interactive dashboard showing KPIs, prompt category
breakdown, fuzz detection distribution, anomaly method comparison,
risk distribution pie chart, top suspicious executions, and detection
metrics.

### Module 9 -- Reporting
Generates a 12-section Markdown report (Executive Summary, Test
Config, Methodology, Test Cases, Backdoor Results, Anomaly Detection,
Risk Distribution, Evaluation Metrics, Suspicious Cases,
Recommendations, Limitations, Conclusion) and a styled PDF version
via PyQt5 QPrinter.

### Module 10 -- Desktop Application + Model Sandbox
PyQt5 desktop forensic application with:
- **Model Forensics tab:** file selection, SHA-256 hash display,
  format detection, metadata form, DB persistence
- **Scan tab:** configurable prompts/seed/trigger, start scan with
  progress bar, quick single-prompt test
- **Results tab:** security score, risk category, detection counts,
  evaluation metrics table with accuracy
- **Activation tab:** aggregated feature heatmap (matplotlib) + stats
- **Report tab:** PDF/Markdown export, open last report, risk
  distribution table, suspicious case explorer

Model sandbox provides SHA-256 streaming hash, JSON/pytorch/safetensors/
onnx format detection, file validation, and a safety gate that blocks
unknown models.

## 9. Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.14 |
| ORM / Database | SQLAlchemy 2.x + SQLite |
| ML | scikit-learn (IsolationForest, OCSVM, LOF), numpy, pandas |
| Desktop GUI | PyQt5 5.15 |
| PDF generation | PyQt5 QPrinter |
| Visualization | matplotlib (desktop), Plotly + Streamlit (dashboard) |
| Config | PyYAML |
| Testing | pytest |
| Data | torch/transformers (optional, not used by default pipeline) |

All testing runs fully offline. No internet access is required.

## 10. Model Sandbox (SHA-256 + Metadata)

Before any pipeline run, the target model file is introspected:

1. **SHA-256 hash** is computed via streaming (1 MB chunks) and stored
   in the `model_metadata` table.
2. **Format detection** identifies JSON, PyTorch, SafeTensors, ONNX,
   or toy_model marker files.
3. **File validation** checks file exists, is readable, is not empty,
   and size is under 2 GB.
4. **Metadata persistence** stores file name, path, size, hash, model
   type, supported status, and a notes field in SQLite.
5. **Safety gate** (`ModelSandbox`) blocks any model not on the
   allowed-targets whitelist before the pipeline proceeds.

The toy model marker file is written to `outputs/builtin_models/`
with the SHA-256 hash embedded in the filename for traceability.

## 11. Adversarial Fuzzer (Module 3)

Seven registered mutation strategies:

| Mutation | Description |
|----------|-------------|
| case_swap | Reverses character casing |
| emoji_inject | Inserts random emoji at a random position |
| character_swap | Swaps two adjacent characters |
| word_repeat | Repeats a random word |
| prompt_concat | Appends a harmful/payload suffix |
| special_chars | Injects special characters (!@#$%^&*) |
| unicode_homoglyph | Replaces ASCII with Unicode lookalikes |

Each prompt is fuzzed with all 7 strategies. Edge-case prompts cover
repetition, token flooding, and mixed languages. Random prompts are
seeded for reproducibility.

## 12. Activation Tracker (Module 6b)

The `SecurityActivationCollector` extracts 6 security features per
execution:

| Feature | Description |
|---------|-------------|
| prompt_length | Character count of the input prompt |
| response_length | Character count of the model response |
| prompt_hash_score | Simple hash-based entropy measure |
| trigger_signal | Detects known trigger tags (1.0 if present) |
| injection_signal | Detects injection patterns (1.0 if present) |
| response_change_signal | Response difference from baseline (0.0-1.0) |

A **normal baseline** is built from the normal-category prompts. Every
execution is scored against this baseline using z-score deviations.
Executions with z > 3.0 on any feature are flagged.

## 13. Backdoor Simulation (Module 4)

Known trigger tags (`[TRIGGER_ALPHA]`, `[TRIGGER_BETA]`,
`[TRIGGER_GAMMA]`) are injected into prompts. The toy model is
hardcoded to respond with `SIMULATED_LEAK` when any trigger tag is
present. Each backdoor test compares the triggered response against
a clean (non-trigger) response to confirm the backdoor fires.

Result: 7/7 trigger tests fire as expected on the default pipeline.

## 14. Anomaly Detection (Module 6)

Three ML methods are run on behavior-score feature vectors:

- **Isolation Forest:** unsupervised outlier detection
- **One-Class SVM:** boundary-based novelty detection
- **Local Outage Factor:** density-based local outlier detection

All three produce binary anomaly labels (0/1) and anomaly scores.
A comparison table is stored for cross-method evaluation.

Note: with only 3 behavior features and class imbalance, ML F1 is
modest (0.12-0.18). This is honest and disclosed. The deterministic
stages (backdoor, activation anomaly, risk scoring) are the primary
detection signals.

## 15. Risk Scoring (Module 6c)

Each execution receives a weighted 0-100 risk score:

| Signal | Weight | Source |
|--------|--------|--------|
| activation_anomaly | 0.40 | Module 6b z-score |
| injection_signal | 0.24 | Security feature |
| trigger_signal | 0.21 | Security feature |
| response_change | 0.15 | Security feature |

Severity levels:

| Level | Range | Meaning |
|-------|-------|---------|
| LOW | 0-30 | Normal expected behavior |
| MEDIUM | 31-60 | Minor anomalies detected |
| HIGH | 61-80 | Strong injection/trigger signals |
| CRITICAL | 81-100 | Multiple severe indicators |

## 16. Evaluation (Module 7)

For each ML method (Isolation Forest, OCSVM, LOF), the pipeline
computes:

- **Precision:** TP / (TP + FP)
- **Recall:** TP / (TP + FN)
- **F1-score:** harmonic mean of precision and recall
- **Accuracy:** (TP + TN) / Total
- **False Positive Rate:** FP / (FP + TN)
- **False Negative Rate:** FN / (FN + TP)
- **Coverage:** percentage of total samples scored (capped at 1.0)

Accuracy is additionally persisted in a separate `evaluation_confusion`
table for cross-run tracking and trend analysis.

Ground truth: fuzzy results flagged by the behavior analyzer
(is_anomaly == True) are treated as the positive class.

## 17. Database

SQLite database with 12 tables:

| Table | Purpose |
|-------|---------|
| prompts | Labeled input prompts |
| fuzz_results | Mutation runs + detection flags |
| backdoor_tests | Trigger injection tests |
| behavior_scores | Heuristic behavior analysis |
| anomaly_results | ML anomaly detection |
| activation_features | Per-execution security features |
| activation_anomaly_results | Z-score activation anomaly scoring |
| risk_assessments | 0-100 risk scores + severity levels |
| evaluation_metrics | ML detection metrics per run |
| evaluation_confusion | Accuracy + TP/TN/FP/FN per run |
| model_metadata | Model file hash, format, path |
| execution_summary | Pipeline run summaries |

Database path and report directory are overridable via
`NEUROFENCE_DB_PATH` and `NEUROFENCE_REPORTS_DIR` environment variables.

## 18. Desktop Application

```bash
python -m src.desktop.app
```

PyQt5-based offline forensic application with 5 tabs:

| Tab | Features |
|-----|----------|
| Model Forensics | File open, SHA-256 display, format detection, metadata form, DB persist |
| Scan / Adversarial | Configurable prompts/seed/trigger, progress bar, quick check |
| Security Results | KPIs, risk category, evaluation metrics with accuracy |
| Activation Analysis | Aggregated feature heatmap (matplotlib), stats table |
| Report Export | PDF/Markdown export, open report, risk distribution, suspicious cases |

Runs the pipeline in a background QThread so the UI never freezes.
Fully offline -- no internet required.

## 19. Reporting

### Markdown Report (12 sections)
1. Executive Summary
2. Test Configuration
3. Testing Methodology
4. Test Cases
5. Backdoor Results
6. Anomaly Detection
7. Risk Distribution
8. Evaluation Metrics (with accuracy)
9. Suspicious Cases
10. Recommendations
11. Limitations
12. Conclusion

### PDF Report
Generated via PyQt5 QPrinter. HTML-to-PDF with styled CSS. Includes
all sections with tables and formatted metrics. Saved to
`outputs/reports/`.

## 20. Installation

```bash
# 1. Clone the repository
git clone https://github.com/<team>/NeuroFence.git
cd NeuroFence

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Sanity check
python -m src.config_loader
```

If `torch`/`transformers` fail to install, comment those two lines in
`requirements.txt` -- they are only needed for optional real HuggingFace
models, not the default toy pipeline.

## 21. Offline Usage

NeuroFence runs **entirely offline**. No internet connection is required
at any stage:

- Dataset is loaded from local CSV files and generated deterministically.
- Fuzzing uses local mutation engine.
- Model inference runs locally (toy model is pure Python, no network).
- Anomaly detection uses scikit-learn (local computation).
- Desktop app and reporting are fully local.

## 22. Running Tests

```bash
# Full test suite (68 tests)
python -m pytest tests/ -v

# Just the comprehensive spec tests
python -m pytest tests/test_full_spec.py -v

# Just the project health tests
python -m pytest tests/test_project_health.py -v
```

All 68 tests pass. Tests use environment variable overrides
(`NEUROFENCE_DB_PATH`) to run in isolated databases and never modify
the main project database.

## 23. Demo Workflow

For the Mid Review demonstration:

```bash
# Step 1: Show the desktop app
python -m src.desktop.app

# Step 2: Run the full pipeline
python main.py

# Step 3: Check the database
python -c "
from src.db.db_manager import get_session
from src.db.models import RiskAssessmentRow, EvaluationMetric
s = get_session()
print('Risks:', s.query(RiskAssessmentRow).count())
print('Metrics:', s.query(EvaluationMetric).count())
s.close()
"

# Step 4: Run the dashboard
streamlit run src/dashboard/app.py

# Step 5: Run the test suite
python -m pytest tests/ -v
```

## 24. Example Results

From a clean `python main.py` run (seed 42):

```
Prompts in dataset            : 50
  (10 normal / 10 adversarial / 10 malicious / 7 trigger /
   8 edge / 5 random)
Fuzz mutation runs            : 350
Backdoor trigger tests        : 7/7 fired as expected

Risk distribution:
  LOW      : 262 (73.4%)
  MEDIUM   :  27  (7.6%)
  HIGH     :  68 (19.0%)
  CRITICAL :   0  (0.0%)

Security score (LOW+MEDIUM)   : 81.0 / 100

ML Detection Metrics:
  isolation_forest  : F1=0.175  Accuracy=0.737  Coverage=1.00
  ocsvm             : F1=0.182  Accuracy=0.748  Coverage=1.00
  lof               : F1=0.123  Accuracy=0.720  Coverage=1.00
```

> **Honest interpretation:** ML F1 is modest (0.12-0.18) because only
> 3 behavior-score features are used with significant class imbalance.
> The ML stage is a supporting cross-check, not the primary detection
> mechanism. The deterministic stages -- backdoor trigger firing,
> activation anomaly scoring, and risk scoring -- are the reliable
> primary signals in this simulated pipeline.

## 25. Limitations

1. **Simulated target only:** The pipeline runs against a synthetic toy
   model with hardcoded backdoors. No real, third-party model is
   targeted.
2. **ML F1 is low:** The ML anomaly detectors show modest performance
   due to limited features and class imbalance. This is documented and
   expected.
3. **Trigger matching is exact:** The toy model's trigger detection is
   case-sensitive and exact. Obfuscated or partial triggers would evade
   it.
4. **Ground truth is heuristic:** Evaluation labels come from the
   behavior analyzer, not human annotation.
5. **Script-level re-runs append:** Running individual modules multiple
   times appends rows. Only `main.py` gives a clean single-run snapshot.
6. **Activation features are aggregated:** The desktop heatmap shows
   aggregated security features, not individual neuron activations,
   because the toy model is rule-based and does not expose real
   activations.

## 26. Future Enhancements

1. **Real local model support:** Integrate a HuggingFace model behind
   the existing safety gate and model sandbox.
2. **Richer features:** Add semantic similarity, embedding-based
   detection, and perplexity scoring to the activation feature set.
3. **Obfuscated trigger variants:** Add lowercased, split, and
   homoglyph-obfuscated trigger tests to reduce evasion.
4. **Human-in-the-loop evaluation:** Replace heuristic ground truth with
   human-annotated labels to get meaningful ML precision/recall.
5. **Additional mutation strategies:** Token-level attacks, gradient-
   based perturbations (for differentiable models), and multi-turn
   injection attempts.
6. **Export formats:** CSV/JSON risk export, STIX/TAXII integration for
   SOC teams.
7. **Model comparison:** Compare multiple models side-by-side on the
   same prompt set.

## 27. Safety & Ethical Guardrails

- **Whitelist enforcement:** `assert_target_is_safe()` blocks any model
  not on the `allowed_targets` list before the pipeline proceeds.
- **Local only:** No network calls, no API endpoints, no data exfil.
  All testing stays on the user's machine.
- **Synthetic model:** Backdoor testing uses a deliberately compromised
  toy model. This is research, not an attack tool.
- **Clear labeling:** All results marked "simulated" in code, report,
  and dashboard. The report includes explicit Limitations and honest
  ML-metric disclosure.
- **No secrets:** No API keys, credentials, or sensitive data are
  stored, logged, or transmitted.
- **Reproducibility:** Seeded random generation ensures identical
  results across runs on the same machine.

---

*NeuroFence is a research and educational security-testing framework.
All backdoor and trigger tests are performed against a simulated,
locally controlled toy model and are clearly labeled as such. This
tool is designed to help teams understand and detect AI security
vulnerabilities, not to exploit them.*
