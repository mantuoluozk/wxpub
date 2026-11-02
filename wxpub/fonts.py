# -*- coding: utf-8 -*-
"""跨平台中文字体探测。

这是把「封面中文字乱码 / 方框」这类问题一次性消掉的地方。
Windows / macOS / Linux 三套候选链，逐个存在性检查，全都没有时给出可操作的报错，
而不是抛一个 FileNotFoundError 让人猜。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

# 候选链按「优先级 + 平台惯例」排列，不做平台判断，直接用存在性筛。
# 这样 WSL、容器挂载、自定义字体目录等边缘情况也能自然命中。
_BOLD_CANDIDATES: List[str] = [
    # Windows
    r"C:\Windows\Fonts\msyhbd.ttc",      # 微软雅黑 Bold
    r"C:\Windows\Fonts\msyhbd.ttf",
    r"C:\Windows\Fonts\simhei.ttf",      # 黑体
    r"C:\Windows\Fonts\Deng.ttf",        # 等线
    r"C:\Windows\Fonts\arialbd.ttf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]

_REGULAR_CANDIDATES: List[str] = [
    # Windows
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
]

# 环境变量覆盖，给「我就要用这个字体」的人留后门
ENV_BOLD = "WXPUB_FONT_BOLD"
ENV_REGULAR = "WXPUB_FONT_REGULAR"

FONT_HELP = """\
找不到可用的中文字体。三种解法，任选一种：

  Windows   一般自带 msyhbd.ttc，若装在非默认路径，设置环境变量：
             set WXPUB_FONT_BOLD=C:\\path\\to\\msyhbd.ttc
  macOS     系统自带 PingFang，通常无需配置
  Linux     安装思源黑体（Noto Sans CJK）：
             Debian/Ubuntu:  sudo apt install fonts-noto-cjk
             CentOS/RHEL:    sudo yum install google-noto-sans-cjk-fonts
             Alpine:         apk add font-noto-cjk

也可以用环境变量直接指定任意 .ttf/.ttc 字体文件：
  WXPUB_FONT_BOLD     标题用
  WXPUB_FONT_REGULAR  正文/副标题用
"""


def _first_existing(candidates: List[str]) -> Optional[str]:
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


@lru_cache(maxsize=1)
def resolve_fonts() -> "tuple[str, str]":
    """返回 (bold_path, regular_path)。结果带缓存，整进程只探测一次。"""
    bold = os.environ.get(ENV_BOLD) or _first_existing(_BOLD_CANDIDATES)
    regular = os.environ.get(ENV_REGULAR) or _first_existing(_REGULAR_CANDIDATES)

    # 只找到一款时，另一款退回同一款（宁可粗细一样，也不要报错中断）
    if bold and not regular:
        regular = bold
    if regular and not bold:
        bold = regular

    if not bold or not regular:
        raise FontNotFoundError(FONT_HELP)

    return bold, regular


class FontNotFoundError(RuntimeError):
    """找不到中文字体，消息本身就是一份安装指引。"""


def font_report() -> str:
    """给 doctor 子命令用的体检报告。"""
    try:
        bold, regular = resolve_fonts()
    except FontNotFoundError as exc:
        return f"✗ 中文字体：未找到\n{exc}"
    lines = [
        "✓ 中文字体：",
        f"    标题  {bold}",
        f"    正文  {regular}",
    ]
    if os.environ.get(ENV_BOLD) or os.environ.get(ENV_REGULAR):
        lines.append("    （来自环境变量覆盖）")
    return "\n".join(lines)
