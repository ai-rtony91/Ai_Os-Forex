from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Dev\Ai.Os")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine import consolidated_readiness_blocker_closure_v1 as c
from automation.forex_engine import forex_live_readiness_blocker_closure_v1 as l

OUT = ROOT / "Reports" / "forex_delivery" / "AIOS_FOREX_A_LANE_REMAINING_CONTROL_GATE_PROBE_V1.json"

payload = {
    "daily_loss_authority": l.current_daily_loss_authority(),
    "kill_switch_authority": l.kill_switch_authority_recovery(),
    "kill_switch_reevaluation": l.reevaluate_kill_switch(l.kill_switch_authority_recovery()),
    "final_status_default": c.build_profitable_live_bot_final_status(),
}
summary = {
    "daily_loss_limit_found": payload["daily_loss_authority"].get("daily_loss_limit_found"),
    "daily_loss_owner_decision_required": payload["daily_loss_authority"].get("daily_loss_owner_decision_required"),
    "kill_switch_ready": payload["kill_switch_reevaluation"].get("kill_switch_ready"),
    "final_status": payload["final_status_default"].get("status"),
    "live_for_keeps_ready": payload["final_status_default"].get("live_for_keeps_ready"),
    "final_blockers": payload["final_status_default"].get("blockers"),
}
payload["summary"] = summary
OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2, sort_keys=True))
