import AiosSymbol from '../AiosSymbol.jsx'

const ITEMS = [
  ['/overview', 'Overview', '⌂'], ['/decisions', 'Decisions', '🎯'], ['/positions', 'Positions', '💼'], ['/risk', 'Risk', '🛡'],
  ['/reports', 'Reports', '▤'], ['/post-mortem', 'Post-Mortem', '🧠'], ['/settings', 'Settings', '⚙'], ['/system-status', 'System Status', '⏻'],
]
export default function NavigationRail({ route, navigate, collapsed }) {
  return <nav className={`navigationRail ${collapsed ? 'isCollapsed' : ''}`} aria-label="Primary navigation">
    <div className="railBrand"><AiosSymbol name="aios-core" size="wide" framed={false} /><span>AIOS</span><small>MILESTONE</small></div>
    {ITEMS.map(([path, label, icon]) => <button key={path} type="button" onClick={() => navigate(path)} aria-current={route === path ? 'page' : undefined}><i aria-hidden="true">{icon}</i><span>{label}</span></button>)}
  </nav>
}
