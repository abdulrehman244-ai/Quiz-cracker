"""Generates the Windows .ico application icon for Quiz Cracker."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def generate_icon(output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded square gradient background (blue -> emerald)
    pad = 12
    radius = 52
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=radius, fill=255)

    grad = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    px = grad.load()
    c1 = (31, 111, 235)   # #1f6feb
    c2 = (46, 160, 67)    # #2ea043
    for y in range(size):
        for x in range(size):
            t = (x + y) / float(2 * size)
            r = int(c1[0] + (c2[0] - c1[0]) * t)
            g = int(c1[1] + (c2[1] - c1[1]) * t)
            b = int(c1[2] + (c2[2] - c1[2]) * t)
            px[x, y] = (r, g, b, 255)

    img.paste(grad, (0, 0), mask)

    # Subtle inner border
    draw.rounded_rectangle(
        [pad + 2, pad + 2, size - pad - 2, size - pad - 2],
        radius=radius - 2,
        outline=(255, 255, 255, 70),
        width=4,
    )

    # Bold "Q" emblem centered
    font = None
    for font_name in ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf"]:
        try:
            font = ImageFont.truetype(font_name, 152)
            break
        except Exception:
            pass
    if font is None:
        font = ImageFont.load_default()

    text = "Q"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0]
    ty = (size - th) // 2 - bbox[1] - 4

    # Soft shadow
    draw.text((tx + 4, ty + 6), text, font=font, fill=(0, 0, 0, 90))
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    # Small glowing green check dot in bottom-right
    draw.ellipse([178, 178, 226, 226], fill=(13, 17, 23, 255))
    draw.ellipse([184, 184, 220, 220], fill=(63, 185, 80, 255))

    img.save(
        output_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Generated icon: {output_path}")


if __name__ == "__main__":
    generate_icon(Path(__file__).resolve().parent / "assets" / "quiz_cracker.ico")
