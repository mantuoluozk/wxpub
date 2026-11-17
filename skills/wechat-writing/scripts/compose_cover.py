"""Place the approved cover title on a generated, text-free illustration."""
import argparse
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


SIZES = {"wechat": (1280, 544), "ppt": (1600, 900)}
INK = "#242F3C"
FONT_PATHS = (
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyhbd.ttc",
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf"),
    Path("/System/Library/Fonts/PingFang.ttc"),
)


def wrap_title(title, font, max_width):
    lines = []
    for paragraph in title.splitlines():
        line = ""
        for char in paragraph:
            if line and font.getlength(line + char) > max_width:
                lines.append(line.rstrip())
                line = char.lstrip()
            else:
                line += char
        if line.strip():
            lines.append(line.rstrip())
    return lines


def put_title(image, title, font_path):
    width, height = image.size
    draw = ImageDraw.Draw(image)
    max_width = width * 0.33
    for size in range(round(width * 0.053), round(width * 0.038) - 1, -2):
        font = ImageFont.truetype(str(font_path), size)
        lines = wrap_title(title, font, max_width)
        if len(lines) <= 2 and all(font.getlength(line) <= max_width for line in lines):
            left = round(width * 0.22)
            top = round(height * 0.20)
            for index, line in enumerate(lines):
                draw.text((left, top + index * round(size * 1.22)), line,
                          font=font, fill=INK, anchor="lt")
            return
    raise ValueError("标题在安全区内放不下，请用更短的封面标题或调整换行。")


def main():
    parser = argparse.ArgumentParser(description="在无字手绘背景上叠加封面标题")
    parser.add_argument("background", type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--format", choices=SIZES, default="wechat")
    parser.add_argument("--font", type=Path, help="可选的中文粗体字体路径")
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()

    title = args.title.strip()
    if not title:
        parser.error("请提供封面标题。")
    if args.background.resolve() == args.output.resolve():
        parser.error("背景和输出请使用不同文件。")
    font_path = args.font or next((path for path in FONT_PATHS if path.is_file()), None)
    if not font_path:
        parser.error("未找到中文字体。请安装思源黑体，或用 --font 指定中文粗体字体。")

    try:
        with Image.open(args.background) as source:
            image = ImageOps.fit(
                ImageOps.exif_transpose(source).convert("RGB"),
                SIZES[args.format], Image.Resampling.LANCZOS,
            )
        put_title(image, title, font_path)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()

