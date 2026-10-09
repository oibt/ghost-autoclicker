"""Ask Windows for an exe's icons the way File Explorer does, and draw them in the log.

usage: python show_exe_icons.py GhostAutoClicker.exe
  W = white, I = indigo (the ghost icon), . = empty, o = anything else
"""
import ctypes
import ctypes.wintypes as wt
import sys

path = sys.argv[1]
shell32, user32, gdi32 = ctypes.windll.shell32, ctypes.windll.user32, ctypes.windll.gdi32
for f in (user32.GetDC, gdi32.CreateCompatibleDC, gdi32.CreateDIBSection, gdi32.SelectObject):
    f.restype = ctypes.c_void_p
user32.DrawIconEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                              ctypes.c_int, wt.UINT, ctypes.c_void_p, wt.UINT]
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.c_void_p, wt.DWORD]


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [("hIcon", ctypes.c_void_p), ("iIcon", ctypes.c_int), ("dwAttributes", wt.DWORD),
                ("szDisplayName", wt.WCHAR * 260), ("szTypeName", wt.WCHAR * 80)]


def render(hicon, size):
    hdc = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmi = (ctypes.c_int32 * 10)(40, size, -size, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)  # top-down 32-bit DIB
    bits = ctypes.c_void_p()
    hbm = gdi32.CreateDIBSection(mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    gdi32.SelectObject(mem, hbm)
    user32.DrawIconEx(mem, 0, 0, hicon, size, size, 0, None, 3)  # DI_NORMAL
    data = ctypes.string_at(bits, size * size * 4)
    rows = []
    for y in range(size):
        row = ""
        for x in range(size):
            b, g, r = data[(y * size + x) * 4:(y * size + x) * 4 + 3]
            if r > 200 and g > 200 and b > 200:
                row += "W"
            elif b > 120 and b > r + 30 and b > g + 30:
                row += "I"
            elif r + g + b < 40:
                row += "."
            else:
                row += "o"
        rows.append(row)
    indigo = sum(row.count("I") for row in rows) / (size * size)
    return rows, indigo


def show(label, hicon, size):
    if not hicon:
        print(f"{label}: NO ICON")
        return
    rows, indigo = render(hicon, size)
    verdict = "ghost" if indigo > 0.3 else "NOT the ghost"
    print(f"{label} ({size}px): {verdict} ({indigo:.0%} indigo)")
    for row in rows:
        print("   ", row)


print("system small icon size:", user32.GetSystemMetrics(49), "large:", user32.GetSystemMetrics(11))

# What Explorer's small views (Small icons, List, Details, Content) and large views use
for flags, label, size in ((0x101, "shell small icon (SHGetFileInfo)", user32.GetSystemMetrics(49)),
                           (0x100, "shell large icon (SHGetFileInfo)", user32.GetSystemMetrics(11))):
    info = SHFILEINFOW()
    shell32.SHGetFileInfoW(path, 0, ctypes.byref(info), ctypes.sizeof(info), flags)
    show(label, info.hIcon, size)

# Straight from the exe's resources at each size
for size in (16, 20, 24, 32, 48):
    hicon, icon_id = ctypes.c_void_p(), wt.UINT()
    user32.PrivateExtractIconsW(path, 0, size, size, ctypes.byref(hicon), ctypes.byref(icon_id), 1, 0)
    show(f"resource icon {size}", hicon.value, size)
