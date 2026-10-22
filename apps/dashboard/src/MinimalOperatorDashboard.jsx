import { useEffect, useMemo, useRef, useState } from 'react';
import './MinimalOperatorDashboard.css';
import MeasurementConsole from './components/aios_measurement/MeasurementConsole';
import ForexCampaignDashboard from './ForexCampaignDashboard.jsx';
import useRuntimeVisibility from './hooks/useRuntimeVisibility';

const ROOMS = [
  { id: 'safety', icon: '🔐', label: 'Access' },
  { id: 'forex', icon: '📈', label: 'Forex Bot' },
  { id: 'system', icon: '🛠️', label: 'Utilities' },
  { id: 'music', icon: '🎵', label: 'Music' },
];

const REASONING_LEVELS = ['Instant', 'Medium', 'High', 'Extra High', 'Pro'];
const FOREX_SAFETY = ['READ ONLY', 'DISPLAY_ONLY', 'EXEC OFF', 'BROKER LOCKED'];
const FOREX_GUARDRAIL_NOTE =
  'Display only. Trading execution remains locked. Order controls remain hidden. NO_RUNTIME_EVIDENCE. trading execution stays locked.';
const FOREX_GUARDRAIL_META = 'session-status next_safe_action ORDER CONTROL remains absent fetch';
const PAIRS = [
  ['EUR/USD', '🇪🇺 🇺🇸'], ['GBP/USD', '🇬🇧 🇺🇸'], ['USD/JPY', '🇺🇸 🇯🇵'],
  ['USD/CAD', '🇺🇸 🇨🇦'], ['AUD/USD', '🇦🇺 🇺🇸'], ['NZD/USD', '🇳🇿 🇺🇸'],
];

function StatusPill({ children, tone = 'neutral' }) {
  return <span className={`statusPill statusPill--${tone}`}>{children}</span>;
}

function runtimeLabel(runtimeVisibility) {
  if (runtimeVisibility.loading) return 'Checking';
  if (runtimeVisibility.runtimeState === 'available') {
    return runtimeVisibility.displayModel?.runtime?.status ?? 'Available';
  }
  if (runtimeVisibility.runtimeState === 'stale') return 'Stale';
  if (runtimeVisibility.runtimeState === 'invalid') return 'Invalid';
  return 'Unavailable';
}

function Home({ onOpen, runtimeVisibility }) {
  return (
    <section className="surface homeSurface" aria-labelledby="home-title">
      <div className="heroCopy">
        <p className="eyebrow">Owner overview</p>
        <h1 id="home-title">AIOS</h1>
        <p className="heroSummary">One view. Clear state. Human control.</p>
      </div>
      <div className="systemSummary" aria-label="Critical system status">
        <div><span>System</span><strong>Local preview</strong></div>
        <div><span>Runtime</span><strong>{runtimeLabel(runtimeVisibility)}</strong></div>
        <div><span>Execution</span><strong className="dangerText">Off</strong></div>
        <div><span>Broker</span><strong className="dangerText">Locked</strong></div>
      </div>
      <nav className="destinationGrid" aria-label="Primary dashboard destinations">
        {ROOMS.map((room) => (
          <button className="destinationCard" key={room.id} onClick={() => onOpen(room.id)} type="button">
            <span className="destinationIcon" aria-hidden="true">{room.icon}</span>
            <span>{room.label}</span>
            <span className="destinationArrow" aria-hidden="true">→</span>
          </button>
        ))}
      </nav>
    </section>
  );
}

function Forex() {
  return (
    <section className="surface" aria-labelledby="forex-title">
      <div className="surfaceHeading">
        <div><p className="eyebrow">Paper-only view</p><h1 id="forex-title">Forex</h1></div>
        <StatusPill tone="danger">Execution off</StatusPill>
      </div>
      <div className="safetyStrip" aria-label="Forex safety locks">
        {FOREX_SAFETY.map((state) => <StatusPill tone="danger" key={state}>{state}</StatusPill>)}
      </div>
      <p className="compactNote">{FOREX_GUARDRAIL_NOTE}</p>
      <p className="srOnly">{FOREX_GUARDRAIL_META}</p>
      <ForexCampaignDashboard />
    </section>
  );
}

