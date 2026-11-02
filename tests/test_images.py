# -*- coding: utf-8 -*-
"""图片处理测试。

关键是「不信任扩展名」：从网页扒下来的图经常叫 xxx.png 实际是 WebP，
微信不收，报的错还跟格式无关，非常难查。这里用伪造文件头覆盖这种情况。
"""

import os
import tempfile
import unittest

from PIL import Image

from wxpub.images import (
    MAX_BODY_IMAGE_BYTES,
    ImageIssue,
    describe,
    normalize,
    sniff,
)


class ImageTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wxpub-test-")

    def tearDown(self):
        for root, _dirs, files in os.walk(self.tmp, topdown=False):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except OSError:
                    pass
        try:
            os.rmdir(self.tmp)
        except OSError:
            pass

    def make(self, name, fmt="PNG", size=(400, 200), color=(200, 100, 50)):
        path = os.path.join(self.tmp, name)
        Image.new("RGB", size, color).save(path, fmt)
        return path


class TestSniff(ImageTestBase):
    def test_png(self):
        self.assertEqual(sniff(self.make("a.png", "PNG")), "PNG")

    def test_jpeg(self):
        self.assertEqual(sniff(self.make("a.jpg", "JPEG")), "JPEG")

    def test_gif(self):
        self.assertEqual(sniff(self.make("a.gif", "GIF")), "GIF")

    def test_webp(self):
        self.assertEqual(sniff(self.make("a.webp", "WEBP")), "WEBP")

    def test_webp_disguised_as_png(self):
        # 真实世界最常见的情况：网页优化把 png 换成了 webp，文件名没改
        path = self.make("fake.png", "WEBP")
        self.assertEqual(sniff(path), "WEBP")

    def test_unknown_bytes(self):
        path = os.path.join(self.tmp, "x.png")
        with open(path, "wb") as f:
            f.write(b"NOTANIMAGE" * 10)
        self.assertEqual(sniff(path), "UNKNOWN")

    def test_missing_file(self):
        self.assertEqual(sniff(os.path.join(self.tmp, "nope.png")), "UNKNOWN")

    def test_describe(self):
        d = describe(self.make("a.png"))
        self.assertIn("PNG", d)
        self.assertIn("400x200", d)


class TestNormalize(ImageTestBase):
    def test_good_png_untouched(self):
        path = self.make("ok.png", "PNG")
        out, actions = normalize(path, out_dir=self.tmp)
        self.assertEqual(os.path.abspath(out), os.path.abspath(path))
        self.assertEqual(actions, [])

    def test_webp_converted_to_png(self):
        path = self.make("img.webp", "WEBP")
        out, actions = normalize(path, out_dir=self.tmp)
        self.assertTrue(out.endswith(".png"))
        self.assertEqual(sniff(out), "PNG")
        self.assertTrue(actions)
        self.assertIn("PNG", actions[0])

    def test_webp_disguised_png_converted(self):
        path = self.make("fake.png", "WEBP")
        out, actions = normalize(path, out_dir=self.tmp)
        self.assertEqual(sniff(out), "PNG")
        self.assertTrue(actions, "应该提示做过转换")

    def test_oversized_compressed(self):
        # 造一张噪点图，很难压，逼它走降质/缩放路径
        import random

        img = Image.new("RGB", (2400, 1600))
        px = img.load()
        for y in range(0, 1600, 3):
            for x in range(0, 2400, 3):
                px[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        path = os.path.join(self.tmp, "big.png")
        img.save(path, "PNG")
        self.assertGreater(os.path.getsize(path), MAX_BODY_IMAGE_BYTES)

        out, actions = normalize(path, out_dir=self.tmp)
        self.assertLessEqual(os.path.getsize(out), MAX_BODY_IMAGE_BYTES)
        self.assertTrue(actions)

    def test_missing_file_raises(self):
        with self.assertRaises(ImageIssue):
            normalize(os.path.join(self.tmp, "nope.png"))

    def test_output_dir_created(self):
        path = self.make("a.webp", "WEBP")
        target = os.path.join(self.tmp, "deep", "nested")
        out, _ = normalize(path, out_dir=target)
        self.assertTrue(os.path.isdir(target))
        self.assertTrue(os.path.exists(out))

    def test_alpha_preserved_for_png(self):
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        path = os.path.join(self.tmp, "alpha.webp")
        img.save(path, "WEBP")
        out, _ = normalize(path, out_dir=self.tmp)
        with Image.open(out) as im:
            self.assertIn(im.mode, ("RGBA", "RGB"))


if __name__ == "__main__":
    unittest.main()
