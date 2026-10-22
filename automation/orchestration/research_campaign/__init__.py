"""Local-only Forex-first research campaign controller."""

from .aios_research_campaign import (
    CampaignDecision,
    CampaignCheckpointError,
    CampaignSpec,
    CampaignValidationError,
    Experiment,
    ExperimentOutcome,
    evaluate_edge_gate,
    experiment_fingerprint,
    load_checkpoint,
    run_campaign_cycle,
    score_evidence,
    write_checkpoint,
)

__all__ = [
    "CampaignDecision",
    "CampaignCheckpointError",
    "CampaignSpec",
    "CampaignValidationError",
    "Experiment",
    "ExperimentOutcome",
    "evaluate_edge_gate",
    "experiment_fingerprint",
    "load_checkpoint",
    "run_campaign_cycle",
    "score_evidence",
    "write_checkpoint",
]
