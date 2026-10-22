# AIOS Master Runtime V1

`python aios.py` is the canonical command surface for deterministic orchestration discovery, planning, validation, checkpointing, and resume.

## Commands

- `status`: inspect repository and capability state.
- `plan`: build a normalized registered-stage plan without a checkpoint.
- `run`: build the plan and atomically save `.aios/runtime/master-runtime-v1.json`.
- `resume`: accept that checkpoint only when repository and graph identity remain compatible.
- `validate`: validate stage receipts and protected-action gates.

The runtime composes `OrchestrationPlatform`; it does not interpret or execute shell text from generated artifacts. Broker, credential, deploy, push, publish, merge, and order actions remain disabled.

Each run invokes the canonical spine, work braid, queue planner, dispatcher,
packet builder, packet resolver, autonomy governor, and countdown through
registered Python APIs. The builder and resolver receive deliberately incomplete
inputs during discovery so their existing fail-closed gates are exercised without
creating an APPLY packet or granting authority.
