import { useRef, useState } from 'react'

function playTone(volume, error = false) {
  const AudioContext = window.AudioContext || window.webkitAudioContext
  if (!AudioContext) return
  const context = new AudioContext(); const gain = context.createGain(); gain.gain.value = Math.max(0, Math.min(1, volume / 100)) * .06; gain.connect(context.destination)
  ;(error ? [180] : [420, 620]).forEach((frequency, index) => { const oscillator = context.createOscillator(); oscillator.frequency.value = frequency; oscillator.connect(gain); oscillator.start(context.currentTime + index * .1); oscillator.stop(context.currentTime + .12 + index * .1) })
}

export default function SettingsCenter({ open, onClose, settings, updateSetting, navigate }) {
  const dialog = useRef(null)
  const [sensoryMix, setSensoryMix] = useState({ master: 70, signals: 45 })
  if (!open) return null
  return <aside className="utilityDrawer settingsDrawer" ref={dialog} aria-label="Settings center"><header><div><small>SETTINGS CENTER</small><h2>Local preferences</h2></div><button type="button" onClick={onClose} aria-label="Close settings">×</button></header>
    <section><h3>Account & Security</h3><dl className="settingsFacts"><div><dt>Microsoft</dt><dd>CONFIG REQUIRED</dd></div><div><dt>GitHub</dt><dd>PARTIAL</dd></div><div><dt>OpenAI</dt><dd>NOT IMPLEMENTED</dd></div><div><dt>Cloudflare</dt><dd>EXTERNAL CONFIG REQUIRED</dd></div><div><dt>Turnstile</dt><dd>NOT FOUND</dd></div></dl></section>
    <section><h3>Appearance</h3><label>Glass intensity <input type="range" min="20" max="100" value={settings.glassIntensity} onChange={(e) => updateSetting('glassIntensity', Number(e.target.value))} /></label><label>Information density <select value={settings.density} onChange={(e) => updateSetting('density', e.target.value)}><option>balanced</option><option>compact</option><option>relaxed</option></select></label><label>Motion level <select value={settings.motionPreference} onChange={(e) => updateSetting('motionPreference', e.target.value)}><option>system</option><option>reduced</option></select></label></section>
    <section><h3>Sound & Music</h3><label><input type="checkbox" checked={settings.interfaceSoundEnabled} onChange={(e) => { updateSetting('interfaceSoundEnabled', e.target.checked); if (e.target.checked) playTone(settings.interfaceSoundVolume) }} /> Enable interface sound</label><label>Master <input type="range" min="0" max="100" value={sensoryMix.master} onChange={(e) => setSensoryMix((value) => ({ ...value, master: Number(e.target.value) }))} /></label><label>Interface <input type="range" min="0" max="100" value={settings.interfaceSoundVolume} onChange={(e) => updateSetting('interfaceSoundVolume', Number(e.target.value))} /></label><label>Signals <input type="range" min="0" max="100" value={sensoryMix.signals} onChange={(e) => setSensoryMix((value) => ({ ...value, signals: Number(e.target.value) }))} /></label><label>Alerts <input type="range" min="0" max="100" value={settings.alertVolume} onChange={(e) => updateSetting('alertVolume', Number(e.target.value))} /></label><label>Music <input type="range" min="0" max="100" value={settings.musicVolume} onChange={(e) => updateSetting('musicVolume', Number(e.target.value))} /></label><small>Master and Signals are session-only; no sensitive state is persisted.</small></section>
    <section><h3>Trading Configuration</h3><p>Draft-only settings. No execution or LIVE modification.</p></section>
    <section><h3>Risk & Safety</h3><p>Emergency Trading Halt: AVAILABLE — NOT ACTIVE. LIVE remains blocked. Research controls cannot alter risk authority.</p></section>
    <section><h3>Broker & Data</h3><p>Read-only sanitized status. Credentials remain runtime-only and are not accepted here.</p></section>
    <section><h3>Strategy Lab</h3><button type="button" onClick={() => { navigate('/markets'); onClose() }}>Open Markets research drawer</button></section>
    <section><h3>Maintenance</h3><button type="button" onClick={() => { navigate('/strategy-maintenance'); onClose() }}>Open Strategy & Maintenance</button></section>
    <section><h3>Notifications</h3><p>Signals · Risk events · Execution errors · Connectivity · Freshness · Maintenance reviews</p></section>
    <section><h3>Audit & History</h3><p>UNAVAILABLE — no sanitized audit receipts were supplied.</p></section>
  </aside>
}
