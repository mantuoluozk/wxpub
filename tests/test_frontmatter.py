# -*- coding: utf-8 -*-
"""frontmatter 解析的边界情况。

重点不是「正常输入能解析」，而是「奇怪输入不会让整篇文章发不出去」。
"""

import unittest

from wxpub.frontmatter import parse_frontmatter, split_tags


class TestFrontmatter(unittest.TestCase):
    def test_basic(self):
        md = "---\ntitle: 标题\ndate: 2026-11-02\n---\n正文"
        meta, body = parse_frontmatter(md)
        self.assertEqual(meta["title"], "标题")
        self.assertEqual(meta["date"], "2026-11-02")
        self.assertEqual(body.strip(), "正文")

    def test_no_frontmatter(self):
        meta, body = parse_frontmatter("# 只有正文")
        self.assertEqual(meta, {})
        self.assertEqual(body, "# 只有正文")

    def test_quoted_values(self):
        # 中文引号在 YAML 里容易被转义成 \" 乱讲\"，所以作者会用单引号包整串
        md = "---\ntitle: '关于\"乱讲\"这件事'\nsubtitle: \"双引号也可以\"\n---\n正文"
        meta, _ = parse_frontmatter(md)
        self.assertEqual(meta["title"], '关于"乱讲"这件事')
        self.assertEqual(meta["subtitle"], "双引号也可以")

    def test_inline_list(self):
        meta, _ = parse_frontmatter("---\ntags: [安全, API, 凭据]\n---\n")
        self.assertEqual(meta["tags"], ["安全", "API", "凭据"])

    def test_block_list(self):
        md = "---\ntags:\n  - 安全\n  - API\n---\n"
        meta, _ = parse_frontmatter(md)
        self.assertEqual(meta["tags"], ["安全", "API"])

    def test_comment_stripped(self):
        meta, _ = parse_frontmatter("---\ntitle: 标题  # 这是注释\n---\n")
        self.assertEqual(meta["title"], "标题")

    def test_hash_inside_value_kept(self):
        # C# / #1 这类内容不该被当注释切掉
        meta, _ = parse_frontmatter("---\ntitle: 学 C# 的第一天\n---\n")
        self.assertEqual(meta["title"], "学 C# 的第一天")

    def test_crlf(self):
        meta, body = parse_frontmatter("---\r\ntitle: 标题\r\n---\r\n正文")
        self.assertEqual(meta["title"], "标题")
        self.assertEqual(body.strip(), "正文")

    def test_empty_frontmatter(self):
        meta, body = parse_frontmatter("---\n---\n正文")
        self.assertEqual(meta, {})
        self.assertEqual(body.strip(), "正文")

    def test_preserves_body_colons(self):
        md = "---\ntitle: 标题\n---\n时间是 10:30，不是字段"
        _, body = parse_frontmatter(md)
        self.assertIn("10:30", body)

    def test_split_tags(self):
        self.assertEqual(split_tags("a,b,c"), ["a", "b", "c"])
        self.assertEqual(split_tags(["a", " ", "b"]), ["a", "b"])
        self.assertEqual(split_tags("AI，安全 工具"), ["AI", "安全", "工具"])
        self.assertEqual(split_tags(""), [])
        self.assertEqual(split_tags(None), [])


if __name__ == "__main__":
    unittest.main()
