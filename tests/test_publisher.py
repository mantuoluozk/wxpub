# -*- coding: utf-8 -*-
"""组装流程的端到端测试（不联网）。

dry-run 必须走完整的组装路径，否则它就失去了「提前发现问题」的意义。
这里验证：封面会自动生成、缺失图片会报警、超长外文引用会被拦、预览页能落地。
"""

import os
import tempfile
import unittest
from pathlib import Path

from wxpub.publisher import build_bundle, check_citations, check_links, write_preview


class PublisherTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wxpub-pub-"))

    def tearDown(self):
        for root, dirs, files in os.walk(self.tmp, topdown=False):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except OSError:
                    pass
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except OSError:
                    pass
        try:
            os.rmdir(self.tmp)
        except OSError:
            pass

    def write_md(self, name, content):
        p = self.tmp / name
        p.write_text(content, encoding="utf-8")
        return str(p)


class TestBuildBundle(PublisherTestBase):
    def test_minimal_article(self):
        md = self.write_md("a.md", "---\ntitle: 标题\n---\n正文一段。")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        self.assertEqual(b.title, "标题")
        self.assertIn("正文一段", b.html)
        self.assertTrue(b.cover_path.exists())
        self.assertEqual(b.cover_path.name, "cover.png")

    def test_cover_size_is_235(self):
        from PIL import Image

        md = self.write_md("a.md", "---\ntitle: 标题\n---\n正文")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        with Image.open(b.cover_path) as im:
            self.assertAlmostEqual(im.width / im.height, 2.35, places=2)

    def test_title_falls_back_to_h1(self):
        md = self.write_md("a.md", "# 从 H1 取标题\n\n正文")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        self.assertEqual(b.title, "从 H1 取标题")

    def test_title_falls_back_to_filename(self):
        md = self.write_md("我的文章.md", "正文没有标题")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        self.assertEqual(b.title, "我的文章")

    def test_digest_from_summary(self):
        md = self.write_md("a.md", "---\ntitle: T\nsummary: 这是摘要\n---\n正文")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        self.assertEqual(b.digest, "这是摘要")

    def test_digest_auto_from_body(self):
        md = self.write_md("a.md", "---\ntitle: T\n---\n" + "正文内容。" * 40)
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        self.assertTrue(b.digest)
        self.assertLessEqual(len(b.digest), 100)

    def test_theme_from_frontmatter(self):
        md = self.write_md("a.md", "---\ntitle: T\ntheme: ocean\n---\n正文")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        self.assertEqual(b.theme, "ocean")

    def test_invalid_theme_falls_back(self):
        md = self.write_md("a.md", "---\ntitle: T\ntheme: 不存在的\n---\n正文")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        self.assertEqual(b.theme, "midnight")

    def test_missing_image_warns(self):
        md = self.write_md("a.md", "---\ntitle: T\n---\n![图](nope.png)")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        self.assertTrue(any("找不到" in w for w in b.warnings))

    def test_local_image_copied_for_preview(self):
        from PIL import Image

        (self.tmp / "imgs").mkdir()
        Image.new("RGB", (100, 60), (10, 20, 30)).save(self.tmp / "imgs" / "x.png")
        md = self.write_md("a.md", "---\ntitle: T\n---\n![图](imgs/x.png)")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        self.assertEqual(len(b.images_local), 1)
        self.assertIn("imgs/x.png", b.html)

    def test_dry_run_copies_images_into_out(self):
        # 回归测试：normalize 对合格图片是原样返回、不落盘的，
        # 但预览页需要图片真的在 out/imgs 下，否则整页裂图。
        from PIL import Image

        (self.tmp / "imgs").mkdir()
        Image.new("RGB", (100, 60), (5, 5, 5)).save(self.tmp / "imgs" / "x.png")
        md = self.write_md("a.md", "---\ntitle: T\n---\n![图](imgs/x.png)")
        out = self.tmp / "out"
        b = build_bundle(md, out_dir=str(out))
        self.assertTrue((out / "imgs" / "x.png").is_file(), "预览用图片没有被复制到 out/imgs")

    def test_preview_cover_copied_into_out(self):
        from PIL import Image

        Image.new("RGB", (1280, 544)).save(self.tmp / "my.png")
        md = self.write_md("a.md", "---\ntitle: T\n---\n正文")
        out = self.tmp / "out"
        b = build_bundle(md, out_dir=str(out), cover=str(self.tmp / "my.png"))
        self.assertEqual(b.cover_path.parent.resolve(), out.resolve())
        self.assertTrue(b.cover_path.is_file())

    def test_image_handler_used(self):
        from PIL import Image

        (self.tmp / "imgs").mkdir()
        Image.new("RGB", (100, 60)).save(self.tmp / "imgs" / "x.png")
        md = self.write_md("a.md", "---\ntitle: T\n---\n![图](imgs/x.png)")
        b = build_bundle(
            md,
            out_dir=str(self.tmp / "out"),
            upload_image=lambda p: "https://mmbiz.qpic.cn/fake.png",
        )
        self.assertIn("https://mmbiz.qpic.cn/fake.png", b.html)

    def test_explicit_cover_used(self):
        from PIL import Image

        Image.new("RGB", (1280, 544)).save(self.tmp / "my.png")
        md = self.write_md("a.md", "---\ntitle: T\n---\n正文")
        b = build_bundle(md, out_dir=str(self.tmp / "out"), cover=str(self.tmp / "my.png"))
        self.assertEqual(b.cover_path.name, "my.png")

    def test_missing_explicit_cover_raises(self):
        md = self.write_md("a.md", "---\ntitle: T\n---\n正文")
        with self.assertRaises(FileNotFoundError):
            build_bundle(md, out_dir=str(self.tmp / "out"), cover="nope.png")

    def test_missing_md_raises(self):
        with self.assertRaises(FileNotFoundError):
            build_bundle(str(self.tmp / "nope.md"))


