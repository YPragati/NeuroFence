class SecurityDecisionEngine:
    """
    Converts activation anomaly results into
    a security decision.
    """

    def decide(self, analysis):
        status = analysis.get("status", "UNKNOWN")
        score = analysis.get("score", 0.0)

        if status == "NORMAL":
            action = "ALLOW"

        elif status == "SUSPICIOUS":
            action = "MONITOR"

        elif status == "ANOMALOUS":
            action = "BLOCK"

        else:
            action = "REVIEW"

        return {
            "status": status,
            "score": score,
            "action": action
        }