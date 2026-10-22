import { useEffect, useRef, useState } from 'react';
export function useAiosDashboardProjection(intervalMs = 30000) {
  const [state, setState] = useState({ projection: null, status: 'UNAVAILABLE', error: null });
  const active = useRef(null);
  useEffect(() => {
    const delay = Math.max(15000, intervalMs); let timer; let mounted = true;
    const load = async () => { if (document.hidden || active.current) return; const controller = new AbortController(); active.current = controller;
      try { const response = await fetch('/aios-dashboard-projection', { signal: controller.signal, headers: { accept: 'application/json' } }); if (!response.ok) throw new Error(`projection ${response.status}`); const projection = await response.json(); if (mounted) setState({ projection, status: projection.projection_state, error: null }); }
      catch (error) { if (mounted && error.name !== 'AbortError') setState((current) => ({ ...current, error: error.message })); } finally { active.current = null; } };
    const visible = () => { if (!document.hidden) load(); }; load(); timer = window.setInterval(load, delay); document.addEventListener('visibilitychange', visible);
    return () => { mounted = false; window.clearInterval(timer); document.removeEventListener('visibilitychange', visible); active.current?.abort(); };
  }, [intervalMs]); return state;
}
