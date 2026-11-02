# -*- coding: utf-8 -*-
"""微信公众平台 API 客户端。

只封装发文章真正用到的那几个接口，不做大而全的 SDK：
  - access_token（带本地缓存，避免多进程互踢）
  - media/uploadimg    正文图片 → 返回一个 CDN url
  - material/add_material 封面 → 返回 media_id（永久素材）
  - draft/add          建草稿
  - freepublish/submit 发布（可选，需要相应权限）

每个请求都过一遍 raise_for_response，把 errcode 变成能照做的中文指引。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from .config import TOKEN_CACHE, Credentials, ensure_config_dir
from .errors import WeChatError, raise_for_response

API = "https://api.weixin.qq.com"

# 微信对草稿各字段的长度限制，本地先卡一遍，别等服务器打回来
LIMITS = {
    "title": 64,
    "author": 8,
    "digest": 120,
    "content": 20000,
}

MIME = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "GIF": "image/gif",
    "BMP": "image/bmp",
}


class NetworkError(Exception):
    """网络层错误，和微信业务错误分开，避免用户看到一堆 traceback。"""


@dataclass
class TokenInfo:
    token: str
    expires_at: float


class WeChatClient:
    def __init__(
        self,
        credentials: Credentials,
        timeout: int = 20,
        use_cache: bool = True,
        verbose: bool = False,
    ) -> None:
        self.cred = credentials
        self.timeout = timeout
        self.use_cache = use_cache
        self.verbose = verbose
        self._session = requests.Session()
        # 公众号接口走直连更稳：代理经常是 40164 的隐形原因（出口 IP 变成代理机）
        self._session.trust_env = False
        self._token: Optional[TokenInfo] = None

    # ------------------------------------------------------------------ 基础
    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"  · {msg}")

    def _post(self, path: str, params: dict, stage: str, **kw) -> dict:
        url = f"{API}{path}"
        try:
            resp = self._session.post(url, params=params, timeout=self.timeout, **kw)
        except requests.exceptions.Timeout:
            raise NetworkError(
                f"请求 {path} 超时（{self.timeout}s）。检查网络，或试试关闭代理后重跑。"
            ) from None
        except requests.exceptions.SSLError as exc:
            raise NetworkError(f"SSL 握手失败：{exc}\n企业网络/杀软的证书拦截是常见原因。") from None
        except requests.exceptions.ConnectionError as exc:
            raise NetworkError(
                f"连不上 api.weixin.qq.com。\n{exc}\n"
                "常见原因：代理没关、DNS 污染、公司网络限制。试试 env -u HTTP_PROXY -u HTTPS_PROXY 后重跑。"
            ) from None

        if resp.status_code != 200:
            raise NetworkError(f"HTTP {resp.status_code}：{resp.text[:300]}")
        try:
            data = resp.json()
        except ValueError:
            raise NetworkError(
                f"返回的不是 JSON（可能被网关拦截了）：{resp.text[:300]}"
            ) from None
        return raise_for_response(data, stage=stage)

    # ------------------------------------------------------------------ token
    def _read_cache(self) -> Optional[TokenInfo]:
        try:
            raw = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        # token 和 app_id 绑定，换号必须作废
        if raw.get("app_id") != self.cred.app_id:
            return None
        if raw.get("expires_at", 0) <= time.time() + 60:
            return None
        return TokenInfo(raw["token"], raw["expires_at"])

    def _write_cache(self, info: TokenInfo) -> None:
        try:
            ensure_config_dir()
            TOKEN_CACHE.write_text(
                json.dumps(
                    {
                        "app_id": self.cred.app_id,
                        "token": info.token,
                        "expires_at": info.expires_at,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            TOKEN_CACHE.chmod(0o600)
        except OSError:
            pass  # 缓存写不了不影响主流程

    def get_token(self, force: bool = False) -> str:
        if self._token and not force:
            if self._token.expires_at > time.time() + 60:
                return self._token.token

        if self.use_cache and not force:
            cached = self._read_cache()
            if cached:
                self._log("复用本地缓存的 access_token")
                self._token = cached
                return cached.token

        self._log("向微信申请 access_token")
        data = self._post(
            "/cgi-bin/token",
            {
                "grant_type": "client_credential",
                "appid": self.cred.app_id,
                "secret": self.cred.app_secret,
            },
            stage="获取 access_token",
        )
        token = data.get("access_token")
        if not token:
            raise WeChatError(-99, f"返回体里没有 access_token：{data}", stage="获取 access_token")
        expires_in = int(data.get("expires_in", 7200))
        # 提前 5 分钟过期，避免卡在边界上
        info = TokenInfo(token, time.time() + expires_in - 300)
        self._token = info
        if self.use_cache:
            self._write_cache(info)
        return token

    # ------------------------------------------------------------------ 上传
    def upload_body_image(self, path: str) -> str:
        """正文内图片。返回可直接写进 <img src> 的 url。"""
        token = self.get_token()
        from .images import sniff

        fmt = sniff(path)
        mime = MIME.get(fmt, "image/png")
        with open(path, "rb") as f:
            files = {"media": (Path(path).name, f.read(), mime)}
        data = self._post(
            "/cgi-bin/media/uploadimg",
            {"access_token": token},
            stage=f"上传正文图片 {Path(path).name}",
            files=files,
        )
        url = data.get("url")
        if not url:
            raise WeChatError(-99, f"上传图片没有返回 url：{data}", stage="上传正文图片")
        self._log(f"正文图 {Path(path).name} → {url[:60]}...")
        return url

    def upload_cover(self, path: str) -> str:
        """封面图。走永久素材，返回 thumb_media_id。"""
        token = self.get_token()
        from .images import cover_bytes, sniff

        fmt = sniff(path)
        mime = MIME.get(fmt, "image/png")
        files = {"media": (Path(path).name, cover_bytes(path), mime)}
        data = self._post(
            "/cgi-bin/material/add_material",
            {"access_token": token, "type": "image"},
            stage=f"上传封面 {Path(path).name}",
            files=files,
        )
        media_id = data.get("media_id")
        if not media_id:
            raise WeChatError(-99, f"上传封面没有返回 media_id：{data}", stage="上传封面")
        self._log(f"封面 media_id = {media_id[:24]}...")
        return media_id

    # ------------------------------------------------------------------ 草稿
    def create_draft(
        self,
        title: str,
        content: str,
        thumb_media_id: str,
        author: str = "",
        digest: str = "",
        source_url: str = "",
        open_comment: bool = False,
    ) -> str:
        self._precheck(title, content, author, digest)
        token = self.get_token()
        article = {
            "title": title,
            "author": author,
            "digest": digest,
            "content": content,
            "content_source_url": source_url,
            "thumb_media_id": thumb_media_id,
            "need_open_comment": 1 if open_comment else 0,
            "only_fans_can_comment": 0,
        }
        body = json.dumps({"articles": [article]}, ensure_ascii=False).encode("utf-8")
        data = self._post(
            "/cgi-bin/draft/add",
            {"access_token": token},
            stage="创建草稿",
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        media_id = data.get("media_id")
        if not media_id:
            raise WeChatError(-99, f"建草稿没有返回 media_id：{data}", stage="创建草稿")
        return media_id

    def publish(self, draft_media_id: str) -> str:
        """草稿 → 正式发布。个人号通常没这个权限，会返回 48001。"""
        token = self.get_token()
        body = json.dumps({"media_id": draft_media_id}).encode("utf-8")
        data = self._post(
            "/cgi-bin/freepublish/submit",
            {"access_token": token},
            stage="发布文章",
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        return str(data.get("publish_id", ""))

    # ------------------------------------------------------------------ 预检
    @staticmethod
    def _precheck(title: str, content: str, author: str, digest: str) -> None:
        problems = []
        if not title.strip():
            problems.append("标题是空的")
        if len(title) > LIMITS["title"]:
            problems.append(f"标题 {len(title)} 字，超过上限 {LIMITS['title']} 字")
        if len(author) > LIMITS["author"]:
            problems.append(f"作者 {len(author)} 字，超过上限 {LIMITS['author']} 字（建议就用昵称）")
        if len(digest) > LIMITS["digest"]:
            problems.append(f"摘要 {len(digest)} 字，超过上限 {LIMITS['digest']} 字")
        if len(content) > LIMITS["content"]:
            problems.append(
                f"正文 HTML {len(content)} 字符，超过上限 {LIMITS['content']}。"
                "公众号按 HTML 源码长度算，不是按字数"
            )
        if problems:
            raise ValueError("本地预检没通过（省得白跑一趟接口）：\n  - " + "\n  - ".join(problems))


# ---------------------------------------------------------------------- 工具
def fetch_current_ip(timeout: int = 6) -> Optional[str]:
    """取本机出口 IP。绕开代理，因为代理会让出口 IP 变成代理机的。"""
    sess = requests.Session()
    sess.trust_env = False
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://ipinfo.io/ip"):
        try:
            r = sess.get(url, timeout=timeout)
            if r.status_code == 200 and r.text.strip():
                return r.text.strip().split()[0]
        except requests.RequestException:
            continue
    return None
