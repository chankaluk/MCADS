"""Privacy-conscious JSON Lines repository for MCADS audit records."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from threading import Lock


class AuditRepository:
    """Persist and summarize redacted audit results with corrupt-line tolerance."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def append(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

    def latest(self, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        records = self._read_valid()
        return list(reversed(records[-limit:]))

    def statistics(self) -> dict:
        records = self._read_valid()
        actions = Counter(item.get("action", "UNKNOWN") for item in records)
        scores = [float(item.get("risk_score", 0.0)) for item in records]
        return {
            "total": len(records),
            "pass_count": actions["PASS"],
            "review_count": actions["REVIEW"],
            "block_count": actions["BLOCK"],
            "average_risk_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        }

    def _read_valid(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        records = []
        for line in lines:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    records.append(value)
            except json.JSONDecodeError:
                continue
        return records