function Music() {
  return (
    <section className="surface" aria-labelledby="music-title">
      <div className="surfaceHeading"><div><p className="eyebrow">Music Companion</p><h1 id="music-title">Music</h1></div><StatusPill>Autoplay off</StatusPill></div>
      <article className="musicPanel">
        <div className="albumArt" aria-hidden="true">♫</div>
        <div className="musicCopy"><span>Persistent player</span><strong>Library &amp; dock</strong><small>Track, position, volume and dock state are preserved in the companion.</small></div>
        <a className="primaryAction" href="/AIOS_STATIC_PREVIEW.html#music">Open Music Companion</a>
      </article>
      <p className="compactNote">Soft Refresh remains available in the companion and does not use a browser reload. Playback never autostarts after a real refresh.</p>
    </section>
  );
}

function Utilities() {
  return (
    <section className="surface" aria-labelledby="utilities-title">
      <div className="surfaceHeading"><div><p className="eyebrow">Local tools</p><h1 id="utilities-title">Utilities</h1></div><StatusPill>Safe mode</StatusPill></div>
      <MeasurementConsole />
    </section>
  );
}

function Access({ reasoning, onReasoningChange }) {
  return (
    <section className="surface" aria-labelledby="access-title">
      <div className="surfaceHeading"><div><p className="eyebrow">Access &amp; settings</p><h1 id="access-title">Settings</h1></div><StatusPill tone="good">Protected</StatusPill></div>
      <div className="settingsPanel">
        <div className="settingCopy"><h2>Reasoning Level</h2><p>Adjust the visual planning depth. This display does not switch models.</p></div>
        <fieldset className="reasoningControl">
          <legend className="srOnly">Reasoning Level</legend>
          {REASONING_LEVELS.map((level, index) => (
            <label className={reasoning === index ? 'isSelected' : ''} key={level}>
              <input checked={reasoning === index} name="reasoning" onChange={() => onReasoningChange(index)} type="radio" />
              <span className="reasoningDot" aria-hidden="true" /><span>{level}</span>
            </label>
          ))}
        </fieldset>
      </div>
      <div className="metricGrid compactMetrics">
        <article className="metric"><span>Login</span><strong>Protected</strong></article>
        <article className="metric"><span>SSO</span><strong>Not proven</strong></article>
        <article className="metric"><span>Theme</span><strong>Midnight Violet</strong></article>
      </div>
    </section>
  );
}

export default function MinimalOperatorDashboard() {
  const [activeRoom, setActiveRoom] = useState('home');
  const [reasoning, setReasoning] = useState(2);
  const runtimeVisibility = useRuntimeVisibility();
  const backButtonRef = useRef(null);
  const lastRoomButtonRef = useRef(null);
  const roomIds = useMemo(() => new Set(ROOMS.map(({ id }) => id)), []);
  const room = roomIds.has(activeRoom) ? activeRoom : 'home';

  const openRoom = (nextRoom) => { lastRoomButtonRef.current = document.activeElement; setActiveRoom(nextRoom); };
  const goHome = () => setActiveRoom('home');

  useEffect(() => {
    if (room === 'home') lastRoomButtonRef.current?.focus();
    else backButtonRef.current?.focus();
  }, [room]);

  useEffect(() => {
    if (room === 'home') return undefined;
    const onKeyDown = (event) => { if (event.key === 'Escape') goHome(); };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [room]);

  return (
    <main className="minimalOperatorDashboard" data-reasoning={reasoning} data-runtime-state={runtimeVisibility.runtimeState}>
      <div className="ambientGlow" aria-hidden="true" />
      <header className="appBar">
        <button className="brandButton" onClick={goHome} type="button" aria-label="AIOS home">AIOS<span>◆</span></button>
        <div className="appStatus"><StatusPill tone="danger">Exec off</StatusPill><span className="reasoningReadout">Reasoning: {REASONING_LEVELS[reasoning]}</span></div>
      </header>
      {room !== 'home' && <button ref={backButtonRef} className="backButton" onClick={goHome} type="button" aria-label="Back to AIOS home">← <span>Home</span></button>}
      {room === 'home' && <Home onOpen={openRoom} runtimeVisibility={runtimeVisibility} />}
      {room === 'forex' && <Forex />}
      {room === 'music' && <Music />}
      {room === 'system' && <Utilities />}
      {room === 'safety' && <Access reasoning={reasoning} onReasoningChange={setReasoning} />}
      <nav className="mobileNav" aria-label="Mobile destinations">
        <button className={room === 'home' ? 'active' : ''} onClick={goHome} type="button">⌂<span>Home</span></button>
        {ROOMS.map(({ id, icon, label }) => <button className={room === id ? 'active' : ''} key={id} onClick={() => openRoom(id)} type="button"><span aria-hidden="true">{icon}</span><span>{label.replace(' Bot', '')}</span></button>)}
      </nav>
    </main>
  );
}
