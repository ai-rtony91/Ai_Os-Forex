#!/usr/bin/env python3
"""CLI for PKT-FOREX-040 synthetic validator certification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from automation.forex_engine.forex_edge_validation_pipeline_v1 import (  # noqa: E402
    compare_certifications,
    pretty_json,
    promote_runtime,
    write_certification,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Synthetic-only AIOS Forex edge-validator certification")
    subparsers = result.add_subparsers(dest="command", required=True)
    certify = subparsers.add_parser("certify")
    certify.add_argument("--output-root", type=Path, required=True)
    certify.add_argument("--runtime-root", type=Path, required=True)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--first-root", type=Path, required=True)
    compare.add_argument("--second-root", type=Path, required=True)
    promote = subparsers.add_parser("promote-runtime")
    promote.add_argument("--source-root", type=Path, required=True)
    promote.add_argument("--runtime-root", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if arguments.command == "certify":
        result = write_certification(arguments.output_root, arguments.runtime_root)
    elif arguments.command == "compare":
        result = compare_certifications(arguments.first_root, arguments.second_root)
    else:
        result = promote_runtime(arguments.source_root, arguments.runtime_root)
    print(pretty_json(result), end="")
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
