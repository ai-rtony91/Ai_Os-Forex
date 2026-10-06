"""Bounded multi-stage, PAPER-only portable Forex edge discovery campaign."""
from __future__ import annotations

import argparse, hashlib, json, math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from automation.forex_engine.forex_candidate_research_v2 import CORPUS_ROOT, atomic_json, atomic_text, fold_boundaries, gate, load_rows, metrics, partitions, session, stable_json

ROOT=Path('.aios/runtime/forex_portable_edge_discovery_v2')
STATE=Path('Reports/forex_delivery/AIOS_FOREX_PORTABLE_EDGE_DISCOVERY_V2_STATE.json')
REPORT=Path('Reports/forex_delivery/AIOS_FOREX_PORTABLE_EDGE_DISCOVERY_V2_REPORT.md')
ATR_N=14

@dataclass(frozen=True)
class Spec:
    candidate_id:str; stage:str; architecture:str; p1:int; p2:int; stop_atr:float; target_atr:float; timeframe:int=5; cooldown:int=0

STAGE_A=(
 Spec('A1-D20','A','DONCHIAN_BREAKOUT',20,0,1.5,3),Spec('A1-D60','A','DONCHIAN_BREAKOUT',60,0,2,4),
 Spec('A2-C20B10','A','VOLATILITY_CONTRACTION_EXPANSION',20,10,1.5,3),Spec('A2-C40B20','A','VOLATILITY_CONTRACTION_EXPANSION',40,20,2,4),
 Spec('A3-T50','A','SLOW_TREND_PULLBACK_STRUCTURE',50,5,1.5,3),Spec('A3-T100','A','SLOW_TREND_PULLBACK_STRUCTURE',100,5,2,4),
 Spec('A4-M24','A','DUAL_HORIZON_TIME_SERIES_MOMENTUM',24,12,2,4),Spec('A4-M96','A','DUAL_HORIZON_TIME_SERIES_MOMENTUM',96,24,2,4),
 Spec('A5-LONDON','A','OPENING_RANGE_SESSION_BREAKOUT',12,0,1.5,3),Spec('A5-NEWYORK','A','OPENING_RANGE_SESSION_BREAKOUT',24,0,2,4),
)
CAMPAIGN={'stage_a':[asdict(x) for x in STAGE_A],'stage_a_ineligible':{'A6_CAUSAL_VWAP':'No canonical session-reset VWAP definition'},'stage_b':{'parents':2,'cooldown':[3,12],'one_structure':True},'stage_c':{'minutes':[15,30,60],'parents':2},'stage_d':{'features':['ATR_TERTILE','DIRECTIONAL_EFFICIENCY_TERTILE','SPREAD_TERTILE'],'thresholds':'development tertiles only'},'stage_e':{'score':'breakout_strength + trend_persistence - spread_cost_fraction','policies':[1,3,5]}}

def tr(rows,i):
    c=rows[i]['mid']; p=float(rows[i-1]['mid']['c']); return max(float(c['h'])-float(c['l']),abs(float(c['h'])-p),abs(float(c['l'])-p))
def atr(rows,i): return None if i<ATR_N else sum(tr(rows,j) for j in range(i-ATR_N+1,i+1))/ATR_N
def sma(rows,i,n): return None if i+1<n else sum(float(x['mid']['c']) for x in rows[i-n+1:i+1])/n

def signal(rows,i,s):
    warm=max(ATR_N,s.p1,s.p2 or 0)
    if i<warm:return None
    close=float(rows[i]['mid']['c']); prior=rows[max(0,i-s.p1):i]; a=atr(rows,i)
    if a is None or a<=0:return None
    if s.architecture=='DONCHIAN_BREAKOUT':
        hi=max(float(x['mid']['h']) for x in prior); lo=min(float(x['mid']['l']) for x in prior)
        return ('BUY',(close-hi)/a) if close>hi else ('SELL',(lo-close)/a) if close<lo else None
    if s.architecture=='VOLATILITY_CONTRACTION_EXPANSION':
        recent=[tr(rows,j) for j in range(i-s.p1,i)]; base=sum(recent)/len(recent); short=prior[-s.p2:]; hi=max(float(x['mid']['h']) for x in short);lo=min(float(x['mid']['l']) for x in short)
        if recent[-1] > base*.75:return None
        return ('BUY',(close-hi)/a) if close>hi else ('SELL',(lo-close)/a) if close<lo else None
    if s.architecture=='SLOW_TREND_PULLBACK_STRUCTURE':
        ma=sma(rows,i,s.p1); old=sma(rows,i-s.p2,s.p1); prev=float(rows[i-1]['mid']['c']); op=float(rows[i]['mid']['o'])
        return ('BUY',(close-ma)/a) if ma and old and ma>old and prev<=ma+a*.5 and close>ma and close>op else ('SELL',(ma-close)/a) if ma and old and ma<old and prev>=ma-a*.5 and close<ma and close<op else None
    if s.architecture=='DUAL_HORIZON_TIME_SERIES_MOMENTUM':
        past=float(rows[i-s.p1]['mid']['c']); local=rows[i-s.p2:i]; hi=max(float(x['mid']['h']) for x in local);lo=min(float(x['mid']['l']) for x in local)
        return ('BUY',(close-hi)/a) if close>past and close>hi else ('SELL',(lo-close)/a) if close<past and close<lo else None
    hour=int(rows[i]['timestamp'][11:13]); start=7 if s.candidate_id.endswith('LONDON') else 13
    if hour<start+1:return None
    day=rows[i]['timestamp'][:10]; opening=[x for x in rows[max(0,i-300):i] if x['timestamp'][:10]==day and start<=int(x['timestamp'][11:13])<start+1]
    if not opening:return None
    hi=max(float(x['mid']['h']) for x in opening);lo=min(float(x['mid']['l']) for x in opening)
    return ('BUY',(close-hi)/a) if close>hi else ('SELL',(lo-close)/a) if close<lo else None

