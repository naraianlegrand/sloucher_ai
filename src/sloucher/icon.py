"""The icon: a person sitting tall, drawn with Pillow, in a colour per state.

The tray uses the same drawing for each state (good, slouch, alert, walk, away),
bent forward when you slouch. `python -m sloucher.icon out.ico` writes the app icon.
"""
import sys

from PIL import Image, ImageDraw, ImageFilter

BG = (0, 0, 0)
STATES = {
    "good": (255, 214, 10),     # signal yellow: the brand colour
    "slouch": (255, 159, 10),   # orange
    "alert": (255, 69, 58),     # red
    "walk": (100, 210, 255),    # blue
    "away": (142, 142, 147),    # grey
}


def draw(size=256, accent=STATES["good"], slouched=False, tile=True):
    """RGBA icon. slouched=True bends the spine and drops the head forward."""
    s = 4 * size                              # supersample for smooth edges
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = s / 100                               # 1 unit = 1% of the icon

    if tile:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=22 * u, fill=BG + (255,))
        # Soft halo behind the figure: the NPU quietly working
        halo = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse([18 * u, 14 * u, 82 * u, 78 * u], outline=accent + (90,), width=int(3 * u))
        img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(1.5 * u)))

    w = int(9 * u)                            # stroke width
    if slouched:
        head, neck, hip, droop = (55, 39), (51, 54), (49, 81), 12
        spine = [neck, (47, 66), hip]
    else:
        head, neck, hip, droop = (50, 31), (50, 47), (50, 80), 7
        spine = [neck, hip]

    def pts(p):
        return [(x * u, y * u) for x, y in p]

    # Shoulders: an arch across the neck, drooping more when slouched
    sx, sy = neck
    ends = [(sx - 16, sy + droop), (sx + 16, sy + droop)]
    d.line(pts([ends[0], (sx - 8, sy + 1), (sx, sy), (sx + 8, sy + 1), ends[1]]), fill=accent, width=w, joint="curve")
    d.line(pts(spine), fill=accent, width=w, joint="curve")
    for x, y in ends + [hip, neck]:
        d.ellipse([(x - 4.5) * u, (y - 4.5) * u, (x + 4.5) * u, (y + 4.5) * u], fill=accent)   # round caps
    hx, hy = head
    d.ellipse([(hx - 10) * u, (hy - 10) * u, (hx + 10) * u, (hy + 10) * u], fill=accent)
    return img.resize((size, size), Image.LANCZOS)


def write_ico(path):
    draw(256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    write_ico(sys.argv[1] if len(sys.argv) > 1 else "icon.ico")
