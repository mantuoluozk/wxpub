# -*- coding: utf-8 -*-
"""命令行入口。

设计原则：默认帮你做对的事，但每一步都说清楚它在干什么。
  - publish 默认 dry-run 之外的所有检查都跑一遍，只有加 --yes 才真的推到草稿箱
  - 任何失败都打印「下一步该做什么」，不抛 traceback
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path
from typing import List, Optional

OK = "✓"
BAD = "✗"
WARN = "!"


def _setup_stdout() -> None:
    """Windows 终端默认 cp936，中文和 emoji 会炸。强制 utf-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# ---------------------------------------------------------------------- cover
def _frontmatter_of(path: Path) -> dict:
    """读 markdown 的 frontmatter。读不出来就返回空字典，走命令行参数。"""
    from .frontmatter import parse_frontmatter

    try:
        meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        return meta or {}
    except (OSError, UnicodeDecodeError):
        return {}


def cmd_cover(args) -> int:
    from .cover import LAYOUTS, SIZES, render_cover
    from .theme import THEMES

    meta: dict = {}
    if getattr(args, "file", None):
        src = Path(args.file)
        if not src.is_file():
            print(f"{WARN} 找不到文件：{src}")
            return 2
        meta = _frontmatter_of(src)

    # 优先级：命令行 > frontmatter > 默认值。
    # 所以这三个参数的 argparse 默认值必须是 None，否则分不清「没传」和「传了默认值」。
    args.title = args.title or meta.get("title") or ""
    args.subtitle = args.subtitle or meta.get("subtitle")
    args.badge = args.badge or meta.get("date")
    args.theme = args.theme or meta.get("theme") or "midnight"
    args.layout = args.layout or meta.get("layout") or "stack"
    args.size = args.size or "hd"

    if args.grid:
        return _render_grid(args)

    if not args.title:
        print(
            "需要 --title，或者传一个带 frontmatter 的 markdown 文件。例如：\n"
            "  wxpub cover --title '你的密钥|在替别人**烧钱**' --subtitle '副标题'\n"
            "  wxpub cover article.md -o cover.png"
        )
        return 2

    if args.all_themes or args.all_layouts:
        return _render_all(args)

    if args.out:
        out = args.out
    elif getattr(args, "file", None):
        out = str(Path(args.file).parent / (meta.get("cover") or "cover.png"))
    else:
        out = "cover.png"

    try:
        img = render_cover(
            title=args.title,
            subtitle=args.subtitle,
            badge=args.badge,
            theme=args.theme,
            layout=args.layout,
            size=args.size,
            width=args.width,
            height=args.height,
            title_size=args.title_size,
            align=args.align,
        )
    except (KeyError, ValueError) as exc:
        print(f"{WARN} {exc}")
        return 2
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(f"{OK} 封面已生成 {out}  {img.width}×{img.height}")
    print(f"  主题 {args.theme} / 布局 {args.layout}")
    if not args.badge:
        print(f"  提示：信息流里封面只露中间一条，关键文字已强制居中")
    return 0


def _render_all(args) -> int:
    from .cover import LAYOUTS, render_cover
    from .theme import THEMES

    out_dir = Path(args.out or "covers")
    out_dir.mkdir(parents=True, exist_ok=True)
    themes = list(THEMES) if args.all_themes else [args.theme or "midnight"]
    layouts = list(LAYOUTS) if args.all_layouts else [args.layout or "stack"]
    n = 0
    for t in themes:
        for l in layouts:
            img = render_cover(
                title=args.title, subtitle=args.subtitle, badge=args.badge,
                theme=t, layout=l, size=args.size,
            )
            img.save(out_dir / f"{t}-{l}.png")
            n += 1
    print(f"{OK} 生成 {n} 张：{out_dir}/")
    print(f"  挑一张满意的，用 --theme / --layout 指定即可")
    return 0