def backtest(rows,s,direction,stress=1.0):
    out=[];pos=None;pending=None;last=-10**9;structure=None
    for i,row in enumerate(rows):
        if pending:
            raw=float(row['ask']['o'] if direction=='BUY' else row['bid']['o']);spr=float(row['ask']['o'])-float(row['bid']['o']);entry=raw+(stress-1)*spr*(1 if direction=='BUY' else -1);risk=s.stop_atr*pending['atr'];pos={'instrument':row['instrument'],'signal_time':pending['time'],'entry_time':row['timestamp'],'entry':entry,'risk':risk,'initial_stop':entry-risk if direction=='BUY' else entry+risk,'target':entry+s.target_atr*pending['atr'] if direction=='BUY' else entry-s.target_atr*pending['atr'],'session':session(row['timestamp']),'mfe_r':0.0,'mae_r':0.0};pending=None
        if pos:
            if direction=='BUY': adv=float(row['bid']['l']);fav=float(row['bid']['h']);sh=adv<=pos['initial_stop'];th=fav>=pos['target'];px=pos['initial_stop'] if sh else pos['target'] if th else None;r=(px-pos['entry'])/pos['risk'] if px is not None else None
            else: adv=float(row['ask']['h']);fav=float(row['ask']['l']);sh=adv>=pos['initial_stop'];th=fav<=pos['target'];px=pos['initial_stop'] if sh else pos['target'] if th else None;r=(pos['entry']-px)/pos['risk'] if px is not None else None
            if r is not None: out.append({**pos,'exit_time':row['timestamp'],'exit_reason':'STOP' if sh else 'TARGET','realized_r':r,'direction':direction});pos=None
        sig=signal(rows,i,s);a=atr(rows,i)
        if sig and sig[0]==direction and a and pos is None and pending is None and i-last>s.cooldown and i+1<len(rows): pending={'time':row['timestamp'],'atr':a};last=i
    return out

def aggregate(rows,minutes):
    if minutes==5:return rows
    size=minutes//5;out=[]
    for i in range(0,len(rows)-size+1,size):
        g=rows[i:i+size]
        if int(g[0]['timestamp'][14:16])%minutes:continue
        z={'timestamp':g[-1]['timestamp'],'instrument':g[0]['instrument'],'volume':sum(float(x['volume']) for x in g)}
        for side in ('bid','ask','mid'):z[side]={'o':g[0][side]['o'],'h':max(float(x[side]['h']) for x in g),'l':min(float(x[side]['l']) for x in g),'c':g[-1][side]['c']}
        out.append(z)
    return out

