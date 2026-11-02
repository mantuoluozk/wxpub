# -*- coding: utf-8 -*-
"""微信 API 错误诊断。

这个模块是整個项目里最值钱的部分。微信的错误码文档写得像天书：
`{"errcode":40164,"errmsg":"invalid ip 1.2.3.4, not in whitelist"}` —— 新手的反应是「什么白名单？」
而老手的第一反应是「哦又要去后台加 IP」，但他得先想起来去哪个菜单。

所以这里不只是把错误码翻译成中文，而是给出一条可以直接照做的修复路径。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

IP_RE = re.compile(r"invalid ip ([0-9a-fA-F:.]{7,45})")


@dataclass
class Diagnostic:
    """一条错误码的完整解释。"""

    code: int
    title: str          # 一句话说人话
    cause: str          # 为什么会这样
    fix: List[str]      # 按顺序照做的步骤
    doc: Optional[str] = None


DIAGNOSTICS: Dict[int, Diagnostic] = {
    40164: Diagnostic(
        code=40164,
        title="调用方 IP 不在公众号白名单里",
        cause=(
            "微信只允许白名单内的 IP 调用接口。你的出口 IP 变了 —— 换网络、"
            "重拨宽带、开/关代理、云主机重建，都会变。"
        ),
        fix=[
            "拿到本机当前出口 IP：wxpub doctor 会自动打印，或手动 curl https://api.ipify.org",
            "打开 https://mp.weixin.qq.com → 设置与开发 → 基本配置 → IP 白名单 → 修改",
            "把刚才的 IP 加进去。IPv4 和 IPv6 分两栏，都要加",
            "保存后等 1-2 分钟再重试。微信有缓存，这期间会继续报 40164，不是没加成功",
        ],
        doc="https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/Get_access_token.html",
    ),
    40125: Diagnostic(
        code=40125,
        title="AppSecret 不正确",
        cause=(
            "Secret 填错了，或者被重置过。注意它是 32 位字符串，容易和 AppID 搞混，"
            "也容易在复制时带上空格或换行。"
        ),
        fix=[
            "打开 设置与开发 → 基本配置，核对 AppID 和 AppSecret（Secret 只显示一次，忘了就重置）",
            "重置 Secret 后，所有用了旧 Secret 的脚本都要改，包括 CI",
            "检查 .env 里有没有多余的空格、引号、换行",
        ],
    ),
    40001: Diagnostic(
        code=40001,
        title="access_token 无效（通常是 Secret 错或 token 被顶掉）",
        cause=(
            "微信的 access_token 是全局唯一的：第二次获取会让第一次的失效。"
            "多个脚本/多台机器同时获取，就会互相踢掉，表现为随机报 40001。"
        ),
        fix=[
            "确认 AppSecret 正确（见 40125）",
            "同一时间只用一个进程发布；或用本工具的 token 缓存 ~/.wxpub/token.json",
            "如果跑在 CI 和多台机器上，把 token 放到共享存储里，别各拿各的",
        ],
    ),
    40013: Diagnostic(
        code=40013,
        title="AppID 不正确",
        cause="AppID 填错，或者把「公众号 AppID」和「开放平台/小程序 AppID」搞混了。",
        fix=[
            "公众号的 AppID 以 wx 开头，在 设置与开发 → 基本配置 里",
            "确认没有把小程序的 AppID 填进来",
        ],
    ),
    48001: Diagnostic(
        code=48001,
        title="接口未授权 —— 你的号多半没认证，用不了草稿箱接口",
        cause=(
            "草稿箱（draft/add）和发布接口要求「已认证的订阅号或服务号」。"
            "个人主体未认证订阅号没有这个权限，这不是配置问题，是账号资质问题。"
        ),
        fix=[
            "登录 mp.weixin.qq.com，右上角看账号类型：个人 + 未认证 = 用不了草稿接口",
            "可行替代：wxpub publish --dry-run 只生成 HTML，手动粘进后台编辑器（样式已经是内联的，粘过去就是成品）",
            "或者：企业主体认证后即可调用；服务号同样需要认证",
        ],
    ),
    45009: Diagnostic(
        code=45009,
        title="接口调用次数超限",
        cause="微信对每个接口有每日/每分钟配额。频繁轮询 token 或批量上传图片最容易撞上。",
        fix=[
            "等配额重置（每日 0 点），或减少调用频率",
            "本工具默认缓存 access_token 两小时，不要每次都强制刷新",
            "批量发多篇时，篇与篇之间留几秒间隔",
        ],
    ),
    45002: Diagnostic(
        code=45002,
        title="内容超长",
        cause="正文 HTML 超过 20000 字符，或单张图片超过大小限制。",
        fix=[
            "正文控制在 2 万字符内（约 6000-8000 汉字，加标签会更多）",
            "图片单张 ≤1MB，工具会自动压缩，但如果原图极大建议先手动缩到 1200px 宽",
            "长文拆成多篇，或者把大段代码截图",
        ],
    ),
    45003: Diagnostic(
        code=45003,
        title="标题超长",
        cause="草稿标题上限 64 个字符（中文按字算，一个汉字算 1）。",
        fix=["把标题压到 64 字以内，公众号标题建议 20 字内更好读"],
    ),
    45004: Diagnostic(
        code=45004,
        title="摘要超长",
        cause="digest（摘要）上限 120 个字符。",
        fix=["把 summary 压到 120 字内，工具默认会从正文自动截取"],
    ),
    45110: Diagnostic(
        code=45110,
        title="作者名超长",
        cause="author 上限 8 个字符。",
        fix=["作者名压到 8 字内，比如「阿派」"],
    ),
    40009: Diagnostic(
        code=40009,
        title="图片不符合要求",
        cause="格式不支持（WebP 是重灾区）或体积超限。注意：很多网页图存成 .png 实际上是 WebP。",
        fix=[
            "本工具会自动嗅探文件头并转 PNG，如果还报错，检查图片是否损坏",
            "确认单张 ≤1MB",
        ],
    ),
    40007: Diagnostic(
        code=40007,
        title="media_id 无效",
        cause="封面素材没上传成功，或者用了别的账号的 media_id。永久素材的 media_id 和账号绑定。",
        fix=[
            "重新跑一次，让工具重新上传封面拿新的 media_id",
            "确认 APP_ID 和生成 media_id 时用的是同一个号",
        ],
    ),
    40113: Diagnostic(
        code=40113,
        title="不支持的文件类型",
        cause="上传了微信不认的格式（WebP、AVIF、SVG 都会被拒）。",
        fix=["转成 PNG 或 JPEG 再传，工具默认已处理"],
    ),
    40132: Diagnostic(
        code=40132,
        title="系统繁忙",
        cause="微信侧偶发故障，通常几秒后恢复。",
        fix=["等 30 秒重试；连续失败就去看 https://developers.weixin.qq.com/community/ 有没有人在报同样的问题"],
    ),
    45166: Diagnostic(
        code=45166,
        title="内容里有微信不接受的东西 —— 头号原因是 <a> 标签",
        cause=(
            "草稿接口对 content 有一套没写进文档的校验，违反时统一报 45166，"
            "却说不出是哪里不对。实测最常见的三个触发点：\n"
            "      · <a> 标签（不管 href 指向哪，连 mp.weixin.qq.com 自己也拦）\n"
            "      · 不可见字符（零宽空格 U+200B、BOM、Emoji 变体选择符，从网页复制粘贴时带进来的）\n"
            "      · <script> / <iframe> / 注释 / class 属性"
        ),
        fix=[
            "如果是自己拼的 HTML：把 <a> 全删掉，只留文字（公众号里外链本来也点不动）",
            "如果是复制粘贴的文本：清掉零宽字符，工具会自动做这一步",
            "用 wxpub 的渲染器生成 HTML 就不会踩这些坑，它提交前会清洗一遍",
            "实在定位不到：把正文对半拆开分别提交，哪半报错就继续对半拆，几轮能锁定",
        ],
    ),
    -1: Diagnostic(
        code=-1,
        title="系统错误",
        cause="微信服务端临时故障，最常见的假错误。",
        fix=["重试。连续多次失败再排查其他原因"],
    ),
}


@dataclass
class WeChatError(Exception):
    """带诊断信息的微信接口错误。"""

    errcode: int
    errmsg: str
    stage: str = ""
    payload: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.errcode}] {self.errmsg}"

    @property
    def ip(self) -> Optional[str]:
        m = IP_RE.search(self.errmsg or "")
        return m.group(1) if m else None

    def explain(self, current_ip: Optional[str] = None) -> str:
        """生成给人看的多行诊断。"""
        d = DIAGNOSTICS.get(self.errcode)
        stage_txt = f"（出错环节：{self.stage}）" if self.stage else ""
        lines: List[str] = [f"微信接口报错 {self.errcode}{stage_txt}"]

        if d:
            lines.append(f"  {d.title}")
            lines.append(f"  原因：{d.cause}")
            lines.append("  怎么修：")
            for i, step in enumerate(d.fix, 1):
                lines.append(f"    {i}. {step}")
            if d.doc:
                lines.append(f"  文档：{d.doc}")
        else:
            lines.append(f"  微信返回：{self.errmsg}")
            lines.append("  没有收录这个错误码。可以在项目 issue 里反馈，或查官方错误码表：")
            lines.append("  https://developers.weixin.qq.com/doc/offiaccount/Getting_Started/Global_Return_Code.html")

        # 40164 特判：把当前 IP 和报错里的 IP 都摆出来
        if self.errcode == 40164:
            bad_ip = self.ip
            if bad_ip:
                lines.append(f"  报错里的 IP：{bad_ip}")
            if current_ip and current_ip != bad_ip:
                lines.append(f"  你现在的出口 IP：{current_ip}（如果和上面不同，说明网络环境变了）")
            lines.append(
                "  快捷跳转：https://mp.weixin.qq.com/advanced/advanced?action=ip_whitelist&t=advanced/ip_whitelist"
            )
        return "\n".join(lines)


def raise_for_response(data: dict, stage: str = "") -> dict:
    """检查微信返回体，有 errcode 就抛带诊断的异常。"""
    if not isinstance(data, dict):
        raise WeChatError(-99, f"返回体不是 JSON：{str(data)[:200]}", stage=stage, payload={})
    code = data.get("errcode", 0)
    if code not in (0, "0", None):
        raise WeChatError(int(code), str(data.get("errmsg", "")), stage=stage, payload=data)
    return data
