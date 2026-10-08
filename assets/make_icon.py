"""Draws the ghost icon (needs Pillow): python assets/make_icon.py assets

Writes ghost.ico (for the .exe), ghost.png and ghost-64.png / ghost-32.png. The app embeds
ghost-64.png and ghost-32.png as base64 (GHOST_ICON_64 / GHOST_ICON_32 in autoclicker.py)."""
import math, sys
from PIL import Image, ImageDraw
N = 1024
img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# tile: rounded square with a vertical indigo gradient
grad = Image.new("RGBA", (N, N))
top, bot = (129, 140, 248), (67, 56, 202)
for y in range(N):
    t = y / (N - 1)
    grad.paste(tuple(int(a + (b - a) * t) for a, b in zip(top, bot)) + (255,), (0, y, N, y + 1))
mask = Image.new("L", (N, N), 0)
ImageDraw.Draw(mask).rounded_rectangle((24, 24, N - 24, N - 24), radius=220, fill=255)
img.paste(grad, (0, 0), mask)

# ghost body: dome + sides + wavy bottom
cx, w = 470, 520                       # centre x, body width
left, right = cx - w // 2, cx + w // 2
top_y, bottom_y = 190, 800
r = w // 2
pts = []
for i in range(181):                   # dome
    a = math.pi + math.pi * i / 180
    pts.append((cx + r * math.cos(a), top_y + r + r * math.sin(a)))
pts.append((right, bottom_y))
waves, amp = 3, 70                     # three scallops along the bottom
for i in range(1, 241):
    x = right - (right - left) * i / 240
    phase = (i / 240) * waves * 2 * math.pi
    pts.append((x, bottom_y - amp * (1 - math.cos(phase)) / 2))
d.polygon(pts, fill=(255, 255, 255, 255))

# eyes
eye = (30, 27, 75, 255)
for ex in (cx - 95, cx + 95):
    d.ellipse((ex - 46, 400 - 66, ex + 46, 400 + 66), fill=eye)
    d.ellipse((ex - 14, 400 - 40, ex + 12, 400 - 12), fill=(255, 255, 255, 255))   # shine

# mouse pointer (bottom right), white with dark outline
def arrow(ox, oy, s):
    p = [(0, 0), (0, 15), (3.6, 11.6), (6.3, 17.6), (8.7, 16.6), (6.1, 10.7), (11, 10.7)]
    return [(ox + x * s, oy + y * s) for x, y in p]
d.polygon(arrow(600, 520, 22), fill=(255, 255, 255, 255), outline=eye, width=16)

out = sys.argv[1]
img.resize((256, 256), Image.LANCZOS).save(f"{out}/ghost.png", optimize=True)
sizes = [16, 24, 32, 48, 64, 128, 256]
icons = [img.resize((s, s), Image.LANCZOS) for s in sizes]
icons[-1].save(f"{out}/ghost.ico", sizes=[(s, s) for s in sizes], append_images=icons[:-1])
for s in (64, 32):
    img.resize((s, s), Image.LANCZOS).save(f"{out}/ghost-{s}.png", optimize=True)
