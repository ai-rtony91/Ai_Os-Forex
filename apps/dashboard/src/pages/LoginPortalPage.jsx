import { useEffect, useRef, useState } from 'react'
import { getLoginPresentation, getLoginProviders } from './loginAuthPresentation.js'
import newLoginBackgroundUrl from '../assets/aios-login-background-new.png'
import microsoftSignInUrl from '../assets/microsoft-signin-dark.svg'
import githubMarkUrl from '../assets/github-invertocat-white.svg'

const previewFonts = [
  { id: 'orbitron', name: 'Orbitron', family: "'Orbitron', sans-serif" },
  { id: 'oxanium', name: 'Oxanium', family: "'Oxanium', sans-serif" },
  { id: 'chakrapetch', name: 'Chakra Petch', family: "'Chakra Petch', sans-serif" },
  { id: 'aldrich', name: 'Aldrich', family: "'Aldrich', sans-serif" },
  { id: 'electrolize', name: 'Electrolize', family: "'Electrolize', sans-serif" },
  { id: 'audiowide', name: 'Audiowide', family: "'Audiowide', sans-serif" },
]

const previewFontGroups = [{ label: 'Focused choices', fonts: previewFonts }]

const loginStars = [
  ['tiny', '7%', '14%', '10s', '-3s'], ['tiny', '15%', '31%', '13s', '-8s'], ['tiny', '22%', '10%', '16s', '-12s'],
  ['tiny', '29%', '24%', '12s', '-5s'], ['tiny', '37%', '9%', '15s', '-10s'], ['tiny', '46%', '18%', '11s', '-2s'],
  ['tiny', '54%', '11%', '14s', '-7s'], ['tiny', '63%', '27%', '17s', '-14s'], ['tiny', '72%', '13%', '12s', '-4s'],
  ['tiny', '81%', '30%', '15s', '-9s'], ['tiny', '91%', '17%', '19s', '-16s'], ['tiny', '5%', '54%', '14s', '-6s'],
  ['tiny', '18%', '68%', '18s', '-11s'], ['tiny', '31%', '58%', '13s', '-1s'], ['tiny', '69%', '63%', '16s', '-13s'],
  ['tiny', '86%', '56%', '11s', '-5s'], ['medium', '12%', '21%', '18s', '-15s'], ['medium', '42%', '29%', '21s', '-9s'],
  ['medium', '78%', '22%', '20s', '-17s'], ['medium', '94%', '42%', '23s', '-12s'], ['focal', '25%', '16%', '26s', '-20s'],
  ['focal', '74%', '18%', '29s', '-24s'], ['focal', '58%', '40%', '31s', '-27s'],
]

function initialPreviewFont() {
  if (!import.meta.env.DEV) return 'orbitron'
  try {
    const requested = new URLSearchParams(window.location.search).get('font')
    if (previewFonts.some((font) => font.id === requested)) return requested
    const saved = window.localStorage.getItem('aios-login-preview-font')
    return previewFonts.some((font) => font.id === saved) ? saved : 'orbitron'
  } catch {
    return 'orbitron'
  }
}

if (import.meta.env.DEV) import('../app/loginPreviewFonts.css')

function loadTurnstile(onToken) {
  window.aiosTurnstileComplete = onToken
  if (document.querySelector('script[data-aios-turnstile]')) return
  const script = document.createElement('script')
  script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=aiosTurnstileReady'
  script.async = true
  script.defer = true
  script.dataset.aiosTurnstile = 'true'
  document.head.appendChild(script)
}

