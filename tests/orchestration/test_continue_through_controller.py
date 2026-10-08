from tests.orchestration.test_aios_continuation_controller import load_module,CONTROLLER_PATH,registry

def test_normal_boundary_prepares_without_owner_continue_prompt():
    module=load_module(CONTROLLER_PATH,'controller_law')
    for event in ('unit_finished','batch_finished','report_written','checkpoint_saved','context_turn_ended','candidate_rejected'):
        result=module.build_continuation_controller(resume_state={'goal':'forex','progress_event':event},
            mode_registry=registry(),bounded_executor_handoff={'handoff_status':'stopped'},
            autonomous_job_state={'state':'CONTINUE','safe_to_continue_without_human':True,
                'security_snapshot':{'overall_state':'CLEAR'},'next_safe_action':'Continue approved DRY_RUN preparation.'})
        assert result['action_type']=='continue_safe_preparation'
        assert result['stop_reason_class'] is None and not result['normal_continue_prompt_required']
        assert not result['execution_authority_granted']
        assert result['approval_required']['worker_dispatch'] and result['approval_required']['broker_live_trading']

def test_progress_never_overrides_real_security_gate():
    module=load_module(CONTROLLER_PATH,'controller_law')
    result=module.build_continuation_controller(resume_state={'goal':'forex','progress_event':'batch_finished','safety':{'broker':True}},
        mode_registry=registry(),autonomous_job_state={'state':'CONTINUE','safe_to_continue_without_human':True})
    assert result['stop_reason_class']=='SAFETY_INTEGRITY_BLOCK'
