const INTENTS = [
  ['Open EUR/USD', '/markets'], ['Show open trades', '/trades'], ['Show broker status', '/broker'], ['Show maintenance', '/strategy-maintenance'],
  ['Explain a visible metric', '/overview'], ['Open Supertrend research', '/markets'], ['Show rejected signals', '/trades'], ['Open About AIOS', '/about'],
]
export default function AiosAssistantDrawer({ open, onClose, navigate }) {
  if (!open) return null
  return <aside className="utilityDrawer assistantDrawer" aria-label="AIOS Assistant"><header><div><small>LOCAL GUIDANCE MODE</small><h2>AIOS Assistant</h2></div><button type="button" onClick={onClose} aria-label="Close assistant">×</button></header>
    <p>Navigation and on-screen evidence explanations only. No model inference, trade authorization, or live analysis.</p>
    <div className="intentGrid">{INTENTS.map(([label, path]) => <button type="button" key={label} onClick={() => { navigate(path); onClose() }}>{label}</button>)}</div>
  </aside>
}