class TestChecks(PublisherTestBase):
    def test_long_english_quote_flagged(self):
        quote = "This is a very long English quotation " * 8
        warns = check_citations("> " + quote)
        self.assertTrue(warns)
        self.assertIn("英文词", warns[0])

    def test_short_quote_ok(self):
        self.assertEqual(check_citations("> short quote here"), [])

    def test_chinese_quote_not_flagged(self):
        self.assertEqual(check_citations("> 这是一段中文引用，不涉及外文原创度问题。"), [])

    def test_external_link_flagged(self):
        warns = check_links("[点我](https://example.com/page)")
        self.assertTrue(warns)

    def test_wechat_link_not_flagged(self):
        self.assertEqual(check_links("[点我](https://mp.weixin.qq.com/s/abc)"), [])

    def test_long_title_flagged(self):
        md = self.write_md("a.md", "---\ntitle: " + "长" * 70 + "\n---\n正文")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        self.assertTrue(any("标题" in w for w in b.warnings))

    def test_long_author_flagged(self):
        md = self.write_md("a.md", "---\ntitle: T\n---\n正文")
        b = build_bundle(md, out_dir=str(self.tmp / "out"), author="一二三四五六七八九十")
        self.assertTrue(any("作者" in w for w in b.warnings))


class TestPreview(PublisherTestBase):
    def test_preview_written(self):
        md = self.write_md("a.md", "---\ntitle: 标题\n---\n正文")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        page = write_preview(b)
        self.assertTrue(page.exists())
        html = page.read_text(encoding="utf-8")
        self.assertIn("标题", html)
        self.assertIn("cover.png", html)
        self.assertNotIn("{{", html)

    def test_preview_shows_warnings(self):
        md = self.write_md("a.md", "---\ntitle: T\n---\n![x](nope.png)")
        b = build_bundle(md, out_dir=str(self.tmp / "out"))
        html = write_preview(b).read_text(encoding="utf-8")
        self.assertIn("发布前检查", html)


if __name__ == "__main__":
    unittest.main()
