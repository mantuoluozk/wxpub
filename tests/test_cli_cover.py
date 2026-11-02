# -*- coding: utf-8 -*-
"""wxpub cover 从 markdown 读 frontmatter 的行为。

这个能力是给「我只要封面，不想跑整个发布流程」用的，
也是 daily-ai-news 那类编排层依赖的接口，改动要小心。
"""

import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from wxpub.cli import main

MD = """---
title: 封面测试|**高亮**
subtitle: 副标题来自 frontmatter
date: 2026-11-02
theme: violet
layout: quote
cover: my-cover.png
---

正文
"""


class TestCoverFromMarkdown(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.md = self.dir / "a.md"
        self.md.write_text(MD, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_title_theme_layout(self):
        code = main(["cover", str(self.md)])
        self.assertEqual(code, 0)
        # cover 字段指定的文件名，且落在 md 同目录
        out = self.dir / "my-cover.png"
        self.assertTrue(out.is_file())
        with Image.open(out) as im:
            self.assertEqual(im.size, (1280, 544))

    def test_cli_overrides_frontmatter(self):
        out = self.dir / "x.png"
        code = main(["cover", str(self.md), "--theme", "ocean", "--layout", "split", "-o", str(out)])
        self.assertEqual(code, 0)
        self.assertTrue(out.is_file())

    def test_default_name_when_cover_absent(self):
        md = self.dir / "b.md"
        md.write_text("---\ntitle: 只有标题\n---\n正文", encoding="utf-8")
        self.assertEqual(main(["cover", str(md)]), 0)
        self.assertTrue((self.dir / "cover.png").is_file())

    def test_missing_file(self):
        code = main(["cover", str(self.dir / "nope.md")])
        self.assertEqual(code, 2)

    def test_unknown_theme_is_friendly(self):
        md = self.dir / "c.md"
        md.write_text("---\ntitle: T\ntheme: 不存在的主题\n---\nx", encoding="utf-8")
        # 不能抛异常，要给非零退出码 + 提示
        self.assertEqual(main(["cover", str(md)]), 2)

    def test_no_title_anywhere(self):
        self.assertEqual(main(["cover"]), 2)

    def test_no_frontmatter_falls_back_to_args(self):
        md = self.dir / "d.md"
        md.write_text("正文里没有 frontmatter", encoding="utf-8")
        out = self.dir / "d.png"
        code = main(["cover", str(md), "--title", "命令行给的标题", "-o", str(out)])
        self.assertEqual(code, 0)
        self.assertTrue(out.is_file())


if __name__ == "__main__":
    unittest.main()
