import { createElement } from 'react'
export default function GlassPanel({ family = 'neutral', importance = 'default', className = '', as = 'section', children, ...props }) { return createElement(as, { className: `glassPanel glass-${family} glass-${importance} ${className}`.trim(), ...props }, children) }
