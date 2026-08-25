from __future__ import annotations

from typing import Any

from automation.forex_engine import broker_paper_adapter


def _bool(value: Any) -> str:
    return "true" if value is True else "false"


def main(_argv: list[str] | None = None) -> int:
    result = broker_paper_adapter.build_default_broker_paper_adapter_result()
    summary = broker_paper_adapter.summarize_broker_paper_adapter(result)

    print("AIOS Broker-Paper Adapter Demo")
    print(f"Mode: {summary['mode']}")
    print(f"Classification: {summary['classification']}")
    print(f"Paper only: {_bool(summary['paper_only'])}")
    print(f"Live execution allowed: {_bool(summary['live_execution_allowed'])}")
    print(f"Paper broker writes allowed: {_bool(summary['paper_broker_writes_allowed'])}")
    print(f"Live broker writes allowed: {_bool(summary['live_broker_writes_allowed'])}")
    print(f"Broker writes: {summary['broker_writes']}")
    print(f"Broker request sent: {_bool(summary['broker_request_sent'])}")
    print(f"Plan gate ready: {_bool(summary['plan_gate_ready'])}")
    print(f"Paper/demo verification ready: {_bool(summary['paper_demo_verification_ready'])}")
    print(f"Owner checkpoint ready: {_bool(summary['owner_checkpoint_ready'])}")
    print(f"Submission state: {summary['submission_state']}")
    print(f"Acknowledgement state: {summary['acknowledgement_state']}")
    print(f"Final state: {summary['final_state']}")
    print(f"Next safe action: {summary['next_safe_action']}")
    print("Safety: paper/demo only; no live execution, no broker writes, no live credentials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
