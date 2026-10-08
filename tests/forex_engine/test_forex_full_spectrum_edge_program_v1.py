from automation.forex_engine import forex_full_spectrum_edge_program_v1 as module


def test_protocol_meets_packet_statistical_caps():
    p=module.protocol();assert p["cap"]==64 and p["tracks"]==8 and p["null_repetitions"]>=750 and p["bootstrap_repetitions"]>=1500


def test_registry_has_eight_complete_tracks():
    r=module.registry(False,False);assert len(r)==64;assert [sum(x.track==t for x in r) for t in range(1,9)]==[8]*8
    assert all(x.sources and x.availability_rule and x.failure_condition and x.cost_mode=="ACTUAL_BID_ASK_SINGLE_CHARGE" for x in r)


def test_unavailable_is_not_negative_edge():
    r=module.registry(False,False);assert not any(x.data_eligible for x in r if x.track in (1,3));assert all(x.data_eligible for x in r if x.track not in (1,3))


def test_scorecard_does_not_hide_critical_gates():
    s=module.scorecard("NOT_CREATED_NO_NEW_USABLE_INFORMATION");assert len([k for k in s if k!="critical_parity"])==10;assert s["FORWARD_PROOF"]["score"]==0;assert s["critical_parity"]["external_coverage_or_missing_formally_untestable"]


def test_registry_hash_is_deterministic():
    a=[module.asdict(x) for x in module.registry(False,False)];b=[module.asdict(x) for x in module.registry(False,False)];assert module.prior.sha(module.stable(a).encode())==module.prior.sha(module.stable(b).encode())
