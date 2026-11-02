# -*- coding: utf-8 -*-
"""凭证读取与打码测试。

打码这件事有个具体的来历：`wxpub doctor` 早期完整打印 AppID，
README 里那段示例输出于是带了一个看起来完整的 AppID（一个纯占位符），
结果 GitHub secret scanning 判成「公开泄露密钥」并给仓库挂了告警。

AppID 不是机密，但它的格式（wx + 16 位十六进制）正好命中那条规则。
所以默认打码，这不只是美观问题，是防止用户把日志贴出去时被误判。
"""

import os
import tempfile
import unittest
from pathlib import Path

from wxpub.config import Credentials, load_credentials, parse_env_file


class TestMasking(unittest.TestCase):
    def setUp(self):
        self.cred = Credentials(
            app_id="wxTESTID0000000001",
            app_secret="SECRET" + "0" * 22 + "TEST",
            source="测试",
        )

    def test_masked_app_id_hides_middle(self):
        m = self.cred.masked_app_id()
        self.assertEqual(m, "wxTE**********0001")
        self.assertNotEqual(m, self.cred.app_id)

    def test_masked_changes_on_first_and_last(self):
        # 首尾各留 4 位：够认出是哪个号，不够还原
        m = self.cred.masked_app_id()
        self.assertTrue(m.startswith("wxTE"))
        self.assertTrue(m.endswith("0001"))

    def test_mask_result_does_not_match_appid_pattern(self):
        # 关键断言：打码后的字符串不能再被 wx[0-9a-f]{16} 命中，
        # 否则贴到 README 里照样会被 GitHub 报一次
        import re

        m = self.cred.masked_app_id()
        self.assertIsNone(re.search(r"wx[0-9a-f]{16}", m))

    def test_masked_secret_hides_middle(self):
        self.assertEqual(self.cred.masked_secret(), "SECR" + "*" * 24 + "TEST")
        self.assertIsNone(
            __import__("re").search(r"[0-9a-f]{32}", self.cred.masked_secret())
        )

    def test_short_values_fully_masked(self):
        c = Credentials(app_id="wx123", app_secret="short", source="t")
        self.assertEqual(c.masked_app_id(), "*****")
        self.assertEqual(c.masked_secret(), "*****")


class TestLoadCredentials(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = self.tmp / ".env"
        self._old = {k: os.environ.pop(k, None) for k in
                     ("WECHAT_APP_ID", "WECHAT_APP_SECRET", "WXPUB_APP_ID", "WXPUB_APP_SECRET")}

    def tearDown(self):
        for k, v in self._old.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def test_env_file_parsed(self):
        self.env.write_text(
            "# 注释\nWECHAT_APP_ID=wxTESTENVID000001\nWECHAT_APP_SECRET=" + "f" * 32 + "\n",
            encoding="utf-8",
        )
        d = parse_env_file(self.env)
        self.assertEqual(d["WECHAT_APP_ID"], "wxTESTENVID000001")
        self.assertEqual(len(d["WECHAT_APP_SECRET"]), 32)

    def test_quotes_stripped(self):
        self.env.write_text('WECHAT_APP_ID="wxTESTENVID000001"\n', encoding="utf-8")
        self.assertEqual(parse_env_file(self.env)["WECHAT_APP_ID"], "wxTESTENVID000001")

    def test_missing_raises(self):
        from unittest import mock

        from wxpub.config import ConfigError

        # 不能真的依赖本机有没有配凭证：把候选路径全部指到一个空目录
        empty = self.tmp / "nowhere" / ".env"
        with mock.patch("wxpub.config._candidate_files", return_value=[empty]):
            with self.assertRaises(ConfigError):
                load_credentials(require=True)

    def test_missing_not_required_returns_none(self):
        from unittest import mock

        from wxpub.config import ConfigError

        empty = self.tmp / "nowhere" / ".env"
        with mock.patch("wxpub.config._candidate_files", return_value=[empty]):
            try:
                r = load_credentials(require=False)
            except ConfigError:
                self.fail("require=False 不该抛异常")
        self.assertTrue(r is None or isinstance(r, Credentials))


class TestRepoHasNoSecretShapedLiterals(unittest.TestCase):
    """整个仓库不该出现「看起来像真凭证」的字面量。

    这条规则是被 GitHub 挂了两次告警之后加的：先是 README 的示例输出，
    后是测试夹具 —— 都只是假值，但形状对了（wx + 16 位十六进制），
    扫描器一律当真，仓库的安全页就红一片，还得逐条解释。

    与其事后解释，不如提交前就被自己的测试拦住。
    """

    ROOT = Path(__file__).resolve().parent.parent
    PATTERNS = {
        "AppID 形状 (wx + 16 位十六进制)": r"wx[0-9a-f]{16}",
        "Secret 形状 (32 位连续十六进制)": r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])",
    }
    BINARY = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".lock", ".pyc"}

    def test_no_secret_shaped_literals(self):
        import re

        offenders = []
        for root, dirs, files in os.walk(self.ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".pytest_cache")]
            for fn in files:
                path = Path(root) / fn
                if path.suffix.lower() in self.BINARY:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for label, pat in self.PATTERNS.items():
                    for m in re.finditer(pat, text):
                        rel = path.relative_to(self.ROOT)
                        offenders.append(f"{rel}: {label} {m.group()[:6]}***")
        self.assertEqual(
            offenders,
            [],
            "仓库里出现了像真凭证的字面量（改用 wxTESTID... 这类明显假值）：\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
