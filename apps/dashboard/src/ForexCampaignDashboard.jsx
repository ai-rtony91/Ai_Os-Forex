import { useEffect, useMemo, useState } from 'react';

const API_URL = '/api/forex/paper-campaign';
const REFRESH_MS = 3000;
const FALLBACK = '—';

function safeText(value, fallback = FALLBACK) {
  return value === null || value === undefined || value === '' ? fallback : String(value);
}

function formatPercent(value) {
  return typeof value === 'number' ? `${value.toFixed(1)}%` : FALLBACK;
}

function formatNumber(value, digits = 3) {
  return typeof value === 'number' ? value.toFixed(digits) : FALLBACK;
}

function formatTradeValue(value) {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(5).replace(/0+$/, '').replace(/\.$/, '');
  return String(value);
}

function StatusPill({ children, tone = 'neutral' }) {
  return <span className={`statusPill statusPill--${tone}`}>{children}</span>;
}

function MetricCard({ label, value, note }) {
  return <article className="metricCard"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function StatRow({ label, value, tone = 'neutral' }) {
  return <div className="statRow"><span>{label}</span><strong className={tone === 'danger' ? 'dangerText' : ''}>{value}</strong></div>;
}

function MiniSparkline({ values, tone = 'var(--aios-cyan)' }) {
  const points = useMemo(() => {
    const filtered = (Array.isArray(values) ? values : []).filter((value) => typeof value === 'number' && Number.isFinite(value));
    if (filtered.length < 2) return '';
    const min = Math.min(...filtered);
    const max = Math.max(...filtered);
    const range = max - min || 1;
    return filtered.map((value, index) => {
      const x = (index / (filtered.length - 1)) * 100;
      const y = 100 - (((value - min) / range) * 100);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ');
  }, [values]);
  if (!points) return <div className="chartEmpty">No chartable evidence yet.</div>;
  return (
    <svg className="sparkline" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={points} fill="none" stroke={tone} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function Gauge({ value, max = 30 }) {
  const ratio = Math.min(1, Math.max(0, (value || 0) / max));
  return <div className="progressBar" aria-hidden="true"><span style={{ width: `${Math.max(ratio * 100, 0)}%` }} /></div>;
}

export default function ForexCampaignDashboard() {
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    let timer = null;

    async function loadSnapshot() {
      try {
        const response = await fetch(API_URL, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP_${response.status}`);
        const next = await response.json();
        if (active) {
          setSnapshot(next);
          setError(null);
        }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : 'FETCH_FAILED');
      } finally {
        if (active) timer = window.setTimeout(loadSnapshot, REFRESH_MS);
      }
    }

    loadSnapshot();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  if (error && !snapshot) {
    return (
      <section className="surface forexCampaignError">
        <p className="eyebrow">AIOS FOREX</p>
        <h2>Campaign dashboard unavailable</h2>
        <p>Read-only campaign snapshot could not be loaded from the local API.</p>
        <p className="mutedMono">Error: {error}</p>
      </section>
    );
  }

  const campaign = snapshot?.campaignState || {};
  const summary = snapshot?.summary || {};
  const active = snapshot?.activeTrade || {};
  const signal = snapshot?.signal || {};
  const integrity = snapshot?.integrity || {};
  const readiness = snapshot?.readiness || {};
  const safety = snapshot?.safety || {};
  const progression = snapshot?.progression || [];
  const chartSeries = {
    pl: progression.map((row) => (typeof row.cumulativePl === 'number' ? row.cumulativePl : null)).filter((value) => value !== null),
    r: progression.map((row) => (typeof row.cumulativeR === 'number' ? row.cumulativeR : null)).filter((value) => value !== null),
    realized: progression.map((row) => (typeof row.realizedR === 'number' ? row.realizedR : null)).filter((value) => value !== null),
  };
  const statusTone = campaign?.campaign_status === 'COMPLETE' ? 'good' : campaign?.campaign_status === 'BLOCKED' ? 'danger' : 'neutral';

  return (
    <section className="forexCampaignDashboard" aria-label="AIOS Forex campaign dashboard">
      <header className="topHeader">
        <div>
          <p className="eyebrow">AIOS FOREX</p>
          <h1>30 TRADE PAPER CAMPAIGN</h1>
          <p className="subtitle">Local, read-only, persisted evidence only.</p>
        </div>
        <div className="headerStatus">
          <StatusPill tone={statusTone}>{safeText(campaign?.campaign_status)}</StatusPill>
          <div className="progressCopy">
            <strong>{summary.accepted ?? 0} / {summary.target ?? 30}</strong>
            <span>{formatPercent(summary.progressPercent)}</span>
            <span>{summary.remaining ?? 0} REMAINING</span>
          </div>
        </div>
      </header>

      <section className="progressPanel">
        <Gauge value={summary.accepted ?? 0} max={summary.target ?? 30} />
      </section>

      <section className="kpiGrid" aria-label="Campaign KPIs">
        <MetricCard label="QUALIFYING TRADES" value={`${summary.accepted ?? 0} / ${summary.target ?? 30}`} note="Canonical PAPER evidence only" />
        <MetricCard label="NET PAPER P/L" value={formatNumber(summary.netPl)} note="Persisted campaign state" />
        <MetricCard label="EXPECTANCY" value={formatNumber(summary.expectancy)} note="Per qualifying trade" />
        <MetricCard label="PROFIT FACTOR" value={safeText(summary.profitFactor)} note="Trade set aggregate" />
        <MetricCard label="WIN RATE" value={summary.winRate == null ? FALLBACK : formatPercent(summary.winRate)} note="Derived from state" />
        <MetricCard label="MAX DRAWDOWN" value={formatNumber(summary.maxDrawdown)} note="PAPER only" />
        <MetricCard label="AVERAGE R" value={formatNumber(summary.averageR)} note="Realized R average" />
        <MetricCard label="TOTAL R" value={formatNumber(summary.totalR)} note="Realized R total" />
      </section>

      <section className="twoCol">
        <article className="panel activeTradePanel">
          <div className="panelHead">
            <div>
              <p className="eyebrow">ACTIVE TRADE</p>
              <h2>{safeText(active.positionStatus, 'UNKNOWN')}</h2>
            </div>
            <StatusPill tone="danger">BROKER LOCKED</StatusPill>
          </div>
          <div className="activeTradeGrid">
            <StatRow label="Instrument" value={safeText(active.instrument, 'EUR/USD')} />
            <StatRow label="Direction" value={safeText(active.direction)} />
            <StatRow label="Entry" value={formatTradeValue(active.entry)} />
            <StatRow label="Current Price" value={formatTradeValue(active.currentPrice)} />
            <StatRow label="Stop" value={formatTradeValue(active.stop)} />
            <StatRow label="Target" value={formatTradeValue(active.target)} />
            <StatRow label="Units" value={safeText(active.units)} />
            <StatRow label="Planned R:R" value={formatTradeValue(active.plannedRr)} />
            <StatRow label="Current / Realized R" value={`${formatTradeValue(active.currentR)} / ${formatTradeValue(active.realizedR)}`} />
            <StatRow label="Unrealized PAPER P/L" value={formatTradeValue(active.unrealizedPl)} />
            <StatRow label="MFE R" value={formatTradeValue(active.mfeR)} />
            <StatRow label="MAE R" value={formatTradeValue(active.maeR)} />
            <StatRow label="Hold Time" value={safeText(active.holdTime)} />
            <StatRow label="Entry Time UTC" value={safeText(active.entryTimeUtc)} />
            <StatRow label="Entry Time New York" value={safeText(active.entryTimeNy)} />
          </div>
        </article>

        <article className="panel strategyPanel">
          <div className="panelHead">
            <div>
              <p className="eyebrow">STRATEGY / SIGNAL</p>
              <h2>{safeText(summary.strategy)}</h2>
            </div>
            <StatusPill tone="neutral">NON-QUALIFYING ANALYSIS</StatusPill>
          </div>
          <div className="stackedStats">
            <StatRow label="Current Signal" value={safeText(signal.currentSignal)} />
            <StatRow label="Supertrend Direction" value={safeText(signal.supertrendDirection)} />
            <StatRow label="ATR Actual / Minimum" value={`${formatTradeValue(signal.atrActual)} / ${formatTradeValue(signal.atrMinimum)}`} />
            <StatRow label="Body Ratio / Minimum" value={`${formatTradeValue(signal.bodyRatio)} / ${formatTradeValue(signal.bodyMinimum)}`} />
            <StatRow label="Spread" value={formatTradeValue(signal.spread)} />
            <StatRow label="Latest Rejection Reason" value={safeText(signal.latestRejectionReason)} />
            <StatRow label="No-signal Reason" value={safeText(signal.noSignalReason)} />
          </div>
          <div className="rejectionList">
            {Object.entries(signal.rejectionCounts || {}).slice(0, 8).map(([key, value]) => (
              <div key={key} className="rejectionItem"><span>{key}</span><strong>{String(value)}</strong></div>
            ))}
          </div>
        </article>
      </section>

      <section className="panel">
        <div className="panelHead">
          <div>
            <p className="eyebrow">30-TRADE PROGRESSION</p>
            <h2>Qualifying trade ledger</h2>
          </div>
          <StatusPill tone="good">READ ONLY</StatusPill>
        </div>
        <div className="tableWrap">
          <table className="tradeTable">
            <thead>
              <tr>
                <th>Trade #</th><th>Trade ID</th><th>Date/Time</th><th>Direction</th><th>Entry</th><th>Stop</th><th>Target</th><th>Planned R:R</th><th>Exit</th><th>Exit Reason</th><th>P/L</th><th>Realized R</th><th>R Classification</th><th>MFE R</th><th>MAE R</th><th>Hold Time</th><th>Cumulative P/L</th><th>Cumulative R</th>
              </tr>
            </thead>
            <tbody>
              {progression.map((row) => (
                <tr key={row.tradeNumber}>
                  <td>{row.tradeNumber}</td>
                  <td>{row.tradeId || ''}</td>
                  <td>{row.dateTime || ''}</td>
                  <td>{row.direction || ''}</td>
                  <td>{formatTradeValue(row.entry)}</td>
                  <td>{formatTradeValue(row.stop)}</td>
                  <td>{formatTradeValue(row.target)}</td>
                  <td>{formatTradeValue(row.plannedRr)}</td>
                  <td>{formatTradeValue(row.exit)}</td>
                  <td>{row.exitReason || ''}</td>
                  <td>{formatTradeValue(row.pl)}</td>
                  <td>{formatTradeValue(row.realizedR)}</td>
                  <td>{row.rClassification}</td>
                  <td>{formatTradeValue(row.mfeR)}</td>
                  <td>{formatTradeValue(row.maeR)}</td>
                  <td>{row.holdTime || ''}</td>
                  <td>{formatTradeValue(row.cumulativePl)}</td>
                  <td>{formatTradeValue(row.cumulativeR)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="summaryGrid">
        <MetricCard label="Positive-R trades" value={safeText(summary.positiveRTrades, 0)} note="R > 0" />
        <MetricCard label="Negative-R trades" value={safeText(summary.negativeRTrades, 0)} note="R < 0" />
        <MetricCard label="Flat-R trades" value={safeText(summary.flatRTrades, 0)} note="R = 0" />
        <MetricCard label="Best R" value={formatNumber(summary.bestR)} note="Maximum realized R" />
        <MetricCard label="Worst R" value={formatNumber(summary.worstR)} note="Minimum realized R" />
        <MetricCard label="Strategy" value={safeText(summary.strategy)} note="Canonical campaign strategy" />
      </section>

      <section className="chartsGrid">
        <article className="panel chartPanel"><div className="panelHead"><h2>Cumulative PAPER P/L</h2></div><MiniSparkline values={chartSeries.pl} /></article>
        <article className="panel chartPanel"><div className="panelHead"><h2>Cumulative realized R</h2></div><MiniSparkline values={chartSeries.r} tone="var(--aios-violet)" /></article>
        <article className="panel chartPanel"><div className="panelHead"><h2>Realized R per trade</h2></div><MiniSparkline values={chartSeries.realized} tone="var(--aios-pink)" /></article>
        <article className="panel chartPanel"><div className="panelHead"><h2>Win / loss distribution</h2></div><MiniSparkline values={[summary.positiveRTrades || 0, summary.negativeRTrades || 0, summary.flatRTrades || 0]} tone="var(--aios-gold)" /></article>
        <article className="panel chartPanel"><div className="panelHead"><h2>Drawdown progression</h2></div><MiniSparkline values={[summary.maxDrawdown || 0, 0]} tone="var(--aios-danger)" /></article>
      </section>

      <section className="threeCol">
        <article className="panel">
          <div className="panelHead"><h2>Data Quality</h2></div>
          <div className="stackedStats">
            <StatRow label="Data freshness" value={safeText(integrity.dataFreshness)} />
            <StatRow label="History freshness" value={safeText(integrity.historyFreshness)} />
            <StatRow label="Snapshot freshness" value={safeText(integrity.snapshotFreshness)} />
            <StatRow label="Last market data" value={safeText(integrity.lastMarketData)} />
            <StatRow label="Last completed M5" value={safeText(integrity.lastCompletedM5)} />
            <StatRow label="Data unavailable count" value={safeText(integrity.dataUnavailableCount, 0)} />
            <StatRow label="Rejected records" value={safeText(integrity.rejectedRecords, 0)} />
            <StatRow label="Duplicate guard count" value={safeText(integrity.duplicateGuardCount, 0)} />
            <StatRow label="Evidence date range" value={safeText(integrity.evidenceDateRange)} />
            <StatRow label="Evidence freshness" value={safeText(integrity.evidenceFreshness)} />
            <StatRow label="Ledger count" value={safeText(integrity.ledgerCount, 0)} />
            <StatRow label="Canonical main SHA" value={safeText(integrity.canonicalMainSha)} />
          </div>
        </article>

        <article className="panel">
          <div className="panelHead"><h2>Live Readiness</h2></div>
          <div className="stackedStats">
            <StatRow label="30 trade sample" value={safeText(summary.accepted != null && summary.target != null ? `${summary.accepted} / ${summary.target}` : null)} />
            <StatRow label="Expectancy" value={formatNumber(readiness.expectancy)} />
            <StatRow label="Profit factor" value={safeText(readiness.profitFactor)} />
            <StatRow label="Max drawdown" value={formatNumber(readiness.maxDrawdown)} />
            <StatRow label="Consecutive losses" value={safeText(readiness.consecutiveLosses)} />
            <StatRow label="P1 status" value={safeText(readiness.p1Status)} />
            <StatRow label="Sample gate" value={safeText(readiness.sampleStatus)} />
            <StatRow label="Expectancy gate" value={safeText(readiness.expectancyStatus)} />
            <StatRow label="Profit factor gate" value={safeText(readiness.profitFactorStatus)} />
            <StatRow label="Drawdown gate" value={safeText(readiness.drawdownStatus)} />
            <StatRow label="Live authority" value={safeText(readiness.liveAuthority)} tone="danger" />
          </div>
        </article>

        <article className="panel">
          <div className="panelHead"><h2>Safety</h2></div>
          <div className="safetyGrid">
            <StatusPill tone="danger">BROKER WRITES: {safety.brokerWrites}</StatusPill>
            <StatusPill tone="danger">PRACTICE ORDERS: {safety.practiceOrders}</StatusPill>
            <StatusPill tone="danger">LIVE AUTHORITY: {safety.liveAuthority}</StatusPill>
            <StatusPill tone="neutral">KILL SWITCH: {safety.killSwitch}</StatusPill>
            <StatusPill tone="neutral">RISK HALT: {safety.riskHalt}</StatusPill>
            <StatusPill tone="neutral">OWNER CANCEL: {safety.ownerCancel}</StatusPill>
            <StatusPill tone="neutral">SECOND WRITER: {safety.secondWriter}</StatusPill>
            <StatusPill tone="neutral">RUNTIME ROOT MODE: {safety.runtimeRootMode}</StatusPill>
            <StatusPill tone="neutral">LOCK STATUS: {safety.lockStatus}</StatusPill>
          </div>
        </article>
      </section>

      <section className="panel sourcesPanel">
        <div className="panelHead"><h2>Sources</h2></div>
        <div className="sourceList">
          {Object.entries(snapshot?.sources || {}).map(([key, value]) => <div key={key}><span>{key}</span><code>{value}</code></div>)}
        </div>
      </section>
    </section>
  );
}
