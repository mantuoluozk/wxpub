# -*- coding: utf-8 -*-
"""Markdown → 微信公众号内联样式 HTML。

为什么不用 markdown 库 + CSS 文件：
公众号编辑器会剥掉 <style> 标签、class 和 id，只认元素上的内联 style。
所以这里直接把样式写进每一个标签，输出即所见，粘进后台不用再调。

样式参考的是公众号长文的实际阅读场景：手机屏宽 375pt、单手滑动、深色代码块、
段间留白靠 margin 而不是 <br>。所有尺寸都是 px，微信不做 rem 换算。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

# ---------------------------------------------------------------- 占位符机制
# 行内替换会生成 HTML 标签，如果不先占位，后面的 HTML 转义会把标签本身也转义掉。
_PH = "\x00{}\x00"
_PH_RE = re.compile("\x00(\\d+)\x00")


@dataclass
class Style:
    """整篇文章的视觉参数。accent 默认跟封面主题走，做到封面内文同色。"""

    font_size: int = 16
    line_height: float = 1.75
    color: str = "#3F3F3F"
    heading_color: str = "#1A1A1A"
    accent: str = "#2563EB"
    muted: str = "#888888"
    code_bg: str = "#1E2430"
    code_fg: str = "#E6EDF3"
    inline_code_bg: str = "#F2F4F7"
    inline_code_fg: str = "#D6336C"
    quote_bg: str = "#F8F9FA"
    quote_fg: str = "#5A6472"
    table_head_bg: str = "#F2F4F7"
    table_border: str = "#E6E8EB"
    divider: str = "#EAEAEA"
    max_width: Optional[int] = None


# 图片回调：(本地路径或 URL, alt) -> 最终 src。publish 阶段会传入「上传到微信并换成 CDN 地址」的实现。
ImageHandler = Callable[[str, str], str]


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _attr(text: str) -> str:
    return html.escape(text, quote=True)


class _Inline:
    """行内语法解析。用占位符保护已生成的 HTML，避免被二次转义。"""

    def __init__(self, style: Style, image_handler: Optional[ImageHandler] = None) -> None:
        self.s = style
        self.image_handler = image_handler

    def convert(self, text: str) -> str:
        slots: List[str] = []

        def stash(fragment: str) -> str:
            slots.append(fragment)
            return _PH.format(len(slots) - 1)

        # 1) 行内代码优先，里面的 ** * [] 都是字面量
        def inline_code(m: re.Match) -> str:
            return stash(
                f'<code style="background:{self.s.inline_code_bg};color:{self.s.inline_code_fg};'
                f'padding:2px 5px;border-radius:4px;font-size:0.9em;'
                f'font-family:Menlo,Consolas,monospace;">{_esc(m.group(1))}</code>'
            )

        text = re.sub(r"`([^`\n]+)`", inline_code, text)

        # 2) 图片（要在链接之前，否则 ![a](b) 会被 [a](b) 规则吃掉）
        def image(m: re.Match) -> str:
            alt, src = m.group(1), m.group(2).strip()
            if self.image_handler:
                src = self.image_handler(src, alt)
            return stash(
                f'<img src="{_attr(src)}" alt="{_attr(alt)}" '
                f'style="max-width:100%;height:auto;display:block;margin:1.6em auto;'
                f'border-radius:6px;" />'
            )

        text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", image, text)

        # 3) 链接
        def link(m: re.Match) -> str:
            label = m.group(1)
            # 关键：这里**不能**生成 <a> 标签。
            # 微信草稿接口对 content 里的 <a> 零容忍，会返回 45166 invalid content hint，
            # 而且不管 href 指向哪 —— 连 mp.weixin.qq.com 自己的链接也一样被拦。
            # 所以只保留「看起来像链接」的视觉，读者反正也点不动（公众号只允许站内链接可点，
            # 且只能通过编辑器插入）。
            return stash(
                f'<span style="color:{self.s.accent};'
                f'border-bottom:1px dashed {self.s.accent}99;">{self.convert(label)}</span>'
            )

        text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", link, text)

        # 4) 转义剩余裸文本
        text = _esc(text)

        # 5) 强调类
        text = re.sub(
            r"\*\*(.+?)\*\*",
            lambda m: f'<strong style="color:{self.s.heading_color};font-weight:600;">{m.group(1)}</strong>',
            text,
            flags=re.S,
        )
        text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text, flags=re.S)
        text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text, flags=re.S)

        # 6) 还原占位符
        for _ in range(6):  # 链接文字里可能又套了占位符
            if not _PH_RE.search(text):
                break
            text = _PH_RE.sub(lambda m: slots[int(m.group(1))], text)
        return text


# ---------------------------------------------------------------- 块级解析
def _is_table_sep(line: str) -> bool:
    s = line.strip()
    return bool(re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", s))


def _split_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _render_code_block(code: str, lang: str, s: Style) -> str:
    lang_tag = (
        f'<div style="font-size:12px;color:#7D8590;margin-bottom:8px;'
        f'font-family:Menlo,Consolas,monospace;">{_esc(lang)}</div>'
        if lang
        else ""
    )
    # 关键：手机上没有横向滚动条，用户不知道代码还能往右滑。
    # 所以用 pre-wrap 让长行自动折行，宁可折断也不藏内容。
    return (
        f'<section style="margin:1.6em 0;border-radius:8px;overflow:hidden;'
        f'background:{s.code_bg};">'
        f'<section style="padding:16px 18px;">'
        f"{lang_tag}"
        f'<pre style="margin:0;font-size:13px;line-height:1.65;color:{s.code_fg};'
        f'font-family:Menlo,Consolas,monospace;white-space:pre-wrap;'
        f'word-break:break-word;overflow-wrap:anywhere;">'
        f'<code style="font-family:Menlo,Consolas,monospace;color:inherit;'
        f'background:none;padding:0;">{_esc(code)}</code></pre></section></section>'
    )


def render(md: str, style: Optional[Style] = None, image_handler: Optional[ImageHandler] = None) -> str:
    """把 markdown 正文渲染成可直接粘进公众号的 HTML 片段。"""
    s = style or Style()
    inline = _Inline(s, image_handler)

    lines = md.replace("\r\n", "\n").split("\n")
    out: List[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # --- 空行
        if not stripped:
            i += 1
            continue

        # --- 围栏代码块
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            buf: List[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过结束围栏
            out.append(_render_code_block("\n".join(buf), lang, s))
            continue

        # --- 分割线
        if re.fullmatch(r"(-\s*){3,}|(\*\s*){3,}|(_\s*){3,}", stripped):
            out.append(
                f'<hr style="border:none;border-top:1px solid {s.divider};margin:2em 0;" />'
            )
            i += 1
            continue

        # --- 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            text = inline.convert(m.group(2).strip())
            if level <= 2:
                # h1 降级成 h2：文章大标题应该填在公众号标题栏，正文里不需要 H1
                out.append(
                    f'<h2 style="font-size:19px;font-weight:600;color:{s.heading_color};'
                    f'margin:1.9em 0 0.9em;padding-left:12px;'
                    f'border-left:4px solid {s.accent};line-height:1.5;">{text}</h2>'
                )
            elif level == 3:
                out.append(
                    f'<h3 style="font-size:17px;font-weight:600;color:{s.heading_color};'
                    f'margin:1.6em 0 0.7em;line-height:1.5;">'
                    f'<span style="color:{s.accent};">▎</span>{text}</h3>'
                )
            else:
                out.append(
                    f'<h4 style="font-size:16px;font-weight:600;color:{s.heading_color};'
                    f'margin:1.4em 0 0.6em;">{text}</h4>'
                )
            i += 1
            continue

        # --- 表格
        if "|" in stripped and i + 1 < n and _is_table_sep(lines[i + 1]):
            header = _split_row(stripped)
            i += 2
            rows: List[List[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            th = "".join(
                f'<th style="border:1px solid {s.table_border};background:{s.table_head_bg};'
                f'padding:9px 11px;font-size:14px;font-weight:600;color:{s.heading_color};'
                f'text-align:left;word-break:break-word;">{inline.convert(c)}</th>'
                for c in header
            )
            body = ""
            for r in rows:
                r = r + [""] * (len(header) - len(r))
                tds = "".join(
                    f'<td style="border:1px solid {s.table_border};padding:9px 11px;'
                    f'font-size:14px;color:{s.color};vertical-align:top;">{inline.convert(c)}</td>'
                    for c in r[: len(header)]
                )
                body += f"<tr>{tds}</tr>"
            out.append(
                f'<section style="overflow-x:auto;margin:1.6em 0;">'
                f'<table style="border-collapse:collapse;width:100%;'
                f'table-layout:auto;font-size:14px;">'
                f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></section>"
            )
            continue

        # --- 引用
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = "<br />".join(inline.convert(x) for x in buf if x.strip())
            out.append(
                f'<blockquote style="margin:1.6em 0;padding:14px 18px;'
                f'background:{s.quote_bg};border-left:3px solid {s.accent};'
                f'border-radius:0 6px 6px 0;color:{s.quote_fg};font-size:15px;'
                f'line-height:1.7;">{inner}</blockquote>'
            )
            continue

        # --- 列表（支持一层嵌套，缩进 2 空格以上算子项）
        if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
            items: List[str] = []
            ordered = bool(re.match(r"^\s*\d+\.", line))
            while i < n and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]):
                raw = lines[i]
                indent = len(raw) - len(raw.lstrip())
                content = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", raw)
                bullet = f'<span style="color:{s.accent};font-weight:600;">•</span>'
                if indent >= 2:
                    mark = "◦"
                    items.append(
                        f'<li style="margin:0.3em 0 0.3em 1.4em;list-style:none;'
                        f'color:{s.accent};">{mark} '
                        f'<span style="color:{s.color};">{inline.convert(content)}</span></li>'
                    )
                else:
                    items.append(
                        f'<li style="margin:0.45em 0;list-style:none;">{bullet} '
                        f'<span style="color:{s.color};">{inline.convert(content)}</span></li>'
                    )
                i += 1
            out.append(
                f'<section style="margin:1.2em 0;padding-left:0.2em;'
                f'font-size:{s.font_size}px;line-height:1.8;">{"".join(items)}</section>'
            )
            continue

        # --- 独占一行的图片（居中展示，不加额外段落间距）
        m = re.fullmatch(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", stripped)
        if m:
            out.append(inline.convert(stripped))
            i += 1
            continue

        # --- 普通段落：连续非空行合成一段（中文习惯不按硬换行断段）
        buf = []
        while i < n and lines[i].strip() and not _starts_block(lines, i):
            buf.append(lines[i].strip())
            i += 1
        text = inline.convert("".join(buf))
        out.append(
            f'<p style="margin:0 0 1.4em;font-size:{s.font_size}px;'
            f'line-height:{s.line_height};color:{s.color};'
            f'letter-spacing:0.02em;">{text}</p>'
        )

    body = "\n".join(out)
    wrapper_style = (
        f"font-size:{s.font_size}px;line-height:{s.line_height};color:{s.color};"
        f"word-break:break-word;"
    )
    if s.max_width:
        wrapper_style += f"max-width:{s.max_width}px;margin:0 auto;"
    return f'<section style="{wrapper_style}">{body}</section>'


def _starts_block(lines: List[str], i: int) -> bool:
    """判断第 i 行是否开启一个新块，用于决定段落在哪里断开。"""
    line = lines[i]
    s = line.strip()
    if not s:
        return True
    if s.startswith("```") or s.startswith(">") or s.startswith("#"):
        return True
    if re.fullmatch(r"(-\s*){3,}|(\*\s*){3,}", s):
        return True
    if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
        return True
    if re.fullmatch(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", s):
        return True
    if "|" in s and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
        return True
    return False


def plain_text(md: str, limit: int = 120) -> str:
    """提取纯文本摘要，用于公众号 digest 字段。"""
    text = md.replace("\r\n", "\n")
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^[#>\-\*\s]+", "", text, flags=re.M)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]
