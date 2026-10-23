from datetime import datetime,timezone
from automation.forex_engine.forex_edge_research_v1 import Candidate,aggregate,bootstrap_probability,gate,metrics,null_campaign,six_folds

def row(i):
 x={'o':1+i*.001,'h':1.01+i*.001,'l':.99+i*.001,'c':1.005+i*.001};return {'timestamp':f'2024-01-01T00:{i*5:02d}:00Z','instrument':'EUR_USD','volume':1,'bid':dict(x),'ask':{k:v+.0001 for k,v in x.items()},'mid':dict(x)}
def test_aggregation_requires_complete_group():assert len(aggregate([row(i) for i in range(4)],15))==1
def test_six_folds_do_not_overlap():
 w=(datetime(2024,1,1,tzinfo=timezone.utc),datetime(2024,1,7,tzinfo=timezone.utc));f=six_folds(w);assert len(f)==6 and all(a[1]==b[0] for a,b in zip(f,f[1:]))
def test_metrics_use_peak_equity_drawdown():
 t=[{'r':2,'pair':'A'},{'r':-1,'pair':'A'}];m=metrics(t);assert m['net_r']==1 and m['max_drawdown_pct']>0
def test_gate_rejects_insufficient_sample():assert not gate({'trades':49,'expectancy_r':1,'profit_factor':2,'net_r':2,'max_drawdown_pct':1,'largest_pair_share':.1},[])
def test_null_and_bootstrap_are_deterministic():
 t=[{'r':1 if i%3 else -1,'pair':'A'} for i in range(120)];assert null_campaign({'x':t},20)==null_campaign({'x':t},20) and bootstrap_probability(t,20)==bootstrap_probability(t,20)
def test_candidate_registry_shape():assert Candidate('x','EVENT_BREAKOUT_CONTINUATION',5,20,1.5,2).target_r==2
