from pathlib import Path

def test_projection_server_is_read_only_and_etag_enabled():
    source=(Path(__file__).parents[2]/'apps/dashboard/server.js').read_text()
    assert '/aios-dashboard-projection' in source and "createHash('sha256')" in source
    assert 'run_once' not in source and '250 * 1024' in source
