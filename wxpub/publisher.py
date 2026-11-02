# -*- coding: utf-8 -*-
"""把「一个 markdown 文件」变成「一篇可以进草稿箱的文章」。

这里做两件事：
  1. 组装：封面、正文、图片、摘要、元信息，全部落到一个 Bundle 里
  2. 体检：发布前把能预见的坑先扫一遍（引用过长、外链失效、图片缺失、字段超限）

dry-run 和真发布走的是同一条组装路径，只是图片处理方式不同
（本地复制 vs 上传换 CDN），这样 dry-run 才有验证价值。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, List, Optional

from .cover import SIZES, render_cover
from .frontmatter import parse_frontmatter, split_tags
from .images import ImageIssue, describe, normalize
from .markdown import Style, plain_text, render
from .sanitize import sanitize
from .theme import THEMES, get_theme

# 主题色带进正文，做到封面和内文同色系
THEME_ACCENT = {
    "midnight": "#4F9BE8",
    "ocean": "#0096DC",
    "ember": "#E8663C",
    "forest": "#14A06E",
    "violet": "#6E4EE0",
    "sunset": "#D2508C",
    "ink": "#5A64D8",
    "mono": "#444444",
    "crimson": "#B03040",
    "paper": "#2563EB",
    "sakura": "#DB447A",
}


@dataclass
class Bundle:
    """一次发布所需的全部材料。"""

    md_path: Path
    title: str
    subtitle: str
    author: str
    digest: str
    html: str
    cover_path: Optional[Path]
    out_dir: Path
    theme: str
    tags: List[str]
    warnings: List[str] = field(default_factory=list)
    images_local: List[str] = field(default_factory=list)
    source_url: str = ""

    def summary(self) -> str:
        w, h = SIZES["hd"]
        lines = [
            f"标题     {self.title}（{len(self.title)} 字）",
            f"副标题   {self.subtitle or '（无）'}",
            f"作者     {self.author or '（无）'}",
            f"摘要     {self.digest[:40]}{'...' if len(self.digest) > 40 else ''}（{len(self.digest)} 字）",
            f"主题     {self.theme}",
            f"封面     {self.cover_path}",
            f"正文     {len(self.html)} 字符 HTML",
            f"图片     {len(self.images_local)} 张",
            f"输出     {self.out_dir}",
        ]
        return "\n".join(lines)


def _pick_cover(
    meta: dict,
    md_dir: Path,
    title: str,
    subtitle: str,
    theme: str,
    layout: str,
    out_dir: Path,
    explicit: Optional[str],
    size: str,
) -> Path:
    # 1) 命令行显式指定
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = md_dir / p
        if not p.is_file():
            raise FileNotFoundError(f"指定的封面不存在：{p}")
        return p

    # 2) frontmatter 里的 cover
    cover_val = (meta.get("cover") or "").strip()
    if cover_val:
        p = Path(cover_val)
        if not p.is_absolute():
            p = md_dir / p
        if p.is_file():
            return p

    # 3) 自动画一张
    badge = (meta.get("badge") or meta.get("date") or "").strip()
    out = out_dir / "cover.png"
    img = render_cover(
        title=title,
        subtitle=subtitle or None,
        badge=badge or None,
        theme=theme,
        layout=layout,
        size=size,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


# ---------------------------------------------------------------- 体检规则
EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
CITE_LIMIT = 30  # 超过 30 个英文词的整段引用，容易卡原创声明


def check_citations(md: str) -> List[str]:
    """扫描引用块里的外文原引长度。

    公众号「编辑原创」对大段外文很敏感：一段超过 50 词基本会被拦，
    30 词是安全线。这里只在超过 30 词时提醒，不阻断发布。
    """
    warns: List[str] = []
    blocks = re.findall(r"((?:^>\s?.*(?:\n|$))+)", md, re.M)
    for i, blk in enumerate(blocks, 1):
        text = re.sub(r"^\s*>\s?", "", blk, flags=re.M)
        en_words = len(EN_WORD_RE.findall(text))
        if en_words > CITE_LIMIT:
            snippet = text.strip().replace("\n", " ")[:40]
            warns.append(
                f"第 {i} 段引用里有 {en_words} 个英文词（超过 {CITE_LIMIT} 词安全线）：「{snippet}…」\n"
                f"    建议缩成一句短引 + 中文复述 + 文末链接，否则「编辑原创」可能卡住保存"
            )
    return warns


def check_links(md: str) -> List[str]:
    """公众号正文里的站外链接不可点击，提前说一声，省得发出去才发现。"""
    urls = re.findall(r"(?<!!)\[[^\]]+\]\((https?://[^)\s]+)\)", md)
    outside = [u for u in urls if "mp.weixin.qq.com" not in u]
    if outside:
        return [
            f"正文有 {len(outside)} 个站外链接（如 {outside[0][:50]}）。"
            "公众号里站外链接不可点击，已渲染成带下划线的普通文字。"
            "建议改成「文末附链接」或二维码"
        ]
    return []


def check_meta(title: str, author: str, digest: str, html: str) -> List[str]:
    warns = []
    if len(title) > 64:
        warns.append(f"标题 {len(title)} 字，超过微信上限 64 字，发布会失败")
    elif len(title) > 30:
        warns.append(f"标题 {len(title)} 字偏长，信息流里可能显示不全（建议 20 字内）")
    if len(author) > 8:
        warns.append(f"作者名 {len(author)} 字，超过上限 8 字")
    if len(digest) > 120:
        warns.append(f"摘要 {len(digest)} 字，超过上限 120 字")
    if len(html) > 20000:
        warns.append(
            f"正文 HTML {len(html)} 字符，超过 20000 上限（按源码算）。"
            "删点长代码块，或把代码换成截图"
        )
    return warns


# ---------------------------------------------------------------- 主流程
def build_bundle(
    md_path: str,
    out_dir: Optional[str] = None,
    theme: Optional[str] = None,
    layout: Optional[str] = None,
    cover: Optional[str] = None,
    author: Optional[str] = None,
    font_size: int = 16,
    size: str = "hd",
    upload_image: Optional[Callable[[str], str]] = None,
    copy_images: bool = True,
) -> Bundle:
    """组装文章。upload_image 为空时按 dry-run 处理（本地复制图片）。"""
    path = Path(md_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"找不到文件：{path}")

    md_dir = path.parent
    raw = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)

    title = (meta.get("title") or _guess_title(body) or path.stem).strip()
    subtitle = (meta.get("subtitle") or meta.get("summary") or "").strip()
    theme_name = (theme or meta.get("theme") or "midnight").strip().lower()
    layout_name = (layout or meta.get("layout") or "stack").strip().lower()
    if theme_name not in THEMES:
        theme_name = "midnight"
    author_name = (author or meta.get("author") or "").strip()
    digest = (meta.get("summary") or meta.get("digest") or "").strip() or plain_text(body, 100)

    out = Path(out_dir).expanduser().resolve() if out_dir else md_dir / "out"
    out.mkdir(parents=True, exist_ok=True)

    cover_path = _pick_cover(
        meta, md_dir, title, subtitle, theme_name, layout_name, out, cover, size
    )

    images_local: List[str] = []
    warnings: List[str] = []

    def handle_image(src: str, alt: str) -> str:
        if src.startswith(("http://", "https://", "data:")):
            return src
        local = Path(src)
        if not local.is_absolute():
            local = md_dir / local
        if not local.is_file():
            warnings.append(f"图片找不到：{src}（渲染时留了空位，发布前请补上或删掉这行）")
            return src

        try:
            fixed, actions = normalize(str(local), out_dir=str(out / "imgs"))
        except ImageIssue as exc:
            warnings.append(f"图片处理失败：{exc}")
            return src
        warnings.extend(f"图片 {describe(fixed)}：{a}" for a in actions)
        images_local.append(fixed)

        if upload_image:
            return upload_image(fixed)
        if copy_images:
            return f"imgs/{Path(fixed).name}"
        return src

    html = render(body, Style(font_size=font_size, accent=THEME_ACCENT.get(theme_name, "#2563EB")), handle_image)
    # 兜底清洗：万一用户自己在 markdown 里写了 <a> 或从别处粘进了零宽字符
    html, sanitize_notes = sanitize(html, drop_local_images=upload_image is not None)
    warnings.extend(sanitize_notes)

    warnings.extend(check_citations(body))
    warnings.extend(check_links(body))
    warnings.extend(check_meta(title, author_name, digest, html))

    return Bundle(
        md_path=path,
        title=title,
        subtitle=subtitle,
        author=author_name,
        digest=digest,
        html=html,
        cover_path=cover_path,
        out_dir=out,
        theme=theme_name,
        tags=split_tags(meta.get("tags")),
        warnings=warnings,
        images_local=images_local,
        source_url=(meta.get("source_url") or "").strip(),
    )


def _guess_title(body: str) -> str:
    for line in body.splitlines():
        if line.strip().startswith("# "):
            return line.strip()[2:].strip()
    return ""


PREVIEW_CSS = """
body{margin:0;background:#eceef1;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
.phone{max-width:420px;margin:0 auto;background:#fff;min-height:100vh;padding-bottom:48px}
.cover{width:100%;display:block}
.head{padding:20px 20px 8px}
.t{font-size:22px;font-weight:600;color:#1a1a1a;line-height:1.45;margin:0 0 10px;letter-spacing:.01em}
.m{font-size:13px;color:#9aa0a6;display:flex;gap:10px;align-items:center}
.m .tag{color:#576b95}
.body{padding:8px 20px 0}
.notice{margin:16px 20px;padding:10px 14px;background:#fff8e6;border:1px solid #ffe1a8;border-radius:8px;font-size:12px;color:#8a6d3b;line-height:1.6}
"""


def write_preview(bundle: Bundle) -> Path:
    """生成一个手机宽度的本地预览页，dry-run 时直接双击就能看成品。"""
    import html as _html

    cover_rel = ""
    if bundle.cover_path:
        cover_rel = os.path.relpath(bundle.cover_path, bundle.out_dir).replace("\\", "/")

    notice = ""
    if bundle.warnings:
        items = "".join(f"<div>· {_html.escape(w)}</div>" for w in bundle.warnings)
        notice = f'<div class="notice"><strong>发布前检查（{len(bundle.warnings)} 条）</strong>{items}</div>'

    page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html.escape(bundle.title)}</title>
<style>{PREVIEW_CSS}</style></head>
<body><div class="phone">
<img class="cover" src="{cover_rel}" alt="封面">
<div class="head">
  <div class="t">{_html.escape(bundle.title)}</div>
  <div class="m"><span>{bundle.author or '未署名'}</span><span>{date.today().isoformat()}</span></div>
</div>
{notice}
<div class="body">{bundle.html}</div>
</div></body></html>"""
    out = bundle.out_dir / "preview.html"
    out.write_text(page, encoding="utf-8")
    return out