def _render_grid(args) -> int:
    """模板墙：把主题×布局压成一张拼图，README 和文章配图都用它。"""
    from PIL import Image, ImageDraw, ImageFont

    from .cover import LAYOUTS, render_cover
    from .fonts import resolve_fonts
    from .theme import THEMES

    themes = list(THEMES) if args.grid == "all" else args.grid.split(",")
    layouts = list(LAYOUTS)
    cols = 4
    cw, ch = 320, 136  # 单格尺寸（保持 2.35:1）
    pad, label_h, head_h = 14, 30, 56
    rows = (len(themes) * len(layouts) + cols - 1) // cols
    W = pad + cols * (cw + pad)
    H = head_h + pad + rows * (ch + label_h + pad)

    canvas = Image.new("RGB", (W, H), (247, 248, 250))
    draw = ImageDraw.Draw(canvas)
    bold, reg = resolve_fonts()
    fb = ImageFont.truetype(bold, 26)
    fl = ImageFont.truetype(reg, 15)
    draw.text((pad, 18), args.grid_title, font=fb, fill=(26, 30, 38))

    idx = 0
    for t in themes:
        for l in layouts:
            r, c = idx // cols, idx % cols
            x = pad + c * (cw + pad)
            y = head_h + pad + r * (ch + label_h + pad)
            img = render_cover(
                title=args.title, subtitle=args.subtitle, badge=args.badge,
                theme=t, layout=l, width=cw, height=ch,
            )
            canvas.paste(img, (x, y))
            draw.text((x + 2, y + ch + 6), f"{t} · {l}", font=fl, fill=(120, 128, 140))
            idx += 1

    out = args.out or "docs/templates.png"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"{OK} 模板墙 {out}  {W}×{H}  共 {idx} 种组合")
    return 0


