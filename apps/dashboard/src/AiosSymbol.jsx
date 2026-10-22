import { getAiosSymbol } from './aiosSymbolManifest.js';
import './AiosSymbol.css';

export default function AiosSymbol({
  name,
  label,
  size = 'md',
  framed = true,
  className = ''
}) {
  const symbol = getAiosSymbol(name);
  const accessibleLabel = label ?? symbol.label;
  const classes = ['aiosSymbol', `aiosSymbol-${size}`, framed ? 'aiosSymbol-framed' : '', className]
    .filter(Boolean)
    .join(' ');

  return (
    <span className={classes} aria-label={accessibleLabel} role="img">
      {name === 'aios-core' ? <span className="aiosWordmark" aria-hidden="true"><i className="markA">A</i><i className="markI"><b /><em /></i><i className="markO"><b className="globeCore" /><b className="globeRing" /></i><i className="markS">$</i></span> : <img src={symbol.src} alt="" aria-hidden="true" draggable="false" />}
    </span>
  );
}
