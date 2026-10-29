"""Generate the repository social preview using Pillow already in the uv lockfile."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCALE = 2
NAVY = "#0B1020"
PANEL = "#151D31"
LIME = "#B7F36B"
LIGHT = "#C4CBDA"
WHITE = "#FFFFFF"


def point(value):
    return int(value * SCALE)


def coords(*values):
    return tuple(point(value) for value in values)


def font(size):
    return ImageFont.load_default(size=point(size))


def main():
    image = Image.new("RGB", coords(1280, 640), NAVY)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(coords(64, 55, 132, 123), radius=point(16), fill=PANEL)
    draw.rectangle(coords(78, 70, 91, 83), outline=LIME, width=point(2))
    draw.rectangle(coords(78, 95, 91, 108), outline=LIME, width=point(2))
    draw.line(
        [coords(91, 76), coords(98, 76), coords(98, 101), coords(91, 101)],
        fill=LIGHT,
        width=point(2),
    )
    draw.line([coords(98, 89), coords(105, 89)], fill=LIGHT, width=point(2))
    for x, y in [(108, 93), (114, 86), (120, 78)]:
        draw.line([coords(x, 101), coords(x, y)], fill=LIME, width=point(3))
    draw.text(coords(148, 73), "MARKETPLACE  /  DATA PLATFORM", fill=LIGHT, font=font(17))
    draw.text(coords(64, 184), "Marketplace", fill=WHITE, font=font(72), stroke_width=1)
    draw.text(coords(64, 270), "Intelligence Platform", fill=WHITE, font=font(72), stroke_width=1)
    draw.text(
        coords(68, 384),
        "A reliable data platform for marketplace operations.",
        fill=LIGHT,
        font=font(25),
    )
    draw.line([coords(68, 477), coords(1212, 477)], fill="#354058", width=point(1))
    stages = [
        (68, "01", "SOURCE"),
        (370, "02", "INGEST"),
        (672, "03", "MODEL"),
        (974, "04", "EXPLORE"),
    ]
    for x, number, label in stages:
        draw.rounded_rectangle(coords(x, 518, x + 240, 581), radius=point(12), fill=PANEL)
        draw.text(coords(x + 20, 536), number, fill=LIME, font=font(18))
        draw.text(coords(x + 57, 536), label, fill=WHITE, font=font(18))
        if x != stages[-1][0]:
            draw.line([coords(x + 250, 550), coords(x + 290, 550)], fill=LIME, width=point(2))
            draw.polygon(
                [coords(x + 290, 545), coords(x + 298, 550), coords(x + 290, 555)], fill=LIME
            )
    output = Path(__file__).resolve().parents[1] / "assets/brand/social-preview.png"
    image.resize((1280, 640), Image.Resampling.LANCZOS).save(output, optimize=True)


if __name__ == "__main__":
    main()
