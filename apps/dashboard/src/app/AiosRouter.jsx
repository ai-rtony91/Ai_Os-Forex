import { useCallback, useEffect, useState } from 'react'
/* eslint-disable react-refresh/only-export-components -- route state and view are intentionally colocated without a router dependency. */
export const ROUTES = Object.freeze(['/login', '/signup', '/overview', '/decisions', '/positions', '/risk', '/reports', '/post-mortem', '/settings', '/system-status'])
function normalize(pathname) { if (ROUTES.includes(pathname)) return pathname; return pathname === '/' ? '/login' : '/overview' }
export function useAiosRouter() {
  const [route, setRoute] = useState(() => normalize(window.location.pathname))
  useEffect(() => { const onPopState = () => setRoute(normalize(window.location.pathname)); window.addEventListener('popstate', onPopState); return () => window.removeEventListener('popstate', onPopState) }, [])
  const navigate = useCallback((next, { replace = false } = {}) => { const target = normalize(next); window.history[replace ? 'replaceState' : 'pushState']({}, '', target); setRoute(target); window.requestAnimationFrame(() => document.querySelector('main h1')?.focus()) }, [])
  return { route, navigate }
}
export default function AiosRouter({ route, routes, fallback = null }) { return routes[route] ?? fallback }
