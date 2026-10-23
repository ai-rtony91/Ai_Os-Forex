import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_runner_help_is_available():
    r=subprocess.run([sys.executable,str(ROOT/'scripts/forex_delivery/run_forex_cross_sectional_currency_strength_v1.py'),'--help'],cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0 and '--dataset-root' in r.stdout and '--preregistration' in r.stdout

def test_runner_requires_bounded_command():
    r=subprocess.run([sys.executable,str(ROOT/'scripts/forex_delivery/run_forex_cross_sectional_currency_strength_v1.py')],cwd=ROOT,capture_output=True,text=True)
    assert r.returncode!=0
