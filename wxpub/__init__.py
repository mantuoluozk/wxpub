# -*- coding: utf-8 -*-
"""wxpub —— Markdown 一键发进微信公众号草稿箱。

对外只暴露高层入口，内部实现随时可重构。
"""

from .cover import SIZES, CoverSpec, CoverRenderer, render_cover
from .fonts import FontNotFoundError, font_report
from .theme import THEMES, get_theme

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "render_cover",
    "CoverSpec",
    "CoverRenderer",
    "SIZES",
    "THEMES",
    "get_theme",
    "FontNotFoundError",
    "font_report",
]
