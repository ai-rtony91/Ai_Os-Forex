export default function SafeActionButton({ children, tone = 'neutral', ...props }) { return <button type="button" className={`safeAction safeAction-${tone}`} {...props}>{children}</button> }
