import { Component, useEffect, useState } from 'react'
import AiosAppShell from './app/AiosAppShell.jsx'
import { useAiosRouter } from './app/AiosRouter.jsx'
import LoginPortalPage from './pages/LoginPortalPage.jsx'
import './App.css'

class AppErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) return <main className="fatalState"><h1>AIOS UNAVAILABLE</h1><p>NO BROKER ACTION OCCURRED</p><button type="button" onClick={() => window.location.assign('/login')}>SECURE ACCESS</button></main>
    return this.props.children
  }
}

export default function App() {
  const { route, navigate } = useAiosRouter()
  const publicRoute = route === '/login' || route === '/signup'
  const [session, setSession] = useState({ phase: 'checking', authenticated: false })

  useEffect(() => {
    if (publicRoute) return undefined
    const controller = new AbortController()
    fetch('/auth/session', { credentials: 'same-origin', signal: controller.signal })
      .then(async (response) => ({ ok: response.ok, body: await response.json() }))
      .then(({ ok, body }) => setSession(ok && body.authenticated
        ? body
        : { phase: 'closed', authenticated: false }))
      .catch((error) => {
        if (error.name !== 'AbortError') setSession({ phase: 'closed', authenticated: false })
      })
    return () => controller.abort()
  }, [publicRoute, route])

  useEffect(() => {
    if (!publicRoute && session.phase === 'closed') navigate('/login', { replace: true })
  }, [navigate, publicRoute, session.phase])

  async function logout() {
    const response = await fetch('/auth/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: session.csrfToken ? { 'x-aios-csrf': session.csrfToken } : {},
    })
    const result = await response.json()
    setSession({ phase: 'closed', authenticated: false })
    if (response.ok && result.logoutUrl && result.logoutUrl !== '/login') window.location.assign(result.logoutUrl)
    else navigate('/login', { replace: true })
  }

  let content
  if (publicRoute) content = <LoginPortalPage navigate={navigate} />
  else if (session.authenticated) content = <><button className="authLogout" type="button" onClick={logout}>SIGN OUT</button><AiosAppShell route={route} navigate={navigate} /></>
  else content = <main className="authChecking"><p>SECURE SESSION CHECK</p><h1 tabIndex="-1">ACCESS CLOSED</h1><span>Verifying the server-owned authentication boundary.</span></main>

  return <AppErrorBoundary>{content}</AppErrorBoundary>
}
