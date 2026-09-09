import json
import os
from datetime import datetime


LOG_FILE = "logs/security_events.json"


class SecurityLogger:
    """
    Records NeuroFence security events.
    """

    def __init__(self, log_file=LOG_FILE):
        self.log_file = log_file

        # Create logs directory if it does not exist.
        os.makedirs(
            os.path.dirname(self.log_file),
            exist_ok=True
        )

        # Create empty log file if it does not exist.
        if not os.path.exists(self.log_file):
            with open(
                self.log_file,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump([], file, indent=4)

    def log_event(self, prompt, security, decision):
        """
        Save one security event.
        """

        with open(
            self.log_file,
            "r",
            encoding="utf-8"
        ) as file:
            events = json.load(file)

        event = {
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "status": security.get("status"),
            "score": security.get("score"),
            "action": decision.get("action")
        }

        events.append(event)

        with open(
            self.log_file,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                events,
                file,
                indent=4
            )