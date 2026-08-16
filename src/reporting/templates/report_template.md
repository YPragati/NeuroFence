# NeuroFence Security Testing Report

**Run ID:** {{ run_id }}
**Generated:** {{ generated_at }}

---

## 1. Executive Summary

This report summarizes an automated AI security testing session run
by NeuroFence against a **local, fully controlled toy model**. All
tests -- adversarial prompt fuzzing, simulated backdoor trigger
testing, and ML-based anomaly detection -- were executed against
locally controlled or explicitly authorized targets only.

- **Total prompts in dataset:** {{ total_prompts }}
- **Total fuzz mutation runs:** {{ total_fuzz_runs }}
- **Total simulated backdoor tests:** {{ total_backdoor_tests }}
- **Overall security score:** {{ security_score }} / 100

---

## 2. Testing Methodology

1. A labeled prompt dataset was built across 4 categories: normal,
   adversarial, malicious-pattern, and trigger prompts.
2. Each prompt was mutated using {{ mutation_type_count }} distinct
   mutation strategies (case swap, character noise, synonym wrapping,
   injection wrapping, encoding hints, whitespace padding, and
   unicode-confusable substitution).
3. Synthetic backdoor triggers were injected into a subset of prompts
   and compared against trigger-stripped ("clean") counterparts to
   test whether the target model's behavior changed only when the
   trigger was present.
4. Behavior scores (consistency, prompt similarity, confidence proxy)
   were computed for every test run.
5. Three ML anomaly detection algorithms (Isolation Forest, One-Class
   SVM, Local Outlier Factor) were run on the behavior score features
   and compared.
6. Detection metrics (precision, recall, F1, false positive/negative
   rate, coverage) were computed against known heuristic/backdoor
   ground truth labels.

---

## 3. Test Case Summary

| Category | Prompt Count |
|---|---|
{{ category_table }}

---

## 4. Backdoor Testing Findings

{{ backdoor_findings }}

---

## 5. Anomaly Detection Results

{{ anomaly_results_table }}

---

## 6. Security Evaluation Metrics

{{ metrics_table }}

---

## 7. Recommendations

{{ recommendations }}

---

*This report was generated automatically by NeuroFence. All backdoor
and trigger tests were performed against a simulated, locally
controlled toy model for research/educational purposes. Results
labeled as "simulated" should not be interpreted as findings against
any real, deployed AI system.*
