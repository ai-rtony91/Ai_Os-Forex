const assert = require('node:assert/strict');
const http = require('node:http');
const net = require('node:net');
const childProcess = require('node:child_process');
const { createRequire } = require('node:module');
const { once } = require('node:events');
const test = require('node:test');

// Resolve the exact dependencies installed for this service, not a root copy.
const serviceRequire = createRequire(require.resolve('../../services/orchestrator/package.json'));
const express = serviceRequire('express');
const qs = serviceRequire('qs');
const proxyaddr = serviceRequire('proxy-addr');

test('orchestrator HTTP routes stay display-only with the installed Express', async (t) => {
  // Node runs this file in its own test process. Never inherit broker settings.
  for (const name of ['AIOS_FOREX_READONLY_LIVE_ENABLE', 'AIOS_FOREX_BROKER',
    'OANDA_API_TOKEN', 'OANDA_ACCOUNT_ID']) delete process.env[name];

  let processCalls = 0;
  for (const name of ['exec', 'execSync', 'execFile', 'execFileSync', 'spawn', 'spawnSync', 'fork']) {
    t.mock.method(childProcess, name, () => {
      processCalls += 1;
      throw new Error('Child processes are forbidden in this offline test');
    });
  }

  const app = express();
  app.use(require('../../services/orchestrator'));
  const server = app.listen(0, '127.0.0.1');
  t.after(() => new Promise((resolve, reject) => {
    server.closeAllConnections();
    server.close((error) => error ? reject(error) : resolve());
  }));
  await once(server, 'listening');
  const port = server.address().port;

  // Permit only this test's loopback listener, including indirect socket calls.
  const connect = net.Socket.prototype.connect;
  t.mock.method(net.Socket.prototype, 'connect', function (...args) {
    const options = Array.isArray(args[0]) ? args[0][0] : args[0];
    assert.equal(options.host, '127.0.0.1', 'external connections are forbidden');
    assert.equal(Number(options.port), port, 'only the test server is allowed');
    return connect.apply(this, args);
  });

  async function request(path, method = 'GET', headers = {}) {
    const result = await new Promise((resolve, reject) => {
      const req = http.request({ host: '127.0.0.1', port, path, method, headers, agent: false }, (res) => {
        let body = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => { body += chunk; });
        res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body }));
        res.on('error', reject);
      });
      req.setTimeout(2000, () => req.destroy(new Error('test request timed out')));
      req.on('error', reject);
      req.end();
    });
    assert.equal(processCalls, 0, 'no Python bridge or other child process may run');
    return result;
  }

  function assertPaperSafety(model) {
    assert.equal(model.paper_only, true);
    assert.equal(model.mode, 'PAPER_ONLY');
    for (const key of ['broker', 'live_trading', 'credentials', 'real_orders', 'network_access']) {
      assert.equal(model.safety[key], false, key);
    }
  }

  await t.test('health returns JSON with PAPER-only safety flags', async () => {
    const res = await request('/health');
    assert.equal(res.status, 200);
    assert.match(res.headers['content-type'], /^application\/json/);
    assertPaperSafety(JSON.parse(res.body));
  });

  await t.test('HEAD health has no response body', async () => {
    const res = await request('/health', 'HEAD');
    assert.equal(res.status, 200);
    assert.equal(res.body, '');
  });

  for (const key of ['sessionId', 'session_id']) {
    await t.test(`session status preserves the ${key} query alias and missing-evidence block`, async () => {
      const res = await request(`/api/forex/session-status?${key}=offline%20fixture`);
      assert.equal(res.status, 200);
      const model = JSON.parse(res.body);
      assert.equal(model.session_id, 'offline fixture');
      assert.equal(model.allowed, false);
      assert.equal(model.display_state, 'NO_RUNTIME_EVIDENCE');
      assert.equal(model.open_trades, 0);
      assert.equal(model.closed_trades, 0);
      assertPaperSafety(model);
    });
  }

  await t.test('query flags cannot enable trading or manufacture replay evidence', async () => {
    const res = await request('/api/forex/session-status?allowed=true&paper_only=false&live_trading=true&evidence[allowed]=true&__proto__[polluted]=yes');
    const model = JSON.parse(res.body);
    assert.equal(res.status, 200);
    assert.equal(model.allowed, false);
    assert.equal(model.display_state, 'NO_RUNTIME_EVIDENCE');
    assert.equal({}.polluted, undefined);
    assertPaperSafety(model);
  });

  await t.test('replay route keeps missing runtime evidence blocked', async () => {
    const res = await request('/api/forex/replay-status?sessionId=offline');
    assert.equal(res.status, 200);
    const model = JSON.parse(res.body);
    assert.equal(model.replay_status.allowed, false);
    assert.ok(model.replay_status.blocked_reasons.includes('NO_RUNTIME_EVIDENCE'));
    assert.equal(model.proof_closure.display_only, true);
    assertPaperSafety(model);
    assertPaperSafety(model.proof_closure);
  });

  await t.test('legacy status remains a display-only projection', async () => {
    const res = await request('/forex/status?session_id=offline');
    assert.equal(res.status, 200);
    const model = JSON.parse(res.body);
    assert.equal(model.status, 'display_only');
    assert.equal(model.proof_closure.status, 'NO_RUNTIME_EVIDENCE');
    assertPaperSafety(model);
  });

  await t.test('money strip blocks disabled, wrong-broker and missing-credential requests', async () => {
    for (const [enabled, broker] of [['0', 'oanda'], ['1', 'unsupported'], ['1', 'oanda']]) {
      process.env.AIOS_FOREX_READONLY_LIVE_ENABLE = enabled;
      process.env.AIOS_FOREX_BROKER = broker;
      const res = await request('/api/forex/oanda/money-strip');
      assert.equal(res.status, 200);
      const model = JSON.parse(res.body);
      assert.equal(model.status, 'BLOCKED');
      for (const key of ['live_order_allowed', 'order_placement_allowed', 'execution_allowed']) {
        assert.equal(model[key], false, key);
      }
      assert.equal(model.safety.network_access, false);
      assert.equal(model.safety.no_write, true);
      assert.equal(model.safety.credentials, false);
    }
    delete process.env.AIOS_FOREX_READONLY_LIVE_ENABLE;
    delete process.env.AIOS_FOREX_BROKER;
  });

  await t.test('write methods are not exposed by any service route', async () => {
    for (const path of ['/health', '/api/forex/session-status', '/api/forex/replay-status',
      '/api/forex/oanda/money-strip', '/forex/status']) {
      for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
        assert.equal((await request(path, method)).status, 404, `${method} ${path}`);
      }
    }
    assert.equal((await request('/api/forex/orders', 'POST')).status, 404);
  });
});

test('qs rejects comma-array overflow for both plain and bracket keys', () => {
  const options = { comma: true, arrayLimit: 3, throwOnLimitExceeded: true };
  for (const input of ['a=1,2,3,4', 'a[]=1,2,3,4']) {
    assert.throws(() => qs.parse(input, options), RangeError, input);
  }
  assert.deepEqual(qs.parse('a=1,2,3', options), { a: ['1', '2', '3'] });
});

test('qs stringify does not call attacker-controlled constructor.isBuffer', () => {
  const parsed = qs.parse('a[constructor][isBuffer]=not-callable', { plainObjects: true });
  assert.doesNotThrow(() => qs.stringify(parsed));
  assert.match(qs.stringify(parsed), /isBuffer/);
});

test('proxy trust does not accept unrelated IPv4 peers for an IPv6 short prefix', () => {
  for (const subnet of ['::ffff:10.0.0.0/8', '::/1']) {
    const trust = proxyaddr.compile(subnet);
    assert.equal(trust('203.0.113.10'), false, subnet);
  }
  const valid = proxyaddr.compile('::ffff:10.0.0.0/104');
  assert.equal(valid('10.1.2.3'), true);
  assert.equal(valid('203.0.113.10'), false);
});
