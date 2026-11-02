# -*- coding: utf-8 -*-
"""凭证与配置加载。

查找顺序（先到先得）：
  1. 环境变量  WECHAT_APP_ID / WECHAT_APP_SECRET（也认 WXPUB_ 前缀）
  2. 当前目录 .env
  3. ~/.wxpub/.env
  4. ~/.baoyu-skills/.env    ← 兼容宝玉那套 skill 的既有配置，迁移成本为零

不引 python-dotenv：只要支持 KEY=VALUE、# 注释、可选引号就够了，多一个依赖不值得。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

CONFIG_DIR = Path.home() / ".wxpub"
TOKEN_CACHE = CONFIG_DIR / "token.json"

# 兼容既有工具链的凭证位置
LEGACY_ENV_FILES = [
    Path.home() / ".baoyu-skills" / ".env",
]


class ConfigError(Exception):
    pass


def parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def _candidate_files() -> list:
    files = [
        Path.cwd() / ".env",
        CONFIG_DIR / ".env",
    ]
    files.extend(LEGACY_ENV_FILES)
    return files


@dataclass
class Credentials:
    app_id: str
    app_secret: str
    source: str  # 从哪读到的，doctor 里显示，方便排查「为什么改了没生效」

    def masked_secret(self) -> str:
        s = self.app_secret
        if len(s) <= 8:
            return "*" * len(s)
        return f"{s[:4]}{'*' * (len(s) - 8)}{s[-4:]}"


def load_credentials(require: bool = True) -> Credentials:
    env_id = os.environ.get("WECHAT_APP_ID") or os.environ.get("WXPUB_APP_ID")
    env_secret = os.environ.get("WECHAT_APP_SECRET") or os.environ.get("WXPUB_APP_SECRET")
    if env_id and env_secret:
        return Credentials(env_id.strip(), env_secret.strip(), "环境变量")

    # 环境变量只给了一半时，另一半从文件补
    for path in _candidate_files():
        if not path.is_file():
            continue
        data = parse_env_file(path)
        app_id = env_id or data.get("WECHAT_APP_ID") or data.get("WXPUB_APP_ID")
        secret = env_secret or data.get("WECHAT_APP_SECRET") or data.get("WXPUB_APP_SECRET")
        if app_id and secret:
            return Credentials(app_id.strip(), secret.strip(), str(path))

    if require:
        raise ConfigError(
            "没有找到公众号凭证。任选一种方式配置：\n"
            "\n"
            "  方式一（推荐）写进 ~/.wxpub/.env：\n"
            "    WECHAT_APP_ID=wx开头的那串\n"
            "    WECHAT_APP_SECRET=32位字符串\n"
            "\n"
            "  方式二 设环境变量：\n"
            "    Windows:  set WECHAT_APP_ID=xxx && set WECHAT_APP_SECRET=yyy\n"
            "    macOS/Linux: export WECHAT_APP_ID=xxx WECHAT_APP_SECRET=yyy\n"
            "\n"
            "  方式三 在当前目录放一个 .env 文件（已在 .gitignore 里，不会被提交）\n"
            "\n"
            "凭证位置：mp.weixin.qq.com → 设置与开发 → 基本配置\n"
            "注意 AppSecret 只在生成时显示一次，忘了就重置（重置后旧的全部失效）。"
        )
    return Credentials("", "", "未配置")


def ensure_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR
