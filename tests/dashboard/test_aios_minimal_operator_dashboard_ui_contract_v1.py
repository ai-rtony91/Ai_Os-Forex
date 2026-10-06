from pathlib import Path

def test_rooms_and_console_are_preserved():
    source=(Path(__file__).parents[2]/'apps/dashboard/src/MinimalOperatorDashboard.jsx').read_text(encoding='utf-8')
    assert all(room in source for room in ('Access','Forex Bot','Utilities','Music'))
    assert '<MeasurementConsole />' in source
