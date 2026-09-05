"""
Statistical Anomaly Detection Engine (real).

Identifies "potentially suspicious activation behavior" from the real
per-layer activation statistics that the adversarial scan records in
`activation_measurements`.

This engine intentionally does NOT claim that a statistical anomaly proves
a neural backdoor. It only computes, per (prompt, layer, feature):

    * a per-layer baseline activation distribution (from normal inputs)
    * per-neuron/feature statistics (the aggregated layer statistics are
      treated as the observable features -- mean, std, max, energy/norm,
      active fraction)
    * mean deviation and standard-deviation Z-scores vs the baseline
    * activation-energy (L2 norm) deviation
    * an input-specific activation-profile correlation (cosine similarity
      of the observed metric vector against the baseline mean vector)
    * an anomaly score bounded to [0, 100] and a LOW / MEDIUM / HIGH /
      CRITICAL severity (from configurable thresholds)
    * a heuristic confidence in [0, 1] that documents how the score was
      reached (agreement across metrics, signal strength, baseline depth)

Everything is deterministic and reproducible. The math is pure Python
(statistics module) so it can run inside the desktop app process without
importing torch.
"""

import json
import math
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.config_loader import get_config

# Observable activation features (metrics) per layer. The aggregated layer
# statistics are the "features" -- per-neuron tensors are not stored, so we
# analyze the practical granularity that is actually recorded.
METRICS: tuple = ("mean", "std", "max_val", "norm", "active_fraction")

NORMAL_CATEGORIES: set = {"normal"}

SEVERITY_ORDER: tuple = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

EPS = 1e-9

# Feature used as the activation-energy proxy (L2 norm of the activation).
ENERGY_METRIC = "norm"

_DISCLAIMER = (
    "Statistical anomaly indicates potentially suspicious activation "
    "behavior; it is not proof of a neural backdoor."
)


class StatisticalConfig:
    """
    Configurable thresholds for the statistical engine.

    Defaults come from config/settings.yaml -> anomaly_detection.statistical
    and are merged over the built-in defaults, so the operator can tune them
    without touching code.
    """

    def __init__(
        self,
        severity_cutoffs: Optional[List[float]] = None,
        z_score_min: float = 2.0,
        baseline_min_n: int = 2,
        score_gain_per_sigma: float = 10.0,
        correlation_min: float = 0.6,
    ):
        # [CRITICAL-bound, HIGH-bound, MEDIUM-bound]; below MEDIUM-bound = LOW.
        self.severity_cutoffs = list(severity_cutoffs) if severity_cutoffs else [80.0, 60.0, 40.0]
        self.z_score_min = float(z_score_min)
        self.baseline_min_n = max(1, int(baseline_min_n))
        self.score_gain_per_sigma = float(score_gain_per_sigma)
        self.correlation_min = float(correlation_min)

    @classmethod
    def from_settings(cls) -> "StatisticalConfig":
        """Build config, honoring config/settings.yaml overrides."""
        base = cls()
        try:
            sec = (get_config().get("anomaly_detection", {}) or {}).get("statistical", {}) or {}
        except Exception:  # noqa: BLE001 -- config optional; fall back to defaults
            sec = {}
        if sec.get("severity_cutoffs"):
            base.severity_cutoffs = [float(x) for x in sec["severity_cutoffs"]]
        if sec.get("z_score_min") is not None:
            base.z_score_min = float(sec["z_score_min"])
        if sec.get("baseline_min_n") is not None:
            base.baseline_min_n = max(1, int(sec["baseline_min_n"]))
        if sec.get("score_gain_per_sigma") is not None:
            base.score_gain_per_sigma = float(sec["score_gain_per_sigma"])
        if sec.get("correlation_min") is not None:
            base.correlation_min = float(sec["correlation_min"])
        return base

    def severity_for_score(self, score: float) -> str:
        """Classify an anomaly score into a severity level."""
        for level, bound in zip(SEVERITY_ORDER, self.severity_cutoffs):
            if score >= bound:
                return level
        return "LOW"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "severity_cutoffs": self.severity_cutoffs,
            "z_score_min": self.z_score_min,
            "baseline_min_n": self.baseline_min_n,
            "score_gain_per_sigma": self.score_gain_per_sigma,
            "correlation_min": self.correlation_min,
        }


