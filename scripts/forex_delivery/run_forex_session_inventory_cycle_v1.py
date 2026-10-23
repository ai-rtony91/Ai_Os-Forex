#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from automation.forex_engine.forex_session_inventory_cycle_v1 import build_artifacts,research,sha256_bytes

def inside(child:Path,parent:Path)->bool:
    try: child.relative_to(parent); return True
    except ValueError: return False

def execute(corpus:Path,output:Path)->dict:
    corpus=corpus.resolve(); output=output.resolve()
    if corpus!=(ROOT/'.aios/runtime/forex_m5_immutable_corpus_v2').resolve(): raise ValueError('CORPUS_ROOT_MISMATCH')
    allowed=(ROOT/'.aios/staging/PKT_FOREX_025').resolve()
    if not inside(output,allowed) or output==allowed: raise ValueError('OUTPUT_OUTSIDE_PACKET_STAGING')
    if output.exists(): raise FileExistsError(f'OUTPUT_EXISTS:{output}')
    result,journals=research(corpus)
    artifacts=build_artifacts(result,journals,ROOT/'automation/forex_engine/forex_session_inventory_cycle_v1.py')
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix=f'.{output.name}.',dir=output.parent))
    for name,content in sorted(artifacts.items()): (temporary/name).write_bytes(content)
    os.replace(temporary,output)
    aggregate=sha256_bytes(b''.join(name.encode()+b'\0'+artifacts[name] for name in sorted(artifacts)))
    receipt=json.loads(artifacts['AIOS_FOREX_SESSION_INVENTORY_RECEIPT.json'])
    return {'status':result['status'],'acceptance_status':receipt['acceptance_status'],'candidate_count':5,'survivor_count':len(result['survivors']),'best_candidate':result['best_candidate'],'eligible_pair_count':result['eligible_pair_count'],'journal_row_count':result['journal_row_count'],'verified_partition_count':result['verified_partition_count'],'holdout_status':result['holdout_status'],'artifact_count':len(artifacts),'aggregate_sha256':aggregate,'output_root':output.as_posix()}

def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['run']);parser.add_argument('--corpus-root',required=True,type=Path);parser.add_argument('--output-root',required=True,type=Path);args=parser.parse_args();print(json.dumps(execute(args.corpus_root,args.output_root),indent=2,sort_keys=True));return 0
if __name__=='__main__': raise SystemExit(main())
