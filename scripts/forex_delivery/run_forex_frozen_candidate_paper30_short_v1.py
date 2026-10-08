from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ["AIOS_FOREX_PAPER30_DIRECTION"] = "SELL"
    from scripts.forex_delivery.run_forex_frozen_candidate_paper30_v1 import main as run_main

    return run_main()


if __name__ == "__main__":
    raise SystemExit(main())
