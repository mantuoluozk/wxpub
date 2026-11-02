# -*- coding: utf-8 -*-
"""图片处理：格式嗅探、WebP 转换、体积压缩。

公众号的两个硬限制，踩过的人都知道：
  1. 正文图片只收 bmp/png/jpeg/gif —— 从网页抓下来的 WebP 直接上传会失败，
     而且很多 WebP 文件名是 .png，光看后缀判断不出来，必须读文件头。
  2. 正文图片单张 ≤ 1MB，封面永久素材 ≤ 10MB。超了会给一个没头没尾的错误码。
"""

from __future__ import annotations

import os
import shutil
from typing import Optional, Tuple

from PIL import Image

# 微信图文消息正文允许的图片格式（media/uploadimg）
WECHAT_OK_FORMATS = {"PNG", "JPEG", "GIF", "BMP"}

MAX_BODY_IMAGE_BYTES = 1 * 1024 * 1024      # 正文图 1MB
MAX_MATERIAL_IMAGE_BYTES = 10 * 1024 * 1024  # 永久素材 10MB


class ImageIssue(Exception):
    """图片不满足微信要求，消息里写清楚该怎么修。"""


def sniff(path: str) -> str:
    """读文件头判断真实格式。不信任扩展名。"""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
    except OSError:
        return "UNKNOWN"

    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if head.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "GIF"
    if head.startswith(b"BM"):
        return "BMP"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    if head[:4] == b"RIFF":
        return "RIFF"
    return "UNKNOWN"


def describe(path: str) -> str:
    fmt = sniff(path)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    try:
        with Image.open(path) as im:
            wh = f"{im.width}x{im.height}"
    except Exception:
        wh = "?"
    return f"{os.path.basename(path)} [{fmt} {wh} {size / 1024:.0f}KB]"


def normalize(
    path: str,
    out_dir: Optional[str] = None,
    max_bytes: int = MAX_BODY_IMAGE_BYTES,
) -> Tuple[str, list]:
    """把一张图变成微信能收的样子，返回 (新路径, 处理动作列表)。

    - WebP / 未知格式 → 转 PNG
    - 体积超限 → 先降 JPEG 质量，再考虑缩尺寸
    - 已经是合格格式且不超限 → 原样返回，不动文件
    """
    actions: list = []
    if not os.path.exists(path):
        raise ImageIssue(f"图片不存在：{path}")

    fmt = sniff(path)
    out_dir = out_dir or os.path.dirname(os.path.abspath(path))
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]

    if fmt not in WECHAT_OK_FORMATS or os.path.getsize(path) > max_bytes:
        with Image.open(path) as im:
            im.load()
            mode = "RGBA" if im.mode in ("RGBA", "LA", "P") and fmt == "PNG" else "RGB"
            img = im.convert(mode)

            if fmt not in WECHAT_OK_FORMATS:
                actions.append(f"格式 {fmt} → PNG（微信不收这种格式）")
                target = os.path.join(out_dir, base + ".png")
                img.save(target, "PNG", optimize=True)
            else:
                target = os.path.join(out_dir, base + ".jpg")
                if mode == "RGBA":
                    img = img.convert("RGB")
                quality = 90
                img.save(target, "JPEG", quality=quality, optimize=True)
                while os.path.getsize(target) > max_bytes and quality > 45:
                    quality -= 10
                    img.save(target, "JPEG", quality=quality, optimize=True)
                if os.path.getsize(target) > max_bytes:
                    # 还大就等比缩小
                    scale = 0.85
                    while os.path.getsize(target) > max_bytes and scale > 0.3:
                        w, h = int(img.width * scale), int(img.height * scale)
                        img.resize((w, h), Image.LANCZOS).save(
                            target, "JPEG", quality=quality, optimize=True
                        )
                        scale *= 0.85
                    actions.append(f"体积超 1MB → 缩放并压到 q{quality}")
                else:
                    actions.append(f"体积超 1MB → JPEG q{quality} 重压")

        if os.path.getsize(target) > max_bytes:
            raise ImageIssue(
                f"图片压到最小仍超过 1MB：{target}\n"
                "建议先手动裁掉无关区域，或降到 1200px 宽以内再试。"
            )
        return target, actions

    return path, actions


def copy_next_to(src: str, dst_dir: str) -> str:
    """dry-run 时把图片复制到输出目录，保证本地预览能打开。"""
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copy2(src, dst)
    return dst


def cover_bytes(path: str) -> bytes:
    """封面读成 bytes 前做一次体积兜底。"""
    size = os.path.getsize(path)
    if size > MAX_MATERIAL_IMAGE_BYTES:
        raise ImageIssue(
            f"封面 {size / 1024 / 1024:.1f}MB 超过永久素材 10MB 上限：{path}"
        )
    with open(path, "rb") as f:
        return f.read()
