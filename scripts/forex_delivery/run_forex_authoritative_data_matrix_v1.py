from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.forex_engine.forex_authoritative_data_matrix_v1 import write_outputs


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()
    allowed = (ROOT / ".aios/staging/PKT_FOREX_027").resolve()
    if repo_root != ROOT:
        raise ValueError("REPO_ROOT_MISMATCH")
    if not _inside(output_root, allowed) or output_root == allowed:
        raise ValueError("OUTPUT_OUTSIDE_PACKET_STAGING")
    if output_root.exists():
        raise FileExistsError(f"OUTPUT_EXISTS:{output_root}")
    receipt = write_outputs(repo_root, output_root)
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
