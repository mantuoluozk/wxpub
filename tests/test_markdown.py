# -*- coding: utf-8 -*-
"""markdown 渲染test。

最要紧的两条：
  1. 任何用户内容都不能变成可执行 HTML（XSS 在公众号里是「整段样式错乱」，很难查）
  2. 生成的每个标签都必须带内联 style —— 微信会剥掉 <style> 和 class
"""

import re
import unittest

from wxpub.markdown import Style, plain_text, render


class TestEscape(unittest.TestCase):
    def test_code_block_escapes_html(self):
        out = render("```python\nprint('<script>alert(1)</script>')\n```")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_inline_code_escapes(self):
        out = render("用 `<div>` 包一层")
        self.assertNotIn("<div>", out)
        self.assertIn("&lt;div&gt;", out)

    def test_raw_html_in_paragraph(self):
        out = render("这段有 <img src=x onerror=alert(1)> 注入")
        # 尖括号被转义后，onerror 只是普通文字，不会成为属性
        self.assertNotIn("<img src=x", out)
        self.assertIn("&lt;img", out)

    def test_ampersand(self):
        out = render("A & B 和 < 号")
        self.assertIn("&amp;", out)


class TestInline(unittest.TestCase):
    def test_bold(self):
        self.assertIn("<strong", render("**加粗**"))

    def test_italic(self):
        self.assertIn("<em>", render("*斜体*"))

    def test_del(self):
        self.assertIn("<del>", render("~~删掉~~"))

    def test_inline_code_not_parsed_as_bold(self):
        # 反引号里的 ** 必须是字面量
        out = render("`**不是加粗**`")
        self.assertNotIn("<strong", out)
        self.assertIn("**不是加粗**", out)

    def test_link_never_becomes_anchor(self):
        # 微信草稿接口对 <a> 零容忍（45166），所以只能渲染成带样式的 span
        out = render("[文字](https://example.com)")
        self.assertNotIn("<a ", out)
        self.assertIn("文字", out)
        self.assertIn("<span", out)

    def test_image_bang_not_swallowed_by_link(self):
        out = render("![图](a.png)")
        self.assertIn("<img", out)
        self.assertNotIn("<a ", out)

    def test_nested_bold_in_link(self):
        out = render("[**粗**链接](https://example.com)")
        self.assertIn("<strong", out)
        self.assertNotIn("<a ", out)

    def test_asterisk_not_eaten_as_italic(self):
        out = render("2 * 3 = 6")
        self.assertIn("2 * 3 = 6", out)


class TestBlocks(unittest.TestCase):
    def test_headings(self):
        out = render("# 一级\n## 二级\n### 三级\n#### 四级")
        self.assertEqual(out.count("<h2"), 2)  # H1 降级为 H2
        self.assertIn("<h3", out)
        self.assertIn("<h4", out)

    def test_table(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |"
        out = render(md)
        self.assertIn("<table", out)
        self.assertIn("<th", out)
        self.assertIn("<td", out)

    def test_table_alignment_row_not_rendered_as_text(self):
        md = "| a | b |\n|:---|---:|\n| 1 | 2 |"
        out = render(md)
        self.assertNotIn("---", out)

    def test_blockquote(self):
        out = render("> 引用一\n> 引用二")
        self.assertIn("<blockquote", out)
        self.assertIn("引用一", out)
        self.assertIn("引用二", out)

    def test_hr(self):
        self.assertIn("<hr", render("---"))
        self.assertIn("<hr", render("***"))

    def test_unordered_list(self):
        out = render("- 一\n- 二\n- 三")
        self.assertEqual(out.count("<li"), 3)

    def test_nested_list(self):
        out = render("- 一\n  - 一点一\n- 二")
        self.assertEqual(out.count("<li"), 3)

    def test_ordered_list_rendered(self):
        out = render("1. 一\n2. 二")
        self.assertEqual(out.count("<li"), 2)

    def test_paragraph_joins_consecutive_lines(self):
        # 中文写作常按屏幕宽度硬折行，渲染时必须合成一段
        out = render("第一行\n第二行")
        self.assertEqual(out.count("<p "), 1)

    def test_code_block_language_tag(self):
        out = render("```python\nx=1\n```")
        self.assertIn("python", out)

    def test_code_block_wraps_instead_of_scrolling(self):
        # 手机上没有横向滚动条，长代码必须自动折行
        out = render("```\n" + "x" * 300 + "\n```")
        self.assertIn("pre-wrap", out)


class TestWeChatCompat(unittest.TestCase):
    def test_every_tag_has_inline_style(self):
        md = "# 标题\n\n正文**粗**。\n\n- 列表\n\n> 引用\n\n| a |\n|---|\n| 1 |\n\n```\ncode\n```\n\n![i](x.png)"
        out = render(md)
        for tag in ("p", "h2", "li", "blockquote", "table", "td", "th", "pre", "code", "img"):
            for m in re.finditer(rf"<{tag}(\s[^>]*)?>", out):
                attrs = m.group(1) or ""
                self.assertIn("style=", attrs, f"<{tag}> 缺少内联样式，微信里会变成默认丑样式")

    def test_no_style_tag_or_class(self):
        out = render("# 标题\n\n正文\n\n- 项")
        self.assertNotIn("<style", out)
        self.assertNotIn("class=", out)
        self.assertNotIn("id=", out)

    def test_no_script(self):
        out = render("正文 <script>x</script>")
        self.assertNotIn("<script>", out)


class TestImageHandler(unittest.TestCase):
    def test_handler_receives_src_and_alt(self):
        calls = []

        def handler(src, alt):
            calls.append((src, alt))
            return "https://cdn.example.com/x.png"

        out = render("![说明](local.png)", image_handler=handler)
        self.assertEqual(calls, [("local.png", "说明")])
        self.assertIn("https://cdn.example.com/x.png", out)

    def test_handler_error_propagates_cleanly(self):
        def handler(src, alt):
            raise RuntimeError("上传失败")

        with self.assertRaises(RuntimeError):
            render("![x](a.png)", image_handler=handler)


class TestPlainText(unittest.TestCase):
    def test_strips_markup(self):
        text = plain_text("# 标题\n\n**粗** *斜* ~~删~~ `码` [链](http://a.b)", 100)
        for token in ("#", "**", "*斜*", "~~", "`", "]("):
            self.assertNotIn(token, text)
        self.assertIn("标题", text)

    def test_limit(self):
        self.assertLessEqual(len(plain_text("字" * 500, 50)), 50)


if __name__ == "__main__":
    unittest.main()