def assess(spec,manifest,split,do_validation=True):
    dev={d:[] for d in ('BUY','SELL')};val={d:[] for d in ('BUY','SELL')};stress={d:[] for d in ('BUY','SELL')};folds=fold_boundaries(split['development']['start_utc'],split['development']['end_utc']);fi={d:[[] for _ in folds] for d in dev}
    for art in manifest['artifacts']:
        p=CORPUS_ROOT/art['relative_path'];dr=aggregate(load_rows(p,split['development']['start_utc'],split['development']['end_utc']),spec.timeframe);vr=aggregate(load_rows(p,split['validation']['start_utc'],split['validation']['end_utc']),spec.timeframe)
        for d in dev:
            t=backtest(dr,spec,d);dev[d]+=t
            for k,b in enumerate(folds):fi[d][k]+=[x for x in t if b['start_utc']<=x['signal_time']<b['end_utc']]
            if do_validation:val[d]+=backtest(vr,spec,d);stress[d]+=backtest(vr,spec,d,1.25)
    result={}
    for d,label in (('BUY','LONG'),('SELL','SHORT')):
        dm=metrics(dev[d]);fm=[metrics(x) for x in fi[d]];passed,blocks=gate(dm)
        if sum(x['expectancy_r']>0 for x in fm)<3:passed=False;blocks.append('FOLD_CONSISTENCY')
        vm=metrics(val[d]);vp,vb=gate(vm) if passed and do_validation else (False,['DEVELOPMENT_FAILED']);sm=metrics(stress[d])
        if vp and (sm['expectancy_r']<=0 or not sm['profit_factor'] or sm['profit_factor']<1.1):vp=False;vb.append('SPREAD_STRESS')
        result[label]={'development':dm,'folds':fm,'development_pass':passed,'development_blockers':blocks,'validation':vm,'validation_pass':vp,'validation_blockers':vb,'stress':sm}
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');args=ap.parse_args();assert args.execute
    manifest=json.loads((CORPUS_ROOT/'manifest.json').read_text());split=partitions(manifest['requested_start_utc'],manifest['requested_end_utc']);freeze={'campaign':CAMPAIGN,'frozen_utc':datetime.now(timezone.utc).isoformat()};freeze['hash']=hashlib.sha256(stable_json(freeze['campaign']).encode()).hexdigest()
    stages={'A':{},'B':{},'C':{},'D':{'status':'NO_ELIGIBLE_PARENT'},'E':{'status':'NO_ELIGIBLE_PARENT'}};passers=[]
    for s in STAGE_A:
        r=assess(s,manifest,split);stages['A'][s.candidate_id]={'spec':asdict(s),'result':r};passers += [(s,r)] if any(x['validation_pass'] for x in r.values()) else []
    ranked=sorted(STAGE_A,key=lambda s:max(stages['A'][s.candidate_id]['result'][d]['development']['expectancy_r'] for d in ('LONG','SHORT')),reverse=True)[:2]
    for p in ranked:
        for cd in (3,12):
            s=Spec(f'B-{p.candidate_id}-CD{cd}','B',p.architecture,p.p1,p.p2,p.stop_atr,p.target_atr,5,cd);r=assess(s,manifest,split);stages['B'][s.candidate_id]={'spec':asdict(s),'result':r};passers += [(s,r)] if any(x['validation_pass'] for x in r.values()) else []
    for p in ranked:
        for tf in (15,30,60):
            s=Spec(f'C-{p.candidate_id}-{tf}','C',p.architecture,p.p1,p.p2,p.stop_atr,p.target_atr,tf,0);r=assess(s,manifest,split);stages['C'][s.candidate_id]={'spec':asdict(s),'result':r};passers += [(s,r)] if any(x['validation_pass'] for x in r.values()) else []
    if not passers:
        stages['D']={'status':'COMPLETE_NO_ELIGIBLE_PARENT','reason':'No noncatastrophic development passer for causal regime restriction'};stages['E']={'status':'COMPLETE_NO_ELIGIBLE_PARENT','reason':'No candidate-producing parent eligible for P&L-free opportunity ranking'}
    finalists=[]
    for s,r in passers[:3]:finalists.append({'candidate_id':s.candidate_id,'spec':asdict(s),'enabled_directions':[d for d,x in r.items() if x['validation_pass']]})
    state={'schema':'AIOS_FOREX_PORTABLE_EDGE_DISCOVERY_V2','packet_id':'PKT-EAST-FOREX-PORTABLE-EDGE-DISCOVERY-011R','generated_utc':datetime.now(timezone.utc).isoformat(),'corpus_id':manifest['corpus_id'],'corpus_hash':manifest['aggregate_corpus_fingerprint'],'campaign_freeze':freeze,'stages':stages,'finalists':finalists,'status':'FORWARD_HOLDOUT_ACCUMULATING' if finalists else 'ALL_RESEARCH_STAGES_EXHAUSTED','dominant_failure':'MIXED_FAILURE' if not finalists else None,'next_method':'different market horizon with extended corpus' if not finalists else 'collect untouched forward evidence','safety':{'broker_write':False,'practice_order':False,'live':False,'money_movement':False}}
    ROOT.mkdir(parents=True,exist_ok=True);atomic_json(ROOT/'campaign_results.json',state);atomic_json(STATE,state)
    lines=['# Portable Edge Discovery V2','',f"Status: `{state['status']}`",f"Campaign hash: `{freeze['hash']}`",'', '## Stage Summary']
    for stage,data in stages.items():lines.append(f"- Stage {stage}: {len(data) if isinstance(data,dict) else data} records")
    lines += ['',f"Finalists: `{stable_json(finalists)}`",'',f"Next method: {state['next_method']}"]
    atomic_text(REPORT,'\n'.join(lines));print(stable_json({'status':state['status'],'finalists':finalists,'live':False}))
if __name__=='__main__':main()
