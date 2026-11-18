"""Lightweight SVG plots with discrete trial times."""

from html import escape
from math import ceil
from pathlib import Path


COLORS = ("#12676d", "#a14531", "#594695", "#94641a", "#28528a")


def write_figure(path: Path, title, subtitle, panels, horizon):
    """Each panel contains a label, a y maximum, and labeled time/value series."""
    width, height = 900, 105 + 284 * len(panels)
    items = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g font-family="system-ui, sans-serif" fill="#182e3b">',
    ]

    def label(x, y, value, size=14, anchor="start"):
        items.append(f'<text x="{x}" y="{y}" font-size="{size}" '
                     f'text-anchor="{anchor}">{escape(str(value))}</text>')

    label(52, 39, title, 26)
    label(52, 65, subtitle)
    for idx, (ylabel, ymax, series) in enumerate(panels):
        top = 112 + 284 * idx
        left, right, bottom = 70, 850, top + 168
        label(left, top - 12, ylabel, 17)
        for y in range(0, ymax + 1, max(1, ceil(ymax / 6))):
            py = bottom - y / ymax * 168
            items.append(f'<path d="M{left} {py}H{right}" stroke="#d9e3e6"/>')
            label(left - 9, py + 5, y, anchor="end")
        for t in sorted(set(range(0, horizon + 1, max(1, ceil(horizon / 8)))) | {horizon}):
            px = left + t / horizon * (right - left)
            label(px, bottom + 20, t, anchor="middle")
        label((left + right) / 2, bottom + 43, "移動試行 t", anchor="middle")
        for j, (name, points) in enumerate(series):
            color = COLORS[j]
            points = [(left + t / horizon * (right-left), bottom - y / ymax * 168)
                      for t, y in points]
            x, y = points[0]
            d = f"M{x:.2f} {y:.2f}" + "".join(f"H{x:.2f}V{y:.2f}" for x, y in points[1:])
            dash = ("none", "8 4", "3 4", "12 4 3 4", "1 3")[j]
            items.append(f'<path d="{d}" fill="none" stroke="{color}" '
                         f'stroke-width="2.5" stroke-dasharray="{dash}"/>')
            key_x = left + 152 * j
            items.append(f'<path d="M{key_x} {bottom+65}h22" stroke="{color}" '
                         f'stroke-width="2.5" stroke-dasharray="{dash}"/>')
            label(key_x + 29, bottom + 70, name)
    items.append("</g></svg>")
    path.write_text("\n".join(items) + "\n", encoding="utf-8")
