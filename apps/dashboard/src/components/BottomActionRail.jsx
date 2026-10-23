const ACTIONS = [
  ['🚀', 'Start', null, 'No approved runtime start action exists.'],
  ['⏹', 'Stop', null, 'No approved runtime stop action exists.'],
  ['⟳', 'Restart', null, 'No approved runtime restart action exists.'],
  ['▤', 'Logs', '/system-status'], ['📊', 'Reports', '/reports'], ['🧠', 'Post-Mortem', '/post-mortem'], ['⚙', 'Settings', '/settings'], ['?', 'Help', 'help'],
]

export default function BottomActionRail({ navigate, onHelp }) {
  return <><nav className="bottomActionRail" aria-label="Safe dashboard actions">{ACTIONS.map(([icon, label, target, reason]) => <button key={label} type="button" disabled={!target} title={reason} onClick={() => target === 'help' ? onHelp() : target && navigate(target)}><i aria-hidden="true">{icon}</i><span>{label}</span>{reason && <small>{reason}</small>}</button>)}</nav><div className="safetyStrip"><span>🛡 EXECUTION OFF</span><b>•</b><span>🔒 BROKER LOCKED</span><b>•</b><span>⊗ NO ORDER CONTROL</span></div></>
}
