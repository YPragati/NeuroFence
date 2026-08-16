# NeuroFence -- AI Security & Backdoor Detection

A local, self-contained framework for adversarial prompt fuzzing,
simulated backdoor trigger testing, and anomaly-based security
evaluation of AI models.

**Status:** All 9 modules complete (Project Setup through Reporting).

## Setup
1. `python -m venv venv` then activate it
   - Windows: `venv\Scripts\Activate.ps1`
   - macOS/Linux: `source venv/bin/activate`
2. `pip install -r requirements.txt`
   - If `torch`/`transformers` are slow/fail to install on your machine,
     comment those two lines out in `requirements.txt` -- they are only
     needed if you later plug in a real local HuggingFace model instead
     of the toy model.
3. `python -m src.config_loader` (sanity check)

## Run the full pipeline (one command)
```
python main.py
```
This runs, in order: dataset build -> adversarial fuzzing -> simulated
backdoor testing -> behavior analysis -> anomaly detection (Isolation
Forest / One-Class SVM / LOF) -> security evaluation metrics -> report
generation. A Markdown report is written to `outputs/reports/`.

## Run the dashboard
```
streamlit run src/dashboard/app.py
```
Opens an interactive dashboard (charts, test history, security score)
reading from the SQLite database populated by `main.py`.

## Run individual modules
Each module can also be run standalone, in order:
```
python -m src.dataset.dataset_builder
python -m src.fuzzer.fuzz_runner
python -m src.backdoor_sim.trigger_injector
python -m src.behavior_analyzer.analyzer
python -m src.anomaly_detection.model_comparator
python -m src.evaluation.metrics
python -m src.reporting.report_builder
```

## Run tests
```
pytest tests/ -v
```

## Safety
NeuroFence only tests locally controlled or explicitly whitelisted
targets, enforced in `src/config_loader.assert_target_is_safe()`.
All backdoor testing uses a fully local, synthetic toy model (see
`src/model_interface/toy_model.py`) -- no real, third-party AI system
is targeted. Results labeled "simulated" are clearly marked as such
throughout the code and generated reports.
