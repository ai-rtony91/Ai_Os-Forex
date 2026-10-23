import { useEffect, useRef, useState } from 'react'
import AiosSymbol from '../AiosSymbol.jsx'
import MarketConstellation from '../components/MarketConstellation.jsx'

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

export default function LoginPortalPage({ navigate, mode = 'login' }) {
  const [authState, setAuthState] = useState({ phase: 'checking', authenticated: false })
  const [message, setMessage] = useState('CHECKING SECURE ACCESS')
  const turnstileHost = useRef(null)
  const isSignup = mode === 'signup'

  useEffect(() => {
    const controller = new AbortController()
    fetch('/auth/session', { credentials: 'same-origin', signal: controller.signal })
      .then(async (response) => ({ ok: response.ok, body: await response.json() }))
      .then(({ ok, body }) => {
        setAuthState(body)
        if (ok && body.authenticated) {
          navigate('/overview', { replace: true })
          return
        }
        setMessage(body.phase === 'turnstile_required'
          ? 'IDENTITY VERIFIED · HUMAN CHECK REQUIRED'
          : 'PROVIDER CONFIGURATION REQUIRED · ACCESS CLOSED')
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setMessage('AUTHENTICATION SERVICE UNAVAILABLE · ACCESS CLOSED')
      })
    return () => controller.abort()
  }, [navigate])

  useEffect(() => {
    if (authState.phase !== 'turnstile_required' || !authState.turnstileSiteKey || !turnstileHost.current) return undefined
    let cancelled = false
    const complete = async (token) => {
      if (cancelled) return
      setMessage('VERIFYING TURNSTILE ON THE SERVER')
      const response = await fetch('/auth/turnstile', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'content-type': 'application/json', 'x-aios-csrf': authState.csrfToken },
        body: JSON.stringify({ token }),
      })
      const result = await response.json()
      if (response.ok && result.authenticated) navigate(result.destination || '/overview', { replace: true })
      else setMessage('TURNSTILE VERIFICATION FAILED · ACCESS CLOSED')
    }
    window.aiosTurnstileReady = () => {
      if (!cancelled && window.turnstile && turnstileHost.current) {
        window.turnstile.render(turnstileHost.current, { sitekey: authState.turnstileSiteKey, callback: complete })
      }
    }
    loadTurnstile(complete)
    if (window.turnstile) window.aiosTurnstileReady()
    return () => { cancelled = true }
  }, [authState, navigate])

  const begin = () => window.location.assign(isSignup ? '/auth/signup' : '/auth/login')
  const switchMode = () => navigate(isSignup ? '/login' : '/signup')
  const unavailable = authState.phase !== 'identity_required'

  return <main className="loginPortal"><MarketConstellation /><section className="identityGate" aria-labelledby="auth-title">
    <div className="identityMark"><AiosSymbol name="aios-core" label="AIOS: slanted A, signal tower I, orbital globe O, and dollar coin S" size="xl" framed /><span>AIOS</span><small>SECURE OPERATOR PORTAL</small></div>
    <div className="identityCopy"><p>MICROSOFT ENTRA EXTERNAL ID</p><h1 id="auth-title" tabIndex="-1">{isSignup ? 'Create your access.' : 'Welcome back.'}</h1><span>{isSignup ? 'Request an AIOS dashboard identity through the governed sign-up path.' : 'Continue through the protected identity path to reach your dashboard.'}</span><ul className="insigniaKey" aria-label="Authentic AIOS insignia"><li><b>A</b>Slanted partial-A</li><li><b>I</b>Signal tower</li><li><b>O</b>Orbital globe</li><li><b>S</b>Dollar coin</li></ul></div>
    <div className="providerStack" aria-label="Secure authentication">
      {authState.phase === 'turnstile_required' ? <><div className="turnstilePanel"><strong>HUMAN VERIFICATION</strong><span>Cloudflare Turnstile is checked by the AIOS server before a session is created.</span><div ref={turnstileHost} /></div></> : <button className="entraAction" type="button" onClick={begin} disabled={unavailable}><span>{isSignup ? 'SIGN UP WITH MICROSOFT' : 'CONTINUE WITH MICROSOFT'}</span><small>ENTRA EXTERNAL ID</small></button>}
      <button className="modeSwitch" type="button" onClick={switchMode}><span>{isSignup ? 'ALREADY HAVE ACCESS?' : 'NEW TO AIOS?'}</span><small>{isSignup ? 'SIGN IN' : 'CREATE ACCOUNT'}</small></button>
      <p role="status" aria-live="polite">{message}</p>
      <div className="accessBoundary"><span><b>01</b>Cloudflare Access</span><span><b>02</b>Microsoft identity</span><span><b>03</b>Server Turnstile</span></div>
    </div>
  </section><footer>AIOS · IDENTITY DOES NOT GRANT TRADING OR APPROVAL AUTHORITY · ACCESS FAILS CLOSED</footer></main>
}
