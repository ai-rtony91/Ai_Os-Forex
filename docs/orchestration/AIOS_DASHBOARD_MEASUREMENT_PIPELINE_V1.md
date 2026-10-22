# AIOS Dashboard Measurement Pipeline V1

This local-only pipeline runs deterministic acquisition (A) and measurement (B), followed by bounded generated-data reconciliation (C) and publication (D). It reads canonical repository evidence and writes only ignored runtime projections under `.aios/runtime/dashboard_measurement/`.

```bash
python automation/orchestration/aios_dashboard_measurement_pipeline_v1.py run-once
python automation/orchestration/aios_dashboard_measurement_pipeline_v1.py status
python automation/orchestration/aios_dashboard_measurement_pipeline_v1.py verify
```

The dashboard server reads the prepared projection at `GET /aios-dashboard-projection`; HTTP requests never execute the pipeline. Completion dimensions remain independent, overall completion is unavailable until the denominator is proven, and P&L is not verified without qualifying canonical closed-trade evidence.

The pipeline has no broker, credential, order, GitHub network, merge, deployment, scheduler, or source-code mutation authority.
