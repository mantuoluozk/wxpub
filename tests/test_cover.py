# -*- coding: utf-8 -*-
"""封面渲染测试。

核心不变量只有一条：**任何标题都不能画出安全区**。
因为微信信息流会裁掉封面左右两边，文字一旦贴边就等于看不见。
其余测试都是围绕这条不变量在各种极端输入下的表现。
"""

import itertools
import unittest

from PIL import Image, ImageDraw

from wxpub.cover import (
    LAYOUTS,
    SAFE_WIDTH_RATIO,
    SIZES,
    CoverRenderer,
    CoverSpec,
    _line_width,
    parse_spans,
    render_cover,
    split_lines,
)
from wxpub.theme import THEMES, get_theme


class TestBasics(unittest.TestCase):
    def test_default_size(self):
        img = render_cover("标题")
        self.assertEqual(img.size, (1280, 544))
        self.assertEqual(img.mode, "RGB")

    def test_ratio_is_235(self):
        # 公众号头图 2.35:1，用 16:9 会在信息流里被裁两侧
        w, h = SIZES["hd"]
        self.assertAlmostEqual(w / h, 2.35, places=2)

    def test_all_size_presets(self):
        for name, (w, h) in SIZES.items():
            img = render_cover("标题", "副标题", badge="2026-11-02", size=name)
            self.assertEqual(img.size, (w, h), name)
            self.assertAlmostEqual(w / h, 2.35, places=2)

    def test_custom_size(self):
        img = render_cover("标题", width=800, height=340)
        self.assertEqual(img.size, (800, 340))

    def test_every_theme(self):
        for name in THEMES:
            img = render_cover("标题", "副标题", badge="2026-11-02", theme=name)
            self.assertEqual(img.size, (1280, 544))

    def test_every_layout(self):
        for name in LAYOUTS:
            img = render_cover("标题|第二行", "副标题", badge="2026-11-02", layout=name)
            self.assertEqual(img.size, (1280, 544))

    def test_all_combinations(self):
        n = 0
        for t, l in itertools.product(THEMES, LAYOUTS):
            render_cover("测试|**高亮**", "副标题", badge="2026-11-02", theme=t, layout=l)
            n += 1
        self.assertEqual(n, len(THEMES) * len(LAYOUTS))

    def test_unknown_theme_raises(self):
        with self.assertRaises(KeyError):
            render_cover("标题", theme="不存在的主题")

    def test_unknown_layout_raises(self):
        with self.assertRaises(ValueError):
            render_cover("标题", layout="不存在的布局")


class TestParsing(unittest.TestCase):
    def test_split_by_pipe(self):
        self.assertEqual(split_lines("第一行|第二行"), ["第一行", "第二行"])

    def test_split_by_newline(self):
        self.assertEqual(split_lines("第一行\n第二行"), ["第一行", "第二行"])

    def test_split_drops_empty(self):
        self.assertEqual(split_lines("一||二|\n"), ["一", "二"])

    def test_accent_spans(self):
        spans = parse_spans("在替别人**烧钱**")
        self.assertEqual([s.text for s in spans], ["在替别人", "烧钱"])
        self.assertEqual([s.accent for s in spans], [False, True])

    def test_multiple_accent(self):
        spans = parse_spans("**A**中间**B**")
        self.assertEqual([s.text for s in spans], ["A", "中间", "B"])
        self.assertEqual([s.accent for s in spans], [True, False, True])

    def test_unclosed_accent_is_literal(self):
        spans = parse_spans("这是 **没闭合")
        self.assertEqual(len(spans), 1)
        self.assertFalse(spans[0].accent)


class TestSafeArea(unittest.TestCase):
    """标题绝不能超出安全宽度 —— 这是封面能不能用的底线。"""

    CASES = [
        "短",
        "中等长度的标题",
        "这是一条非常非常长的标题用来测试折行逻辑是否正常工作",
        "中文 English 混排 12345 的标题",
        "https://example.com/a/very/long/url/that/never/breaks 后面还有字",
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "标点，应该优先在这里断行。然后是第二句。最后一句。",
    ]

    def _check(self, title, theme="midnight", layout="stack", size=(1280, 544)):
        spec = CoverSpec(title=title, subtitle="副标题", badge="2026-11-02",
                         theme=theme, layout=layout, width=size[0], height=size[1])
        r = CoverRenderer(spec)
        lines, font_size = r._prepare_lines(start_size=int(size[1] * 0.176), max_height=size[1] * 0.55)
        font = r.fonts.get(font_size)
        draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        max_w = size[0] * SAFE_WIDTH_RATIO
        for line in lines:
            w = _line_width(line, font, draw)
            self.assertLessEqual(
                w, max_w + 1.5,
                f"标题行超出安全区：{w:.0f} > {max_w:.0f}  『{''.join(s.text for s in line)}』",
            )
        return lines

    def test_safe_area_1280(self):
        for t in self.CASES:
            self._check(t)

    def test_safe_area_small(self):
        # 900×383 也要成立，很多人生成小图上传更快
        for t in self.CASES:
            self._check(t, size=(900, 383))

    def test_long_title_wraps_into_multiple_lines(self):
        lines = self._check(self.CASES[2])
        self.assertGreaterEqual(len(lines), 2)

    def test_break_prefers_punctuation(self):
        # 断点应落在标点之后，而不是把词劈开
        lines = self._check(self.CASES[6])
        first = "".join(s.text for s in lines[0])
        self.assertTrue(
            first.endswith(("，", "。")) or len(first) > 6,
            f"第一行断在了奇怪的位置：{first}",
        )


class TestEdgeInputs(unittest.TestCase):
    def test_empty_title(self):
        img = render_cover("", "副标题")
        self.assertEqual(img.size, (1280, 544))

    def test_whitespace_title(self):
        render_cover("   ", "副标题")

    def test_very_long_single_char_repeat(self):
        render_cover("测" * 80)

    def test_emoji_title(self):
        # 字体没字形时会画空白，但不应该崩
        render_cover("测试 🚀 emoji")

    def test_no_subtitle_no_badge(self):
        render_cover("只有标题")

    def test_title_size_override(self):
        spec = CoverSpec(title="标题", theme="midnight", title_size=120)
        self.assertEqual(CoverRenderer(spec)._title_font_size([parse_spans("标题")], 200, 100), 120)

    def test_left_align(self):
        img = render_cover("左对齐标题", "副标题", align="left", layout="split")
        self.assertEqual(img.size, (1280, 544))


class TestTheme(unittest.TestCase):
    def test_get_theme_case_insensitive(self):
        self.assertEqual(get_theme("MIDNIGHT").name, "midnight")

    def test_paper_is_light(self):
        # 浅色主题必须被正确标记，否则深色背景上会用白字变成隐形
        self.assertFalse(get_theme("paper").dark)
        self.assertTrue(get_theme("midnight").dark)

    def test_title_lighter_than_bg_on_dark(self):
        for name, t in THEMES.items():
            if not t.dark:
                continue
            bg_lum = sum(t.bg) / 3
            title_lum = sum(t.title) / 3
            self.assertGreater(title_lum, bg_lum + 80, f"{name} 标题和背景对比度不够")


if __name__ == "__main__":
    unittest.main()
