"""Check that the built .exe carries the ghost icon (Windows only).

Reads the icon group out of the exe's resources and compares it with assets/ghost.ico:
same sizes, and bitmaps (not PNG) below 256 px, which Explorer needs for some views.
usage: python check_exe_icon.py dist/GhostAutoClicker.exe assets/ghost.ico
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

exe, ico = sys.argv[1], sys.argv[2]
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.LoadLibraryExW.restype = wt.HMODULE
k32.LoadLibraryExW.argtypes = [wt.LPCWSTR, wt.HANDLE, wt.DWORD]
k32.FindResourceW.restype = wt.HANDLE
k32.FindResourceW.argtypes = [wt.HMODULE, ctypes.c_void_p, ctypes.c_void_p]
k32.LoadResource.restype = wt.HANDLE
k32.LoadResource.argtypes = [wt.HMODULE, wt.HANDLE]
k32.LockResource.restype = ctypes.c_void_p
k32.LockResource.argtypes = [wt.HANDLE]
k32.SizeofResource.restype = wt.DWORD
k32.SizeofResource.argtypes = [wt.HMODULE, wt.HANDLE]
ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMODULE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
k32.EnumResourceNamesW.argtypes = [wt.HMODULE, ctypes.c_void_p, ENUMPROC, ctypes.c_void_p]
RT_ICON, RT_GROUP_ICON = 3, 14

mod = k32.LoadLibraryExW(exe, None, 0x2)  # LOAD_LIBRARY_AS_DATAFILE
if not mod:
    sys.exit(f"can't open {exe}")


def resource(name, rtype):
    h = k32.FindResourceW(mod, name, rtype)
    if not h:
        sys.exit(f"resource {name} missing")
    return ctypes.string_at(k32.LockResource(k32.LoadResource(mod, h)), k32.SizeofResource(mod, h))


groups = []
k32.EnumResourceNamesW(mod, RT_GROUP_ICON, ENUMPROC(lambda m, t, name, p: groups.append(name) or True), None)
if not groups:
    sys.exit("no icon in the exe")
grp = resource(groups[0], RT_GROUP_ICON)
count = struct.unpack("<HHH", grp[:6])[2]
found = {}
for i in range(count):
    w, h, _, _, planes, bpp, size, icon_id = struct.unpack("<BBBBHHIH", grp[6 + 14 * i:20 + 14 * i])
    data = resource(icon_id, RT_ICON)
    found[w or 256] = "PNG" if data[:8] == b"\x89PNG\r\n\x1a\n" else "BMP"

d = open(ico, "rb").read()
want = sorted((d[6 + 16 * i] or 256) for i in range(struct.unpack("<HHH", d[:6])[2]))
print("icon sizes in exe:", ", ".join(f"{s} ({found[s]})" for s in sorted(found)))
problems = [s for s in want if s not in found]
problems += [s for s, kind in found.items() if s < 256 and kind != "BMP"]
if problems:
    sys.exit(f"icon problem at sizes {sorted(set(problems))}")
print("icon OK")
