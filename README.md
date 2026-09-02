# 🛡️ NeuroFence -- AI Security & Backdoor Detection

A local, self-contained framework for adversarial prompt fuzzing,
simulated backdoor trigger testing, activation-feature anomaly
analysis, and risk-based security evaluation of AI models. **All
testing runs against a fully local, controlled toy model** -- no real,
third-party AI system is ever targeted.

> **Status:** Complete for the Mid Review. All pipeline stages
> (Modules 2-9, including Member-2 activation/risk integration) are
> implemented, tested (46 tests), and wired into the dashboard and
> reporting.

---

## 1. Problem

AI systems deployed in production can be subverted by **prompt
injection**, **adversarial inputs**, and **backdoors / data
poisoning**. Detecting these before deployment is hard and typically
requires expensive, risky tests against live systems. Teams need a
cheap, local, deterministic way to probe a model's behavior for
abnormal responses.

## 2. Motivation

NeuroFence exists to give security engineers and ML teams a **safe,
reproducible harness** for security-testing a model without touching a
production endpoint. By using a controllable toy model with *injected,
known* behaviors, NeuroFence's pipeline (fuzz → trigger → analyze →
detect → score → report) can be validated end-to-end and then pointed
at a local real model later.

## 3. Objectives

- Build labeled prompt datasets across normal / adversarial /
  malicious-pattern / trigger categories, plus deterministic
  edge/random prompts.
- Fuzz every prompt with multiple mutations and detect anomalies.
- Simulate backdoor triggers and verify the toy model fires them.
- Collect per-execution **activation features**, build a normal
  baseline, and score deviations.
- Combine anomaly/injection/trigger/response signals into a single
  **0-100 risk score** with clear severity levels.
- Evaluate ML detectors against the known ground truth.
- Generate a human-readable security report and an interactive
  dashboard.
- Be fully reproducible (seeded) and honest about which results are
  simulated.

## 4. Solution Overview

NeuroFence runs a nine-stage pipeline and stores every result in a
SQLite database:

```
Dataset Build (2) -> Adversarial Fuzzing (3) -> Simulated Backdoor
Testing (4) -> Behavior Analysis (5) -> ML Anomaly Detection (6) ->
Activation Anomaly Detection (6b) -> Security Risk Scoring (6c) ->
Security Evaluation (7) -> Dashboard (8) -> Report (9)
```

## 5. Architecture

```
config/settings.yaml            Central configuration (paths, seed, weights)
src/
  config_loader.py              Single source of truth for config + safety gate
  dataset/dataset_builder.py    Build labeled prompt dataset (Module 2)
  fuzzer/                       Adversarial prompt fuzzing (Module 3)
    mutation_engine.py          Mutation strategies (7 registered)
    prompt_generator.py         Deterministic edge/random prompts
    fuzz_runner.py              Orchestrates fuzzing + feature collection
  backdoor_sim/                 Simulated backdoor testing (Module 4)
    trigger_injector.py         Runs triggered vs clean comparisons
    trigger_library.py          Known trigger tags + stripping
  behavior_analyzer/analyzer.py Behavior scores (Module 5)
  activation/collector.py       SecurityActivationCollector features
  anomaly_detection/            Anomaly detection (Modules 6, 6b, 6c)
    model_comparator.py         Isolation Forest / OCSVM / LOF
    activation_anomaly.py       Feature-baseline anomaly scoring
    risk_scorer.py              Weighted 0-100 risk scoring
  model_interface/toy_model.py  Local synthetic model with injected backdoors
  evaluation/metrics.py         Detection metrics vs ground truth (Module 7)
  dashboard/app.py              Streamlit dashboard (Module 8)
  reporting/report_builder.py   Markdown report generator (Module 9)
  db/                           SQLAlchemy models + manager + cleanup
main.py                         Runs the full pipeline end-to-end
tests/                          46 tests across 10 files
```

## 6. Modules & Data Flow

| # | Module | Input | Output |
|---|--------|-------|--------|
| 2 | Dataset Build | raw CSVs | `prompts` table |
| 3 | Adversarial Fuzzing | prompts | `fuzz_results`, `activation_features` |
| 4 | Simulated Backdoor Testing | trigger prompts | `backdoor_tests`, `activation_features` |
| 5 | Behavior Analysis | results | `behavior_scores` |
| 6 | ML Anomaly Detection | behavior scores | `anomaly_results` |
| 6b | Activation Anomaly | activation features | `activation_anomaly_results` |
| 6c | Security Risk Scoring | features + anomalies | `risk_assessments` |
| 7 | Security Evaluation | anomalies + labels | `evaluation_metrics`, `evaluation_confusion` |
| 8 | Dashboard | all tables | interactive UI |
| 9 | Report Generation | all tables | `outputs/reports/*.md` |

## 7. Risk Scoring Model (Module 6c)

Each execution gets a normalized **0-100 risk score** combining four
signals with fixed weights (defined in `risk_scorer.py`):

| Signal | Weight |
|---|---|
| activation anomaly | 0.40 |
| injection signal | 0.24 |
| trigger signal | 0.21 |
| response change | 0.15 |

Severity levels:

| Level | Range |
|---|---|
| LOW | 0-30 |
| MEDIUM | 31-60 |
| HIGH | 61-80 |
| CRITICAL | 81-100 |

