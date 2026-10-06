import { useRef, useState } from 'react'
import { AIOS_MUSIC_CATALOG } from '../services/musicCatalog.js'

export default function PersistentMusicDock({ settings, updateSetting }) {
  const [expanded, setExpanded] = useState(false)
  const [started, setStarted] = useState(false)
  const drag = useRef(null)
  const track = AIOS_MUSIC_CATALOG[0]
  const position = settings.musicDockPosition ?? { x: 28, y: 28 }
  const move = (event) => {
    if (!drag.current) return
    const x = Math.max(8, Math.min(window.innerWidth - 330, event.clientX - drag.current.x))
    const y = Math.max(8, Math.min(window.innerHeight - 170, window.innerHeight - event.clientY + drag.current.y))
    updateSetting('musicDockPosition', { x, y })
  }
  const moveWithKeyboard = (event) => {
    const step = event.shiftKey ? 24 : 8
    const offsets = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }
    if (!offsets[event.key]) return
    event.preventDefault()
    updateSetting('musicDockPosition', { x: Math.max(8, Math.min(window.innerWidth - 330, position.x + offsets[event.key][0])), y: Math.max(8, Math.min(window.innerHeight - 170, position.y + offsets[event.key][1])) })
  }
  return <section className={`musicDock ${expanded ? 'isExpanded' : ''}`} style={{ right: position.x, bottom: position.y }} aria-label="Persistent music dock" onPointerMove={move} onPointerUp={() => { drag.current = null }}>
    <header tabIndex="0" aria-label="Drag music dock or use arrow keys to move" onKeyDown={moveWithKeyboard} onPointerDown={(event) => { drag.current = { x: event.clientX - position.x, y: position.y - (window.innerHeight - event.clientY) }; event.currentTarget.setPointerCapture(event.pointerId) }}><span><small>MUSIC</small><b>{track.title}</b></span><button type="button" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}>{expanded ? '−' : '+'}</button></header>
    {expanded && <div className="musicBody">
      {started ? <iframe title="AIOS Music Companion on YouTube" src={`https://www.youtube-nocookie.com/embed/${track.id}?autoplay=0&controls=1`} allow="encrypted-media; picture-in-picture" referrerPolicy="strict-origin-when-cross-origin" /> : <button type="button" className="musicStart" onClick={() => setStarted(true)}>Load YouTube player</button>}
      <div className="musicControls"><button type="button" disabled title="Only one approved track is present">Previous</button><button type="button" onClick={() => setStarted((value) => !value)}>{started ? 'Stop player' : 'Play / load'}</button><button type="button" disabled title="Only one approved track is present">Next</button><button type="button" disabled title="Use the official player control">Mute in player</button></div>
      <label>Music volume <input type="range" min="0" max="100" value={settings.musicVolume} onChange={(event) => updateSetting('musicVolume', Number(event.target.value))} /></label>
      <details><summary>Playlist</summary><button type="button" onClick={() => setStarted(true)} aria-current="true">{track.title} · {track.source}</button></details>
      <small>User-initiated official YouTube playback. No audio is downloaded.</small>
    </div>}
  </section>
}
