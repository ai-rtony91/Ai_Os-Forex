import { useEffect, useRef, useState } from 'react'

export default function TradingViewAdvancedChart({ symbol, interval }) {
  const container = useRef(null)
  const [state, setState] = useState('LOADING')
  useEffect(() => {
    const node = container.current
    if (!node) return undefined
    node.innerHTML = '<div class="tradingview-widget-container__widget"></div>'
    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.async = true
    script.type = 'text/javascript'
    script.text = JSON.stringify({ autosize: true, symbol, interval, timezone: 'Etc/UTC', theme: 'dark', style: '1', locale: 'en', backgroundColor: 'rgba(3,5,8,1)', gridColor: 'rgba(143,164,184,.08)', allow_symbol_change: true, hide_side_toolbar: false, hide_top_toolbar: false, save_image: false, studies: [], support_host: 'https://www.tradingview.com' })
    script.onload = () => setState('READY')
    script.onerror = () => setState('UNAVAILABLE')
    node.appendChild(script)
    return () => { node.innerHTML = '' }
  }, [symbol, interval])
  return <div className="chartFrame"><div className="tradingview-widget-container" ref={container} /><div className="chartAttribution"><a href={`https://www.tradingview.com/symbols/${symbol.replace(':', '-')}/`} target="_blank" rel="noreferrer">{symbol} chart by TradingView</a><span>{state === 'UNAVAILABLE' ? 'Third-party chart unavailable.' : 'TradingView display — not AIOS market data.'}</span></div></div>
}