## 8. Tech Stack

Python 3.14, SQLAlchemy (SQLite), scikit-learn, pandas, numpy, PyYAML,
Streamlit, Plotly, pytest. `torch`/`transformers` are included for
optional real local models but are **not needed** for the default toy
pipeline (see [Setup](#11-setup)).

## 9. Safety & Ethical Guardrails

- `src/config_loader.assert_target_is_safe()` enforces a hard
  whitelist (`allowed_targets`) before any prompt is sent.
- All backdoor/trigger testing uses the **fully local synthetic
  `toy_model`** with deliberately injected behaviors -- this is
  research/education, never an attack on a real system.
- Results marked "simulated" are clearly labeled in the code, report,
  and dashboard. The report includes explicit **Limitations** and
  honest ML-metric disclosure.

## 10. Example Results (latest clean run)

From a single `python main.py` run (clean DB, seed 42):

```
Prompts in dataset            : 50  (10 normal / 10 adversarial / 10
                                     malicious / 7 trigger / 8 edge / 5 random)
Fuzz mutation runs            : 350
Backdoor trigger tests        : 7/7 fired as expected
Risk distribution             : LOW 262 (73.4%) / MEDIUM 27 (7.6%) /
                                 HIGH 68 (19.0%) / CRITICAL 0
Security score (LOW/MEDIUM)   : 81.0 / 100
ML F1 (isolation_forest)      : 0.175   (low, documented below)
ML F1 (ocsvm)                 : 0.182
ML F1 (lof)                   : 0.123
```

> **Honest interpretation:** the ML anomaly detectors show **modest F1
> scores (≈0.12-0.18)** against NeuroFence's own heuristic ground
> truth. This is expected and disclosed: with only 3 behavior-score
> features and a class-imbalanced set, the ML stage is a supporting
> cross-check. The **deterministic** stages -- backdoor trigger firing
> (Module 4), activation-feature anomaly scoring (Module 6b), and
> weighted risk scoring (Module 6c) -- are the reliable primary
> signals in this simulated pipeline. Accuracy for the ML stage is
> ≈0.72-0.75 because the majority class (normal) is predicted well
> even though true-positive detection is weak.

## 11. Setup

1. Create and activate a virtual environment:
   - Windows: `python -m venv venv` then `venv\Scripts\Activate.ps1`
   - macOS/Linux: `python -m venv venv` then `source venv/bin/activate`
2. `pip install -r requirements.txt`
   - If `torch`/`transformers` are slow/fail to install, comment those
     two lines out -- they are only needed for an optional real local
     HuggingFace model, not the default toy pipeline.
3. `python -m src.config_loader` (sanity check: loads config, passes
   the whitelist safety gate).

## 12. Run the Full Pipeline

```
python main.py
```

This runs every stage in order and writes a Markdown report to
`outputs/reports/`. A full run **resets the result tables** to a clean
single-run state (prompts and report history are preserved), so counts
are reproducible across runs.

The database path and report directory can be overridden with the
`NEUROFENCE_DB_PATH` and `NEUROFENCE_REPORTS_DIR` environment
variables (used by the automated tests and useful for custom setups).

## 13. Run Individual Modules

Each module can also be run standalone, in order:

```
python -m src.dataset.dataset_builder
python -m src.fuzzer.fuzz_runner
python -m src.backdoor_sim.trigger_injector
python -m src.behavior_analyzer.analyzer
python -m src.anomaly_detection.model_comparator
python -m src.anomaly_detection.activation_anomaly
python -m src.anomaly_detection.risk_scorer
python -m src.evaluation.metrics
python -m src.reporting.report_builder
```

> Note: script-level re-runs **append** rows (they don't reset).
> Delete the database file or run `main.py` for a clean snapshot.

## 14. Dashboard

```
streamlit run src/dashboard/app.py
```

Shows: KPIs, prompt category breakdown, fuzz detection pie, backdoor
results, anomaly-method comparison, **security risk distribution
(Module 6c)**, **top suspicious executions**, security score, and
detection metrics (including accuracy) with a note that ML F1 is a
supporting cross-check.

## 15. Tests

```
python -m pytest tests/ -v
```

46 tests across 10 files cover: dataset builder, fuzzer mutations,
backdoor simulation, behavior analyzer, ML anomaly detection,
activation collection, activation anomaly, risk scoring, Member-2
integration, and **project health** (full-pipeline end-to-end,
repeated-run reproducibility, report sections, coverage cap, and the
DB-path environment override).

## 16. Known Limitations & Future Work

**Limitations**
- Simulated target only (no real/live model tested).
- ML-metric ground truth is heuristic; ML F1 is low and disclosed.
- Trigger matching is exact/case-sensitive on the toy model.
- Script-level re-runs append; only `main.py` gives a clean snapshot.

**Future work**
- Richer behavior features and a stronger feature-based detector.
- Additional adversarial / malicious pattern prompts over time.
- Optional real local model (HuggingFace) behind the existing safety
  gate and toy fallback.
- Lowercased / obfuscated trigger variants to reduce evasion.

---

*NeuroFence is a research/educational security-testing framework. All
backdoor and trigger tests are performed against a simulated, locally
controlled toy model and are clearly labeled as such.*
