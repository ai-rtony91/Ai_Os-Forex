from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from automation.forex_engine.forex_cftc_asset_manager_weekly_change_stage0_v1 import main


if __name__ == "__main__":
    raise SystemExit(main())
