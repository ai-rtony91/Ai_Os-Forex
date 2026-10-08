"""Sealed, bounded Packet 011-F opportunity and edge research on Corpus V2."""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,os,random,tempfile
from collections import defaultdict
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Any

CORPUS=Path('.aios/runtime/forex_m5_immutable_corpus_v2');ROOT=Path('.aios/runtime/forex_edge_research_v1');STATE=Path('Reports/forex_delivery/AIOS_FOREX_EDGE_RESEARCH_V1_STATE.json');REPORT=Path('Reports/forex_delivery/AIOS_FOREX_EDGE_RESEARCH_V1_REPORT.md');RISK=.0025
@dataclass(frozen=True)
class Candidate:id:str;architecture:str;timeframe:int;lookback:int;stop_atr:float;target_r:float
def stable(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def atomic_json(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
  os.replace(name,path)
 finally:
  if os.path.exists(name):os.unlink(name)
def atomic_text(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.tmp',dir=path.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(value)
  os.replace(name,path)
 finally:
  if os.path.exists(name):os.unlink(name)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def ts(x):return datetime.fromisoformat(x.replace('Z','+00:00')).astimezone(timezone.utc)
def load_pair(manifest,pair):
 rows=[]
 for a in manifest['artifacts']:
  if a['instrument']!=pair:continue
  with gzip.open(CORPUS/a['path'],'rt',encoding='ascii') as f:rows.extend(json.loads(x) for x in f if x.strip())
 return sorted({x['timestamp']:x for x in rows}.values(),key=lambda x:x['timestamp'])
def aggregate(rows,minutes):
 if minutes==5:return rows
 size=minutes//5;out=[]
 for i in range(0,len(rows)-size+1,size):
  g=rows[i:i+size];t=ts(g[0]['timestamp'])
  if t.minute%minutes:continue
  z={'timestamp':g[-1]['timestamp'],'instrument':g[0]['instrument'],'volume':sum(x['volume'] for x in g)}
  for s in ('bid','ask','mid'):z[s]={'o':g[0][s]['o'],'h':max(float(x[s]['h']) for x in g),'l':min(float(x[s]['l']) for x in g),'c':g[-1][s]['c']}
  out.append(z)
 return out
def tr(rows,i):
 c=rows[i]['mid'];p=float(rows[i-1]['mid']['c']);return max(float(c['h'])-float(c['l']),abs(float(c['h'])-p),abs(float(c['l'])-p))
def atr(rows,i,n=14):return None if i<n else sum(tr(rows,j) for j in range(i-n+1,i+1))/n
def split_contract(manifest):
 start=ts(manifest['start_utc']);end=ts(manifest['end_utc']);span=end-start;dev=start+span*.6;val=start+span*.8
 return {'development':[start,dev],'validation':[dev,val],'sealed_holdout':[val,end]}
def in_window(row,w):v=ts(row['timestamp']);return w[0]<=v<w[1]
def future_label(rows,i,h,a,side):
 future=rows[i+1:min(len(rows),i+h+1)]
 if not future or not a:return None
 close=float(rows[i]['mid']['c'])
 if side=='LONG':mfe=(max(float(x['bid']['h']) for x in future)-float(rows[i]['ask']['c']))/a;mae=(min(float(x['bid']['l']) for x in future)-float(rows[i]['ask']['c']))/a
 else:mfe=(float(rows[i]['bid']['c'])-min(float(x['ask']['l']) for x in future))/a;mae=(float(rows[i]['bid']['c'])-max(float(x['ask']['h']) for x in future))/a
 return mfe,mae
def opportunity(manifest,split):
 horizons={30:6,60:12,120:24,240:48,480:96,1440:288};stats=defaultdict(lambda:{'n':0,'mfe':0.,'mae':0.,'p05':0,'p1':0,'p2':0,'p3':0});pairs=manifest['eligible_pairs']
 for pair in pairs:
  rows=[x for x in load_pair(manifest,pair) if in_window(x,split['development'])]
  for i in range(60,len(rows)-289,24):
   a=atr(rows,i);close=float(rows[i]['mid']['c']);prior=rows[i-20:i];hi=max(float(x['mid']['h']) for x in prior);lo=min(float(x['mid']['l']) for x in prior);trend=close-float(rows[i-48]['mid']['c']);prev=float(rows[i-1]['mid']['c']);old=rows[i-21:i-1];old_hi=max(float(x['mid']['h']) for x in old);old_lo=min(float(x['mid']['l']) for x in old);atr_history=[atr(rows,j) for j in range(i-40,i)];atr_history=[x for x in atr_history if x];rank=sum(x<=a for x in atr_history)/len(atr_history) if a and atr_history else .5
   conditions=[('NULL','LONG'),('NULL','SHORT')];conditions+=[('BREAKOUT_LONG','LONG')] if close>hi else [('BREAKOUT_SHORT','SHORT')] if close<lo else [];conditions+=[('TREND_LONG','LONG')] if trend>0 else [('TREND_SHORT','SHORT')];conditions+=[(('LOW_VOL' if rank<1/3 else 'HIGH_VOL' if rank>2/3 else 'MID_VOL')+'_'+side,side) for side in ('LONG','SHORT')]
   if a and a<sum(atr_history)/len(atr_history)*.67:conditions += [('COMPRESSION_LONG','LONG'),('COMPRESSION_SHORT','SHORT')]
   if prev>old_hi and close<=hi:conditions.append(('FAILED_BREAKOUT_SHORT','SHORT'))
   if prev<old_lo and close>=lo:conditions.append(('FAILED_BREAKOUT_LONG','LONG'))
   for condition,side in conditions:
    for minutes,bars in horizons.items():
     result=future_label(rows,i,bars,a,side)
     if not result:continue
     mfe,mae=result;k=f'{condition}:{side}:{minutes}';s=stats[k];s['n']+=1;s['mfe']+=mfe;s['mae']+=mae
     for threshold,name in ((.5,'p05'),(1,'p1'),(2,'p2'),(3,'p3')):s[name]+=int(mfe>=threshold and mae>-1)
 out={}
 for k,s in stats.items():out[k]={'samples':s['n'],'mean_mfe_atr':s['mfe']/s['n'],'mean_mae_atr':s['mae']/s['n'],**{x:s[x]/s['n'] for x in ('p05','p1','p2','p3')}}
 return out
def registry_from_opportunity(surface):
 supported=[]
 for architecture,condition in [('EVENT_BREAKOUT_CONTINUATION','BREAKOUT'),('SLOW_TREND_PULLBACK_CONTINUATION','TREND'),('FAILED_BREAKOUT_REVERSAL','FAILED_BREAKOUT'),('VOLATILITY_COMPRESSION_EXPANSION','COMPRESSION')]:
  effects=[]
  for side in ('LONG','SHORT'):
   for h in (30,60,120,240,480,1440):
    a=surface.get(f'{condition}_{side}:{side}:{h}');n=surface.get(f'NULL:{side}:{h}')
    if a and n:effects.append(a['p1']-n['p1'])
  if effects and max(effects)>.01:supported.append(architecture)
 candidates=[]
 for architecture in supported:
  for tf in (5,10,15,30):
   for lookback,stop,target in ((20,1.5,2),(40,2,3)):
    candidates.append(Candidate(f'{architecture[:3]}-{tf}-{lookback}-{int(target)}',architecture,tf,lookback,stop,target))
 return candidates[:36]
def signal(rows,i,c):
 if i<max(50,c.lookback):return None
 close=float(rows[i]['mid']['c']);prior=rows[i-c.lookback:i];hi=max(float(x['mid']['h']) for x in prior);lo=min(float(x['mid']['l']) for x in prior)
 if c.architecture=='EVENT_BREAKOUT_CONTINUATION':return 'LONG' if close>hi else 'SHORT' if close<lo else None
 if c.architecture=='FAILED_BREAKOUT_REVERSAL':
  old=rows[i-c.lookback-1:i-1];old_hi=max(float(x['mid']['h']) for x in old);old_lo=min(float(x['mid']['l']) for x in old);prev=float(rows[i-1]['mid']['c']);return 'SHORT' if prev>old_hi and close<=hi else 'LONG' if prev<old_lo and close>=lo else None
 if c.architecture=='VOLATILITY_COMPRESSION_EXPANSION':
  previous_atr=atr(rows,i-1);history=[atr(rows,j) for j in range(i-21,i-1)];history=[x for x in history if x]
  if not previous_atr or not history or previous_atr>=sum(history)/len(history)*.67:return None
  return 'LONG' if close>hi else 'SHORT' if close<lo else None
 ma=sum(float(x['mid']['c']) for x in rows[i-50:i])/50;old=sum(float(x['mid']['c']) for x in rows[i-55:i-5])/50
 return 'LONG' if ma>old and close>ma and float(rows[i-1]['mid']['c'])<=ma else 'SHORT' if ma<old and close<ma and float(rows[i-1]['mid']['c'])>=ma else None
def backtest(rows,c,side):
 trades=[];pending=None;position=None;active_event=None
 for i,row in enumerate(rows):
  if pending:
   entry=float(row['ask']['o'] if side=='LONG' else row['bid']['o']);risk=pending['atr']*c.stop_atr;stop=entry-risk if side=='LONG' else entry+risk;target=entry+c.target_r*risk if side=='LONG' else entry-c.target_r*risk;position={'event_id':pending['event'],'signal_time':pending['time'],'entry_time':row['timestamp'],'entry':entry,'risk':risk,'stop':stop,'target':target,'pair':row['instrument']};pending=None
  if position:
   if side=='LONG':sh=float(row['bid']['l'])<=position['stop'];th=float(row['bid']['h'])>=position['target'];px=position['stop'] if sh else position['target'] if th else None;r=None if px is None else (px-position['entry'])/position['risk']
   else:sh=float(row['ask']['h'])>=position['stop'];th=float(row['ask']['l'])<=position['target'];px=position['stop'] if sh else position['target'] if th else None;r=None if px is None else (position['entry']-px)/position['risk']
   if r is not None:trades.append({**position,'exit_time':row['timestamp'],'r':r,'reason':'STOP' if sh else 'TARGET','side':side});position=None
  s=signal(rows,i,c);a=atr(rows,i)
  if s is None:active_event=None
  if s==side and a and position is None and pending is None and i+1<len(rows):
   event=f'{row["instrument"]}:{c.id}:{side}:{row["timestamp"]}' if active_event is None else active_event
   if active_event is None:pending={'time':row['timestamp'],'atr':a,'event':event};active_event=event
 return trades
def metrics(trades):
 rs=[x['r'] for x in trades];wins=[x for x in rs if x>0];loss=[x for x in rs if x<0];eq=peak=100000.;dd=0
 for r in rs:eq+=eq*RISK*r;peak=max(peak,eq);dd=max(dd,100*(peak-eq)/peak)
 pairs=defaultdict(int)
 for t in trades:pairs[t['pair']]+=1
 return {'trades':len(rs),'expectancy_r':sum(rs)/len(rs) if rs else 0.,'profit_factor':sum(wins)/abs(sum(loss)) if loss else (math.inf if wins else 0.),'net_r':sum(rs),'max_drawdown_pct':dd,'pair_count':len(pairs),'largest_pair_share':max(pairs.values())/len(rs) if rs else 0.}
def six_folds(window):
 span=window[1]-window[0];return [(window[0]+span*i/6,window[0]+span*(i+1)/6) for i in range(6)]
def gate(m,folds):return m['trades']>=50 and m['expectancy_r']>0 and m['profit_factor']>=1.1 and m['net_r']>0 and m['max_drawdown_pct']<=10 and sum(x['expectancy_r']>0 and x['trades']>=8 for x in folds)>=4 and m['largest_pair_share']<=.25
def null_campaign(results,repetitions=500):
 rng=random.Random(11011);best=[];blocks={k:[sum(t['r'] for t in v[i:i+50]) for i in range(0,len(v),50)] for k,v in results.items()}
 for _ in range(repetitions):
  values=[]
  for k,b in blocks.items():values.append(sum(x*(1 if rng.random()>.5 else -1) for x in b)/max(1,len(results[k])))
  best.append(max(values,default=0.))
 best.sort();return {'repetitions':repetitions,'best_expectancy_95pct':best[int(.95*(len(best)-1))] if best else 0.}
def bootstrap_probability(trades,repetitions=1000):
 if not trades:return 0.
 rng=random.Random(11012);blocks=[[x['r'] for x in trades[i:i+50]] for i in range(0,len(trades),50)];positive=0
 for _ in range(repetitions):
  sample=[r for _ in blocks for r in rng.choice(blocks)];positive+=sum(sample)>0
 return positive/repetitions
def run():
 manifest=json.loads((CORPUS/'manifest.json').read_text());split=split_contract(manifest);contract={'split':{k:[v[0].isoformat(),v[1].isoformat()] for k,v in split.items()},'six_folds':6,'embargo_m5_bars':288,'candidate_cap':36,'null_repetitions':500,'bootstrap_repetitions':1000,'holdout':'SEALED_UNTIL_SHORTLIST_FREEZE'};atomic_json(ROOT/'research_contract.json',contract)
 surface=opportunity(manifest,split);atomic_json(ROOT/'opportunity_surface.json',surface);registry=registry_from_opportunity(surface);reg={'candidates':[asdict(x) for x in registry]};reg['hash']=hashlib.sha256(stable(reg['candidates']).encode()).hexdigest();atomic_json(ROOT/'candidate_registry.json',reg)
 dev_trades={};dev_results={};val_results={};passers=[]
 for c in registry:
  pooled={s:[] for s in ('LONG','SHORT')};folded={s:[[] for _ in range(6)] for s in pooled}
  for pair in manifest['eligible_pairs']:
   rows=aggregate([x for x in load_pair(manifest,pair) if in_window(x,split['development'])],c.timeframe)
   for side in pooled:
    t=backtest(rows,c,side);pooled[side]+=t
    for j,w in enumerate(six_folds(split['development'])):folded[side][j]+=[x for x in t if w[0]<=ts(x['signal_time'])<w[1]]
  dev_results[c.id]={}
  for side in pooled:
   m=metrics(pooled[side]);fm=[metrics(x) for x in folded[side]];dev_results[c.id][side]={'metrics':m,'folds':fm,'pass':gate(m,fm)};dev_trades[c.id+':'+side]=pooled[side]
   if gate(m,fm):passers.append((c,side))
 null=null_campaign(dev_trades)
 shortlist=[]
 for c,side in passers:
  m=dev_results[c.id][side]['metrics'];prob=bootstrap_probability(dev_trades[c.id+':'+side]);significant=m['expectancy_r']>null['best_expectancy_95pct'] and prob>=.95
  dev_results[c.id][side]['bootstrap_probability_positive']=prob;dev_results[c.id][side]['registry_null_pass']=significant
  if not significant:continue
  trades=[]
  for pair in manifest['eligible_pairs']:trades+=backtest(aggregate([x for x in load_pair(manifest,pair) if in_window(x,split['validation'])],c.timeframe),c,side)
  vm=metrics(trades);val_results[c.id+':'+side]=vm
  if vm['trades']>=50 and vm['expectancy_r']>0 and vm['profit_factor']>=1.1 and vm['net_r']>0 and vm['max_drawdown_pct']<=10:shortlist.append((c,side,vm))
 shortlist=shortlist[:5];shortlist_payload=[{'candidate':asdict(c),'side':s,'validation':m} for c,s,m in shortlist];shortlist_hash=hashlib.sha256(stable(shortlist_payload).encode()).hexdigest();atomic_json(ROOT/'shortlist_freeze.json',{'shortlist':shortlist_payload,'hash':shortlist_hash,'frozen_utc':datetime.now(timezone.utc).isoformat()})
 holdout_results={};finalists=[]
 for c,side,_ in shortlist:
  trades=[]
  for pair in manifest['eligible_pairs']:trades+=backtest(aggregate([x for x in load_pair(manifest,pair) if in_window(x,split['sealed_holdout'])],c.timeframe),c,side)
  hm=metrics(trades);prob=bootstrap_probability(trades);holdout_results[c.id+':'+side]={'metrics':hm,'bootstrap_probability_positive':prob}
  if hm['trades']>=50 and hm['expectancy_r']>0 and hm['profit_factor']>=1.1 and hm['net_r']>0 and hm['max_drawdown_pct']<=10 and prob>=.95:finalists.append({'candidate':asdict(c),'side':side,'holdout':hm})
 state={'schema':'AIOS_FOREX_EDGE_RESEARCH_V1','packet_id':'PKT-EAST-FOREX-FORENSIC-EDGE-PROGRAM-011F','generated_utc':datetime.now(timezone.utc).isoformat(),'corpus_hash':manifest['aggregate_corpus_fingerprint'],'contract':contract,'opportunity_surface_path':(ROOT/'opportunity_surface.json').as_posix(),'registry_count':len(registry),'registry_hash':reg['hash'],'development':dev_results,'registry_null':null,'validation':val_results,'shortlist_hash':shortlist_hash,'sealed_holdout':holdout_results,'finalists':finalists,'status':'FINALIST_ELIGIBLE' if finalists else 'RESEARCH_EXHAUSTED_NO_ROBUST_EDGE','dominant_failure':None if finalists else 'NO_PORTABLE_SIGNAL_EDGE','historical_holdout_status':'PASSERS_EVALUATED_ONCE' if shortlist else 'NOT_APPLICABLE_NO_SHORTLIST','forward_status':'NOT_STARTED_NO_FINALIST' if not finalists else 'READY_TO_INITIALIZE','safety':{'broker_write':False,'practice_order':False,'live':False,'money_movement':False}}
 atomic_json(STATE,state);atomic_json(ROOT/'campaign_state.json',state);atomic_text(REPORT,f"# AIOS Forex Edge Research V1\n\n- Status: `{state['status']}`\n- Corpus: `{state['corpus_hash']}`\n- Candidate registry: {len(registry)} (`{reg['hash']}`)\n- Development passers: {len(passers)}\n- Validation passers: {len(shortlist)}\n- Historical holdout finalists: {len(finalists)}\n- Registry-wide null repetitions: 500\n- Candidate bootstrap repetitions: 1000\n- LIVE: false\n")
 return state
def finalize_existing():
 state=json.loads(STATE.read_text());state['dominant_failure']='NO_PORTABLE_SIGNAL_EDGE';state['historical_holdout_status']='PASSERS_EVALUATED_ONCE' if state.get('validation') else 'NOT_APPLICABLE_NO_SHORTLIST';state['forward_status']='NOT_STARTED_NO_FINALIST' if not state.get('finalists') else 'READY_TO_INITIALIZE';state['production_engine_blocker']={'owner_file':'automation/forex_engine/costs.py','defect':'Synthetic spread/slippage can be charged in adjusted entry and exit prices and then charged again by apply_cost_to_pnl.','validator':'tests/forex_engine/test_costs.py plus a new single-charge integration assertion','research_affected':False};atomic_json(STATE,state);atomic_json(ROOT/'campaign_state.json',state);return state
def main():
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');p.add_argument('--finalize-existing',action='store_true');a=p.parse_args()
 if not a.execute and not a.finalize_existing:p.error('--execute or --finalize-existing required')
 r=finalize_existing() if a.finalize_existing else run();print(stable({'status':r['status'],'registry_count':r['registry_count'],'finalists':len(r['finalists'])}));return 0
if __name__=='__main__':raise SystemExit(main())
