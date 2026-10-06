import { useState } from 'react'
import GlassPanel from '../components/GlassPanel.jsx'
import PageHeader from '../components/PageHeader.jsx'
import TradingViewAdvancedChart from '../components/TradingViewAdvancedChart.jsx'
import { TIMEFRAMES, TRADING_VIEW_SYMBOLS } from '../services/tradingViewSymbols.js'
import { formatCurrency } from '../utils/formatFinance.js'

const LAYERS = ['Supertrend', 'ATR', 'EMA', 'AIOS Entries', 'Stops / Price Targets', 'Rejected Setups', 'News Events', 'Session Boundaries']
export default function MarketsPage({ state, settings, updateSetting }) {
  const [asset, setAsset] = useState('Forex'); const [query, setQuery] = useState(''); const [researchOpen, setResearchOpen] = useState(false)
  const symbols = TRADING_VIEW_SYMBOLS[asset].filter((symbol) => symbol.toLowerCase().includes(query.toLowerCase()))
  const runtimePairs = state.envelope?.source === 'runtime' && Array.isArray(state.envelope?.data?.pairs) ? state.envelope.data.pairs : []
  return <><PageHeader eyebrow="AIOS · M5" title="Currency Pairs" actions={<span className="readModelBadge">{runtimePairs.length ? `${runtimePairs.length} LIVE RECORDS` : 'READ MODEL NOT CONNECTED'}</span>} />
    <div className="marketWorkspace"><GlassPanel family="market" className="watchPanel"><div className="assetTabs">{Object.keys(TRADING_VIEW_SYMBOLS).map((name) => <button type="button" key={name} aria-pressed={asset === name} onClick={() => setAsset(name)}>{name}</button>)}</div><label className="searchField">PAIR<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="EURUSD" /></label><div className="symbolList">{symbols.map((symbol) => <button type="button" key={symbol} aria-pressed={settings.selectedMarketSymbol === symbol} onClick={() => updateSetting('selectedMarketSymbol', symbol)}><b>{symbol.split(':')[1]}</b><small>{symbol.split(':')[0]} · CHART SYMBOL</small></button>)}</div></GlassPanel>
      <div className="chartWorkspace"><GlassPanel family="market"><div className="chartToolbar"><b>{settings.selectedMarketSymbol}</b><span>MARKET STATUS: THIRD-PARTY WIDGET</span><select aria-label="Chart timeframe" value={settings.selectedTimeframe} onChange={(event) => updateSetting('selectedTimeframe', event.target.value)}>{TIMEFRAMES.map((frame) => <option key={frame}>{frame}</option>)}</select></div><TradingViewAdvancedChart symbol={settings.selectedMarketSymbol} interval={settings.selectedTimeframe} /></GlassPanel>
        <GlassPanel family="research" className="layerPanel"><div className="panelHeading"><div><small>LAYERS</small><h2>Research</h2></div><button type="button" onClick={() => setResearchOpen((value) => !value)}>{researchOpen ? 'CLOSE' : 'OPEN'}</button></div><div className="layerGrid">{LAYERS.map((layer) => <label key={layer}><input type="checkbox" disabled />{layer}</label>)}</div>
          {researchOpen && <form className="researchForm" onSubmit={(event) => event.preventDefault()}><b>DISPLAY ONLY · NO EXECUTION AUTHORITY</b>{[['ATR period',''],['Multiplier',''],['Price source',''],['Minimum planned R:R',''],['Session',''],['Pair',settings.selectedMarketSymbol],['Timeframe',settings.selectedTimeframe]].map(([label, value]) => <label key={label}>{label}<input value={value} readOnly={Boolean(value)} onChange={() => {}} /></label>)}<small>NOT CONFIGURED</small></form>}
        </GlassPanel>
        <GlassPanel family="market" className="tablePanel"><div className="windowTitle"><span>🌍</span><b>READ MODEL</b><small>{runtimePairs.length ? 'RUNTIME' : 'NOT CONNECTED'}</small></div>{runtimePairs.length ? <div className="tableScroll"><table><thead><tr>{['PAIR','DIRECTION','STATE','FRESHNESS','VALUE'].map((item) => <th key={item}>{item}</th>)}</tr></thead><tbody>{runtimePairs.map((pair) => <tr key={pair.pair}><td><b>{pair.pair}</b></td><td>{pair.direction ?? 'UNKNOWN'}</td><td>{pair.state ?? 'UNKNOWN'}</td><td>{pair.freshness ?? 'UNKNOWN'}</td><td>{Number.isFinite(Number(pair.open_pnl)) ? formatCurrency(Number(pair.open_pnl)) : 'NO DATA'}</td></tr>)}</tbody></table></div> : <div className="windowEmpty"><b>NOT CONNECTED</b><small>NO 68-PAIR READ MODEL EXPOSED</small></div>}</GlassPanel>
      </div></div>
  </>
}
