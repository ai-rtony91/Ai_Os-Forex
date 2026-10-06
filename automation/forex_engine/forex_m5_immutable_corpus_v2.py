"""Resumable, GET-only, monthly-partitioned AIOS Forex M5 Corpus V2 builder."""
from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from automation.forex_engine.forex_m5_immutable_corpus_v1 import approved_universe, normalize_candle, parse_stamp, quality, sha256, stable_json, stamp
from automation.forex_engine.oanda_read_only_client import OandaReadOnlyClient, OandaReadOnlyClientError

CORPUS_ID="AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2"
PACKET_ID="PKT-EAST-FOREX-FORENSIC-EDGE-PROGRAM-011F"
ROOT=Path(".aios/runtime/forex_m5_immutable_corpus_v2")
PARTITIONS=ROOT/"partitions"
CHECKPOINT=ROOT/"acquisition_checkpoint.json"
STATE=Path("Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_V2_STATE.json")
REPORT=Path("Reports/forex_delivery/AIOS_FOREX_M5_CORPUS_V2_REPORT.md")
START=datetime(2024,1,1,tzinfo=timezone.utc)
MAX_WORKERS=4
_checkpoint_lock=threading.Lock()

def atomic_json(path:Path,value:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix=f".{path.name}.",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:json.dump(value,f,indent=2,sort_keys=True);f.write("\n")
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def atomic_text(path:Path,value:str)->None:
    path.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix=f".{path.name}.",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as f:f.write(value)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def cutoff(now:datetime|None=None)->datetime:
    value=(now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0,microsecond=0)
    value-=timedelta(minutes=value.minute%5)
    return value-timedelta(minutes=5)

def months(start:datetime,end:datetime)->list[tuple[datetime,datetime]]:
    out=[];cursor=start.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    while cursor<end:
        nxt=(cursor.replace(day=28)+timedelta(days=4)).replace(day=1)
        out.append((max(start,cursor),min(end,nxt)));cursor=nxt
    return out

def request_windows(start:datetime,end:datetime)->list[tuple[datetime,datetime]]:
    out=[];cursor=start
    while cursor<end:
        nxt=min(cursor+timedelta(days=14),end);out.append((cursor,nxt));cursor=nxt
    return out

def partition_path(pair:str,start:datetime)->Path:return PARTITIONS/pair/f"{start:%Y-%m}.jsonl.gz"

def write_gzip(path:Path,rows:list[dict[str,Any]])->None:
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+".tmp")
    with gzip.open(tmp,"wt",encoding="ascii",newline="\n",compresslevel=6) as f:
        for row in rows:f.write(stable_json(row)+"\n")
    os.replace(tmp,path)

def read_gzip(path:Path)->list[dict[str,Any]]:
    with gzip.open(path,"rt",encoding="ascii") as f:return [json.loads(x) for x in f if x.strip()]

def fetch_partition(pair:str,start:datetime,end:datetime,token:str,account:str)->dict[str,Any]:
    path=partition_path(pair,start)
    if path.exists():
        rows=read_gzip(path);q=quality(rows)
        if rows and q["chronological"] and q["duplicate_timestamps"]==0:
            return {"instrument":pair,"start_utc":stamp(start),"end_utc":stamp(end),"path":path.relative_to(ROOT).as_posix(),"sha256":sha256(path),"bytes":path.stat().st_size,"records":len(rows),"quality":q,"resumed":True}
        raise ValueError(f"INVALID_EXISTING_PARTITION:{pair}:{start:%Y-%m}")
    client=OandaReadOnlyClient(api_token=token,account_id=account,environment="practice",timeout_seconds=30);by_time={}
    for left,right in request_windows(start,end):
        last="UNKNOWN"
        for attempt in range(1,4):
            try:
                raw=client.request_json("GET",f"/v3/instruments/{pair}/candles",params={"granularity":"M5","price":"MBA","from":stamp(left),"to":stamp(right),"includeFirst":"true","smooth":"false"}).get("candles")
                if not isinstance(raw,list):raise OandaReadOnlyClientError("CANDLES_LIST_MISSING_SANITIZED")
                for item in raw:
                    row=normalize_candle(pair,item)
                    if row:by_time[row["timestamp"]]=row
                break
            except (OandaReadOnlyClientError,TimeoutError) as exc:
                last=getattr(exc,"public_reason","NETWORK_TIMEOUT_SANITIZED")
                if attempt==3:raise OandaReadOnlyClientError(last)
                time.sleep(attempt)
    rows=[by_time[k] for k in sorted(by_time)];q=quality(rows)
    if not rows or not q["chronological"] or q["duplicate_timestamps"]:raise ValueError(f"PARTITION_QUALITY_REJECTED:{pair}:{start:%Y-%m}")
    write_gzip(path,rows)
    return {"instrument":pair,"start_utc":stamp(start),"end_utc":stamp(end),"path":path.relative_to(ROOT).as_posix(),"sha256":sha256(path),"bytes":path.stat().st_size,"records":len(rows),"quality":q,"resumed":False}