# -------------------------------------------------------------------- publish
def cmd_publish(args) -> int:
    from .client import WeChatClient, fetch_current_ip
    from .config import ConfigError, load_credentials
    from .errors import WeChatError
    from .images import ImageIssue
    from .publisher import build_bundle, write_preview

    # 先组装。dry-run 也要走完整路径，否则验证不到真实问题。
    client = None
    upload = None
    if not args.dry_run:
        try:
            cred = load_credentials()
        except ConfigError as exc:
            print(f"{BAD} {exc}")
            return 2
        client = WeChatClient(cred, verbose=args.verbose)
        upload = client.upload_body_image

    try:
        bundle = build_bundle(
            args.file,
            out_dir=args.out,
            theme=args.theme,
            layout=args.layout,
            cover=args.cover,
            author=args.author,
            font_size=args.font_size,
            size=args.size,
            upload_image=upload,
        )
    except FileNotFoundError as exc:
        print(f"{BAD} {exc}")
        return 2
    except ImageIssue as exc:
        print(f"{BAD} {exc}")
        return 2

    html_path = bundle.out_dir / "article.html"
    html_path.write_text(bundle.html, encoding="utf-8")
    preview = write_preview(bundle)

    print("=" * 62)
    print(bundle.summary())
    print("=" * 62)

    if bundle.warnings:
        print(f"\n{WARN} 发布前检查发现 {len(bundle.warnings)} 条，建议先看一遍：")
        for w in bundle.warnings:
            print(f"  · {w}")
    else:
        print(f"\n{OK} 发布前检查全部通过")

    print(f"\n本地预览：{preview}")
    print(f"HTML：    {html_path}")

    if args.dry_run:
        print(f"\n{OK} dry-run 完成，没有上传任何东西。")
        print("  确认无误后去掉 --dry-run 重跑，或加 --yes 直接推到草稿箱。")
        return 0

    # 交互式终端下确认一次；CI / 管道里直接过（配合 --yes 或自动化场景）
    if not args.yes and sys.stdin.isatty():
        try:
            ans = input("\n推送到草稿箱？[y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans not in ("y", "yes", "是"):
            print("已取消，什么都没上传。")
            return 0

    # ---- 真发布
    assert client is not None
    try:
        print(f"\n→ 上传封面…")
        thumb_id = client.upload_cover(str(bundle.cover_path))
        print(f"{OK} 封面 media_id：{thumb_id[:28]}…")

        print(f"→ 创建草稿…")
        draft_id = client.create_draft(
            title=bundle.title,
            content=bundle.html,
            thumb_media_id=thumb_id,
            author=bundle.author,
            digest=bundle.digest,
            source_url=bundle.source_url,
            open_comment=args.open_comment,
        )
        print(f"{OK} 草稿已创建")
        print(f"  draft_media_id：{draft_id}")
        print(f"  去后台看看：https://mp.weixin.qq.com/ → 内容管理 → 草稿箱")

        log = bundle.out_dir / "publish-log.md"
        with open(log, "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(
                f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"- draft_media_id: `{draft_id}`\n"
                f"- cover_media_id: `{thumb_id}`\n"
                f"- title: {bundle.title}\n"
                f"- theme: {bundle.theme}\n"
            )
        print(f"  已记录到 {log}")

        if args.publish:
            print("→ 提交发布…")
            pid = client.publish(draft_id)
            print(f"{OK} 已提交，publish_id：{pid}")
        return 0

    except WeChatError as exc:
        current_ip = fetch_current_ip() if exc.errcode == 40164 else None
        print(f"\n{BAD} 失败\n")
        print(exc.explain(current_ip=current_ip))
        return 1
    except Exception as exc:  # 网络层
        msg = str(exc)
        print(f"\n{BAD} {msg}")
        if "proxy" in msg.lower() or "连接" in msg:
            print("  试试关掉代理再跑：")
            print("    Windows:  set HTTP_PROXY= && set HTTPS_PROXY=")
            print("    macOS/Linux: env -u HTTP_PROXY -u HTTPS_PROXY wxpub publish ...")
        return 1


# --------------------------------------------------------------------- doctor
def cmd_doctor(args) -> int:
    from .client import WeChatClient, fetch_current_ip
    from .config import ConfigError, load_credentials
    from .errors import WeChatError
    from .fonts import font_report

    print("wxpub 环境体检\n" + "=" * 62)

    # 1. 运行时
    import PIL
    import requests

    print(f"{OK} Python {sys.version.split()[0]}")
    print(f"{OK} Pillow {PIL.__version__}")
    print(f"{OK} requests {requests.__version__}")

    # 2. 字体
    print(font_report())

    # 3. 凭证
    print("\n[凭证]")
    try:
        cred = load_credentials()
    except ConfigError:
        print(f"{BAD} 未配置。运行 wxpub init 查看配置方法")
        return 1
    print(f"{OK} AppID     {cred.app_id if args.show_credentials else cred.masked_app_id()}")
    print(f"{OK} AppSecret {cred.masked_secret()}")
    print(f"     来源      {cred.source}")
    if not args.show_credentials:
        print("     已打码：这段输出可以直接贴到 issue / 文档里。加 --show-credentials 看完整值")

    # 4. 出口 IP（40164 的头号原因）
    print("\n[网络]")
    ip = fetch_current_ip()
    if ip:
        print(f"{OK} 当前出口 IP  {ip}")
        print("     如果发布报 40164，就是这个 IP 还没进白名单")
        print("     https://mp.weixin.qq.com/advanced/advanced?action=ip_whitelist&t=advanced/ip_whitelist")
    else:
        print(f"{WARN} 取不到出口 IP（网络受限）。发布若报 40164 无法自动定位")

    # 5. 接口连通性 + 权限
    print("\n[接口]")
    client = WeChatClient(cred, verbose=False)
    try:
        client.get_token(force=True)
        print(f"{OK} access_token 获取成功")
    except WeChatError as exc:
        print(f"{BAD} 取 token 失败\n{exc.explain(current_ip=ip)}")
        return 1
    except Exception as exc:
        print(f"{BAD} 取 token 失败：{exc}")
        return 1

    # 只读探测草稿权限，不产生副作用
    try:
        import json as _json

        data = client._post(
            "/cgi-bin/draft/batchget",
            {"access_token": client.get_token()},
            stage="探测草稿箱权限",
            data=_json.dumps({"offset": 0, "count": 1, "no_content": 1}).encode(),
            headers={"Content-Type": "application/json"},
        )
        print(f"{OK} 草稿箱接口可用（现有草稿 {data.get('total_count', 0)} 篇）")
    except WeChatError as exc:
        if exc.errcode == 48001:
            print(f"{WARN} 草稿箱接口未授权 —— 大概率是未认证订阅号")
            print("     你仍然可以用 wxpub publish --dry-run 生成成品 HTML，手动粘进后台")
        else:
            print(f"{WARN} 草稿箱探测失败：{exc.explain(current_ip=ip)}")

    print("\n" + "=" * 62)
    print(f"{OK} 体检完成")
    return 0


# ---------------------------------------------------------------------- init
def cmd_init(args) -> int:
    from .config import CONFIG_DIR, ensure_config_dir

    ensure_config_dir()
    env_file = CONFIG_DIR / ".env"
    if env_file.exists() and not args.force:
        print(f"{WARN} 已存在 {env_file}，没动它。要覆盖加 --force")
    else:
        env_file.write_text(
            "# 微信公众号凭证\n"
            "# 位置：mp.weixin.qq.com → 设置与开发 → 基本配置\n"
            "WECHAT_APP_ID=\n"
            "WECHAT_APP_SECRET=\n",
            encoding="utf-8",
        )
        print(f"{OK} 已创建 {env_file}")

    sample = Path(args.example) if args.example else Path("article.md")
    if not sample.exists():
        sample.write_text(SAMPLE_MD, encoding="utf-8")
        print(f"{OK} 已创建示例文章 {sample}")
    print("\n下一步：")
    print("  1. 把 AppID / AppSecret 填进上面的 .env")
    print("  2. wxpub doctor            # 体检，顺便看当前出口 IP")
    print("  3. wxpub cover --title '标题' -o cover.png")
    print("  4. wxpub publish article.md --dry-run")
    return 0


SAMPLE_MD = """---
title: 你的密钥在替别人烧钱
subtitle: 一个月 9 家 AI 开发平台被攻破
date: 2026-11-02
author: 阿派
tags: [安全, API]
theme: midnight
layout: stack
summary: 三条独立的安全事件，共同指向同一个结论。
---

# 正文标题会被降级成二级标题

正文支持**加粗**、*斜体*、`行内代码`、~~删除线~~。

## 二级标题

段落靠 margin 撑间距，不要用 <br> 硬换行。

> 引用块会自动加左侧色条。

```python
print("代码块自动深色背景，长行自动折行")
```

| 列一 | 列二 |
|---|---|
| 内容 | 内容 |

![图片放在 imgs/ 目录下](imgs/demo.png)
"""


# -------------------------------------------------------------------- themes
def cmd_themes(args) -> int:
    from .cover import LAYOUTS, SIZES
    from .theme import THEMES

    print("主题（--theme）")
    for k, v in THEMES.items():
        print(f"  {k:<10} {v.label:<6} {'深色' if v.dark else '浅色'}")
    print("\n布局（--layout）")
    desc = {
        "stack": "双行大标题 + 副标题 + 顶部胶囊（默认，最稳）",
        "hero": "单行超大标题 + 彩色副标题（结论式选题）",
        "minimal": "只有标题和副标题（缩略图辨识度最高）",
        "split": "左对齐 + 竖色条（对比判断型）",
        "banner": "顶部色带（重磅消息）",
        "quote": "引号水印（观点、访谈）",
    }
    for k in LAYOUTS:
        print(f"  {k:<10} {desc.get(k, '')}")
    print("\n尺寸（--size）")
    for k, (w, h) in SIZES.items():
        print(f"  {k:<10} {w}×{h}")
    print("\n标题里用 | 分行，用 **文字** 标记高亮片段")
    return 0


# ----------------------------------------------------------------------- 入口
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wxpub",
        description="Markdown 一键发进微信公众号草稿箱，封面自动生成。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""常用：
  wxpub doctor                              体检：凭证、字体、网络、接口权限
  wxpub cover --title '标题' -o cover.png    只出封面
  wxpub publish article.md --dry-run        本地渲染，不上传
  wxpub publish article.md                  推到草稿箱
  wxpub themes                              看所有主题和布局
  wxpub cover --grid all -o docs/templates.png   生成模板墙
""",
    )
    sub = p.add_subparsers(dest="cmd")

    c = sub.add_parser("cover", help="生成封面图")
    c.add_argument("file", nargs="?", help="markdown 文件，从 frontmatter 读标题/主题（可省略）")
    c.add_argument("--title", help="主标题，用 | 分行，**文字** 标记高亮")
    c.add_argument("--subtitle", help="副标题")
    c.add_argument("--badge", help="顶部胶囊文字，通常填日期")
    c.add_argument("--theme", help="主题名，见 wxpub themes（默认取 frontmatter，否则 midnight）")
    c.add_argument("--layout", help="布局名，见 wxpub themes（默认取 frontmatter，否则 stack）")
    c.add_argument("--size", help="hd/fhd/small，默认 hd")
    c.add_argument("--width", type=int)
    c.add_argument("--height", type=int)
    c.add_argument("--title-size", type=int, dest="title_size", help="强制标题字号")
    c.add_argument("--align", default="center", choices=["center", "left"])
    c.add_argument("-o", "--out", help="输出路径")
    c.add_argument("--all-themes", action="store_true", help="批量出所有主题")
    c.add_argument("--all-layouts", action="store_true", help="批量出所有布局")
    c.add_argument("--grid", nargs="?", const="all", help="生成模板墙，可传主题列表 a,b,c")
    c.add_argument("--grid-title", default="wxpub 封面模板", help="模板墙标题")
    c.set_defaults(func=cmd_cover)

    pb = sub.add_parser("publish", help="发到公众号草稿箱")
    pb.add_argument("file", help="markdown 文件")
    pb.add_argument("--dry-run", action="store_true", help="只本地渲染，不上传")
    pb.add_argument("-o", "--out", help="输出目录")
    pb.add_argument("--theme", help="覆盖 frontmatter 里的主题")
    pb.add_argument("--layout", help="覆盖布局")
    pb.add_argument("--cover", help="指定已有封面图，不自动生成")
    pb.add_argument("--author", help="作者名，≤8 字")
    pb.add_argument("--font-size", type=int, default=16, dest="font_size")
    pb.add_argument("--size", default="hd", help="封面尺寸")
    pb.add_argument("--open-comment", action="store_true", dest="open_comment")
    pb.add_argument("--publish", action="store_true", help="建完草稿后直接发布（需权限）")
    pb.add_argument("--yes", action="store_true", help="跳过确认")
    pb.add_argument("--verbose", action="store_true")
    pb.set_defaults(func=cmd_publish)

    d = sub.add_parser("doctor", help="体检：凭证、字体、网络、接口权限")
    d.add_argument(
        "--show-credentials",
        action="store_true",
        help="显示完整 AppID（默认打码，避免贴日志时被 GitHub 误报为泄露密钥）",
    )
    d.set_defaults(func=cmd_doctor)

    i = sub.add_parser("init", help="初始化配置和示例文章")
    i.add_argument("--force", action="store_true", help="覆盖已有 .env")
    i.add_argument("--example", help="示例文章路径")
    i.set_defaults(func=cmd_init)

    t = sub.add_parser("themes", help="列出主题和布局")
    t.set_defaults(func=cmd_themes)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    _setup_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
