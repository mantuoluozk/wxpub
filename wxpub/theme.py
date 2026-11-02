# -*- coding: utf-8 -*-
"""封面主题：一套配色 = 一个主题。

设计约束（来自 18 篇公众号封面的实战结论）：
1. 微信信息流里封面只露出中间一条窄带，左右会被裁掉，所以关键元素必须水平居中。
2. 缩略图极小，所以标题必须够大、对比度必须够高，装饰元素越少越好。
3. 背景用「纯色 + 两个径向光晕」就够了，比渐变图和贴图更干净，也不会有压缩噪点。

光晕位置用比例坐标表示（0~1），这样同一套主题在任意画布尺寸下都成立。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class Glow:
    """一个径向光晕。位置和半径都是相对画布的比例。"""

    x: float          # 0~1，光晕中心横坐标
    y: float          # 0~1，光晕中心纵坐标
    radius: float     # 相对画布宽度的半径比例
    color: RGB
    peak: int = 100   # 中心最大不透明度 0~255


@dataclass(frozen=True)
class Theme:
    name: str
    label: str
    bg: RGB
    title: RGB
    accent: RGB
    subtitle: RGB
    glows: List[Glow] = field(default_factory=list)
    badge_bg: Tuple[int, int, int, int] = (48, 66, 96, 150)
    badge_fg: RGB = (170, 190, 215)
    dark: bool = True          # 深底浅字。paper 之类浅色主题设为 False
    preview_color: RGB = (0, 0, 0)  # 模板墙缩略图用的代表色


THEMES: Dict[str, Theme] = {
    # ---------------------------------------------------------------- 深色系
    "midnight": Theme(
        name="midnight",
        label="午夜蓝",
        bg=(12, 17, 28),
        title=(255, 255, 255),
        accent=(255, 138, 128),
        subtitle=(168, 182, 202),
        badge_bg=(48, 66, 96, 150),
        badge_fg=(170, 190, 215),
        glows=[
            Glow(0.234, 0.165, 0.406, (79, 195, 247), 85),
            Glow(0.781, 0.846, 0.422, (255, 138, 128), 80),
        ],
        preview_color=(40, 90, 140),
    ),
    "ocean": Theme(
        name="ocean",
        label="深海",
        bg=(8, 20, 34),
        title=(255, 255, 255),
        accent=(77, 208, 225),
        subtitle=(150, 178, 200),
        badge_bg=(20, 60, 90, 150),
        badge_fg=(150, 200, 225),
        glows=[
            Glow(0.20, 0.10, 0.46, (0, 150, 220), 105),
            Glow(0.82, 0.92, 0.44, (0, 200, 180), 70),
        ],
        preview_color=(16, 90, 150),
    ),
    "ember": Theme(
        name="ember",
        label="余烬",
        bg=(24, 14, 12),
        title=(255, 250, 245),
        accent=(255, 152, 80),
        subtitle=(200, 175, 165),
        badge_bg=(80, 40, 24, 150),
        badge_fg=(225, 175, 145),
        glows=[
            Glow(0.18, 0.12, 0.44, (220, 90, 40), 110),
            Glow(0.84, 0.90, 0.46, (255, 170, 60), 80),
        ],
        preview_color=(150, 60, 30),
    ),
    "forest": Theme(
        name="forest",
        label="墨林",
        bg=(10, 22, 18),
        title=(244, 252, 246),
        accent=(110, 231, 183),
        subtitle=(150, 180, 168),
        badge_bg=(26, 64, 52, 150),
        badge_fg=(150, 205, 180),
        glows=[
            Glow(0.22, 0.14, 0.44, (20, 160, 110), 95),
            Glow(0.80, 0.88, 0.42, (120, 220, 170), 60),
        ],
        preview_color=(20, 100, 75),
    ),
    "violet": Theme(
        name="violet",
        label="紫夜",
        bg=(22, 16, 46),
        title=(255, 255, 255),
        accent=(255, 190, 90),
        subtitle=(168, 158, 200),
        badge_bg=(70, 50, 110, 160),
        badge_fg=(215, 195, 160),
        glows=[
            Glow(0.30, 0.20, 0.50, (90, 60, 200), 115),
            Glow(0.78, 0.85, 0.48, (200, 60, 140), 75),
        ],
        preview_color=(70, 45, 140),
    ),
    "sunset": Theme(
        name="sunset",
        label="暮色",
        bg=(26, 14, 32),
        title=(255, 248, 250),
        accent=(255, 138, 180),
        subtitle=(190, 160, 190),
        badge_bg=(78, 36, 70, 150),
        badge_fg=(225, 175, 200),
        glows=[
            Glow(0.24, 0.16, 0.46, (210, 80, 140), 100),
            Glow(0.80, 0.86, 0.48, (255, 140, 80), 80),
        ],
        preview_color=(140, 50, 100),
    ),
    "ink": Theme(
        name="ink",
        label="浓墨",
        bg=(16, 16, 18),
        title=(250, 250, 250),
        accent=(129, 140, 248),
        subtitle=(160, 160, 168),
        badge_bg=(44, 44, 52, 160),
        badge_fg=(170, 170, 180),
        glows=[
            Glow(0.26, 0.18, 0.40, (70, 70, 110), 90),
            Glow(0.78, 0.84, 0.38, (110, 100, 160), 55),
        ],
        preview_color=(80, 80, 100),
    ),
    "mono": Theme(
        name="mono",
        label="极简灰",
        bg=(18, 18, 18),
        title=(255, 255, 255),
        accent=(255, 255, 255),
        subtitle=(150, 150, 150),
        badge_bg=(52, 52, 52, 160),
        badge_fg=(180, 180, 180),
        glows=[
            Glow(0.50, 0.10, 0.55, (60, 60, 60), 60),
        ],
        preview_color=(90, 90, 90),
    ),
    "crimson": Theme(
        name="crimson",
        label="朱印",
        bg=(26, 10, 14),
        title=(255, 250, 250),
        accent=(255, 200, 100),
        subtitle=(200, 160, 160),
        badge_bg=(90, 28, 36, 160),
        badge_fg=(235, 180, 170),
        glows=[
            Glow(0.20, 0.16, 0.46, (170, 30, 45), 115),
            Glow(0.82, 0.88, 0.44, (230, 120, 60), 65),
        ],
        preview_color=(140, 30, 45),
    ),
    # ---------------------------------------------------------------- 浅色系
    "paper": Theme(
        name="paper",
        label="纸白",
        bg=(248, 249, 251),
        title=(24, 28, 38),
        accent=(37, 99, 235),
        subtitle=(110, 120, 140),
        badge_bg=(226, 232, 240, 255),
        badge_fg=(90, 100, 120),
        dark=False,
        glows=[
            Glow(0.22, 0.10, 0.42, (180, 210, 245), 90),
            Glow(0.82, 0.92, 0.40, (250, 225, 200), 70),
        ],
        preview_color=(200, 215, 235),
    ),
    "sakura": Theme(
        name="sakura",
        label="浅樱",
        bg=(252, 248, 249),
        title=(40, 28, 34),
        accent=(219, 68, 122),
        subtitle=(140, 115, 125),
        badge_bg=(244, 228, 234, 255),
        badge_fg=(150, 100, 120),
        dark=False,
        glows=[
            Glow(0.24, 0.12, 0.40, (250, 200, 215), 110),
            Glow(0.84, 0.90, 0.38, (225, 210, 250), 80),
        ],
        preview_color=(240, 205, 218),
    ),
}


def get_theme(name: str) -> Theme:
    key = (name or "").strip().lower()
    if key not in THEMES:
        available = "、".join(f"{k}({v.label})" for k, v in THEMES.items())
        raise KeyError(f"未知主题 {name!r}。可用主题：{available}")
    return THEMES[key]


def theme_names() -> List[str]:
    return list(THEMES.keys())
