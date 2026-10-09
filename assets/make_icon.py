"""Draws the ghost icon (needs Pillow): python assets/make_icon.py assets

Writes ghost.ico (for the .exe), ghost.png and ghost-64.png / ghost-32.png. The app embeds
ghost-64.png and ghost-32.png as base64 (GHOST_ICON_64 / GHOST_ICON_32 in autoclicker.py)."""
import io, math, struct, sys
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

def write_ico(img, path, sizes=(16, 20, 24, 32, 40, 48, 64, 96, 128, 256)):
    """Write a .ico the classic way: 32-bit bitmaps below 256 px, PNG only at 256 px.
    (Pillow stores every size as PNG, and Explorer then shows the default icon in some views.)"""
    entries = []
    for size in sizes:
        im = img.resize((size, size), Image.LANCZOS)
        if size >= 256:
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)
            entries.append((size, buf.getvalue()))
            continue
        px = im.load()
        xor = bytearray()
        for y in range(size - 1, -1, -1):                  # bitmaps are stored bottom-up
            for x in range(size):
                r, g, b, a = px[x, y]
                xor += bytes((b, g, r, a))
        row = ((size + 31) // 32) * 4                      # 1-bit mask rows, padded to 4 bytes
        mask = bytearray()
        for y in range(size - 1, -1, -1):
            bits = bytearray(row)
            for x in range(size):
                if px[x, y][3] == 0:                       # fully transparent pixel
                    bits[x // 8] |= 0x80 >> (x % 8)
            mask += bits
        header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, len(xor) + len(mask), 0, 0, 0, 0)
        entries.append((size, header + bytes(xor) + bytes(mask)))
    data = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    for size, blob in entries:
        dim = 0 if size >= 256 else size                   # 0 means 256
        data += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    with open(path, "wb") as f:
        f.write(data + b"".join(blob for _, blob in entries))


out = sys.argv[1]
img.resize((256, 256), Image.LANCZOS).save(f"{out}/ghost.png", optimize=True)
write_ico(img, f"{out}/ghost.ico")
for s in (64, 32):
    img.resize((s, s), Image.LANCZOS).save(f"{out}/ghost-{s}.png", optimize=True)
