import { useEffect, useRef, useState } from 'react'
import './LoginScene.css'

const MOTION_KEY = 'AIOS_LOGIN_BACKGROUND_PAUSED'

/** Presentation only: this component never reads or changes login state. */
export default function LoginScene({ poster, src = '/aios-login-scene/AIOS-Portal-3D.mp4' }) {
  const video = useRef(null)
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [paused, setPaused] = useState(() => {
    try { return window.localStorage.getItem(MOTION_KEY) === 'true' } catch { return false }
  })
  const [hidden, setHidden] = useState(() => document.hidden)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onMotion = () => setReducedMotion(media.matches)
    const onVisibility = () => setHidden(document.hidden)
    media.addEventListener('change', onMotion)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      media.removeEventListener('change', onMotion)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  useEffect(() => {
    const element = video.current
    if (!element) return
    if (paused || hidden || reducedMotion || failed) element.pause()
    else if (ready) element.play().catch(() => setFailed(true))
  }, [paused, hidden, reducedMotion, failed, ready])

  function toggleMotion() {
    const next = !paused
    setPaused(next)
    try { window.localStorage.setItem(MOTION_KEY, String(next)) } catch { /* In-memory preference still works. */ }
  }

  return <>
    {!reducedMotion && !failed && <video
      ref={video}
      className={`loginSceneVideo${ready ? ' isReady' : ''}`}
      src={src}
      poster={poster}
      muted
      loop
      playsInline
      preload="metadata"
      aria-hidden="true"
      onCanPlay={() => setReady(true)}
      onError={() => { setFailed(true); setReady(false) }}
    />}
    {!reducedMotion && !failed && ready && <button className="loginMotionControl" type="button" onClick={toggleMotion} aria-pressed={paused}>
      <span aria-hidden="true">{paused ? '▶' : 'Ⅱ'}</span> {paused ? 'Play background' : 'Pause background'}
    </button>}
  </>
}
