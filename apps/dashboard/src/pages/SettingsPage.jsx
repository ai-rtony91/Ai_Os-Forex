import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'
export default function SettingsPage({ settings, updateSetting }) {
  return <section className="milestonePage"><PageHeader eyebrow="LOCAL DISPLAY ONLY" title="Settings" description="These controls change this display. They cannot place orders or change broker settings." />
    <div className="settingsGrid">
      <GlassPanel><label>Refresh interval<select value={settings.refreshInterval} onChange={(event) => updateSetting('refreshInterval', Number(event.target.value))}><option value="15">15 seconds</option><option value="30">30 seconds</option><option value="60">60 seconds</option></select></label></GlassPanel>
      <GlassPanel><label>Time zone<select value={settings.timeZone} onChange={(event) => updateSetting('timeZone', event.target.value)}><option>UTC</option><option>America/New_York</option></select></label></GlassPanel>
      <GlassPanel><label>Default pair<select value={settings.selectedMarketSymbol} onChange={(event) => updateSetting('selectedMarketSymbol', event.target.value)}><option>EUR_USD</option><option>GBP_USD</option><option>USD_JPY</option></select></label></GlassPanel>
      <GlassPanel><label>Default granularity<select value={settings.selectedTimeframe} onChange={(event) => updateSetting('selectedTimeframe', event.target.value)}><option>M1</option><option>M5</option><option>S5</option></select></label></GlassPanel>
      <GlassPanel><label>Table density<select value={settings.tableDensity} onChange={(event) => updateSetting('tableDensity', event.target.value)}><option>compact</option><option>balanced</option><option>comfortable</option></select></label></GlassPanel>
      <GlassPanel><label>Chart display<select value={settings.chartDisplay} onChange={(event) => updateSetting('chartDisplay', event.target.value)}><option>candles</option><option>line</option></select></label></GlassPanel>
      <GlassPanel><label>Notification display<select value={settings.notificationDisplay} onChange={(event) => updateSetting('notificationDisplay', event.target.value)}><option>important</option><option>all</option><option>none</option></select></label></GlassPanel>
      <GlassPanel><label>Text size<input type="range" min="90" max="125" value={settings.textScale} onChange={(event) => updateSetting('textScale', Number(event.target.value))} /><output>{settings.textScale}%</output></label></GlassPanel>
      <GlassPanel><label><input type="checkbox" checked={settings.highContrast} onChange={(event) => updateSetting('highContrast', event.target.checked)} /> High contrast</label></GlassPanel>
    </div>
    <GlassPanel family="critical"><strong>NO CREDENTIALS · NO BROKER SETTINGS · NO MONEY MOVEMENT</strong></GlassPanel>
  </section>
}
