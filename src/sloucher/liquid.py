"""Smoked glass for Tk: tiles, capsule buttons and bars that look like dark glass.

On a near-black window, each piece gets what Liquid Glass is known for: a body lit from above,
a fine bright rim where the light catches the top edge, a faint sheen across the top, capsule
shapes and concentric corners, and colour only on the main action. It isn't see-through on
purpose: it stays readable on any desktop and looks the same everywhere.

Everything is drawn once with Pillow (antialiased at 3x) and cached; nothing animates or redraws
while a window is idle.
"""
from PIL import Image, ImageDraw, ImageFilter, ImageTk

SS = 3                      # supersampling for smooth corners
BODY = (0x22, 0x0E)         # clear glass: top and bottom of the body gradient
TINT = (1.0, 0.78)          # tinted glass: share of the colour at the top and bottom
SHEEN = 10                  # brightness of the band across the top
RIM = (120, 24, 34)         # rim brightness: top edge, sides, bottom edge
_cache = {}


def _mix(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def _shape(w, h, r, tint, level):
    """RGBA image of one glass piece. level: 1 normal, 1.35 hover, 0.8 pressed."""
    W, H, R = w * SS, h * SS, min(r, h / 2, w / 2) * SS
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), R, fill=255)

    # Body: a vertical gradient, lighter at the top, so it looks lit from above
    top, bottom = (_mix(tint, TINT[0]), _mix(tint, TINT[1])) if tint else ((BODY[0],) * 3, (BODY[1],) * 3)
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / max(1, H - 1)
        grad.putpixel((0, y), tuple(min(255, int((a * (1 - t) + b * t) * level)) for a, b in zip(top, bottom)))
    body = grad.resize((W, H))

    # Sheen: a soft brighter band across the top
    sheen = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sheen).rounded_rectangle((R * 0.4, SS, W - R * 0.4, min(H * 0.38, 60 * SS)), R,
                                            fill=int(SHEEN * level))
    sheen = sheen.filter(ImageFilter.GaussianBlur(H * 0.08))
    body = Image.composite(Image.new("RGB", (W, H), (255, 255, 255)), body, sheen)

    # Rim: bright at the top edge, fading down the sides, a little light again at the bottom
    rim = Image.new("L", (W, H), 0)
    ImageDraw.Draw(rim).rounded_rectangle((0, 0, W - 1, H - 1), R, outline=255, width=int(1.4 * SS))
    fade = Image.new("L", (1, H))
    peak, side, low = RIM
    for y in range(H):
        t = y / max(1, H - 1)
        fade.putpixel((0, y), int((peak * (1 - t) ** 3 + side + low * t ** 6) * min(level, 1.2)))
    rim = Image.composite(fade.resize((W, H)), Image.new("L", (W, H), 0), rim)
    rim_colour = (255, 255, 255) if not tint else tuple(min(255, int(v * 0.5 + 140)) for v in tint)
    body = Image.composite(Image.new("RGB", (W, H), rim_colour), body, rim)

    # Transparent outside the shape, so a bar over a panel keeps the panel's glass in its corners
    out = body.convert("RGBA")
    out.putalpha(mask)
    return out.resize((w, h), Image.LANCZOS)


def piece(w, h, r, tint=None, level=1.0):
    """A Tk image of a glass tile / button / bar. tint: (r, g, b) or None for clear glass."""
    key = (int(w), int(h), int(r), tint, level)
    if key not in _cache:
        _cache[key] = ImageTk.PhotoImage(_shape(int(w), int(h), r, tint, level))
    return _cache[key]


def rgb(hex_colour):
    return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))


class Button:
    """A glass capsule on a Canvas: brightens on hover, dims when pressed, calls `command` on release.

    Tinted glass carries black text; clear glass carries white.
    """

    def __init__(self, canvas, x, y, text, command, tint=None, font=("Segoe UI Semibold", 11), pad=22, h=40,
                 anchor="nw"):
        self.cv, self.command, self.tint = canvas, command, tint
        probe = canvas.create_text(0, 0, text=text, font=font, anchor="nw")
        x0, y0, x1, y1 = canvas.bbox(probe)
        canvas.delete(probe)
        self.w, self.h = (x1 - x0) + 2 * pad, h
        if anchor == "ne":
            x -= self.w
        self.x, self.y = x, y
        self.img = canvas.create_image(x, y, image=piece(self.w, h, h / 2, tint), anchor="nw")
        self.label = canvas.create_text(x + self.w / 2, y + h / 2, text=text, font=font,
                                        fill="#000000" if tint else "#F7F7F5")
        for item in (self.img, self.label):
            canvas.tag_bind(item, "<Enter>", lambda e: self._look(1.35))
            canvas.tag_bind(item, "<Leave>", lambda e: self._look(1.0))
            canvas.tag_bind(item, "<ButtonPress-1>", lambda e: self._look(0.8))
            canvas.tag_bind(item, "<ButtonRelease-1>", self._release)

    def _look(self, level):
        self.cv.itemconfigure(self.img, image=piece(self.w, self.h, self.h / 2, self.tint, level))
        self.cv.configure(cursor="hand2" if level != 1.0 else "")

    def _release(self, e):
        self._look(1.35)
        self.command()
