# -*- coding: utf-8 -*-
"""frontmatter 解析。

只实现公众号写作实际会用到的 YAML 子集，不引入 PyYAML：
  - key: value
  - key: "带引号的值" / key: '单引号值'
  - key: [a, b, c] 或 key:\n  - a\n  - b（列表）
  - # 开头的注释行

够用就好，遇到解析不了的行不报错、原样跳过，避免因为一个奇怪字段导致整篇文章发不出去。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

FM_RE = re.compile(r"^---[ \t]*\r?\n(.*?)---[ \t]*(?:\r?\n|$)", re.S)


def _unquote(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _strip_comment(value: str) -> str:
    """去掉行尾注释，但不动引号里的内容。"""
    in_q = None
    for i, ch in enumerate(value):
        if in_q:
            if ch == in_q:
                in_q = None
        elif ch in "\"'":
            in_q = ch
        elif ch == "#" and (i == 0 or value[i - 1] in " \t"):
            return value[:i]
    return value


def parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """返回 (元数据字典, 正文)。没有 frontmatter 时返回 ({}, 原文)。"""
    text = text.replace("\r\n", "\n")
    m = FM_RE.match(text)
    if not m:
        return {}, text

    raw = m.group(1)
    body = text[m.end():]
    meta: Dict[str, Any] = {}
    current_list_key: str | None = None

    for line in raw.split("\n"):
        if not line.strip() or line.strip().startswith("#"):
            continue

        # 列表项  - value
        stripped = line.strip()
        if stripped.startswith("- ") and current_list_key:
            # 上一行只写了 "tags:"（值留空），这里要把它从空字符串升级成列表
            if not isinstance(meta.get(current_list_key), list):
                meta[current_list_key] = []
            meta[current_list_key].append(_unquote(stripped[2:]))
            continue

        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = _strip_comment(value).strip()
        if not key:
            continue

        if not value:
            # 可能是下面跟着 - 列表，也可能就是个空值
            current_list_key = key
            meta[key] = ""
        elif value.startswith("[") and value.endswith("]"):
            items = [_unquote(x) for x in value[1:-1].split(",") if x.strip()]
            meta[key] = items
            current_list_key = None
        else:
            meta[key] = _unquote(value)
            current_list_key = None

    # 空值统一成空字符串，方便下游写 meta.get("x") or 默认值
    for k, v in list(meta.items()):
        if v == "":
            meta[k] = ""
    return meta, body


def split_tags(value: Any) -> List[str]:
    """tags 可能写成 "a,b"、[a, b] 或多行列表，统一成列表。"""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [t.strip() for t in re.split(r"[,，\s]+", value) if t.strip()]
    return []