def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _features_of(measurement: Dict[str, Any]) -> Dict[str, float]:
    """Extract the finite metric values available on a measurement."""
    out: Dict[str, float] = {}
    for met in METRICS:
        val = measurement.get(met)
        if _finite(val):
            out[met] = float(val)
    return out


def _safe_z(observed: float, baseline_mean: float, baseline_std: float) -> float:
    """
    Z-score with a bounded fallback when the baseline has zero spread:
    if the baseline is degenerate (std == 0), scale by a small fraction of
    the baseline mean so a real deviation is still visible.
    """
    if baseline_std and baseline_std > EPS:
        return (observed - baseline_mean) / baseline_std
    scale = max(abs(baseline_mean) * 0.1, EPS)
    if scale <= EPS:
        return 0.0
    return (observed - baseline_mean) / scale


def _cosine(a: List[float], b: List[float]) -> Optional[float]:
    """Cosine similarity between two non-empty vectors (input activation
    profile vs baseline profile). Returns None if undefined."""
    if len(a) < 2 or len(b) < 2 or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= EPS or nb <= EPS:
        return None
    return dot / (na * nb)


def _relative_deviation(observed: float, baseline: float) -> Optional[float]:
    """Relative deviation (observed - baseline) / |baseline|, or 0 when both
    are zero; None if the baseline is zero but observed is not."""
    if baseline == 0:
        return 0.0 if observed == 0 else None
    return (observed - baseline) / abs(baseline)


