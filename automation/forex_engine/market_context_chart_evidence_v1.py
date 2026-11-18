"""Dependency-free deterministic SVG evidence for market-context snapshots."""

from __future__ import annotations

from html import escape
from typing import Any, Mapping, Sequence


def render_market_context_svg(snapshots: Sequence[Mapping[str, Any]], *, width: int = 1000, height: int = 560) -> str:
    if not snapshots:
        raise ValueError("At least one snapshot is required")
    points = [item["ohlc"] for item in snapshots]
    low = min(item["low"] for item in points); high = max(item["high"] for item in points)
    span = high - low or 1.0
    left, top, plot_w, plot_h = 70, 55, width - 100, height - 100
    def x(i: int) -> float: return left + plot_w * (i + 0.5) / len(points)
    def y(price: float) -> float: return top + plot_h * (high - price) / span
    def line(key: str, color: str) -> str:
        coords = [(x(i), y(item[key])) for i, item in enumerate((s["supertrend"] for s in snapshots)) if item.get(key) is not None]
        return "" if not coords else f'<polyline fill="none" stroke="{color}" points="' + " ".join(f"{a:.3f},{b:.3f}" for a,b in coords) + '"/>'
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>']
    first = snapshots[0]
    title = f"{first.get('pair')} {first.get('timeframe')} market context | {first.get('timestamp')}"
    parts.append(f'<text x="20" y="25" font-family="sans-serif" font-size="14">{escape(title)}</text>')
    candle_w = max(2.0, plot_w / len(points) * 0.55)
    for i, snapshot in enumerate(snapshots):
        o, h, l, c = points[i]["open"], points[i]["high"], points[i]["low"], points[i]["close"]
        color = "#16803c" if c >= o else "#b42318"
        parts.append(f'<line x1="{x(i):.3f}" x2="{x(i):.3f}" y1="{y(h):.3f}" y2="{y(l):.3f}" stroke="{color}"/>')
        parts.append(f'<rect x="{x(i)-candle_w/2:.3f}" y="{min(y(o),y(c)):.3f}" width="{candle_w:.3f}" height="{max(1,abs(y(o)-y(c))):.3f}" fill="{color}"/>')
        st = snapshot.get("supertrend", {}).get("value")
        if st is not None:
            parts.append(f'<circle cx="{x(i):.3f}" cy="{y(st):.3f}" r="2" fill="#6f42c1"/>')
        if snapshot.get("rejection_reason"):
            parts.append(f'<text x="{x(i):.3f}" y="{max(40,y(h)-8):.3f}" font-size="9" text-anchor="middle" fill="#b42318">R</text>')
    parts.extend([line("value", "#6f42c1"), f'<line x1="{left}" x2="{left+plot_w}" y1="{top+plot_h}" y2="{top+plot_h}" stroke="#333"/>', '</svg>'])
    return "".join(parts)