export default function LoginPortalPage({ navigate }) {
  const [authState, setAuthState] = useState({ phase: 'checking', authenticated: false })
  const [previewFont, setPreviewFont] = useState(initialPreviewFont)
  const [redirecting, setRedirecting] = useState(false)
  const turnstileHost = useRef(null)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/auth/session', { credentials: 'same-origin', signal: controller.signal })
      .then(async (response) => ({ ok: response.ok, body: await response.json() }))
      .then(({ ok, body }) => {
        if (ok && body?.authenticated === true) {
          navigate('/overview', { replace: true })
          return
        }
        setAuthState(ok && body && typeof body === 'object' ? body : { phase: 'error', code: body?.code, authenticated: false })
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setAuthState({ phase: 'error', authenticated: false })
      })
    return () => controller.abort()
  }, [navigate])

  useEffect(() => {
    if (authState.phase !== 'turnstile_required' || !authState.turnstileSiteKey || !turnstileHost.current) return undefined
    let cancelled = false
    let widgetId
    const complete = async (token) => {
      if (cancelled) return
      try {
        const response = await fetch('/auth/turnstile', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'content-type': 'application/json', 'x-aios-csrf': authState.csrfToken },
          body: JSON.stringify({ token }),
        })
        const result = await response.json()
        if (cancelled) return
        if (response.ok && result?.authenticated === true) navigate('/overview', { replace: true })
        else setAuthState((current) => ({ ...current, phase: 'turnstile_error', authenticated: false }))
      } catch {
        if (!cancelled) setAuthState((current) => ({ ...current, phase: 'turnstile_error', authenticated: false }))
      }
    }
    window.aiosTurnstileReady = () => {
      if (!cancelled && widgetId === undefined && window.turnstile && turnstileHost.current) {
        widgetId = window.turnstile.render(turnstileHost.current, { sitekey: authState.turnstileSiteKey, callback: complete })
      }
    }
    loadTurnstile(complete)
    if (window.turnstile) window.aiosTurnstileReady()
    return () => {
      cancelled = true
      if (widgetId !== undefined) window.turnstile?.remove(widgetId)
    }
  }, [authState, navigate])

  const begin = (provider) => {
    if (!provider.enabled || redirecting) return
    setRedirecting(true)
    window.location.assign(provider.href)
  }
  const { available, tone: messageTone, message } = getLoginPresentation(authState)
  const providers = getLoginProviders(authState)
  const selectedFont = import.meta.env.DEV ? (previewFonts.find((font) => font.id === previewFont) || previewFonts[0]) : previewFonts[0]
  const changePreviewFont = (event) => {
    const next = event.target.value
    setPreviewFont(next)
    try { window.localStorage.setItem('aios-login-preview-font', next) } catch {}
  }
  const resetPreviewFont = () => {
    setPreviewFont('orbitron')
    try { window.localStorage.setItem('aios-login-preview-font', 'orbitron') } catch {}
  }
  const movePreviewFont = (offset) => {
    const currentIndex = previewFonts.findIndex((font) => font.id === previewFont)
    const next = previewFonts[(currentIndex + offset + previewFonts.length) % previewFonts.length]
    setPreviewFont(next.id)
    try { window.localStorage.setItem('aios-login-preview-font', next.id) } catch {}
  }
  return <main className="loginPortal" style={{ '--login-preview-font': selectedFont.family }}><img className="loginArtwork" src={newLoginBackgroundUrl} alt="" aria-hidden="true" /><div className="loginStars" aria-hidden="true">{loginStars.map(([kind, left, top, duration, delay], index) => <i className={`loginStar loginStar-${kind}`} key={`${kind}-${index}`} style={{ left, top, '--star-duration': duration, '--star-delay': delay }} />)}</div><section className="identityGate" aria-labelledby="auth-title">
    <div className="identityCopy"><h1 id="auth-title" tabIndex="-1"><span className="loginHeadingLead">Sign in to</span><span className="loginHeadingMark">AIOS</span></h1><span>Continue with your approved account.</span></div>
    <div className="providerStack" aria-label="Secure authentication">
      {authState.phase === 'turnstile_required' ? <div className="turnstilePanel"><strong>Complete verification</strong><span>Confirm you are human to finish sign-in.</span><div ref={turnstileHost} /></div> : providers.map((provider) => <div className="providerOption" key={provider.id}>
        <button className={`providerAction providerAction-${provider.id}`} type="button" onClick={() => begin(provider)} disabled={!provider.enabled || redirecting} aria-label={provider.label} aria-describedby={`auth-status${provider.id === 'github' && available && !provider.enabled ? ' github-unavailable' : ''}`}>
          {provider.id === 'microsoft' ? <img className="microsoftSignIn" src={microsoftSignInUrl} alt="" aria-hidden="true" /> : <><img className="githubMark" src={githubMarkUrl} alt="" aria-hidden="true" /><span>{provider.label}</span></>}
        </button>
        {provider.id === 'github' && available && !provider.enabled && <span id="github-unavailable" className="providerAvailability">GitHub sign-in is not available yet.</span>}
      </div>)}
      <p id="auth-status" className={`authStatus authStatus-${messageTone}`} role="status" aria-live="polite">{redirecting ? 'Opening secure sign-in…' : message}</p>
    </div>
  </section>{import.meta.env.DEV && <div className="devFontPicker" aria-label="Development login preview controls"><label htmlFor="dev-preview-font">Preview font</label><button type="button" onClick={() => movePreviewFont(-1)} aria-label="Previous preview font">Previous</button><select id="dev-preview-font" value={previewFont} onChange={changePreviewFont}>{previewFontGroups.map((group) => <optgroup key={group.label} label={group.label}>{group.fonts.map((font) => <option key={font.id} value={font.id} style={{ fontFamily: font.family }}>{font.name}</option>)}</optgroup>)}</select><button type="button" onClick={() => movePreviewFont(1)} aria-label="Next preview font">Next</button><button type="button" onClick={resetPreviewFont}>Reset to Orbitron</button></div>}<footer>AIOS · Access is limited to approved owners · Access fails closed</footer></main>
}