def compute_baseline(
    measurements: List[Dict[str, Any]],
    config: Optional[StatisticalConfig] = None,
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Build the per-layer baseline activation distribution from inputs whose
    category is 'normal'.

    Returns {layer: {metric: {"mean", "std", "n", "min", "max"}}}.
    A metric is only present for a layer when at least
    config.baseline_min_n normal samples are available.
    """
    cfg = config or StatisticalConfig.from_settings()
    groups: Dict[str, List[Dict[str, float]]] = defaultdict(list)
    for m in measurements:
        if str(m.get("category", "")).lower() not in NORMAL_CATEGORIES:
            continue
        feats = _features_of(m)
        if m.get("layer"):
            groups[str(m["layer"])].append(feats)

    baseline: Dict[str, Dict[str, Dict[str, float]]] = {}
    for layer, items in groups.items():
        layer_base: Dict[str, Dict[str, float]] = {}
        for met in METRICS:
            vals = [it[met] for it in items if met in it]
            vals = [v for v in vals if math.isfinite(v)]
            if len(vals) < cfg.baseline_min_n:
                continue
            mean = statistics.fmean(vals)
            std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
            layer_base[met] = {
                "mean": mean,
                "std": std,
                "n": len(vals),
                "min": min(vals),
                "max": max(vals),
            }
        if layer_base:
            baseline[layer] = layer_base
    return baseline


def _confidence(voting: float, signal: float, breadth: float) -> float:
    """
    Heuristic confidence in [0, 1]:
        0.5 * voting   (share of metrics that agree the signal is anomalous)
        0.3 * signal   (how far the strongest deviation is past the threshold)
        0.2 * breadth  (baseline depth, saturated at 10 samples)
    This is a transparent engineering heuristic, not a scientific claim.
    """
    return min(1.0, max(0.0, 0.5 * voting + 0.3 * signal + 0.2 * breadth))


def _explanation(
    feature: str,
    layer: str,
    category: str,
    observed: float,
    bmean: float,
    bstd: float,
    n: int,
    z: float,
    score: float,
    severity: str,
    extra: str,
) -> str:
    parts = [
        f"Observed '{feature}' = {observed:.5g} in layer '{layer}' for a "
        f"{category} input; the normal baseline (N={n}) is {bmean:.5g} "
        f"(mean) \u00b1 {bstd:.5g} (std).",
        f"Deviation is {z:+.2f}\u03c3, anomaly score {score:.0f}/100 "
        f"({severity}).",
    ]
    if extra:
        parts.append(extra)
    parts.append(_DISCLAIMER)
    return " ".join(parts)


def evaluate_measurements(
    measurements: List[Dict[str, Any]],
    config: Optional[StatisticalConfig] = None,
    baseline: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None,
) -> List[Dict[str, Any]]:
    """
    Score every measurement against the per-layer normal baseline.

    Returns one finding-dict per (prompt, layer, feature) whose |z| exceeds
    config.z_score_min and whose layer has a usable baseline. Each dict holds
    the exact fields the StatisticalFinding row stores.
    """
    cfg = config or StatisticalConfig.from_settings()
    if baseline is None:
        baseline = compute_baseline(measurements, cfg)

    findings: List[Dict[str, Any]] = []

    for m in measurements:
        layer = str(m.get("layer", ""))
        base = baseline.get(layer)
        if not base:
            continue
        feats = _features_of(m)
        present = {met: val for met, val in feats.items() if met in base}
        if not present:
            continue

        zs: Dict[str, float] = {}
        for met, val in present.items():
            zs[met] = _safe_z(val, base[met]["mean"], base[met]["std"])

        base_means = [base[met]["mean"] for met in present]
        obs_vec = [present[met] for met in present]
        corr = _cosine(obs_vec, base_means)

        voting_share = sum(1 for z in zs.values() if abs(z) >= cfg.z_score_min) / len(zs)
        first_met = list(present)[0]
        breadth = min(1.0, base[first_met]["n"] / 10.0)  # baseline depth (per-layer, any metric)
        sigma = math.sqrt(statistics.fmean(z * z for z in zs.values())) if zs else 0.0

        energy_obs = present.get(ENERGY_METRIC)
        energy_base = base.get(ENERGY_METRIC, {}).get("mean")
        energy_dev = (
            _relative_deviation(energy_obs, energy_base)
            if energy_obs is not None and energy_base is not None
            else None
        )

        for met, z in zs.items():
            if abs(z) < cfg.z_score_min:
                continue
            score = min(100.0, max(0.0, abs(z) * cfg.score_gain_per_sigma))
            severity = cfg.severity_for_score(score)
            signal = min(1.0, abs(z) / (2.0 * cfg.z_score_min))
            confidence = _confidence(voting_share, signal, breadth)

            mean_dev = None
            if met == "mean":
                mean_dev = _relative_deviation(present[met], base[met]["mean"])

            extras = []
            if met == ENERGY_METRIC and energy_dev is not None:
                extras.append(
                    f"Activation energy (L2 norm) deviation "
                    f"{energy_dev:+.1%}."
                )
            extra = " ".join(extras)

            findings.append({
                "run_id": m.get("run_id"),
                "prompt_id": m.get("prompt_id"),
                "category": str(m.get("category", "")),
                "model": m.get("model"),
                "layer": layer,
                "feature": met,
                "observed_statistic": present[met],
                "baseline_mean": base[met]["mean"],
                "baseline_std": base[met]["std"],
                "baseline_n": int(base[met]["n"]),
                "baseline_min": base[met]["min"],
                "baseline_max": base[met]["max"],
                "z_score": z,
                "mean_deviation": mean_dev,
                "energy_deviation": energy_dev,
                "correlation": corr,
                "layer_sigma": sigma,
                "anomaly_score": round(score, 2),
                "confidence": round(confidence, 3),
                "severity": severity,
                "explanation": _explanation(
                    met, layer, m.get("category", ""), present[met],
                    base[met]["mean"], base[met]["std"], int(base[met]["n"]),
                    z, score, severity, extra,
                ),
                "evidence": json.dumps({
                    "run_id": m.get("run_id"),
                    "prompt_id": m.get("prompt_id"),
                    "category": m.get("category"),
                    "input_text": m.get("input_text"),
                    "layer": layer,
                    "feature": met,
                    "observed_statistic": present[met],
                    "baseline_mean": base[met]["mean"],
                    "baseline_std": base[met]["std"],
                    "baseline_n": int(base[met]["n"]),
                    "baseline_min": base[met]["min"],
                    "baseline_max": base[met]["max"],
                    "z_score": z,
                    "mean_deviation": mean_dev,
                    "energy_deviation": energy_dev,
                    "correlation": corr,
                    "layer_sigma": sigma,
                    "all_features": {
                        k: {
                            "observed": present[k],
                            "baseline_mean": base[k]["mean"],
                            "baseline_std": base[k]["std"],
                            "z_score": zs[k],
                        }
                        for k in present
                    },
                    "method": "statistical_baseline_zscore",
                }, ensure_ascii=False),
            })

    findings.sort(
        key=lambda f: (
            SEVERITY_ORDER.index(f["severity"]),
            -abs(f["z_score"]),
        )
    )
    return findings


# ---------------------------------------------------------------------------
# Database integration
# ---------------------------------------------------------------------------

def _run_row(session, run_id: Optional[int]):
    from src.db.models import AdversarialScanRun
    if run_id is not None:
        return session.get(AdversarialScanRun, int(run_id))
    return (
        session.query(AdversarialScanRun)
        .filter(AdversarialScanRun.status == "completed")
        .order_by(AdversarialScanRun.run_id.desc())
        .first()
    )


def latest_completed_run() -> Optional[Dict[str, Any]]:
    """Return {run_id, scan_label} for the most recent completed scan, if any."""
    from src.db.db_manager import get_session
    session = get_session()
    try:
        row = _run_row(session, None)
    finally:
        session.close()
    if row is None:
        return None
    return {"run_id": row.run_id, "scan_label": row.run_label}


def persist_statistical_findings(
    session,
    records: List[Dict[str, Any]],
    scan_label: str,
    run_id: Optional[int] = None,
    force: bool = True,
) -> int:
    """Insert finding records into the DB (used by the standalone detector
    AND the scan pipeline so both write identical rows).

    Returns the number of rows inserted.
    """
    from src.db.models import StatisticalFinding

    if not records:
        return 0
    if run_id is None:
        run_id = records[0].get("run_id")
    if run_id is not None and force:
        session.query(StatisticalFinding).filter(
            StatisticalFinding.run_id == run_id
        ).delete(synchronize_session=False)

    for r in records:
        session.add(StatisticalFinding(
            run_id=run_id or r.get("run_id"),
            scan_label=scan_label,
            prompt_id=r["prompt_id"],
            category=r["category"],
            model=r["model"],
            layer=r["layer"],
            feature=r["feature"],
            baseline_mean=r["baseline_mean"],
            baseline_std=r["baseline_std"],
            baseline_n=r["baseline_n"],
            observed_statistic=r["observed_statistic"],
            z_score=r["z_score"],
            mean_deviation=r["mean_deviation"],
            energy_deviation=r["energy_deviation"],
            correlation=r["correlation"],
            anomaly_score=r["anomaly_score"],
            confidence=r["confidence"],
            severity=r["severity"],
            explanation=r["explanation"],
            evidence=r["evidence"],
        ))
    return len(records)


def generate_statistical_findings(
    run_id: Optional[int] = None,
    force: bool = True,
    config: Optional[StatisticalConfig] = None,
) -> Dict[str, Any]:
    """
    Run the statistical anomaly engine over a scan run's activation
    measurements and persist StatisticalFinding rows.

    `force=True` (default) removes previously stored findings for the run
    first, so re-running refreshes instead of duplicating.
    """
    from src.db.db_manager import get_session
    from src.fuzzer.adversarial_scan import measurements_for_run

    cfg = config or StatisticalConfig.from_settings()

    session = get_session()
    try:
        run = _run_row(session, run_id)
        if run is None:
            return {"status": "no_run", "run_id": run_id, "findings_created": 0}

        rid = run.run_id
        scan_label = run.run_label

        # Only analyze completed runs with data.
        measurements = measurements_for_run(rid, limit=100000)

        baseline = compute_baseline(measurements, cfg)
        if not baseline:
            return {
                "status": "insufficient_baseline",
                "run_id": rid,
                "scan_label": scan_label,
                "message": ("No baseline could be built: the run has no 'normal' "
                            "category measurements (need at least "
                            f"{cfg.baseline_min_n})."),
                "findings_created": 0,
            }

        records = evaluate_measurements(measurements, cfg, baseline)
        baseline_layers = sorted(baseline.keys())
        normal_n = sum(1 for m in measurements if str(m.get("category", "")).lower() in NORMAL_CATEGORIES)

        created = persist_statistical_findings(
            session, records, scan_label=scan_label, run_id=rid, force=force
        )
        session.commit()

        dist = {level: 0 for level in SEVERITY_ORDER}
        for r in records:
            dist[r["severity"]] += 1
        peak = max((r["anomaly_score"] for r in records), default=0.0)

        return {
            "status": "completed",
            "run_id": rid,
            "scan_label": scan_label,
            "method": "statistical_baseline_zscore",
            "baseline_layers": baseline_layers,
            "baseline_normal_samples": normal_n,
            "measurements_analyzed": len(measurements),
            "findings_created": created,
            "current_anomaly_score": round(peak, 2),
            "severity_distribution": dist,
            "thresholds": cfg.as_dict(),
            "disclaimer": _DISCLAIMER,
        }
    finally:
        session.close()


def list_findings(
    limit: int = 500,
    run_id: Optional[int] = None,
    severity: Optional[str] = None,
    layer: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return statistical findings from the database, most severe first."""
    from src.db.db_manager import get_session
    from src.db.models import StatisticalFinding

    session = get_session()
    try:
        q = session.query(StatisticalFinding)
        if run_id is not None:
            q = q.filter(StatisticalFinding.run_id == int(run_id))
        if severity:
            q = q.filter(StatisticalFinding.severity == str(severity).upper())
        if layer:
            q = q.filter(StatisticalFinding.layer == str(layer))
        rows = q.order_by(
            StatisticalFinding.anomaly_score.desc(),
            StatisticalFinding.finding_id.desc(),
        ).limit(limit).all()
        return [_finding_dict(r) for r in rows]
    finally:
        session.close()


def get_finding(finding_id: int) -> Optional[Dict[str, Any]]:
    from src.db.db_manager import get_session
    from src.db.models import StatisticalFinding

    session = get_session()
    try:
        row = session.get(StatisticalFinding, int(finding_id))
        return _finding_dict(row) if row is not None else None
    finally:
        session.close()


def findings_summary(run_id: Optional[int] = None) -> Dict[str, Any]:
    """Severity distribution + aggregate numbers for the Findings UI."""
    from src.db.db_manager import get_session
    from src.db.models import StatisticalFinding

    session = get_session()
    try:
        q = session.query(StatisticalFinding)
        if run_id is not None:
            q = q.filter(StatisticalFinding.run_id == int(run_id))
        rows = q.all()
    finally:
        session.close()

    dist = {level: 0 for level in SEVERITY_ORDER}
    for r in rows:
        dist[r.severity] = dist.get(r.severity, 0) + 1
    total = len(rows)
    peak = max((r.anomaly_score for r in rows), default=0.0)
    peak_row = max(rows, key=lambda r: r.anomaly_score, default=None)
    scanned_runs = len({r.run_id for r in rows})
    return {
        "severity_distribution": dist,
        "total": total,
        "scanned_runs": scanned_runs,
        "peak_score": round(peak, 1),
        "peak": None if peak_row is None else {
            "finding_id": peak_row.finding_id,
            "layer": peak_row.layer,
            "feature": peak_row.feature,
            "anomaly_score": peak_row.anomaly_score,
            "severity": peak_row.severity,
        },
    }


def _finding_dict(r) -> Dict[str, Any]:
    return {
        "finding_id": r.finding_id,
        "run_id": r.run_id,
        "scan_id": r.run_id,               # the scan this finding belongs to
        "scan_label": r.scan_label,
        "prompt_id": r.prompt_id,
        "category": r.category,
        "model": r.model,
        "layer": r.layer,
        "feature": r.feature,
        "baseline_mean": r.baseline_mean,
        "baseline_std": r.baseline_std,
        "baseline_n": r.baseline_n,
        "observed_statistic": r.observed_statistic,
        "z_score": r.z_score,
        "mean_deviation": r.mean_deviation,
        "energy_deviation": r.energy_deviation,
        "correlation": r.correlation,
        "anomaly_score": r.anomaly_score,
        "confidence": r.confidence,
        "severity": r.severity,
        "explanation": r.explanation,
        "evidence": r.evidence,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }