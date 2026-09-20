import { useState } from 'react'
import AiosAssistantDrawer from '../components/AiosAssistantDrawer.jsx'
import GlobalStatusBar from '../components/GlobalStatusBar.jsx'
import BottomActionRail from '../components/BottomActionRail.jsx'
import NavigationRail from '../components/NavigationRail.jsx'
import NotificationCenter from '../components/NotificationCenter.jsx'
import SettingsCenter from '../components/SettingsCenter.jsx'
import { useLiveDashboard } from '../hooks/useLiveDashboard.js'
import { usePersistentUiSettings } from '../hooks/usePersistentUiSettings.js'
import DecisionsPage from '../pages/DecisionsPage.jsx'
import PositionsPage from '../pages/PositionsPage.jsx'
import PostMortemPage from '../pages/PostMortemPage.jsx'
import ReportsPage from '../pages/ReportsPage.jsx'
import RiskPage from '../pages/RiskPage.jsx'
import SettingsPage from '../pages/SettingsPage.jsx'
import SystemStatusPage from '../pages/SystemStatusPage.jsx'
import TradingOverviewPage from '../pages/TradingOverviewPage.jsx'
import AiosRouter from './AiosRouter.jsx'
import './AiosAppShell.css'

export default function AiosAppShell({ route, navigate }) {
  const { settings, updateSetting } = usePersistentUiSettings()
  const state = useLiveDashboard(45000, settings.refreshInterval * 1000)
  const [utility, setUtility] = useState(null)
  const routes = {
    '/overview': <TradingOverviewPage state={state} navigate={navigate} settings={settings} updateSetting={updateSetting} />,
    '/decisions': <DecisionsPage state={state} />,
    '/positions': <PositionsPage state={state} />,
    '/risk': <RiskPage state={state} settings={settings} />,
    '/reports': <ReportsPage state={state} />,
    '/post-mortem': <PostMortemPage state={state} />,
    '/settings': <SettingsPage settings={settings} updateSetting={updateSetting} />,
    '/system-status': <SystemStatusPage state={state} />,
  }
  const runtimeData = state.envelope?.source === 'runtime'
  return <div className="aiosShell milestoneDashboard" data-density={settings.density} data-motion={settings.motionPreference} data-contrast={settings.highContrast ? 'high' : 'normal'} style={{ '--glass-intensity': settings.glassIntensity / 100, '--text-scale': settings.textScale / 100 }}>
    <NavigationRail route={route} navigate={navigate} collapsed={settings.navigationCollapsed} />
    <div className="shellStage"><div className="shellTopBar"><GlobalStatusBar envelope={state.envelope} connection={state.connection} stale={state.stale} runtimeVisibility={state.runtimeVisibility} />
      <header className="shellToolbar"><div><span className={state.stale || !runtimeData ? 'freshness stale' : 'freshness'}>{state.stale ? 'STALE' : (runtimeData ? state.envelope?.freshness : 'NOT CONNECTED')}</span></div><div className="utilityLaunchers"><button type="button" aria-label="AIOS Assistant" onClick={() => setUtility(utility === 'assistant' ? null : 'assistant')}>✦<span>Assistant</span></button><button type="button" aria-label="Notifications" onClick={() => setUtility(utility === 'notifications' ? null : 'notifications')}>◉<span>Alerts</span></button><button type="button" aria-label="Settings" onClick={() => setUtility(utility === 'settings' ? null : 'settings')}>⚙<span>Settings</span></button><button type="button" aria-label="Exit local preview" onClick={() => navigate('/login')}>↗<span>Exit</span></button><span className="profileSurface" aria-label="Local preview profile"><b>AM</b><span>Anthony<small>LOCAL PREVIEW</small></span></span></div></header></div>
      <main className="pageCanvas"><AiosRouter route={route} routes={routes} fallback={<TradingOverviewPage state={state} navigate={navigate} settings={settings} updateSetting={updateSetting} />} />
        <BottomActionRail navigate={navigate} onHelp={() => setUtility('help')} />
        <footer className="appFooter">© 2026 AIOS. Read-only operator view.</footer></main>
    </div>
    <NotificationCenter open={utility === 'notifications'} onClose={() => setUtility(null)} navigate={navigate} />
    <AiosAssistantDrawer open={utility === 'assistant'} onClose={() => setUtility(null)} navigate={navigate} />
    <SettingsCenter open={utility === 'settings'} onClose={() => setUtility(null)} settings={settings} updateSetting={updateSetting} navigate={navigate} />
    {utility === 'help' && <div className="milestoneDialog" role="dialog" aria-modal="true" aria-label="Milestone Dashboard help"><button type="button" onClick={() => setUtility(null)} aria-label="Close help">×</button><h2>Milestone Dashboard</h2><p>This dashboard shows verified AIOS evidence. Disabled controls cannot start trading or contact a broker.</p></div>}
  </div>
}
