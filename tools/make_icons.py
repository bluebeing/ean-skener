"""Vygeneruje ikony PWA a agenta (spustit jednou: python tools/make_icons.py)."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BG, BAR, LINE = (15, 17, 21), (232, 234, 237), (61, 220, 132)
# šířky čar a mezer čárového kódu (jednotky)
PATTERN = [2, 1, 1, 1, 3, 2, 1, 1, 2, 3, 1, 1, 2, 1, 1, 2, 3, 1, 1, 1, 2, 2, 1, 1, 2]


def draw(size, safe=0.62, rounded=True):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=BG)
    else:
        d.rectangle((0, 0, size, size), fill=BG)
    w = size * safe
    unit = w / sum(PATTERN)
    x, top, bottom = (size - w) / 2, size * 0.30, size * 0.70
    for i, u in enumerate(PATTERN):
        if i % 2 == 0:
            d.rectangle((x, top, x + u * unit - 1, bottom), fill=BAR)
        x += u * unit
    y = size / 2
    d.rectangle((size * 0.14, y - size * 0.012, size * 0.86, y + size * 0.012), fill=LINE)
    return img


icons = ROOT / "pwa" / "icons"
icons.mkdir(parents=True, exist_ok=True)
draw(192).save(icons / "icon-192.png")
draw(512).save(icons / "icon-512.png")
draw(512, safe=0.5, rounded=False).save(icons / "maskable-512.png")
draw(180, rounded=False).convert("RGB").save(icons / "apple-touch-icon.png")
draw(256).save(ROOT / "agent" / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
print("ikony hotové")
