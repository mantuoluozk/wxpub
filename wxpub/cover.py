# -*- coding: utf-8 -*-
"""封面渲染引擎。

一条主线：所有元素水平居中、整块垂直居中、字号按可用宽度自动收缩。
这三点直接对应微信信息流的三个物理限制（左右裁切 / 上下裁切 / 缩略图看不清），
不是审美偏好，是适配规则。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .fonts import FontNotFoundError, resolve_fonts
from .theme import Theme, get_theme

RGB = Tuple[int, int, int]

# 公众号头图标准比例 2.35:1。16:9 在信息流里会被裁掉两侧，不要用。
SIZES = {
    "hd": (1280, 544),    # 默认，官方推荐
    "fhd": (1920, 817),
    "small": (900, 383),  # 最小可用尺寸，上传更快
}

# 文字安全宽度上限（相对画布宽度）。
# 信息流里左右各会被裁掉一大块，0.82 是实测后仍能完整显示的保守值。
SAFE_WIDTH_RATIO = 0.82

# 标题字号下限。再小在缩略图里就是噪点，宁可折行也不缩到更小。
MIN_TITLE_SIZE = 44

ACCENT_RE = re.compile(r"\*\*(.+?)\*\*", re.S)


@dataclass
class Span:
    text: str
    accent: bool = False


@dataclass
class CoverSpec:
    """封面内容。title 里用 | 或换行显式分行，用 ** ** 标记高亮片段。"""

    title: str
    subtitle: Optional[str] = None
    badge: Optional[str] = None
    layout: str = "stack"
    theme: str = "midnight"
    width: int = 1280
    height: int = 544
    # 布局微调（单位：相对画布宽度的比例），给特殊排版留的口子
    title_size: Optional[int] = None
    align: str = "center"          # center | left
    extra: List[str] = field(default_factory=list)  # 底部补充小字（hero 布局用）

    def resolved_theme(self) -> Theme:
        return get_theme(self.theme)


def parse_spans(line: str) -> List[Span]:
    """把 '在替别人**烧钱**' 解析成 [Span('在替别人'), Span('烧钱', accent=True)]"""
    spans: List[Span] = []
    pos = 0
    for m in ACCENT_RE.finditer(line):
        if m.start() > pos:
            spans.append(Span(line[pos:m.start()]))
        spans.append(Span(m.group(1), accent=True))
        pos = m.end()
    if pos < len(line):
        spans.append(Span(line[pos:]))
    return spans or [Span("")]


def split_lines(title: str) -> List[str]:
    """支持 | 和真实换行两种分行写法，并丢掉空行。"""
    raw = title.replace("\r\n", "\n")
    parts: List[str] = []
    for chunk in raw.split("\n"):
        parts.extend(chunk.split("|"))
    return [p.strip() for p in parts if p.strip()]


class _FontCache:
    def __init__(self) -> None:
        self._bold, self._regular = resolve_fonts()
        self._cache: dict = {}

    def get(self, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
        key = (size, bold)
        if key not in self._cache:
            path = self._bold if bold else self._regular
            try:
                self._cache[key] = ImageFont.truetype(path, size)
            except OSError as exc:  # 字体文件存在但损坏 / 不是合法字体
                raise FontNotFoundError(
                    f"字体文件无法加载：{path}\n{exc}\n"
                    "请用 WXPUB_FONT_BOLD / WXPUB_FONT_REGULAR 指定其他字体。"
                ) from exc
        return self._cache[key]


def _glow_layer(
    size: Tuple[int, int],
    center: Tuple[float, float],
    radius: float,
    color: RGB,
    peak: int,
    power: float = 2.2,
) -> Image.Image:
    """径向光晕。

    用 Image.radial_gradient 生成 256×256 的距离场再缩放，避免几十万次 Python 循环。
    视觉上与逐像素计算一致，速度快一到两个数量级。
    """
    d = max(4, int(radius * 2))
    # radial_gradient: 中心 0，边缘 255，正好是归一化距离 t
    grad = Image.radial_gradient("L").resize((d, d), Image.BICUBIC)
    lut = [int(peak * (1 - v / 255.0) ** power) for v in range(256)]
    alpha_small = grad.point(lut)

    mask = Image.new("L", size, 0)
    x0 = int(round(center[0] - radius))
    y0 = int(round(center[1] - radius))
    mask.paste(alpha_small, (x0, y0))

    layer = Image.new("RGBA", size, color + (0,))
    layer.putalpha(mask)
    return layer.filter(ImageFilter.GaussianBlur(max(1, radius * 0.12)))


def _measure(text: str, font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw) -> float:
    return draw.textlength(text, font=font)


def _line_width(spans: Sequence[Span], font: ImageFont.FreeTypeFont, draw: ImageDraw.ImageDraw) -> float:
    return sum(_measure(s.text, font, draw) for s in spans)


def _fit_title_size(
    lines: Sequence[Sequence[Span]],
    draw: ImageDraw.ImageDraw,
    fonts: _FontCache,
    max_width: float,
    max_height: float,
    start: int,
    floor: int = MIN_TITLE_SIZE,
    line_ratio: float = 1.22,
) -> int:
    """从 start 往下找第一个能让所有行都放得下的字号。"""
    size = start
    while size > floor:
        font = fonts.get(size, bold=True)
        widest = max(_line_width(line, font, draw) for line in lines)
        total_h = len(lines) * size * line_ratio
        if widest <= max_width and total_h <= max_height:
            return size
        size -= 2
    return floor


# 可以在其后断行的标点。优先在标点后断，避免「是否正 / 常工作」这种把词劈开的断法。
_BREAK_AFTER = "，。、；：！？）》」』】…—,.;:!?)]}·"

# ASCII 词字符，用于保护英文单词不被从中间劈开
_WORD_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/.")


def _merge_spans(chars: Sequence[Tuple[str, bool]]) -> List[Span]:
    """把 (字符, 是否高亮) 序列合并回 Span 列表。"""
    out: List[Span] = []
    for ch, accent in chars:
        if out and out[-1].accent == accent:
            out[-1].text += ch
        else:
            out.append(Span(ch, accent))
    return out


def _auto_wrap(
    spans: Sequence[Span],
    font: ImageFont.FreeTypeFont,
    draw: ImageDraw.ImageDraw,
    max_width: float,
) -> List[List[Span]]:
    """字号已到下限仍放不下时的折行。

    优先在标点后断，其次在空格后断，再次保护英文单词整体移行，最后才硬断。
    断点太靠前（少于行宽 55%）时宁可硬断，避免出现只有两三个字的第一行。
    """
    chars: List[Tuple[str, bool]] = [(ch, s.accent) for s in spans for ch in s.text]
    widths = [draw.textlength(ch, font=font) for ch, _ in chars]

    out: List[List[Span]] = []
    cur: List[Tuple[str, bool]] = []
    cur_w = 0.0
    last_break = 0  # cur 中「断点位于其前」的下标

    for i, (ch, accent) in enumerate(chars):
        w = widths[i]
        if cur and cur_w + w > max_width:
            cut = len(cur)
            if last_break and last_break >= len(cur) * 0.55:
                cut = last_break
            else:
                # 断点落在英文单词中间时，把整个词推到下一行
                j = cut
                while j > 1 and chars[i - len(cur) + j - 1][0] in _WORD_CHARS:
                    j -= 1
                if j > len(cur) * 0.5:
                    cut = j
            out.append(_merge_spans(cur[:cut]))
            cur = cur[cut:]
            cur_w = sum(draw.textlength(c, font=font) for c, _ in cur)
            last_break = 0

        cur.append((ch, accent))
        cur_w += w
        if ch in _BREAK_AFTER or ch == " ":
            last_break = len(cur)

    if cur:
        out.append(_merge_spans(cur))
    return [line for line in out if any(s.text for s in line)]


def _draw_spans(
    draw: ImageDraw.ImageDraw,
    spans: Sequence[Span],
    font: ImageFont.FreeTypeFont,
    x: float,
    y: float,
    theme: Theme,
) -> None:
    cx = x
    for span in spans:
        color = theme.accent if span.accent else theme.title
        draw.text((cx, y), span.text, font=font, fill=color)
        cx += draw.textlength(span.text, font=font)


def _draw_badge(
    draw: ImageDraw.ImageDraw,
    text: str,
    theme: Theme,
    cx: float,
    y: float,
    font: ImageFont.FreeTypeFont,
    pad_x: int = 22,
    height: Optional[int] = None,
) -> float:
    h = height or int(font.size * 2.0)
    tw = draw.textlength(text, font=font)
    w = tw + pad_x * 2
    draw.rounded_rectangle(
        [(cx - w / 2), y, (cx + w / 2), y + h],
        radius=h / 2,
        fill=theme.badge_bg,
    )
    draw.text(
        (cx - tw / 2, y + (h - font.size) / 2 - font.size * 0.12),
        text,
        font=font,
        fill=theme.badge_fg,
    )
    return h


class CoverRenderer:
    def __init__(self, spec: CoverSpec) -> None:
        self.spec = spec
        self.theme = spec.resolved_theme()
        self.W = int(spec.width)
        self.H = int(spec.height)
        self.fonts = _FontCache()

    # 所有像素常量都以 1280×544 为基准，按高度等比缩放。
    # 不这么做，出 320×136 缩略图时字号还是 16px、胶囊还是 42px 高，直接糊出画布。
    @property
    def k(self) -> float:
        return self.H / 544.0

    def px(self, v: float) -> int:
        return max(1, int(round(v * self.k)))

    # ------------------------------------------------------------------ 背景
    def _background(self) -> Image.Image:
        t = self.theme
        img = Image.new("RGB", (self.W, self.H), t.bg)
        base = img.convert("RGBA")
        for g in t.glows:
            base = Image.alpha_composite(
                base,
                _glow_layer(
                    (self.W, self.H),
                    (g.x * self.W, g.y * self.H),
                    g.radius * self.W,
                    g.color,
                    g.peak,
                ),
            )
        return base

    # ------------------------------------------------------------------ 主流程
    def render(self) -> Image.Image:
        layout = (self.spec.layout or "stack").strip().lower()
        if layout not in LAYOUTS:
            raise ValueError(
                f"未知布局 {self.spec.layout!r}。可用布局：{'、'.join(LAYOUTS)}"
            )
        img = self._background()
        draw = ImageDraw.Draw(img)
        LAYOUTS[layout](self, img, draw)
        return img.convert("RGB")

    # ------------------------------------------------------------------ 公共部件
    def _title_font_size(self, lines, max_height: float, start: int) -> int:
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        if self.spec.title_size:
            return int(self.spec.title_size)
        return _fit_title_size(
            lines, draw, self.fonts,
            max_width=self.W * SAFE_WIDTH_RATIO,
            max_height=max_height,
            start=start,
            floor=self.px(MIN_TITLE_SIZE),
        )

    def _prepare_lines(self, start_size: int, max_height: float):
        """返回 (lines_of_spans, size)。超宽时先缩字号，仍超宽则折行。"""
        parsed = [parse_spans(l) for l in split_lines(self.spec.title)]
        if not parsed:
            parsed = [parse_spans("")]
        draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        size = self._title_font_size(parsed, max_height, start_size)
        font = self.fonts.get(size, bold=True)
        max_w = self.W * SAFE_WIDTH_RATIO

        if any(_line_width(l, font, draw) > max_w for l in parsed):
            wrapped: List[List[Span]] = []
            for line in parsed:
                wrapped.extend(_auto_wrap(line, font, draw, max_w))
            parsed = wrapped
        return parsed, size

    def _x_for(self, width: float) -> float:
        if self.spec.align == "left":
            return self.W * (1 - SAFE_WIDTH_RATIO) / 2
        return (self.W - width) / 2


# ====================================================================== 布局
def _layout_stack(r: CoverRenderer, img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    """双行大标题 + 副标题 + 顶部日期胶囊。默认布局，最稳。"""
    spec, theme = r.spec, r.theme
    badge_font = r.fonts.get(r.px(21), bold=False)
    sub_size = r.px(31)
    sub_font = r.fonts.get(sub_size, bold=False)

    lines, size = r._prepare_lines(start_size=int(r.H * 0.176), max_height=r.H * 0.52)
    line_h = size * 1.22

    # 先算总高度，再整体垂直居中
    badge_h = r.px(42) if spec.badge else 0
    badge_gap = r.px(46) if spec.badge else 0
    sub_h = (sub_size * 1.5 + r.px(26)) if spec.subtitle else 0
    total = badge_h + badge_gap + len(lines) * line_h + sub_h
    y = (r.H - total) / 2

    if spec.badge:
        _draw_badge(draw, spec.badge, theme, r.W / 2, y, badge_font, pad_x=r.px(22), height=badge_h)
        y += badge_h + badge_gap

    for line in lines:
        w = _line_width(line, r.fonts.get(size, bold=True), draw)
        _draw_spans(draw, line, r.fonts.get(size, bold=True), r._x_for(w), y, theme)
        y += line_h

    if spec.subtitle:
        y += r.px(26)
        w = _measure(spec.subtitle, sub_font, draw)
        draw.text((r._x_for(w), y), spec.subtitle, font=sub_font, fill=theme.subtitle)


def _layout_hero(r: CoverRenderer, img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    """单行超大标题 + 彩色副标题 + 底部小字。适合一句话结论式的选题。"""
    spec, theme = r.spec, r.theme
    badge_font = r.fonts.get(r.px(21), bold=False)
    sub_size = r.px(32)
    sub_font = r.fonts.get(sub_size, bold=True)
    foot_font = r.fonts.get(r.px(18), bold=False)

    lines, size = r._prepare_lines(start_size=int(r.H * 0.20), max_height=r.H * 0.40)
    line_h = size * 1.18

    badge_h = r.px(42) if spec.badge else 0
    badge_gap = r.px(40) if spec.badge else 0
    sub_h = sub_size * 1.6 if spec.subtitle else 0
    foot_h = (foot_font.size * 2.2 + r.px(8)) if spec.extra else 0
    total = badge_h + badge_gap + len(lines) * line_h + sub_h + foot_h
    y = (r.H - total) / 2

    if spec.badge:
        _draw_badge(draw, spec.badge, theme, r.W / 2, y, badge_font, pad_x=r.px(22), height=badge_h)
        y += badge_h + badge_gap

    font = r.fonts.get(size, bold=True)
    for line in lines:
        w = _line_width(line, font, draw)
        _draw_spans(draw, line, font, r._x_for(w), y, theme)
        y += line_h

    if spec.subtitle:
        y += sub_size * 0.36
        w = _measure(spec.subtitle, sub_font, draw)
        draw.text((r._x_for(w), y), spec.subtitle, font=sub_font, fill=theme.accent)
        y += sub_h

    if spec.extra:
        y += r.px(8)
        foot = "  ·  ".join(spec.extra)
        w = _measure(foot, foot_font, draw)
        draw.text((r._x_for(w), y), foot, font=foot_font, fill=theme.subtitle)


def _layout_minimal(r: CoverRenderer, img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    """无胶囊、无装饰，只有标题和副标题。信息流缩略图里辨识度最高。"""
    spec, theme = r.spec, r.theme
    sub_size = r.px(30)
    sub_font = r.fonts.get(sub_size, bold=False)

    lines, size = r._prepare_lines(start_size=int(r.H * 0.19), max_height=r.H * 0.56)
    line_h = size * 1.24
    sub_h = sub_size * 1.5 + r.px(30) if spec.subtitle else 0
    total = len(lines) * line_h + sub_h
    y = (r.H - total) / 2

    font = r.fonts.get(size, bold=True)
    for line in lines:
        w = _line_width(line, font, draw)
        _draw_spans(draw, line, font, r._x_for(w), y, theme)
        y += line_h

    if spec.subtitle:
        y += r.px(30)
        w = _measure(spec.subtitle, sub_font, draw)
        draw.text((r._x_for(w), y), spec.subtitle, font=sub_font, fill=theme.subtitle)


def _layout_split(r: CoverRenderer, img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    """左侧一条主题色竖条 + 左对齐标题。适合比较判断型标题。"""
    spec, theme = r.spec, r.theme
    spec.align = "left"
    sub_size = r.px(30)
    sub_font = r.fonts.get(sub_size, bold=False)

    lines, size = r._prepare_lines(start_size=int(r.H * 0.165), max_height=r.H * 0.54)
    line_h = size * 1.22
    badge_h = r.px(76) if spec.badge else 0
    sub_h = sub_size * 1.5 + r.px(26) if spec.subtitle else 0
    total = badge_h + len(lines) * line_h + sub_h
    y = (r.H - total) / 2

    text_x = r.W * (1 - SAFE_WIDTH_RATIO) / 2
    bar_x = text_x - r.px(26)
    # 竖条只覆盖标题区，不压住上面的胶囊
    bar_top = y + (badge_h if spec.badge else 0) + r.px(6)
    draw.rounded_rectangle(
        [bar_x, bar_top, bar_x + r.px(8), y + total - r.px(6)],
        radius=r.px(4),
        fill=theme.accent,
    )

    if spec.badge:
        badge_font = r.fonts.get(r.px(21), bold=False)
        tw = draw.textlength(spec.badge, font=badge_font)
        bh = r.px(42)
        draw.rounded_rectangle(
            [text_x, y, text_x + tw + r.px(44), y + bh], radius=bh / 2, fill=theme.badge_bg
        )
        draw.text(
            (text_x + r.px(22), y + (bh - badge_font.size) / 2 - badge_font.size * 0.12),
            spec.badge,
            font=badge_font,
            fill=theme.badge_fg,
        )
        y += badge_h

    font = r.fonts.get(size, bold=True)
    for line in lines:
        _draw_spans(draw, line, font, text_x, y, theme)
        y += line_h

    if spec.subtitle:
        y += r.px(26)
        draw.text((text_x, y), spec.subtitle, font=sub_font, fill=theme.subtitle)


def _layout_banner(r: CoverRenderer, img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    """顶部一条主题色实心色带压住标题区。视觉重量最大，适合重磅消息。"""
    spec, theme = r.spec, r.theme
    band_h = int(r.H * 0.045)
    draw.rectangle([0, 0, r.W, band_h], fill=theme.accent)

    sub_size = r.px(30)
    sub_font = r.fonts.get(sub_size, bold=False)

    lines, size = r._prepare_lines(start_size=int(r.H * 0.17), max_height=r.H * 0.50)
    line_h = size * 1.22
    sub_h = sub_size * 1.5 + r.px(26) if spec.subtitle else 0
    total = len(lines) * line_h + sub_h
    y = band_h + (r.H - band_h - total) / 2

    font = r.fonts.get(size, bold=True)
    for line in lines:
        w = _line_width(line, font, draw)
        _draw_spans(draw, line, font, r._x_for(w), y, theme)
        y += line_h

    if spec.subtitle:
        y += r.px(26)
        w = _measure(spec.subtitle, sub_font, draw)
        draw.text((r._x_for(w), y), spec.subtitle, font=sub_font, fill=theme.subtitle)


def _layout_quote(r: CoverRenderer, img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
    """左上引号装饰 + 引用式标题。适合观点、访谈、名人名言类。"""
    spec, theme = r.spec, r.theme

    sub_size = r.px(29)
    sub_font = r.fonts.get(sub_size, bold=False)

    lines, size = r._prepare_lines(start_size=int(r.H * 0.145), max_height=r.H * 0.46)
    line_h = size * 1.26
    sub_h = sub_size * 1.5 + r.px(26) if spec.subtitle else 0
    total = len(lines) * line_h + sub_h
    y = (r.H - total) / 2 + 10

    # 引号按字形实际包围盒定位。中文字体里引号字形上方留白极大，
    # 用 (0,0) 直接画会飞到画布外面去，必须用 textbbox 校正。
    # 做成半透明水印靠左上，是装饰不是主角。
    q_size = int(r.H * 0.34)
    q_font = r.fonts.get(q_size, bold=True)
    q_text = "\u201c"
    bbox = draw.textbbox((0, 0), q_text, font=q_font)
    q_w = bbox[2] - bbox[0]
    q_h = bbox[3] - bbox[1]
    q_x = r.W * (1 - SAFE_WIDTH_RATIO) / 2 - bbox[0]
    q_y = y - q_h + q_h * 0.30 - bbox[1]
    if q_y > -q_h * 0.2:  # 上方空间不够时干脆不画，宁可少一个装饰也不要压文字
        layer = Image.new("RGBA", (r.W, r.H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((q_x, q_y), q_text, font=q_font, fill=theme.accent + (58,))
        img.alpha_composite(layer)
        draw = ImageDraw.Draw(img)

    font = r.fonts.get(size, bold=True)
    for line in lines:
        w = _line_width(line, font, draw)
        _draw_spans(draw, line, font, r._x_for(w), y, theme)
        y += line_h

    if spec.subtitle:
        y += r.px(26)
        sub = f"— {spec.subtitle}" if not spec.subtitle.startswith("—") else spec.subtitle
        w = _measure(sub, sub_font, draw)
        draw.text((r._x_for(w), y), sub, font=sub_font, fill=theme.subtitle)


LAYOUTS = {
    "stack": _layout_stack,
    "hero": _layout_hero,
    "minimal": _layout_minimal,
    "split": _layout_split,
    "banner": _layout_banner,
    "quote": _layout_quote,
}


def render_cover(
    title: str,
    subtitle: Optional[str] = None,
    badge: Optional[str] = None,
    theme: str = "midnight",
    layout: str = "stack",
    size: str = "hd",
    width: Optional[int] = None,
    height: Optional[int] = None,
    title_size: Optional[int] = None,
    align: str = "center",
    extra: Optional[List[str]] = None,
) -> Image.Image:
    """最常用的入口：一行调用拿到 PIL Image。"""
    if width is None or height is None:
        w, h = SIZES.get(size, SIZES["hd"])
        width = width or w
        height = height or h
    spec = CoverSpec(
        title=title,
        subtitle=subtitle,
        badge=badge,
        layout=layout,
        theme=theme,
        width=width,
        height=height,
        title_size=title_size,
        align=align,
        extra=extra or [],
    )
    return CoverRenderer(spec).render()
