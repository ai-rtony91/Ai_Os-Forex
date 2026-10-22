"""Generate deterministic empty-state Profit Track P1 evidence reports."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_profit_track_p1_strategy_evidence_v1 import (  # noqa: E402
    evaluate_strategy_evidence,
    result_to_markdown,
)

STATE_PATH = ROOT / "Reports/forex_delivery/AIOS_FOREX_PROFIT_TRACK_P1_STRATEGY_EVIDENCE_V1_STATE.json"
REPORT_PATH = ROOT / "Reports/forex_delivery/AIOS_FOREX_PROFIT_TRACK_P1_STRATEGY_EVIDENCE_V1_REPORT.md"
DETERMINISTIC_AS_OF = datetime(2026, 8, 6, tzinfo=timezone.utc)


def main() -> int:
    result = evaluate_strategy_evidence([], as_of=DETERMINISTIC_AS_OF)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(result_to_markdown(result), encoding="utf-8")
    print(f"Wrote {STATE_PATH.relative_to(ROOT)}")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
