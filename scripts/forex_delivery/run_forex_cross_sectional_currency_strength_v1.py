import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from automation.forex_engine.forex_cross_sectional_currency_strength_v1 import research,write_outputs
def main():
 p=argparse.ArgumentParser();p.add_argument("command",choices=["run"]);p.add_argument("--dataset-root",type=Path,required=True);p.add_argument("--preregistration",type=Path,required=True);p.add_argument("--output-root",type=Path,required=True);p.add_argument("--report-path",type=Path,required=True);p.add_argument("--rejection-path",type=Path,required=True);a=p.parse_args();pre=json.loads(a.preregistration.read_text(encoding="utf-8"));result=research(a.dataset_root, a.preregistration);print(json.dumps(write_outputs(result,pre,a.output_root,a.report_path,a.rejection_path),sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
