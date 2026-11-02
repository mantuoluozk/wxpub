# -*- coding: utf-8 -*-
"""HTML 清洗测试。

这套规则对应微信草稿接口那条没写进文档的校验：
只要踩中任何一条，就返回 45166，而且不告诉你为什么。
"""

import unittest

from wxpub.sanitize import has_anchor, sanitize


class TestAnchor(unittest.TestCase):
    def test_anchor_removed_but_text_kept(self):
        html, actions = sanitize('<p>看 <a href="https://x.com">这个</a> 链接</p>')
        self.assertNotIn("<a ", html)
        self.assertIn("这个", html)
        self.assertTrue(actions)

    def test_wechat_domain_also_removed(self):
        # 连微信自己的域名也照样被拦，这是最容易误判的一点
        html, _ = sanitize('<a href="https://mp.weixin.qq.com/s/x">站内</a>')
        self.assertNotIn("<a ", html)
        self.assertIn("站内", html)

    def test_anchor_with_attributes(self):
        html, _ = sanitize('<a class="x" target="_blank" href="https://x.com">t</a>')
        self.assertNotIn("<a", html)

    def test_nested_content_preserved(self):
        html, _ = sanitize('<a href="x"><strong>粗体</strong></a>')
        self.assertIn("<strong>粗体</strong>", html)

    def test_multiple_anchors(self):
        html, actions = sanitize('<a href="a">1</a><a href="b">2</a>')
        self.assertFalse(has_anchor(html))
        self.assertIn("2 个", actions[0])


class TestInvisible(unittest.TestCase):
    def test_zero_width_space(self):
        html, actions = sanitize("正\u200b文")
        self.assertEqual(html, "正文")
        self.assertTrue(actions)

    def test_bom(self):
        html, _ = sanitize("\ufeff正文")
        self.assertEqual(html, "正文")

    def test_emoji_variation_selector(self):
        html, _ = sanitize("箭头↩\ufe0e结束")
        self.assertNotIn("\ufe0e", html)

    def test_bidi_control(self):
        html, _ = sanitize("abc\u202edef")
        self.assertNotIn("\u202e", html)

    def test_normal_text_untouched(self):
        html, actions = sanitize("<p>正常的中文和 English 混排</p>")
        self.assertEqual(html, "<p>正常的中文和 English 混排</p>")
        self.assertEqual(actions, [])


class TestDangerousTags(unittest.TestCase):
    def test_script_removed_with_content(self):
        html, _ = sanitize("<p>a</p><script>alert(1)</script><p>b</p>")
        self.assertNotIn("script", html)
        self.assertNotIn("alert", html)

    def test_style_removed(self):
        html, _ = sanitize("<style>.a{color:red}</style><p>x</p>")
        self.assertNotIn("<style", html)

    def test_iframe_removed(self):
        html, _ = sanitize('<iframe src="x"></iframe>')
        self.assertNotIn("iframe", html)

    def test_comments_removed(self):
        html, _ = sanitize("<p>a</p><!-- 这是注释 --><p>b</p>")
        self.assertNotIn("<!--", html)


class TestAttributes(unittest.TestCase):
    def test_class_id_data_removed(self):
        html, actions = sanitize('<p class="x" id="y" data-z="1" style="color:red">文字</p>')
        self.assertNotIn("class=", html)
        self.assertNotIn("id=", html)
        self.assertNotIn("data-z", html)
        self.assertIn('style="color:red"', html)  # style 必须保留
        self.assertTrue(actions)

    def test_aria_removed(self):
        html, _ = sanitize('<div aria-hidden="true">x</div>')
        self.assertNotIn("aria-", html)


class TestControlChars(unittest.TestCase):
    def test_control_removed_whitespace_kept(self):
        html, _ = sanitize("a\x00b\x07c\n\tok")
        self.assertNotIn("\x00", html)
        self.assertNotIn("\x07", html)
        self.assertIn("\n", html)
        self.assertIn("\t", html)


class TestLocalImages(unittest.TestCase):
    def test_local_src_removed(self):
        html, actions = sanitize('<img src="imgs/x.png" style="a">')
        self.assertNotIn("imgs/x.png", html)
        self.assertTrue(any("本地图片" in a for a in actions))

    def test_http_src_kept(self):
        html, _ = sanitize('<img src="https://mmbiz.qpic.cn/x.png" style="a">')
        self.assertIn("mmbiz.qpic.cn", html)


class TestIdempotent(unittest.TestCase):
    def test_running_twice_same_result(self):
        html = '<p class="a">看<a href="x">这</a>\u200b里</p><script>1</script>'
        once, _ = sanitize(html)
        twice, actions = sanitize(once)
        self.assertEqual(once, twice)
        self.assertEqual(actions, [])


if __name__ == "__main__":
    unittest.main()
