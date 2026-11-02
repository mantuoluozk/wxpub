# -*- coding: utf-8 -*-
"""错误诊断测试。

这些断言看起来像在测文案，其实在测产品承诺：
「报错时会告诉你下一步做什么」——如果哪天有人把 fix 步骤删了，测试就该红。
"""

import unittest

from wxpub.errors import DIAGNOSTICS, WeChatError, raise_for_response


class TestDiagnosticContent(unittest.TestCase):
    def test_40164_extracts_ip(self):
        e = WeChatError(40164, "invalid ip 203.0.113.7, not in whitelist")
        self.assertEqual(e.ip, "203.0.113.7")

    def test_40164_explain_has_steps(self):
        e = WeChatError(40164, "invalid ip 203.0.113.7, not in whitelist")
        text = e.explain(current_ip="203.0.113.7")
        self.assertIn("203.0.113.7", text)
        self.assertIn("白名单", text)
        # 必须告诉人去哪个菜单，而不是只说「加白名单」
        self.assertIn("基本配置", text)
        # 必须提醒保存后有缓存延迟，否则用户会以为没生效
        self.assertIn("1-2 分钟", text)

    def test_40164_shows_current_ip_when_different(self):
        e = WeChatError(40164, "invalid ip 1.1.1.1, not in whitelist")
        text = e.explain(current_ip="9.9.9.9")
        self.assertIn("1.1.1.1", text)
        self.assertIn("9.9.9.9", text)

    def test_48001_explains_account_qualification(self):
        e = WeChatError(48001, "api unauthorized")
        text = e.explain()
        self.assertIn("认证", text)
        # 关键：要给出替代方案，而不是让人卡死
        self.assertIn("dry-run", text)

    def test_all_diagnostics_have_actionable_fix(self):
        for code, d in DIAGNOSTICS.items():
            self.assertTrue(d.fix, f"{code} 没有修复步骤")
            self.assertTrue(all(len(s) > 5 for s in d.fix), f"{code} 的修复步骤太笼统")
            self.assertTrue(d.title and d.cause, f"{code} 缺少标题或原因")

    def test_40125_mentions_secret_reset_consequence(self):
        text = WeChatError(40125, "invalid appsecret").explain()
        self.assertIn("重置", text)

    def test_unknown_code_falls_back_gracefully(self):
        e = WeChatError(99999, "some unknown error")
        text = e.explain()
        self.assertIn("99999", text)
        self.assertIn("没有收录", text)

    def test_explain_includes_stage(self):
        e = WeChatError(40001, "invalid credential", stage="创建草稿")
        self.assertIn("创建草稿", e.explain())


class TestRaiseForResponse(unittest.TestCase):
    def test_ok_response_passes_through(self):
        data = {"access_token": "x", "expires_in": 7200}
        self.assertIs(raise_for_response(data), data)

    def test_errcode_zero_is_ok(self):
        raise_for_response({"errcode": 0, "errmsg": "ok"})

    def test_error_response_raises(self):
        with self.assertRaises(WeChatError) as cm:
            raise_for_response({"errcode": 40164, "errmsg": "invalid ip 1.2.3.4, not in whitelist"})
        self.assertEqual(cm.exception.errcode, 40164)

    def test_non_dict_raises(self):
        with self.assertRaises(WeChatError):
            raise_for_response("<html>502 Bad Gateway</html>")

    def test_errmsg_preserved(self):
        with self.assertRaises(WeChatError) as cm:
            raise_for_response({"errcode": 45009, "errmsg": "api freq out of limit"})
        self.assertIn("freq", cm.exception.errmsg)


if __name__ == "__main__":
    unittest.main()
