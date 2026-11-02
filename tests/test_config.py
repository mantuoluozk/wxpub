# -*- coding: utf-8 -*-
"""凭证读取与打码测试。

打码这件事有个具体的来历：`wxpub doctor` 早期完整打印 AppID，
README 里那段示例输出于是带了一个完整 AppID（占位符 wx1234567890abcdef），
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
            app_id="wx1a2b3c4d5e6f7890",
            app_secret="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
            source="测试",
        )

    def test_masked_app_id_hides_middle(self):
        m = self.cred.masked_app_id()
        self.assertEqual(m, "wx1a**********7890")
        self.assertNotEqual(m, self.cred.app_id)

    def test_masked_changes_on_first_and_last(self):
        # 首尾各留 4 位：够认出是哪个号，不够还原
        m = self.cred.masked_app_id()
        self.assertTrue(m.startswith("wx1a"))
        self.assertTrue(m.endswith("7890"))

    def test_mask_result_does_not_match_appid_pattern(self):
        # 关键断言：打码后的字符串不能再被 wx[0-9a-f]{16} 命中，
        # 否则贴到 README 里照样会被 GitHub 报一次
        import re

        m = self.cred.masked_app_id()
        self.assertIsNone(re.search(r"wx[0-9a-f]{16}", m))

    def test_masked_secret_hides_middle(self):
        self.assertEqual(self.cred.masked_secret(), "a1b2************************c5d6")
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
            "# 注释\nWECHAT_APP_ID=wx139876543210abcd\nWECHAT_APP_SECRET=" + "f" * 32 + "\n",
            encoding="utf-8",
        )
        d = parse_env_file(self.env)
        self.assertEqual(d["WECHAT_APP_ID"], "wx139876543210abcd")
        self.assertEqual(len(d["WECHAT_APP_SECRET"]), 32)

    def test_quotes_stripped(self):
        self.env.write_text('WECHAT_APP_ID="wx139876543210abcd"\n', encoding="utf-8")
        self.assertEqual(parse_env_file(self.env)["WECHAT_APP_ID"], "wx139876543210abcd")

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


if __name__ == "__main__":
    unittest.main()
