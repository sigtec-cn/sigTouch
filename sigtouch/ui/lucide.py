"""内嵌 Lucide 图标(子集)与 QIcon 渲染。

图标 path/shape 数据取自 Lucide 图标集(https://lucide.dev),
以 ISC 许可证发布:https://github.com/lucide-icons/lucide/blob/main/LICENSE

    ISC License

    Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022
    as part of Feather (MIT). All other copyright (c) for Lucide are held
    by Lucide Contributors 2022.

    Permission to use, copy, modify, and/or distribute this software for
    any purpose with or without fee is hereby granted, provided that the
    above copyright notice and this permission notice appear in all
    copies.

    THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
    WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
    MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
    ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
    WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
    ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
    OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

本模块仅内嵌 SigTouch 使用到的图标子集,原始 markup 为 24x24 viewBox、
stroke-width 2、圆头圆角连接(stroke-linecap/linejoin round)。
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

# name -> raw inner SVG markup (currentColor 占位符会在渲染时替换为目标色)
_ICONS: dict[str, str] = {
    "camera": (
        '<path d="M13.997 4a2 2 0 0 1 1.76 1.05l.486.9A2 2 0 0 0 18.003 7'
        'H20a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2'
        'h1.997a2 2 0 0 0 1.759-1.048l.489-.904A2 2 0 0 1 10.004 4z"/>'
        '<circle cx="12" cy="13" r="3"/>'
    ),
    "hand": (
        '<path d="M18 11V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2"/>'
        '<path d="M14 10V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v2"/>'
        '<path d="M10 10.5V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2v8"/>'
        '<path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86'
        '-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>'
    ),
    "palette": (
        '<path d="M12 22a1 1 0 0 1 0-20 10 9 0 0 1 10 9 5 5 0 0 1-5 5h'
        '-2.25a1.75 1.75 0 0 0-1.4 2.8l.3.4a1.75 1.75 0 0 1-1.4 2.8z"/>'
        '<circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/>'
        '<circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/>'
        '<circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/>'
        '<circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/>'
    ),
    "settings": (
        '<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0'
        ' 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831'
        ' 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34'
        ' 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1'
        '-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051'
        'a2.34 2.34 0 0 0 3.319-1.915"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "mouse-pointer": (
        '<path d="M12.586 12.586 19 19"/>'
        '<path d="M3.688 3.037a.497.497 0 0 0-.651.651l6.5 15.999a.501'
        '.501 0 0 0 .947-.062l1.569-6.083a2 2 0 0 1 1.448-1.479l6.124'
        '-1.579a.5.5 0 0 0 .063-.947z"/>'
    ),
    "keyboard": (
        '<path d="M10 8h.01"/>'
        '<path d="M12 12h.01"/>'
        '<path d="M14 8h.01"/>'
        '<path d="M16 12h.01"/>'
        '<path d="M18 8h.01"/>'
        '<path d="M6 8h.01"/>'
        '<path d="M7 16h10"/>'
        '<path d="M8 12h.01"/>'
        '<rect width="20" height="16" x="2" y="4" rx="2"/>'
    ),
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "triangle-alert": (
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21'
        'h16a2 2 0 0 0 1.73-3"/>'
        '<path d="M12 9v4"/>'
        '<path d="M12 17h.01"/>'
    ),
    "rotate-cw": (
        '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>'
        '<path d="M21 3v5h-5"/>'
    ),
    "video": (
        '<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0'
        ' 0-.752-.432L16 10.5"/>'
        '<rect x="2" y="6" width="14" height="12" rx="2"/>'
    ),
    "shield": (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5'
        ' 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17'
        ' 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
    ),
    "power": '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>',
    "circle": '<circle cx="12" cy="12" r="10"/>',
    "pause": (
        '<rect x="14" y="3" width="5" height="18" rx="1"/>'
        '<rect x="5" y="3" width="5" height="18" rx="1"/>'
    ),
    "play": (
        '<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003'
        ' 3.458l-12 7A2 2 0 0 1 5 19z"/>'
    ),
}

_SUPERSAMPLE = 2  # 渲染倍率,渲染后缩小以防止小尺寸描边发糊


def _markup(name: str, color: str, fill: bool) -> str:
    body = _ICONS[name].replace("currentColor", color)
    fill_attr = color if fill else "none"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" fill="{fill_attr}" stroke="{color}" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg>"
    )


def icon(name: str, color: str = theme.TEXT, size: int = 16, fill: bool = False) -> QIcon:
    """按名称渲染内嵌 lucide 图标为 QIcon;未知名称抛 KeyError。"""
    if name not in _ICONS:
        raise KeyError(f"unknown lucide icon: {name!r}")

    renderer = QSvgRenderer(QByteArray(_markup(name, color, fill).encode("utf-8")))
    big = size * _SUPERSAMPLE
    pixmap = QPixmap(big, big)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, big, big))
    painter.end()

    # 不做平滑降采样(会糊描边)。改为把高分辨率像素图标记为 devicePixelRatio,
    # 交给 Qt 的高 DPI 管线按 size 逻辑像素显示——在 2x Retina 屏上呈现原生清晰度。
    pixmap.setDevicePixelRatio(float(_SUPERSAMPLE))
    return QIcon(pixmap)
