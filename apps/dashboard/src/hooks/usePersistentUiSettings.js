import { useCallback, useState } from 'react'
const STORAGE_KEY = 'AIOS_OBSIDIAN_UI_SETTINGS_V1'
const DEFAULTS = Object.freeze({ density: 'balanced', glassIntensity: 72, motionPreference: 'system', interfaceSoundEnabled: false, interfaceSoundVolume: 30, musicVolume: 55, alertVolume: 70, musicDockPosition: { x: 28, y: 28 }, navigationCollapsed: false, selectedWorkspace: 'Trading', selectedMarketSymbol: 'EUR_USD', selectedTimeframe: 'M5', refreshInterval: 30, timeZone: 'UTC', tableDensity: 'balanced', chartDisplay: 'candles', notificationDisplay: 'important', textScale: 100, highContrast: true })
function loadSettings() { try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') } } catch { return { ...DEFAULTS } } }
export function usePersistentUiSettings() {
  const [settings, setSettings] = useState(loadSettings)
  const updateSetting = useCallback((key, value) => {
    if (!(key in DEFAULTS)) return
    setSettings((current) => { const next = { ...current, [key]: value }; localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); return next })
  }, [])
  return { settings, updateSetting }
}
