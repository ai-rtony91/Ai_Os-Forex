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

from automation.orchestration.aios_master_runtime_v1 import ResumeRejected, run


def main() -> int:
    parser = argparse.ArgumentParser(prog="aios.py")
    parser.add_argument("command", choices=("status", "plan", "run", "resume", "validate"))
    args = parser.parse_args()
    try:
        result = run(command=args.command)
    except ResumeRejected as error:
        print(json.dumps({"schema": "AIOS_MASTER_RUNTIME_ERROR.v1", "status": "BLOCKED", "reason_codes": str(error).split(",")}, indent=2))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("validation", {}).get("status", "PASS") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
