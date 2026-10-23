#!/usr/bin/env python3
"""Root command for the AI_OS master runtime."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


# Keep the CLI entrypoint available while allowing `import aios.modules.*`.
_AIOS_PACKAGE_DIR = Path(__file__).with_name("aios")
if _AIOS_PACKAGE_DIR.is_dir():
    __path__ = [str(_AIOS_PACKAGE_DIR)]
    if __spec__ is not None:
        __spec__.submodule_search_locations = __path__

from automation.orchestration.aios_master_runtime_v1 import AIOSMasterRuntime, ResumeRejected, RuntimeBlocked, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aios.py")
    parser.add_argument("command", choices=("status", "plan", "run", "resume", "validate"))
    parser.add_argument("--mode", choices=("DRY_RUN", "APPLY"), default="DRY_RUN")
    parser.add_argument("--mission-contract", type=Path)
    parser.add_argument("--max-cycles", type=int, default=5)
    parser.add_argument("--timebox-seconds", type=int, default=120)
    parser.add_argument("--invocation-timebox-seconds", type=int)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    if args.max_cycles <= 0 or args.timebox_seconds <= 0:
        parser.error("Cycle and time limits must be positive")
    try:
        result = run(repo_root=Path(__file__).resolve().parent, command=args.command, mode=args.mode, mission_contract=args.mission_contract,
                     max_cycles=args.max_cycles, timebox_seconds=args.timebox_seconds, state_dir=args.state_dir,
                     invocation_timebox_seconds=args.invocation_timebox_seconds)
    except (ResumeRejected, RuntimeBlocked) as error:
        reason = str(error)
        stop_class = "OWNER_ACTION_REQUIRED" if reason == "MISSION_CONTRACT_REQUIRED" else "SAFETY_INTEGRITY_BLOCK"
        if "RESOURCE_BOUNDARY" in reason or "TIME_EXHAUSTED" in reason:
            stop_class = "RESOURCE_TIME_BLOCK"
        print(json.dumps({"schema": "AIOS_MASTER_RUNTIME_ERROR.v1", "status": "BLOCKED",
                          "stop_class": stop_class, "reason_codes": reason.split(",")}, indent=2))
        return 2
    if args.format == "text" and result.get("schema") == "AIOS_MASTER_CONTROL_VIEW.v1":
        print(AIOSMasterRuntime.render_control(result))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    if args.mode == "APPLY" and args.command in {"run", "resume"}:
        if result.get("stop_class") == "RESOURCE_TIME_BLOCK" and result.get("continuation_ready") is True:
            return 3
        if result.get("stop_class") != "CAMPAIGN_COMPLETE":
            return 2
    return 0 if result.get("validation", {}).get("status", "PASS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
