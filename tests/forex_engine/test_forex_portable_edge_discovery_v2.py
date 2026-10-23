from automation.forex_engine.forex_portable_edge_discovery_v2 import CAMPAIGN, STAGE_A, Spec, aggregate, signal

def row(ts,c,h=None,l=None):
    h=c if h is None else h;l=c if l is None else l;x={'o':c,'h':h,'l':l,'c':c};return {'timestamp':ts,'instrument':'EUR_USD','volume':1,'bid':dict(x),'ask':dict(x),'mid':dict(x)}
def test_campaign_frozen_all_stages():
    assert len(STAGE_A)==10 and set(CAMPAIGN)=={'stage_a','stage_a_ineligible','stage_b','stage_c','stage_d','stage_e'}
def test_donchian_excludes_current_bar():
    rows=[row(f'2026-01-01T00:{i:02d}:00Z',1.0,1.1,.9) for i in range(20)]+[row('2026-01-01T01:40:00Z',1.2,1.2,1.1)]
    s=Spec('x','A','DONCHIAN_BREAKOUT',20,0,1.5,3)
    assert signal(rows,20,s)[0]=='BUY'
def test_aggregation_uses_only_complete_groups():
    rows=[row(f'2026-01-01T00:{i*5:02d}:00Z',1+i/100) for i in range(4)]
    out=aggregate(rows,15);assert len(out)==1 and out[0]['volume']==3
def test_zero_volatility_is_not_a_signal():
    rows=[row(f'2026-01-01T07:{i:02d}:00Z',1.0) for i in range(60)]
    s=Spec('A5-LONDON','A','OPENING_RANGE_SESSION_BREAKOUT',12,0,1.5,3)
    assert signal(rows,59,s) is None
