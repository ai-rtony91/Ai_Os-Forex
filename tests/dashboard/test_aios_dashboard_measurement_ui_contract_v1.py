from pathlib import Path

def test_measurement_console_has_four_controls_and_safe_hook():
    root=Path(__file__).parents[2]/'apps/dashboard/src'; console=(root/'components/aios_measurement/MeasurementConsole.jsx').read_text(encoding='utf-8'); hook=(root/'hooks/useAiosDashboardProjection.js').read_text(encoding='utf-8')
    assert all(label in console for label in ('Completion','Verified P&L','Health','Receipts'))
    assert 'AbortController' in hook and '30000' in hook and 'visibilitychange' in hook

def test_evidence_conservative_labels():
    root=Path(__file__).parents[2]/'apps/dashboard/src/components/aios_measurement'
    assert 'OVERALL NOT YET MEASURABLE' in (root/'CompletionForecastPanel.jsx').read_text(encoding='utf-8')
    assert 'NOT VERIFIED - 0 qualifying closed records' in (root/'VerifiedPnlProgressChart.jsx').read_text(encoding='utf-8')
