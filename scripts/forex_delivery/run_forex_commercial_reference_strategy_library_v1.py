#!/usr/bin/env python3
"""CLI for PKT-FOREX-041 synthetic-only reference registration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from automation.forex_engine.forex_commercial_reference_strategy_library_v1 import (  # noqa: E402
    compare_stage0,
    promote_stage0,
    write_stage0,
)
from automation.forex_engine.forex_edge_validation_pipeline_v1 import pretty_json  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="PKT-FOREX-041 commercial reference Stage-0")
    subparsers = result.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--output-root", type=Path, required=True)
    build.add_argument("--ledger", type=Path, required=True)
    build.add_argument("--fingerprint-index", type=Path, required=True)
    build.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--first-root", type=Path, required=True)
    compare.add_argument("--second-root", type=Path, required=True)
    promote = subparsers.add_parser("promote")
    promote.add_argument("--source-root", type=Path, required=True)
    promote.add_argument("--runtime-registry", type=Path, required=True)
    promote.add_argument("--ledger", type=Path, required=True)
    promote.add_argument("--fingerprint-index", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.command == "build":
        output = write_stage0(arguments.output_root, arguments.ledger, arguments.fingerprint_index, arguments.repo_root)
    elif arguments.command == "compare":
        output = compare_stage0(arguments.first_root, arguments.second_root)
    else:
        output = promote_stage0(arguments.source_root, arguments.runtime_registry, arguments.ledger, arguments.fingerprint_index)
    print(pretty_json(output), end="")
    return 0 if output.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