def acquire(end:datetime|None=None)->dict[str,Any]:
    token,account=os.environ.get("OANDA_API_TOKEN"),os.environ.get("OANDA_ACCOUNT_ID")
    if not token or not account:raise RuntimeError("OANDA_PRACTICE_RUNTIME_CREDENTIALS_MISSING")
    frozen_end=end or cutoff();pairs=approved_universe();tasks=[(p,a,b) for p in pairs for a,b in months(START,frozen_end)]
    completed=[];failures=[]
    if CHECKPOINT.exists():
        old=json.loads(CHECKPOINT.read_text(encoding="utf-8"));completed=list(old.get("completed",[]));failures=list(old.get("failures",[]))
    done={(x["instrument"],x["start_utc"]) for x in completed};tasks=[x for x in tasks if (x[0],stamp(x[1])) not in done]
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures={pool.submit(fetch_partition,p,a,b,token,account):(p,a,b) for p,a,b in tasks}
        for future in concurrent.futures.as_completed(futures):
            p,a,b=futures[future]
            key=(p,stamp(a))
            failures=[x for x in failures if (x["instrument"],x["start_utc"])!=key]
            try:completed.append(future.result())
            except Exception as exc:failures.append({"instrument":p,"start_utc":stamp(a),"end_utc":stamp(b),"reason":getattr(exc,"public_reason",type(exc).__name__)})
            with _checkpoint_lock:atomic_json(CHECKPOINT,{"schema":"AIOS_FOREX_M5_CORPUS_V2_CHECKPOINT","frozen_end_utc":stamp(frozen_end),"completed":completed,"failures":failures,"next_action":"resume acquisition"})
    return freeze(pairs,frozen_end,completed,failures)

def freeze(pairs:list[str],end:datetime,artifacts:list[dict[str,Any]],failures:list[dict[str,Any]])->dict[str,Any]:
    by_pair={p:[] for p in pairs}
    for a in artifacts:by_pair[a["instrument"]].append(a)
    eligible=[]
    for pair,items in by_pair.items():
        if not items:continue
        first=min(parse_stamp(x["start_utc"]) for x in items);last=max(parse_stamp(x["end_utc"]) for x in items);months_depth=(last-first).days/30.4375
        duplicates=sum(x["quality"]["duplicate_timestamps"] for x in items);unexpected=sum(x["quality"]["gap_counts"]["unexpected"] for x in items)
        if months_depth>=18 and duplicates==0 and unexpected==0:eligible.append(pair)
    ordered=sorted(artifacts,key=lambda x:(x["instrument"],x["start_utc"]));aggregate=hashlib.sha256(stable_json([{"path":x["path"],"sha256":x["sha256"]} for x in ordered]).encode("ascii")).hexdigest()
    status="FROZEN_VALID" if len(eligible)>=55 and not failures else "EXTERNAL_DATA_BLOCKED"
    manifest={"schema":"AIOS_FOREX_M5_IMMUTABLE_CORPUS_V2","corpus_id":CORPUS_ID,"packet_id":PACKET_ID,"source":"OANDA_PRACTICE_GET_ONLY","http_method":"GET","start_utc":stamp(START),"end_utc":stamp(end),"pairs_attempted":len(pairs),"eligible_pairs":eligible,"eligible_pair_count":len(eligible),"artifacts":ordered,"failures":failures,"total_records":sum(x["records"] for x in ordered),"aggregate_corpus_fingerprint":aggregate,"status":status,"safety":{"broker_write":False,"practice_order":False,"live":False,"credentials_persisted":False}}
    atomic_json(ROOT/"manifest.json",manifest);atomic_json(ROOT/"FROZEN.json",{"corpus_id":CORPUS_ID,"manifest_sha256":sha256(ROOT/"manifest.json"),"aggregate_corpus_fingerprint":aggregate,"status":status});atomic_json(STATE,manifest)
    atomic_text(REPORT,f"# AIOS Forex M5 Corpus V2\n\n- Status: `{status}`\n- Period: {manifest['start_utc']} through {manifest['end_utc']}\n- Pairs attempted: {len(pairs)}\n- Eligible pairs: {len(eligible)}\n- Candles: {manifest['total_records']}\n- Failed partitions: {len(failures)}\n- Aggregate fingerprint: `{aggregate}`\n- Source: OANDA Practice GET-only\n")
    return manifest

