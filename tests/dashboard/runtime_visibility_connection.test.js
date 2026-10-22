const assert = require('node:assert/strict');
const path = require('node:path');
const test = require('node:test');
const { pathToFileURL } = require('node:url');

const clientUrl = pathToFileURL(
  path.resolve(__dirname, '../../apps/dashboard/src/runtimeVisibilityClient.js')
).href;

async function loadClient() {
  return import(`${clientUrl}?test=${Date.now()}-${Math.random()}`);
}

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

const basePayload = {
  schema: 'aios.runtime_visibility_api.v1',
  mode: 'READ_ONLY',
  generatedAt: '2026-08-09T00:00:00.000Z',
  frontend_contract: {
    display_state: 'READY',
    freshness: { is_stale: false },
    stale_or_legacy: false,
  },
  runtime: { status: 'READY', heartbeat: { heartbeatAt: '2026-08-09T00:00:00.000Z' } },
  health: { healthy: true, health: 'OK', problems: [] },
  queue: { itemCount: 0, countsByStatus: {} },
  audit: { sourceEventCount: 0, invalidLineCount: 0, recentTimeline: [] },
};

test('runtime visibility client returns available state for a valid read-only payload', async (t) => {
  const originalFetch = global.fetch;
  t.after(() => { global.fetch = originalFetch; });
  global.fetch = async () => jsonResponse(basePayload);

  const { fetchRuntimeVisibilityReadOnly } = await loadClient();
  const result = await fetchRuntimeVisibilityReadOnly({ apiUrl: '/api/runtime/visibility', timeoutMs: 1000 });

  assert.equal(result.runtimeState, 'available');
  assert.equal(result.data.mode, 'READ_ONLY');
  assert.equal(result.error, null);
});

test('runtime visibility client reports stale state deterministically', async (t) => {
  const originalFetch = global.fetch;
  t.after(() => { global.fetch = originalFetch; });
  global.fetch = async () => jsonResponse({
    ...basePayload,
    frontend_contract: {
      ...basePayload.frontend_contract,
      freshness: { is_stale: true },
      stale_or_legacy: true,
    },
  });

  const { fetchRuntimeVisibilityReadOnly } = await loadClient();
  const result = await fetchRuntimeVisibilityReadOnly({ apiUrl: '/api/runtime/visibility', timeoutMs: 1000 });

  assert.equal(result.runtimeState, 'stale');
});

test('runtime visibility client rejects invalid schema as invalid state', async (t) => {
  const originalFetch = global.fetch;
  t.after(() => { global.fetch = originalFetch; });
  global.fetch = async () => jsonResponse({ ...basePayload, schema: 'unexpected.schema' });

  const { fetchRuntimeVisibilityReadOnly, createRuntimeVisibilityErrorState } = await loadClient();

  let error;
  try {
    await fetchRuntimeVisibilityReadOnly({ apiUrl: '/api/runtime/visibility', timeoutMs: 1000 });
  } catch (caught) {
    error = caught;
  }

  const state = createRuntimeVisibilityErrorState(error);
  assert.equal(error.code, 'INVALID_SCHEMA');
  assert.equal(state.runtimeState, 'invalid');
});

test('runtime visibility client maps service unavailable to unavailable state', async (t) => {
  const originalFetch = global.fetch;
  t.after(() => { global.fetch = originalFetch; });
  global.fetch = async () => jsonResponse({ error: 'unavailable' }, 503);

  const { fetchRuntimeVisibilityReadOnly, createRuntimeVisibilityErrorState } = await loadClient();

  let error;
  try {
    await fetchRuntimeVisibilityReadOnly({ apiUrl: '/api/runtime/visibility', timeoutMs: 1000 });
  } catch (caught) {
    error = caught;
  }

  const state = createRuntimeVisibilityErrorState(error);
  assert.equal(error.code, 'API_UNAVAILABLE');
  assert.equal(state.runtimeState, 'unavailable');
});
