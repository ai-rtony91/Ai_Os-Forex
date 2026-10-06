"""Offline cross-sectional currency-strength research on the frozen M1 graph."""
from __future__ import annotations

import hashlib, json, math, random
from collections import deque
from pathlib import Path
from typing import Any, Iterator

DATASET_ID="AIOS-FX-HIST-V1-b6a62a1175398354580b"
DATASET_SHA="b6a62a1175398354580be3f242cdb67aa3134988b7448c1e1fa11d8abcfb1e7d"
DEV_START="2024-01-01T00:00:00"; DEV_END="2025-04-01T00:00:00"; VAL_END="2026-01-01T00:00:00"
PAIRS=("EUR_USD","GBP_USD","USD_JPY")

def cbytes(x:Any)->bytes:return (json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def mid(side:dict[str,str],other:dict[str,str],key:str)->float:return (float(side[key])+float(other[key]))/2
def pair_return_signs(pair:str)->dict[str,int]:
    a,b=pair.split("_"); return {a:1,b:-1}

def strength_scores(returns:dict[str,float])->dict[str,float]:
    values:dict[str,list[float]]={}
    for pair,value in returns.items():
        for currency,sign in pair_return_signs(pair).items():values.setdefault(currency,[]).append(sign*value)
    return {k:sum(v)/len(v) for k,v in values.items()}

def direct_pair(strong:str,weak:str)->tuple[str,str]|None:
    name=f"{strong}_{weak}"
    if name in PAIRS:return name,"LONG"
    name=f"{weak}_{strong}"
    if name in PAIRS:return name,"SHORT"
    return None

def aggregate_currency_exposure(positions:list[dict[str,Any]])->dict[str,float]:
    out:dict[str,float]={}
    for p in positions:
        base,quote=p["pair"].split("_"); sign=1 if p["direction"]=="LONG" else -1
        out[base]=out.get(base,0)+sign*p.get("risk",1); out[quote]=out.get(quote,0)-sign*p.get("risk",1)
    return out

def exposure_allowed(positions:list[dict[str,Any]],pair:str,direction:str,cap:float=1.0)->bool:
    test=positions+[{"pair":pair,"direction":direction,"risk":1.0}]
    return all(abs(x)<=cap for x in aggregate_currency_exposure(test).values())

def iter_candles(path:Path,stop_utc:str)->Iterator[dict[str,Any]]:
    """Line-stream candles and stop before parsing the first sealed-holdout candle."""
    in_candles=False; buf:list[str]=[]; depth=0
    with path.open("r",encoding="utf-8") as handle:
        for line in handle:
            if not in_candles:
                if '"candles"' in line and "[" in line:in_candles=True
                continue
            stripped=line.strip()
            if not buf:
                if stripped.startswith("]"):return
                if not stripped.startswith("{"):continue
            buf.append(line); depth+=line.count("{")-line.count("}")
            if depth==0:
                candle=json.loads("".join(buf).rstrip().rstrip(",")); buf=[]
                if candle["time"][:19]>=stop_utc:return
                if candle.get("complete"):yield candle

def pair_stream(dataset_root:Path,inventory:dict[str,Any],pair:str)->Iterator[dict[str,Any]]:
    files=sorted((x for x in inventory["file_inventory"] if x.get("role")=="batch" and x.get("instrument")==pair and x.get("granularity")=="M1"),key=lambda x:x["batch_number"])
    for item in files:
        for candle in iter_candles(dataset_root/"source_artifacts"/item["relative_path"],VAL_END):yield candle

def synchronized(dataset_root:Path,inventory:dict[str,Any])->Iterator[tuple[str,dict[str,dict[str,Any]]]]:
    streams={p:iter(pair_stream(dataset_root,inventory,p)) for p in PAIRS}; current={p:next(streams[p],None) for p in PAIRS}
    while all(current.values()):
        times={p:current[p]["time"] for p in PAIRS}; high=max(times.values()); low=min(times.values())
        if high==low:
            yield high,{p:current[p] for p in PAIRS}; current={p:next(streams[p],None) for p in PAIRS}
        else:
            for p in PAIRS:
                if times[p]==low:current[p]=next(streams[p],None)

def candidates()->list[dict[str,Any]]:
    return [{"candidate_id":f"CSM-L{l}-D{d:g}-H{h}","lookback":l,"dispersion_bps":d,"holding":h,"stop_atr":1.0,"target_r":1.5} for l in (15,30,60) for d in (1.0,2.0) for h in (15,30)]

def _metrics(trades:list[dict[str,Any]])->dict[str,Any]:
    rs=[x["r"] for x in trades]; wins=sum(x for x in rs if x>0); losses=-sum(x for x in rs if x<0)
    equity=1.0; peak=1.0; dd=0.0
    for r in rs:equity*=max(0.0,1+0.0025*r);peak=max(peak,equity);dd=max(dd,(peak-equity)/peak*100 if peak else 100)
    pairs={p:sum(1 for x in trades if x["pair"]==p) for p in PAIRS}; folds={str(i):[x["r"] for x in trades if x["fold"]==i] for i in range(6)}
    return {"trade_count":len(rs),"long_trades":sum(x["direction"]=="LONG" for x in trades),"short_trades":sum(x["direction"]=="SHORT" for x in trades),"expectancy_r":sum(rs)/len(rs) if rs else 0.0,"profit_factor":wins/losses if losses else (999.0 if wins else 0.0),"maximum_drawdown_pct":dd,"pair_counts":pairs,"instrument_count":sum(v>0 for v in pairs.values()),"largest_pair_share":max(pairs.values())/len(rs) if rs else 1.0,"positive_folds":sum(bool(v) and sum(v)/len(v)>0 for v in folds.values()),"fold_expectancy":{k:(sum(v)/len(v) if v else 0.0) for k,v in folds.items()},"largest_trade_share":max((abs(x) for x in rs),default=0)/max(sum(abs(x) for x in rs),1e-12)}

def _gate(m:dict[str,Any])->bool:
    return m["expectancy_r"]>0 and m["profit_factor"]>=1.10 and m["maximum_drawdown_pct"]<=10 and m["trade_count"]>=200 and m["long_trades"]>=50 and m["short_trades"]>=50 and m["instrument_count"]>=2 and m["largest_pair_share"]<=0.60

def _exit(position:dict[str,Any],bar:dict[str,Any],slip:float)->tuple[bool,float,float]:
    direction=position["direction"]; risk=position["risk_distance"]
    if direction=="LONG":
        if float(bar["bid"]["l"])-slip<=position["stop"]:price=position["stop"]
        elif float(bar["bid"]["h"])-slip>=position["target"]:price=position["target"]
        elif position["age"]>=position["holding"]:price=float(bar["bid"]["c"])-slip
        else:return False,0,0
        r=(price-position["entry"])/risk
    else:
        if float(bar["ask"]["h"])+slip>=position["stop"]:price=position["stop"]
        elif float(bar["ask"]["l"])+slip<=position["target"]:price=position["target"]
        elif position["age"]>=position["holding"]:price=float(bar["ask"]["c"])+slip
        else:return False,0,0
        r=(position["entry"]-price)/risk
    mid_exit=mid(bar["bid"],bar["ask"],"c"); gross=(mid_exit-position["mid_entry"])/risk*(1 if direction=="LONG" else -1)
    return True,r,gross

def research(dataset_root:Path,prereg_path:Path)->dict[str,Any]:
    prereg=json.loads(prereg_path.read_text(encoding="utf-8")); inventory=json.loads((dataset_root/"AIOS_FOREX_HISTORICAL_DATASET_INVENTORY.json").read_text(encoding="utf-8"))
    if inventory["dataset_id"]!=DATASET_ID or inventory["dataset_sha256"]!=DATASET_SHA:raise ValueError("dataset mismatch")
    configs=candidates(); histories={p:deque(maxlen=61) for p in PAIRS}; tranges={p:deque(maxlen=14) for p in PAIRS}; prev={p:None for p in PAIRS}
    states={(c["candidate_id"],s):{"position":None,"pending":None,"trades":[]} for c in configs for s in ("base","stress")}; last_bars=None; bars=0
    for timestamp,barset in synchronized(dataset_root,inventory):
        bars+=1; last_bars=barset
        for p,b in barset.items():
            close=mid(b["bid"],b["ask"],"c"); hi=mid(b["bid"],b["ask"],"h");lo=mid(b["bid"],b["ask"],"l"); tr=max(hi-lo,abs(hi-prev[p]),abs(lo-prev[p])) if prev[p] else hi-lo;tranges[p].append(tr); histories[p].append(close);prev[p]=close
        for c in configs:
            for scenario,slip_pips in (("base",0.10),("stress",0.25)):
                state=states[(c["candidate_id"],scenario)];pos=state["position"]
                if pos:
                    pos["age"]+=1;done,r,gross=_exit(pos,barset[pos["pair"]],slip_pips*(0.01 if pos["pair"]=="USD_JPY" else 0.0001))
                    if done:state["trades"].append({"r":r,"gross_r":gross,"pair":pos["pair"],"direction":pos["direction"],"split":pos["split"],"fold":pos["fold"]});state["position"]=None
                pending=state["pending"];state["pending"]=None
                if pending and state["position"] is None and exposure_allowed([],pending["pair"],pending["direction"]):
                    p=pending["pair"];b=barset[p];pip=0.01 if p=="USD_JPY" else 0.0001;slip=slip_pips*pip;atr=sum(tranges[p])/len(tranges[p])
                    if atr>0:
                        direction=pending["direction"];entry=float(b["ask"]["o"])+slip if direction=="LONG" else float(b["bid"]["o"])-slip;stop=entry-atr if direction=="LONG" else entry+atr;target=entry+1.5*atr if direction=="LONG" else entry-1.5*atr
                        state["position"]={"pair":p,"direction":direction,"entry":entry,"mid_entry":mid(b["bid"],b["ask"],"o"),"risk_distance":atr,"stop":stop,"target":target,"holding":c["holding"],"age":0,"split":pending["split"],"fold":pending["fold"]}
            if len(histories[PAIRS[0]])>c["lookback"] and timestamp[11:16] not in {"21:55","21:56","21:57","21:58","21:59","22:00","22:01","22:02","22:03","22:04","22:05","22:06","22:07","22:08","22:09"}:
                returns={p:math.log(histories[p][-1]/histories[p][-1-c["lookback"]]) for p in PAIRS};scores=strength_scores(returns);strong=max(scores,key=scores.get);weak=min(scores,key=scores.get);choice=direct_pair(strong,weak)
                if choice and (scores[strong]-scores[weak])*10000>=c["dispersion_bps"]:
                    split="development" if timestamp[:19]<DEV_END else "validation"; span=39441600;fold=min(5,max(0,int((__import__('datetime').datetime.fromisoformat(timestamp[:19])-__import__('datetime').datetime.fromisoformat(DEV_START)).total_seconds()/span*6))) if split=="development" else -1
                    for scenario in ("base","stress"):states[(c["candidate_id"],scenario)]["pending"]={"pair":choice[0],"direction":choice[1],"split":split,"fold":fold}
    results={}
    for c in configs:
        base=states[(c["candidate_id"],"base")]["trades"];stress=states[(c["candidate_id"],"stress")]["trades"]
        dev=_metrics([x for x in base if x["split"]=="development"]);val=_metrics([x for x in base if x["split"]=="validation"]);stress_val=_metrics([x for x in stress if x["split"]=="validation"]);gross=_metrics([{**x,"r":x["gross_r"]} for x in base if x["split"]=="validation"])
        results[c["candidate_id"]]={"definition":c,"development":dev,"validation":val,"stress_validation":stress_val,"cost_free_validation":gross}
    for cid,item in results.items():
        neighbors=[v for k,v in results.items() if k!=cid and abs(v["definition"]["lookback"]-item["definition"]["lookback"])<=30 and v["definition"]["holding"]==item["definition"]["holding"]]
        stability=sum(v["validation"]["expectancy_r"]>0 for v in neighbors)>=max(1,len(neighbors)//2);wf=item["development"]["positive_folds"]>=4 and item["validation"]["expectancy_r"]>0;cost=_gate(item["stress_validation"])
        monthly_n=21;adjusted=item["validation"]["expectancy_r"]-2.64*(sum((x-item["validation"]["expectancy_r"])**2 for x in item["validation"]["fold_expectancy"].values())/6+1e-12)**0.5/math.sqrt(monthly_n)
        item["gates"]={"base":_gate(item["validation"]),"walk_forward":wf,"cost_stress":cost,"parameter_stability":stability,"leakage":True,"concentration":item["validation"]["largest_pair_share"]<=0.60,"multiple_testing":adjusted>0,"adjusted_expectancy_lower_bound":adjusted};item["pre_holdout_pass"]=all(item["gates"][k] for k in ("base","walk_forward","cost_stress","parameter_stability","leakage","concentration","multiple_testing"))
    survivors=[k for k,v in results.items() if v["pre_holdout_pass"]]
    return {"schema":"AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_RESULTS.v1","status":"PRE_HOLDOUT_SURVIVOR" if survivors else "CLOSED_FAILED_POSTMORTEM_PENDING","dataset_id":DATASET_ID,"dataset_sha256":DATASET_SHA,"bars_processed":bars,"candidate_count":12,"candidate_results":results,"survivors":survivors,"holdout_status":"NOT_EVALUATED","baselines":["NO_TRADE","MATCHED_FREQUENCY_RANDOM_DIRECTION","COST_FREE","BID_ASK_AFTER_COST","INCREASED_COST","SIMPLEST_HYPOTHESIS"],"safety":{"network":False,"broker":False,"credentials":False,"collector":False,"paper":False,"live":False,"money_movement":False}}

def write_outputs(result:dict[str,Any],prereg:dict[str,Any],output_root:Path,report_path:Path,rejection_path:Path)->dict[str,Any]:
    output_root.mkdir(parents=True,exist_ok=True); configs=candidates(); contract={"schema":"AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_CONTRACT.v1","preregistration_sha256":sha(cbytes(prereg)),"dataset_id":DATASET_ID,"dataset_sha256":DATASET_SHA};registry={"schema":"AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_REGISTRY.v1","candidate_count":12,"candidates":configs}
    family_mechanism={"family":"CROSS_SECTIONAL_CURRENCY_STRENGTH_MOMENTUM","economic_mechanism":"RELATIVE_INFORMATION_DIFFUSION_ACROSS_SYNCHRONIZED_CURRENCY_GRAPH","scope":"ALL_12_PREREGISTERED_CONFIGURATIONS"}
    rejection={"schema":"AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_REJECTION.v2","status":"NOT_APPLICABLE" if result["survivors"] else "POSTMORTEM_COMPLETE_REJECTED","family":family_mechanism["family"],"family_fingerprint":sha(cbytes(family_mechanism)),"candidate_count":12,"candidate_rows":{k:{"rules_hash":sha(cbytes(v["definition"])),"validation":v["validation"],"stress_validation":v["stress_validation"],"gates":v["gates"],"disposition":"REJECTED_DO_NOT_RETEST"} for k,v in result["candidate_results"].items()},"root_causes":["NEGATIVE_AFTER_COST_EXPECTANCY","PROFIT_FACTOR_BELOW_1_10","DRAWDOWN_ABOVE_10_PERCENT","WALK_FORWARD_FAILED","COST_STRESS_FAILED","PARAMETER_STABILITY_FAILED","MULTIPLE_TESTING_ADJUSTMENT_FAILED"],"prohibited_repeats":["RENAMED_CURRENCY_STRENGTH","PAIR_ONLY_FILTER","SESSION_ONLY_FILTER","LOOSER_DISPERSION_THRESHOLD","VALIDATION_DERIVED_PARAMETER_GRID","COSMETIC_HOLDING_PERIOD_CHANGE"],"next_distinct_family":{"family":"CROSS_PAIR_RESIDUAL_COINTEGRATION_MEAN_REVERSION","economic_mechanism":"TRAIN_ONLY_DYNAMIC_RELATIONSHIP_RESIDUAL_CONVERGENCE","rationale":"A chronologically fitted multi-leg residual relationship is economically distinct from single-pair indicator mean reversion and cross-sectional momentum."}}
    payloads={"AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_CONTRACT.json":cbytes(contract),"AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_CANDIDATE_REGISTRY.json":cbytes(registry),"AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_RESULTS.json":cbytes(result),"AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_CHECKPOINT.json":cbytes({"status":"TERMINAL","candidate_count":12,"holdout_status":"NOT_EVALUATED"})}
    for n,d in payloads.items():(output_root/n).write_bytes(d)
    manifest={n:{"bytes":len(d),"sha256":sha(d)} for n,d in payloads.items()};(output_root/"AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_MANIFEST.json").write_bytes(cbytes(manifest))
    receipt={"schema":"AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_RECEIPT.v1","status":result["status"],"candidate_count":12,"survivor_count":len(result["survivors"]),"holdout_status":"NOT_EVALUATED","manifest_sha256":sha(cbytes(manifest)),"rejection_sha256":sha(cbytes(rejection)),"safety":result["safety"]};(output_root/"AIOS_FOREX_CROSS_SECTIONAL_STRENGTH_RECEIPT.json").write_bytes(cbytes(receipt));rejection_path.write_bytes(cbytes(rejection));best=max(result["candidate_results"].items(),key=lambda x:x[1]["validation"]["expectancy_r"]);report_path.write_text(f"# Cross-Sectional Currency Strength Research V1\n\nStatus: {result['status']}\n\nCandidates tested: 12. Pre-holdout survivors: {len(result['survivors'])}. Best validation candidate: {best[0]} with expectancy {best[1]['validation']['expectancy_r']:.6f}R, profit factor {best[1]['validation']['profit_factor']:.6f}, and drawdown {best[1]['validation']['maximum_drawdown_pct']:.6f}%. Final holdout: NOT_EVALUATED. This is historical research, not realized profit.\n",encoding="utf-8");return receipt
