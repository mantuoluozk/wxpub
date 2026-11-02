# -*- coding: utf-8 -*-
"""提交前的 HTML 清洗。

微信草稿接口 `draft/add` 有一套**完全没写进文档**的内容校验，违反时统一返回
`45166 invalid content hint` —— 不说哪个字段、不说哪段内容，只说「你 Hint 不对」。

实测下来会触发 45166 的东西：
  1. `<a>` 标签。不管 href 指向哪（连 mp.weixin.qq.com 自己也不行），只要 content
     里出现 <a> 就拦。这是头号杀手，也是这个模块存在的首要原因。
  2. 不可见 Unicode 字符。零宽空格 U+200B、BOM U+FEFF、Emoji 变体选择符 U+FE0F、
     双向控制符 U+202A-U+202E。从网页/Word 复制粘贴过来的文本里非常常见。
  3. `<script>` `<style>` `<iframe>` `<form>` `<object>` 这类标签。
  4. HTML 注释、class、id、data-*、aria-* 属性。
  5. ASCII 控制字符（保留 \t \n \r）。

清洗是幂等的，重复跑不会破坏内容。
"""

from __future__ import annotations

import re
from typing import List, Tuple

# 不可见但有意义的字符：全部删掉
INVISIBLE_RE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff\ufe0e\ufe0f\u00ad]")

# ASCII 控制字符，保留 \t\n\r
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# <a ...>文字</a> → 文字。保留内部内容，因为它可能是加粗或图片
ANCHOR_RE = re.compile(r"<a\b[^>]*>([\s\S]*?)</a\s*>", re.I)

# 整块删除的标签（含内容）
BLOCK_DROP_RE = re.compile(
    r"<(script|style|iframe|form|object|embed|noscript|svg|math|canvas|video|audio)\b"
    r"[^>]*>[\s\S]*?</\1\s*>",
    re.I,
)
# 自闭合或没有闭合的同类标签
BLOCK_DROP_OPEN_RE = re.compile(
    r"</?(script|style|iframe|form|object|embed|noscript|svg|math|canvas|video|audio)\b[^>]*>",
    re.I,
)

COMMENT_RE = re.compile(r"<!--[\s\S]*?-->")

# 会被微信过滤、且可能干扰校验的属性
ATTR_DROP_RE = re.compile(
    r'\s(?:class|id|data-[a-z0-9\-]+|aria-[a-z0-9\-]+)\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)',
    re.I,
)


def sanitize(html: str, drop_local_images: bool = True) -> Tuple[str, List[str]]:
    """返回 (清洗后的 HTML, 做过的处理说明)。

    drop_local_images: 提交给微信时置 True（本地路径的图发出去一定是裂图，不如去掉）；
    dry-run 本地预览时置 False，否则预览页里图片全空。
    """
    actions: List[str] = []
    original = html

    # 1) 链标签：微信草稿接口零容忍
    n_anchor = len(ANCHOR_RE.findall(html))
    if n_anchor:
        html = ANCHOR_RE.sub(r"\1", html)
        actions.append(f"移除了 {n_anchor} 个链接标签（微信草稿接口会因此报 45166）")

    # 2) 危险标签
    html, n_block = BLOCK_DROP_RE.subn("", html)
    html = BLOCK_DROP_OPEN_RE.sub("", html)
    if n_block:
        actions.append(f"删除了 {n_block} 个 script/style/iframe 类标签")

    # 3) 注释
    html, n_comment = COMMENT_RE.subn("", html)
    if n_comment:
        actions.append(f"删除了 {n_comment} 处 HTML 注释")

    # 4) 属性
    html, n_attr = ATTR_DROP_RE.subn("", html)
    if n_attr:
        actions.append(f"清除了 {n_attr} 个 class/id/data-* 属性")

    # 5) 不可见字符
    invisible = INVISIBLE_RE.findall(html)
    if invisible:
        html = INVISIBLE_RE.sub("", html)
        actions.append(
            f"清除了 {len(invisible)} 个不可见字符（零宽空格/BOM/变体选择符，"
            "从网页复制粘贴时极易带入）"
        )

    # 6) 控制字符
    n_ctrl = len(CONTROL_RE.findall(html))
    if n_ctrl:
        html = CONTROL_RE.sub("", html)
        actions.append(f"清除了 {n_ctrl} 个控制字符")

    # 7) 未上传成功的本地图片：发布出去会是个裂图，不如去掉
    def _drop_local_img(m: re.Match) -> str:
        src = m.group(1)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        actions.append(f"移除了未上传成功的本地图片 {src}")
        return ""

    if drop_local_images:
        html = re.sub(r'<img\b[^>]*\ssrc="([^"]*)"[^>]*>', _drop_local_img, html, flags=re.I)

    # 8) 收尾：连续空白和空段落
    html = re.sub(r"<p\b[^>]*>\s*</p>", "", html)
    html = re.sub(r"\n{3,}", "\n\n", html)

    if html == original:
        actions.clear()
    return html.strip(), actions


def has_anchor(html: str) -> bool:
    return bool(ANCHOR_RE.search(html))