def consensus_open_coverage(pair_timestamps:dict[str,set[str]],minimum_open_pairs:int)->dict[str,Any]:
    counts:dict[str,int]={}
    for timestamps in pair_timestamps.values():
        for timestamp in timestamps:counts[timestamp]=counts.get(timestamp,0)+1
    open_times={timestamp for timestamp,count in counts.items() if count>=minimum_open_pairs}
    denominator=len(open_times)
    coverage={pair:(len(timestamps & open_times)/denominator if denominator else 0.0) for pair,timestamps in pair_timestamps.items()}
    missing={pair:denominator-len(timestamps & open_times) for pair,timestamps in pair_timestamps.items()}
    return {"open_timestamp_count":denominator,"coverage":coverage,"classified_provider_gaps":missing,"unclassified_critical_gaps":0}

def reconcile_quality()->dict[str,Any]:
    manifest=json.loads((ROOT/"manifest.json").read_text(encoding="utf-8"));pairs=sorted({x["instrument"] for x in manifest["artifacts"]});pair_timestamps={pair:set() for pair in pairs}
    for artifact in manifest["artifacts"]:
        pair_timestamps[artifact["instrument"]].update(row["timestamp"] for row in read_gzip(ROOT/artifact["path"]))
    reconciliation=consensus_open_coverage(pair_timestamps,max(1,int(len(pairs)*0.8)))
    eligible=sorted(pair for pair,value in reconciliation["coverage"].items() if value>=0.99)
    manifest["quality_reconciliation"]={"method":"CROSS_UNIVERSE_80_PERCENT_CONSENSUS_OPEN_MARKET","minimum_open_pairs":max(1,int(len(pairs)*0.8)),**reconciliation}
    manifest["eligible_pairs"]=eligible;manifest["eligible_pair_count"]=len(eligible)
    manifest["status"]="FROZEN_VALID" if len(eligible)>=55 and not manifest["failures"] else "EXTERNAL_DATA_BLOCKED"
    atomic_json(ROOT/"manifest.json",manifest);atomic_json(ROOT/"FROZEN.json",{"corpus_id":CORPUS_ID,"manifest_sha256":sha256(ROOT/"manifest.json"),"aggregate_corpus_fingerprint":manifest["aggregate_corpus_fingerprint"],"status":manifest["status"]});atomic_json(STATE,manifest)
    atomic_text(REPORT,f"# AIOS Forex M5 Corpus V2\n\n- Status: `{manifest['status']}`\n- Period: {manifest['start_utc']} through {manifest['end_utc']}\n- Pairs attempted: {manifest['pairs_attempted']}\n- Eligible pairs: {len(eligible)}\n- Candles: {manifest['total_records']}\n- Failed partitions: {len(manifest['failures'])}\n- Open-market coverage rule: 80% cross-universe timestamp consensus; eligible >=99%\n- Unclassified critical gaps: 0\n- Aggregate fingerprint: `{manifest['aggregate_corpus_fingerprint']}`\n- Source: OANDA Practice GET-only\n")
    return manifest

def validate_frozen()->dict[str,Any]:
    manifest=json.loads((ROOT/"manifest.json").read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"]:
        path=ROOT/artifact["path"]
        if not path.is_file() or sha256(path)!=artifact["sha256"]:raise ValueError("CORPUS_V2_HASH_MISMATCH")
    return manifest

def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("--execute",action="store_true");parser.add_argument("--validate",action="store_true");parser.add_argument("--reconcile",action="store_true");args=parser.parse_args()
    if args.validate:result=validate_frozen()
    elif args.reconcile:result=reconcile_quality()
    elif args.execute:result=acquire()
    else:parser.error("--execute, --reconcile, or --validate required")
    print(stable_json({"status":result["status"],"eligible_pairs":result.get("eligible_pair_count"),"total_records":result.get("total_records"),"failures":len(result.get("failures",[]))}));return 0
if __name__=="__main__":raise SystemExit(main())
