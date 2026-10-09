"""
Ghost Auto Clicker (Windows) - v1.2.2
-------------------------------------
Run:   python autoclicker.py        (Python 3.8+, no extra packages needed)

Hotkeys (work even when this window isn't focused; change them on the Hotkeys tab):
  F6  = Start / Stop (or set it to "hold": clicks only while the key is held down)
  F7  = Add a click point where your mouse is right now
  F8  = Remove the last point

Two kinds of click points:
  Window points - any app or browser window. Background mode posts clicks to
                  the window; Foreground mode moves your real mouse.
  Tab points    - tabs in the "automation browser" (launched from this app).
                  Every tab can be clicked, even tabs that aren't showing,
                  in one single browser window.

Points are clicked in order (1, 2, 3, ... then back to 1).
With no points in the list, Start clicks wherever your mouse is.
"""
VERSION = "1.2.2"

import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import queue
import random
import select
import socket
import struct
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
import urllib.parse
import urllib.request
from tkinter import ttk, messagebox

if not hasattr(ctypes, "WinDLL"):
    raise SystemExit("This app only runs on Windows.")

# Make coordinates match real screen pixels on scaled (125%/150%) displays
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.WinDLL("user32", use_last_error=True)
winmm = ctypes.WinDLL("winmm")

user32.WindowFromPoint.argtypes = [wt.POINT]
user32.WindowFromPoint.restype = wt.HWND
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.ScreenToClient.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.PostMessageW.restype = wt.BOOL
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.mouse_event.argtypes = [wt.DWORD, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
user32.keybd_event.argtypes = [wt.BYTE, wt.BYTE, wt.DWORD, ctypes.c_size_t]

WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
VK_RETURN, VK_DELETE, VK_F6_KEY = 0x0D, 0x2E, 0x75
SCAN_RETURN, SCAN_DELETE, SCAN_F6 = 0x1C, 0x53, 0x40
WM_APPCOMMAND = 0x0319
APPCOMMAND_BROWSER_REFRESH = 3
VK_F5, F5_SCAN = 0x74, 0x3F
KEYEVENTF_KEYUP = 0x0002
RELOAD_CMD = "Browser refresh command"
RELOAD_F5 = "F5 key"

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
MK_LBUTTON, MK_RBUTTON = 0x0001, 0x0002
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
GA_ROOT = 2
VK_SHIFT, VK_CONTROL, VK_MENU, VK_ESCAPE = 0x10, 0x11, 0x12, 0x1B

METHOD_AUTO = "Auto (recommended)"
METHOD_MAIN = "Main window"
METHOD_CHILD = "Control under cursor"

TAB_REAL = "Real mouse input (recommended)"
TAB_JS = "JavaScript click"

CDP_PORT = 9222

# Flags that stop Chromium browsers from pausing pages you can't see
# (covered windows, hidden tabs, windows on another virtual desktop).
BACKGROUND_FLAGS = [
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
    "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
]

BROWSERS = {
    "Brave": ("brave.exe", [r"BraveSoftware\Brave-Browser\Application\brave.exe"]),
    "Chrome": ("chrome.exe", [r"Google\Chrome\Application\chrome.exe"]),
    "Edge": ("msedge.exe", [r"Microsoft\Edge\Application\msedge.exe"]),
}

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# App icon (a ghost with a mouse pointer), drawn by assets/make_icon.py
GHOST_ICON_64 = (
    "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"
    "gg=="
)
GHOST_ICON_32 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAHZElEQVR42q2Xa4xdVRXHf2ufx310nkBbEIU2gfIqjOWRShGV"
    "+AF5CUFEP1BImmAixOADTUTxciNVYhBN/GAEUT9gVCIRNSohMQa1LQ+BDo+2U9vSKS2RGV7zuHPvPWfvtfxw7p3OTKclJexk"
    "3Zy7b+5aa6/1///XPkJn1Wrm6nXRznOaDGRnhuCWqnpRDcJ7WM5F5lxsgr7Rn6TbbrtN2gtjSbFRc/V6XWu1V8pSOeErRG69"
    "qj81cknM+7CC5t65eLfAQzo9fl+9fuJMNwnpPtxx9xsnxnHPo5VK6fx2K+B9GzO19yMBESdxnFIqx7Sa7WGfz1y98c5jRms1"
    "c1KrmZvso1SZmd5UqfSsacxMZoLEAu7wHovSGd2Pd18GCuYr1b601Wy8nPjGR2DZjKvXRdPJidsqlZ41U5MTGUpqak7VWGhg"
    "mBk+N9ptI8/m7y/2n66ZmjMlnZ6cyCrlJWe1pfK1el1Ubqq9Ul6m/S8lSXVlnjUREXcomCAEo9kykljo7RVKqRACTDeMmaaS"
    "JMWe6rtUwkzjpIzPW/u12TozXpoPnG7CiqzddGAsbLuLoNEwqhXhEx8tMXR2yvHLI0ophADvTCg7d3m2PN3m1Vc91aocuTWC"
    "y9tNRORDWkrOjtXr8ihJohAyA5GFJ5+aMs5YlfC565awbGk0z1eSwPHliOOXR6xbm/L431v87fEZ0lTepQpokqTOvF8eB+8R"
    "F6NBu6ycDT49ZQydXeLmDX1EEWRZwDkhitzckuK9EseOyy+tMDAgPPSbKcolweywCaBOCSEUSF8EMLRbynHHOm5a30vUOXia"
    "RsSx61CrMOeENI1wTvDBWLe2zCUXV5iaCoChYXFQBjXw4HzwaNB5Zqa0WsoVl1WplAtgtdsZG7/7CzZvGkYEQijQ1phuUq/d"
    "z3PP7SCOhBCMKy6rMjjgyNqFr4X+uxZCwAXobBTZFqc3jjvWsWaojKriHNx3768ZGdnL9zb+ktdff2sWLfd8/1fs2XOAeu0B"
    "JiamcQ6qVce5Hy4x0wiY2qzveeaL/jjaEOaW34xWK7Di5JhS6SCtXhj+LyM7RtmxfS+vHRjHuaIVW7fuZOfIPrZv28P4+NuI"
    "FCw4fVVaoO0I2hACOE9A/fzS+FwZHCgarx1annfBmTz97DOUyyVWrDwB7WS25tzTePKZLQwO9vGBE47DzBBgcNARRUbwR2qB"
    "J8aDRjYbSAANNktk10H8LbdeR9bOuPhjaxgc7JvFwO1fX08cRXzq8nVUl1QIwYgiiCLBFIK3xVkgBgFi7z2xxJ0TCU5AVWcF"
    "STrUrFbL3PHtDbNOulTs61vCd+66ec7gORhIDyOLZsVv3gdiAAsHFVCR4rvNGSMIZkYIinMy2/9uEFVjZGSU4APnDJ3aCWwL"
    "/MxPwKRT4RC6Tg5aCIotyF5EiONoXvCusziOGB97i9qdP+PFF3bjnCPPQwdselgLIRDjA0p8CAbsqG8Cwq1fup5//fN5ZprT"
    "rF49RJ7lJEl0RAw4H1gEoYGjvYvkuSdOIr5462fY/O+t/PHRp+jt7cN73+H+YYQI/OLze04JDtfHeed3QpZ5RIQvf3U9o3tH"
    "GNn+JGncQwiLxwgeXPAsrlTKPM2fG9AOmZvdAdYFq/HNb93IVVc32LXrKeKoFw3hkBiFEi7aggIkZsXMHx/LEQHVwkRgbCyf"
    "Tcqsa4aI0L3T3P6Nz3LNtW8xOvoEQtpJogPCoPgQcH6RFgRvRK4IdO89+9lw406ef67Qeefg6aem2HDDTn78wwNEkUME4giS"
    "JAUMEc9LL+7hmqvuZ/j5iHZ7D83m25i5WdpqKEAYrTrlllMEd4Oqx6yobLMZOGv1EnZsn+H3D79BqeTYsnmSoTU9vP6/nLvv"
    "2ocB219qEFT54EkVHvjpdlas9Pz8/i08/LutrDot5ZGHm5SSjzM4cHqhJZ2qYmZCJCG0fytXXjp8rhP3jMicW7BBFAvNmUCp"
    "VJwwz404LgZN8EaSFBeOdtvTP9DH/gPP4uJNVJIbGBt/hR/8aCl/+fM+hp89g4HByiJ3RTFRvchVJhrbTW0vlqoG1W6PsnYg"
    "SYQQFO+LkdwdLM6B94VgJYmjMdWip7qM1F1Lb28/A/0r+MMjo1z/+dOYae4CKx3sf1DFEg3eH0ha7sVo2/4H/SkrvtCXxv2f"
    "zPNGjhHNgkvtIMC6umB0aNrdBwg410OSVMiyJpVyL/tGxyEa4cA+j5OTMPOdGWB5Gg/E3jd+8ug/hh6TWs3c5s3Dldjbk0nc"
    "tzrL38kEEkTkaFRwlhJSDDC1nDff3Mexx6zEOYeZmkGeJv2p91M7tdG+YO1la6cFzIHo5RduOtnSvj8lcc85eZhGNesy/j2+"
    "nglxnOJ9S0DEuYQ46sWH6W2WtT/92Obzd4M5B6JQc3/dctGof/u1de1ssh582G2KYalgiXtvFjufB4elYopp0D1ZNrHxzZlX"
    "LyyC1xyIzilzzUFdAa487z/VrFpejfllqpkrWq9ydOd3VihpZEh5LIvGXn7iiUumAWqYq1O8nv8f/bmGv3CbXwAAAAAASUVO"
    "RK5CYII="
)


# ---------------------------------------------------------------- win32 helpers
def cursor_pos():
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def window_text(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_pid(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def root_window_at(sx, sy):
    child = user32.WindowFromPoint(wt.POINT(sx, sy))
    if not child:
        return None
    return user32.GetAncestor(child, GA_ROOT) or child


def to_client(hwnd, sx, sy):
    p = wt.POINT(sx, sy)
    user32.ScreenToClient(hwnd, ctypes.byref(p))
    return p.x, p.y


def make_lparam(x, y):
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


def post_key(hwnd, vk, scan, extended=False):
    lp = 1 | (scan << 16) | ((1 << 24) if extended else 0)
    user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lp)
    user32.PostMessageW(hwnd, WM_KEYUP, vk, lp | (1 << 30) | (1 << 31))


def open_url_in_window(hwnd, url, wait):
    """Type a URL into a Chromium window's address bar and press Enter.
    Messages are posted, so it never touches your real keyboard or the F6 hotkey."""
    post_key(hwnd, VK_F6_KEY, SCAN_F6)          # F6 = focus + select address bar
    wait(0.35)   # give the address bar time to take focus, or keys like "/" go to the page
    for ch in url:
        user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 1)
    wait(0.25)
    post_key(hwnd, VK_DELETE, SCAN_DELETE, extended=True)  # drop autocomplete suggestion
    post_key(hwnd, VK_RETURN, SCAN_RETURN)


def find_browser(name):
    exe, rels = BROWSERS[name]
    roots = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    for root in filter(None, roots):
        for rel in rels:
            path = os.path.join(root, rel)
            if os.path.isfile(path):
                return path
    return None


def process_running(exe):
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe}", "/NH"],
                             capture_output=True, text=True, creationflags=NO_WINDOW).stdout
        return exe.lower() in out.lower()
    except Exception:
        return False


# ---------------------------------------------------------------- hotkeys & settings
# A hotkey is (virtual-key code, modifiers), e.g. (0x75, ("Ctrl",)) = Ctrl+F6. None = no hotkey.
HOTKEY_ACTIONS = (("toggle", "Start / stop"), ("add", "Add point under mouse"), ("remove", "Remove last point"))
DEFAULT_HOTKEYS = {"toggle": (0x75, ()), "add": (0x76, ()), "remove": (0x77, ())}
MODIFIERS = (("Ctrl", VK_CONTROL), ("Shift", VK_SHIFT), ("Alt", VK_MENU))
# Can't be a hotkey on their own: left/right mouse button, modifier keys, Windows keys
NOT_BINDABLE = {0x01, 0x02, VK_SHIFT, VK_CONTROL, VK_MENU, 0x5B, 0x5C, *range(0xA0, 0xA6)}
KEY_NAMES = {0x04: "Middle mouse", 0x05: "Mouse 4", 0x06: "Mouse 5", 0x08: "Backspace", 0x09: "Tab",
             0x0D: "Enter", 0x13: "Pause", 0x14: "Caps Lock", 0x20: "Space", 0x21: "Page Up",
             0x22: "Page Down", 0x23: "End", 0x24: "Home", 0x25: "Left", 0x26: "Up", 0x27: "Right",
             0x28: "Down", 0x2C: "Print Screen", 0x2D: "Insert", 0x2E: "Delete", 0x5D: "Menu",
             0x6A: "Num *", 0x6B: "Num +", 0x6D: "Num -", 0x6E: "Num .", 0x6F: "Num /", 0x90: "Num Lock",
             0x91: "Scroll Lock", 0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/",
             0xC0: "`", 0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'"}
SETTINGS_FILE = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "AutoClicker",
                             "settings.json")


def key_name(vk):
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return f"Num {vk - 0x60}"
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    return KEY_NAMES.get(vk, f"Key {vk:#04x}")


def hotkey_name(hk):
    if not hk:
        return "Not set"
    vk, mods = hk
    return "+".join([*mods, key_name(vk)])


def held_modifiers():
    return tuple(name for name, vk in MODIFIERS if user32.GetAsyncKeyState(vk) & 0x8000)


def types_text(hk):
    """True for a hotkey that is also normal typing (a letter, digit, space, punctuation)."""
    vk, mods = hk
    if "Ctrl" in mods or "Alt" in mods:
        return False
    return vk == 0x20 or 0x30 <= vk <= 0x5A or 0x60 <= vk <= 0x6F or 0xBA <= vk <= 0xDE


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def load_hotkeys():
    hotkeys = dict(DEFAULT_HOTKEYS)
    saved = load_settings().get("hotkeys")
    if not isinstance(saved, dict):
        return hotkeys
    for action in hotkeys:
        if action not in saved:
            continue
        v = saved[action]
        try:
            if v is None:
                hotkeys[action] = None
            elif int(v["vk"]) not in NOT_BINDABLE:
                hotkeys[action] = (int(v["vk"]), tuple(n for n, _ in MODIFIERS if n in v["mods"]))
        except (TypeError, KeyError, ValueError):
            pass
    return hotkeys


def load_hold_mode():
    return load_settings().get("start_key_mode") == "hold"


def save_hold_mode(hold):
    data = load_settings()
    data["start_key_mode"] = "hold" if hold else "toggle"
    save_settings(data)


def save_hotkeys(hotkeys):
    data = load_settings()
    data["hotkeys"] = {a: None if hk is None else {"vk": hk[0], "mods": list(hk[1])}
                       for a, hk in hotkeys.items()}
    save_settings(data)


# ---------------------------------------------------------------- browser connection
class CDPError(Exception):
    pass


class WebSocket:
    """Minimal WebSocket client (enough for the browser's local debug connection)."""

    def __init__(self, url, timeout=3):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("connection closed during handshake")
            resp += chunk
        head, self.buf = resp.split(b"\r\n\r\n", 1)
        if b" 101" not in head.split(b"\r\n")[0]:
            raise ConnectionError(head.split(b"\r\n")[0].decode(errors="replace"))

    def _exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("connection closed")
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def _frame(self, opcode, payload):
        n = len(payload)
        hdr = bytearray([0x80 | opcode])
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126)
            hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127)
            hdr += struct.pack(">Q", n)
        mask = os.urandom(4)
        hdr += mask
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
        self.sock.sendall(bytes(hdr) + masked)

    def send(self, text):
        self._frame(0x1, text.encode())

    def recv(self):
        msg = b""
        while True:
            b1, b2 = self._exact(2)
            fin, op, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._exact(8))[0]
            mask = self._exact(4) if b2 & 0x80 else None
            data = self._exact(n)
            if mask:
                data = bytes(b ^ mask[i & 3] for i, b in enumerate(data))
            if op == 0x9:          # ping
                self._frame(0xA, data)
                continue
            if op == 0x8:          # close
                raise ConnectionError("connection closed by browser")
            if op in (0x0, 0x1, 0x2):
                msg += data
                if fin:
                    return msg.decode("utf-8", errors="replace")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


class CDPTab:
    """Connection to one browser tab."""

    def __init__(self, url):
        self.url = url
        self.ws = None
        self.lock = threading.Lock()
        self.mid = 0

    def close(self):
        if self.ws:
            self.ws.close()
        self.ws = None

    def _rpc(self, method, params, timeout):
        self.ws.sock.settimeout(timeout)
        self.mid += 1
        mid = self.mid
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise CDPError(m["error"].get("message", "browser error"))
                return m.get("result", {})

    def _connect(self, timeout):
        if self.ws is None:
            self.ws = WebSocket(self.url, timeout)
            # Make hidden tabs behave as if focused and never freeze them
            for m, p in (("Emulation.setFocusEmulationEnabled", {"enabled": True}),
                         ("Page.setWebLifecycleState", {"state": "active"})):
                try:
                    self._rpc(m, p, timeout)
                except CDPError:
                    pass

    def _drain(self):
        """Throw away replies to earlier fire-and-forget messages that have arrived."""
        while True:
            if not self.ws.buf:
                ready, _, _ = select.select([self.ws.sock], [], [], 0)
                if not ready:
                    return
            self.ws.sock.settimeout(2)
            self.ws.recv()

    def call(self, method, params=None, timeout=3):
        with self.lock:
            try:
                self._connect(timeout)
                return self._rpc(method, params or {}, timeout)
            except CDPError:
                raise
            except Exception:
                self.close()
                raise

    def send(self, method, params=None, timeout=3):
        """Send without waiting for the reply. Hidden tabs can take up to a second to
        confirm input even though the click itself lands right away."""
        with self.lock:
            try:
                self._connect(timeout)
                self._drain()
                self.mid += 1
                self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params or {}}))
            except Exception:
                self.close()
                raise

    def evaluate(self, expr, timeout=3):
        r = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, timeout)
        return r.get("result", {}).get("value")


# Remembers where the mouse last was inside each page (for picking points)
TRACK_JS = ("(()=>{if(window.__acT)return;window.__acT=1;"
            "addEventListener('mousemove',e=>{window.__acPos=[e.clientX,e.clientY,Date.now()]},true);})()")
PICK_JS = "[window.__acPos||null, document.visibilityState, document.title, location.href]"

JS_CLICK = """(()=>{const x=$X,y=$Y,b=$B;const el=document.elementFromPoint(x,y);if(!el)return false;
const o={bubbles:true,cancelable:true,composed:true,clientX:x,clientY:y,button:b,buttons:b===2?2:1,view:window};
const p=Object.assign({pointerId:1,pointerType:'mouse',isPrimary:true},o);
el.dispatchEvent(new PointerEvent('pointerdown',p));el.dispatchEvent(new MouseEvent('mousedown',o));
o.buttons=0;p.buttons=0;
el.dispatchEvent(new PointerEvent('pointerup',p));el.dispatchEvent(new MouseEvent('mouseup',o));
el.dispatchEvent(new MouseEvent(b===2?'contextmenu':'click',o));return true;})()"""


def http_json(path, timeout=2):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{CDP_PORT}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode())


def is_web_page(t):
    return t.get("type") == "page" and t.get("url", "").startswith(("http://", "https://", "file://"))


class Browser:
    """Talks to the automation browser through its local debug port."""

    def __init__(self):
        self.tabs = {}
        self.lock = threading.Lock()
        self.up = False
        self.tab_count = 0
        self.paused = False
        self.pid = None
        threading.Thread(target=self._tracker, daemon=True).start()

    def pages(self):
        return [t for t in http_json("/json/list") if is_web_page(t)]

    def tab(self, tid):
        with self.lock:
            if tid not in self.tabs:
                self.tabs[tid] = CDPTab(f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{tid}")
            return self.tabs[tid]

    def _tracker(self):
        while True:
            try:
                pages = self.pages()
                self.up, self.tab_count = True, len(pages)
            except Exception:
                self.up, self.tab_count = False, 0
                time.sleep(2)
                continue
            if not self.paused:
                for p in pages:
                    try:
                        self.tab(p["id"]).evaluate(TRACK_JS, timeout=1.5)
                    except Exception:
                        pass
            ids = {p["id"] for p in pages}
            with self.lock:
                for tid in list(self.tabs):
                    if tid not in ids:
                        self.tabs.pop(tid).close()
            time.sleep(2)

    def pick(self):
        """Visible tab where the mouse moved most recently -> (x, y, page info)."""
        best = None
        for p in self.pages():
            try:
                v = self.tab(p["id"]).evaluate(PICK_JS, timeout=1.5)
            except Exception:
                continue
            if not v or not v[0] or v[1] != "visible":
                continue
            if best is None or v[0][2] > best[0][2]:
                best = (v[0], p, v[2])
        if not best:
            return None
        pos, page, title = best
        return pos[0], pos[1], page["id"], title or page.get("title", ""), page.get("url", "")


# ---------------------------------------------------------------- click points
class WindowPoint:
    """A screen point plus the windows under it."""
    kind = "window"

    def __init__(self, sx, sy):
        self.sx, self.sy = sx, sy
        self.child = user32.WindowFromPoint(wt.POINT(sx, sy))
        self.root = (user32.GetAncestor(self.child, GA_ROOT) or self.child) if self.child else None
        self.child_xy = to_client(self.child, sx, sy) if self.child else (0, 0)
        self.root_xy = to_client(self.root, sx, sy) if self.root else (0, 0)
        self.chromium = bool(self.child) and (
            class_name(self.child).startswith("Chrome_")
            or class_name(self.root).startswith("Chrome_WidgetWin")
        )
        self.title = (window_text(self.root) if self.root else "") or "(untitled window)"
        self.reload_every = 0
        self.reload_wait = 3.0
        self.reload_url = ""
        self.clicks = 0

    def endpoint(self, method):
        use_main = method == METHOD_MAIN or (method == METHOD_AUTO and self.chromium)
        if use_main:
            return self.root, self.root_xy
        return self.child, self.child_xy


class TabPoint:
    """A point inside one tab of the automation browser (works on hidden tabs)."""
    kind = "tab"

    def __init__(self, browser, tid, x, y, title, url):
        self.browser = browser
        self.tid = tid
        self.x, self.y = float(x), float(y)
        self.sx, self.sy = round(x), round(y)
        self.page_title = title or url
        self.title = "Tab: " + self.page_title
        self.url = url
        self.reload_every = 0
        self.reload_wait = 3.0
        self.reload_url = ""
        self.clicks = 0


class CursorPoint:
    """No fixed spot: click wherever the mouse is (used when the point list is empty)."""
    kind = "cursor"

    def __init__(self, own_hwnd):
        self.own_hwnd = own_hwnd           # this app's window: never click on it
        self.title = "Mouse cursor"
        self.sx = self.sy = 0
        self.reload_every = 0
        self.reload_wait = 0.0
        self.reload_url = ""
        self.clicks = 0


class SkipClick(Exception):
    """This click was skipped on purpose (not an error)."""


# ---------------------------------------------------------------- clicker
class Clicker(threading.Thread):
    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.stop_evt = threading.Event()
        self.clicks = 0
        self.current = 0
        self.status = "Clicking"
        self.last_error = ""

    # --- window points
    def press_window(self, t, dx, dy):
        c = self.cfg
        hold = c["hold"]
        if c["background"]:
            hwnd, (cx, cy) = t.endpoint(c["method"])
            if c["right"]:
                down, up, mk = WM_RBUTTONDOWN, WM_RBUTTONUP, MK_RBUTTON
            else:
                down, up, mk = WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON
            lp = make_lparam(cx + dx, cy + dy)
            user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
            user32.PostMessageW(hwnd, down, mk, lp)
            if hold:
                self.stop_evt.wait(hold)
            user32.PostMessageW(hwnd, up, 0, lp)
        else:
            user32.SetCursorPos(t.sx + dx, t.sy + dy)
            if c["right"]:
                d, u = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
            else:
                d, u = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
            user32.mouse_event(d, 0, 0, 0, 0)
            if hold:
                self.stop_evt.wait(hold)
            user32.mouse_event(u, 0, 0, 0, 0)

    def reload_window(self, t):
        if t.reload_url:
            open_url_in_window(t.root, t.reload_url, self.stop_evt.wait)
        elif self.cfg["background"]:
            hwnd = t.root
            if self.cfg["reload_method"] == RELOAD_F5:
                post_key(hwnd, VK_F5, F5_SCAN)
            else:
                user32.PostMessageW(hwnd, WM_APPCOMMAND, hwnd or 0, APPCOMMAND_BROWSER_REFRESH << 16)
        else:
            user32.keybd_event(VK_F5, F5_SCAN, 0, 0)
            user32.keybd_event(VK_F5, F5_SCAN, KEYEVENTF_KEYUP, 0)

    # --- mouse cursor
    def press_cursor(self, t, dx, dy):
        x, y = cursor_pos()
        if t.own_hwnd and root_window_at(x, y) == t.own_hwnd:
            # Started with the mouse on our Start button: clicking here would stop the clicker
            raise SkipClick("mouse is over Ghost Auto Clicker")
        if self.cfg["right"]:
            d, u = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        else:
            d, u = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        if dx or dy:
            user32.SetCursorPos(x + dx, y + dy)
        user32.mouse_event(d, 0, 0, 0, 0)
        if self.cfg["hold"]:
            self.stop_evt.wait(self.cfg["hold"])
        user32.mouse_event(u, 0, 0, 0, 0)
        if dx or dy:
            user32.SetCursorPos(x, y)

    # --- tab points
    def press_tab(self, t, dx, dy):
        c = self.cfg
        tab = t.browser.tab(t.tid)
        x, y = t.x + dx, t.y + dy
        if c["tab_method"] == TAB_JS:
            js = JS_CLICK.replace("$X", repr(x)).replace("$Y", repr(y)).replace("$B", "2" if c["right"] else "0")
            tab.evaluate(js)
            return
        btn, buttons = ("right", 2) if c["right"] else ("left", 1)
        tab.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        tab.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y,
                                              "button": btn, "buttons": buttons, "clickCount": 1})
        if c["hold"]:
            self.stop_evt.wait(c["hold"])
        tab.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y,
                                              "button": btn, "buttons": 0, "clickCount": 1})

    def reload_tab(self, t):
        tab = t.browser.tab(t.tid)
        if t.reload_url:
            tab.call("Page.navigate", {"url": t.reload_url}, timeout=10)
        else:
            tab.call("Page.reload", {}, timeout=10)

    # --- dispatch
    def press(self, t):
        j = self.cfg["jitter"]
        dx = random.randint(-j, j) if j else 0
        dy = random.randint(-j, j) if j else 0
        if t.kind == "tab":
            self.press_tab(t, dx, dy)
        elif t.kind == "cursor":
            self.press_cursor(t, dx, dy)
        else:
            self.press_window(t, dx, dy)

    def reload_page(self, t):
        if t.kind == "tab":
            self.reload_tab(t)
        else:
            self.reload_window(t)

    def run(self):
        points = self.cfg["points"]
        n = len(points)
        self.ready_at = [0.0] * n          # point is skipped until this time (page reloading)
        self.loading = [False] * n         # tab point: wait for the page to finish loading too
        self.page_locks = {}
        self.page_locks_lock = threading.Lock()
        self.per_point = [0] * n          # clicks on each point (shown in the list)
        self.reload_pool = ThreadPoolExecutor(max_workers=8)
        winmm.timeBeginPeriod(1)  # 1 ms timer precision for accurate CPS
        try:
            if self.cfg["together"]:
                self.run_together()
            else:
                self.run_in_order()
        finally:
            winmm.timeEndPeriod(1)
            self.reload_pool.shutdown(wait=False)

    # --- reloads run in the background; the clicker keeps going with the other points
    @staticmethod
    def page_key(t):
        if t.kind == "cursor":
            return ("cursor",)
        return ("tab", t.tid) if t.kind == "tab" else ("win", t.root)

    def page_lock(self, key):
        with self.page_locks_lock:
            return self.page_locks.setdefault(key, threading.Lock())

    def start_reload(self, i):
        points = self.cfg["points"]
        t = points[i]
        key = self.page_key(t)
        until = time.perf_counter() + t.reload_wait
        # Every point on the same page waits for it to come back
        for j, p in enumerate(points):
            if self.page_key(p) == key:
                self.ready_at[j] = max(self.ready_at[j], until)
                if p.kind == "tab":
                    self.loading[j] = True

        def work():
            with self.page_lock(key):       # one reload / URL at a time per page
                try:
                    self.reload_page(t)
                except Exception as e:
                    self.last_error = f"reload point {i + 1}: {e or e.__class__.__name__}"

        self.reload_pool.submit(work)

    def is_ready(self, i):
        if time.perf_counter() < self.ready_at[i]:
            return False
        if self.loading[i]:
            t = self.cfg["points"][i]
            try:
                state = t.browser.tab(t.tid).evaluate("document.readyState", timeout=1)
            except Exception:
                return False
            if state != "complete":
                return False
            self.loading[i] = False
        return True

    def update_status(self):
        now = time.perf_counter()
        busy = sum(1 for r in self.ready_at if r > now)
        self.status = f"Clicking — {busy} page(s) reloading" if busy else "Clicking"

    def window_gone(self, t):
        c = self.cfg
        return t.kind == "window" and c["background"] and not user32.IsWindow(t.endpoint(c["method"])[0])

    def wait_next(self, next_t, interval):
        """Sleep until the next scheduled click. Returns (new next_t, stopped)."""
        next_t += interval
        delay = next_t - time.perf_counter()
        if delay > 0:
            if self.stop_evt.wait(delay):
                return next_t, True
        else:
            next_t = time.perf_counter()  # fell behind: don't burst
        return next_t, False

    def batch_pause(self):
        """Pause after the set amount of clicks. Returns True if stopped."""
        self.status = f"Pausing {self.cfg['pause']:g}s"
        if self.stop_evt.wait(self.cfg["pause"]):
            return True
        self.status = "Clicking"
        return False

    def due_for_reload(self, i, per_point):
        t = self.cfg["points"][i]
        return t.reload_every and per_point[i] % t.reload_every == 0

    # --- one point after another
    def run_in_order(self):
        c = self.cfg
        points = c["points"]
        n = len(points)
        interval = 1.0 / c["cps"]
        per_point = self.per_point
        batch = 0
        idx = 0
        next_t = time.perf_counter()
        while not self.stop_evt.is_set():
            chosen = next((j for j in ((idx + k) % n for k in range(n)) if self.is_ready(j)), None)
            if chosen is None:
                self.status = "Waiting for pages to load"
                if self.stop_evt.wait(0.05):
                    break
                next_t = time.perf_counter()
                continue
            t = points[chosen]
            self.current = chosen
            idx = (chosen + 1) % n

            if self.window_gone(t):
                self.status = f"Stopped: window for point {chosen + 1} was closed"
                return
            try:
                self.press(t)
            except SkipClick as e:
                self.status = f"Waiting: {e}"
                if self.stop_evt.wait(0.05):
                    break
                next_t = time.perf_counter()
                continue
            except Exception as e:
                self.last_error = f"point {chosen + 1}: {e or e.__class__.__name__}"
                if self.stop_evt.wait(0.5):
                    break
                continue

            self.clicks += 1
            batch += 1
            per_point[chosen] += 1

            if c["limit"] and self.clicks >= c["limit"]:
                self.status = "Done"
                return

            if self.due_for_reload(chosen, per_point):
                self.start_reload(chosen)   # reloads in the background; move straight on
            self.update_status()

            if c["every"] and batch >= c["every"]:
                batch = 0
                if self.batch_pause():
                    break
                next_t = time.perf_counter()
                continue

            next_t, stopped = self.wait_next(next_t, interval)
            if stopped:
                break
        self.status = "Stopped"

    # --- every point at the same time
    def run_together(self):
        c = self.cfg
        points = c["points"]
        n = len(points)
        interval = 1.0 / c["cps"]          # here: clicks per second for EACH point
        per_point = self.per_point
        rounds = 0
        batch = 0
        # Different pages are clicked at the same time, but each page only has ONE mouse:
        # points on the same tab/window are clicked one right after another, never mixed
        # together (mixed presses make the click land on the page background instead).
        # Foreground window points all share your real mouse, so they form one group.
        groups = {}
        for i, t in enumerate(points):
            key = self.page_key(t) if (t.kind == "tab" or c["background"]) else ("foreground",)
            groups.setdefault(key, []).append(i)
        pool = ThreadPoolExecutor(max_workers=max(1, min(32, len(groups))))
        self.current = -1
        next_t = time.perf_counter()

        def attempt(i):
            try:
                self.press(points[i])
                return True
            except SkipClick as e:
                self.status = f"Waiting: {e}"
                return False
            except Exception as e:
                self.last_error = f"point {i + 1}: {e or e.__class__.__name__}"
                return False

        def click_group(idxs):
            done = []
            for i in idxs:
                if self.stop_evt.is_set():
                    break
                if attempt(i):
                    done.append(i)
            return done

        try:
            while not self.stop_evt.is_set():
                for i, t in enumerate(points):
                    if self.window_gone(t):
                        self.status = f"Stopped: window for point {i + 1} was closed"
                        return

                ready = [i for i in range(n) if self.is_ready(i)]
                if not ready:
                    self.status = "Waiting for pages to load"
                    if self.stop_evt.wait(0.05):
                        break
                    next_t = time.perf_counter()
                    continue

                ready_set = set(ready)
                futures = [pool.submit(click_group, [i for i in idxs if i in ready_set])
                           for idxs in groups.values() if any(i in ready_set for i in idxs)]
                ok = sorted(i for f in futures for i in f.result())

                self.clicks += len(ok)
                for i in ok:
                    per_point[i] += 1
                if not ok:
                    if self.stop_evt.wait(0.05 if self.status.startswith("Waiting") else 0.5):
                        break
                    continue
                rounds += 1
                batch += 1

                if c["limit"] and rounds >= c["limit"]:
                    self.status = "Done"
                    return

                # Reload each page at most once per round, in the background
                started = set()
                for i in ok:
                    key = self.page_key(points[i])
                    if key not in started and self.due_for_reload(i, per_point):
                        started.add(key)
                        self.start_reload(i)
                self.update_status()

                if c["every"] and batch >= c["every"]:
                    batch = 0
                    if self.batch_pause():
                        break
                    next_t = time.perf_counter()
                    continue

                next_t, stopped = self.wait_next(next_t, interval)
                if stopped:
                    break
            self.status = "Stopped"
        finally:
            pool.shutdown(wait=False)

    def stop(self):
        self.stop_evt.set()


# ---------------------------------------------------------------- look & feel
FONT = "Segoe UI"
THEMES = {
    "light": dict(bg="#f5f6f8", field="#ffffff", text="#111827", muted="#6b7280", border="#d9dce1",
                  button="#e9ebef", button_hover="#dde0e6", accent="#4f46e5", accent_hover="#4338ca",
                  accent_text="#ffffff", select="#e0e7ff", select_text="#111827", stripe="#f8f9fb",
                  active_row="#dcfce7", good="#16a34a", good_hover="#15803d", bad="#dc2626",
                  bad_hover="#b91c1c", warn="#b45309"),
    "dark": dict(bg="#15171c", field="#1f2228", text="#e5e7eb", muted="#9ca3af", border="#30343c",
                 button="#272b33", button_hover="#323741", accent="#6366f1", accent_hover="#818cf8",
                 accent_text="#ffffff", select="#312e81", select_text="#ffffff", stripe="#23262d",
                 active_row="#14532d", good="#16a34a", good_hover="#22c55e", bad="#dc2626",
                 bad_hover="#ef4444", warn="#f59e0b"),
}


def system_dark():
    """True when Windows is set to dark mode for apps."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except Exception:
        return False


def set_title_bar(win, dark):
    """Dark or light Windows title bar (Windows 10 20H1+ and Windows 11)."""
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        on = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
    except Exception:
        pass


def style_widgets(root, c):
    s = ttk.Style(root)
    s.theme_use("clam")
    font = (FONT, 10)
    root.configure(bg=c["bg"])
    for opt, val in (("background", c["field"]), ("foreground", c["text"]), ("font", font),
                     ("selectBackground", c["accent"]), ("selectForeground", c["accent_text"])):
        root.option_add(f"*TCombobox*Listbox.{opt}", val)

    s.configure(".", background=c["bg"], foreground=c["text"], font=font, bordercolor=c["border"],
                lightcolor=c["bg"], darkcolor=c["bg"], troughcolor=c["bg"], fieldbackground=c["field"],
                selectbackground=c["accent"], selectforeground=c["accent_text"], insertcolor=c["text"],
                arrowcolor=c["muted"], focuscolor=c["bg"])
    s.configure("Title.TLabel", font=(FONT, 15, "bold"))
    s.configure("Section.TLabel", font=(FONT, 10, "bold"))
    s.configure("Muted.TLabel", foreground=c["muted"])
    s.configure("Warn.TLabel", foreground=c["warn"])
    s.configure("Good.TLabel", foreground=c["good"])
    s.configure("Count.TLabel", font=(FONT, 20, "bold"))
    s.configure("Key.TLabel", background=c["button"], foreground=c["text"], font=(FONT, 8, "bold"),
                padding=(6, 1))
    s.configure("Empty.TLabel", background=c["field"], foreground=c["muted"])

    def button(name, bg, hover, fg, **extra):
        s.configure(name, background=bg, foreground=fg, bordercolor=bg, lightcolor=bg, darkcolor=bg,
                    padding=(12, 5), relief="flat", **extra)
        s.map(name, background=[("disabled", c["button"]), ("pressed", hover), ("active", hover)],
              lightcolor=[("pressed", hover), ("active", hover)],
              darkcolor=[("pressed", hover), ("active", hover)],
              bordercolor=[("focus", hover)],
              foreground=[("disabled", c["muted"])])

    button("TButton", c["button"], c["button_hover"], c["text"])
    button("Ghost.TButton", c["bg"], c["button"], c["muted"])
    button("Accent.TButton", c["accent"], c["accent_hover"], c["accent_text"])
    big = dict(font=(FONT, 11, "bold"))
    button("Start.TButton", c["good"], c["good_hover"], "#ffffff", **big)
    button("Stop.TButton", c["bad"], c["bad_hover"], "#ffffff", **big)
    for name in ("Start.TButton", "Stop.TButton"):
        s.configure(name, padding=(18, 9))

    for name in ("TEntry", "TSpinbox", "TCombobox"):
        s.configure(name, fieldbackground=c["field"], foreground=c["text"], bordercolor=c["border"],
                    lightcolor=c["field"], darkcolor=c["field"], background=c["button"],
                    arrowcolor=c["muted"], padding=(6, 3))
        s.map(name, bordercolor=[("focus", c["accent"])], fieldbackground=[("readonly", c["field"])],
              foreground=[("readonly", c["text"])], background=[("active", c["button_hover"])])
    s.map("TCombobox", selectbackground=[("readonly", c["field"])], selectforeground=[("readonly", c["text"])],
          bordercolor=[("focus", c["accent"])], fieldbackground=[("readonly", c["field"])],
          foreground=[("readonly", c["text"])], background=[("active", c["button_hover"])])

    for name in ("TRadiobutton", "TCheckbutton"):
        s.configure(name, background=c["bg"], indicatorbackground=c["field"], indicatorforeground=c["accent"],
                    upperbordercolor=c["border"], lowerbordercolor=c["border"], indicatormargin=(0, 0, 6, 0))
        s.map(name, background=[("active", c["bg"])],
              indicatorbackground=[("pressed", c["field"]), ("selected", c["field"])])

    s.configure("TNotebook", background=c["bg"], bordercolor=c["border"], lightcolor=c["bg"],
                darkcolor=c["bg"], tabmargins=(0, 0, 0, 0))
    s.configure("TNotebook.Tab", background=c["button"], foreground=c["muted"], padding=(10, 6),
                bordercolor=c["border"], lightcolor=c["button"], darkcolor=c["button"])
    s.map("TNotebook.Tab", background=[("selected", c["bg"])], foreground=[("selected", c["text"])],
          lightcolor=[("selected", c["bg"])], expand=[("selected", (0, 0, 0, 0))])

    s.configure("Treeview", background=c["field"], fieldbackground=c["field"], foreground=c["text"],
                rowheight=30, bordercolor=c["border"], lightcolor=c["field"], darkcolor=c["field"])
    s.map("Treeview", background=[("selected", c["select"])], foreground=[("selected", c["select_text"])])
    s.configure("Treeview.Heading", background=c["button"], foreground=c["muted"], font=(FONT, 9, "bold"),
                padding=(6, 5), relief="flat", bordercolor=c["border"], lightcolor=c["button"],
                darkcolor=c["button"])
    s.map("Treeview.Heading", background=[("active", c["button_hover"])])
    s.configure("Vertical.TScrollbar", background=c["button"], troughcolor=c["field"], bordercolor=c["field"],
                lightcolor=c["button"], darkcolor=c["button"], arrowcolor=c["muted"], gripcount=0)
    s.map("Vertical.TScrollbar", background=[("active", c["button_hover"])])


# ---------------------------------------------------------------- UI
HINT = "Double-click a point to edit it · Ctrl/Shift+click to edit several together"
KEEP = "(keep each point's own)"
START_TEXT, STOP_TEXT = "▶  Start", "■  Stop"


class App:
    def __init__(self, root):
        self.root = root
        self.points = []
        self.clicker = None
        self.events = queue.Queue()
        self.countdown = 0
        self.browser = Browser()
        self.dark = system_dark()
        self.flash_job = None
        self.active_row = None
        self.hotkeys = load_hotkeys()
        self.hold_mode = tk.BooleanVar(value=load_hold_mode())   # start/stop key: hold to click
        self.holding = False
        self.capturing = None              # action waiting for a new hotkey

        root.title("Ghost Auto Clicker")
        self.set_icon()
        root.minsize(940, 560)
        self.apply_theme()

        # Header
        head = ttk.Frame(root, padding=(16, 12, 16, 4))
        head.pack(fill="x")
        ttk.Label(head, text="Ghost Auto Clicker", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text=f"v{VERSION}", style="Muted.TLabel").pack(side="left", padx=(6, 0), pady=(6, 0))
        ttk.Label(head, text="Clicks windows and hidden browser tabs in the background",
                  style="Muted.TLabel").pack(side="left", padx=(12, 0), pady=(6, 0))
        self.topmost = tk.BooleanVar(value=False)
        ttk.Checkbutton(head, text="Keep on top", variable=self.topmost,
                        command=lambda: root.attributes("-topmost", self.topmost.get())).pack(side="right")
        self.theme_btn = ttk.Button(head, style="Ghost.TButton", command=self.toggle_theme)
        self.theme_btn.pack(side="right", padx=(0, 12))
        self.update_theme_button()

        # Footer (packed before the body so it stays visible when the window is small)
        foot = ttk.Frame(root, padding=(16, 12, 16, 14))
        foot.pack(side="bottom", fill="x")
        self.line = tk.Frame(root, height=1, bg=self.colors["border"])
        self.line.pack(side="bottom", fill="x")
        self.start_btn = ttk.Button(foot, text=START_TEXT, style="Start.TButton", command=self.toggle, width=10)
        self.start_btn.pack(side="left")
        self.count_lbl = ttk.Label(foot, text="0", style="Count.TLabel")
        self.count_lbl.pack(side="left", padx=(20, 4))
        ttk.Label(foot, text="clicks", style="Muted.TLabel").pack(side="left", pady=(8, 0))
        info = ttk.Frame(foot)
        info.pack(side="left", fill="x", expand=True, padx=(20, 0))
        self.status_lbl = ttk.Label(info, text="Idle")
        self.status_lbl.pack(anchor="w")
        self.err_lbl = ttk.Label(info, text="", style="Warn.TLabel")
        self.err_lbl.pack(anchor="w")
        keys = ttk.Frame(foot)
        keys.pack(side="right")
        self.key_lbls, self.key_texts = {}, {}
        for action, text in (("toggle", "start / stop"), ("add", "add point"), ("remove", "remove last")):
            self.key_lbls[action] = ttk.Label(keys, style="Key.TLabel")
            self.key_lbls[action].pack(side="left", padx=(12, 4))
            self.key_texts[action] = ttk.Label(keys, text=text, style="Muted.TLabel")
            self.key_texts[action].pack(side="left")

        # Body: point list on the left, settings on the right
        body = ttk.Frame(root, padding=(16, 8, 16, 12))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="ns")
        self.build_points(left)
        self.build_settings(right)

        self.update_key_texts()
        self.refresh_points()
        threading.Thread(target=self.hotkey_loop, daemon=True).start()
        self.ui_loop()

    # --- layout
    def build_points(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Click points", style="Section.TLabel").pack(side="left")
        self.summary_lbl = ttk.Label(top, style="Muted.TLabel")
        self.summary_lbl.pack(side="left", padx=(10, 0))
        ttk.Button(top, text="Clear all", style="Ghost.TButton", command=self.clear_points).pack(side="right")
        ttk.Button(top, text="Select all", style="Ghost.TButton",
                   command=lambda: self.tree.selection_set(self.tree.get_children())).pack(side="right")

        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=("n", "kind", "pos", "reload", "clicks", "win"),
                                 show="headings", height=10, selectmode="extended")
        for col, text, w, anchor in (("n", "#", 40, "center"), ("kind", "Type", 72, "w"),
                                     ("pos", "Position", 96, "center"), ("reload", "Reload", 150, "w"),
                                     ("clicks", "Clicks", 72, "center"), ("win", "Window / tab", 220, "w")):
            self.tree.heading(col, text=text, anchor=anchor)
            self.tree.column(col, width=w, minwidth=w, anchor=anchor, stretch=col == "win")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.edit_point)
        self.tree.bind("<Delete>", lambda e: self.remove_selected())
        self.tree.bind("<Control-a>", lambda e: (self.tree.selection_set(self.tree.get_children()), "break")[1])
        self.empty_lbl = ttk.Label(self.tree, style="Empty.TLabel", justify="center")
        self.style_tree()

        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(8, 0))
        self.pick_btn = ttk.Button(bar, text="+  Add point", style="Accent.TButton", command=self.start_pick)
        self.pick_btn.pack(side="left")
        ttk.Button(bar, text="Edit…", command=self.edit_point).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Remove", command=self.remove_selected).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="▲", width=3, command=lambda: self.move(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="▼", width=3, command=lambda: self.move(1)).pack(side="left", padx=(2, 0))
        self.pick_lbl = ttk.Label(parent, text=HINT, style="Muted.TLabel")
        self.pick_lbl.pack(anchor="w", pady=(6, 0))

    @staticmethod
    def page(nb, title):
        p = ttk.Frame(nb, padding=(14, 12))
        p.columnconfigure(2, weight=1)
        nb.add(p, text=title)
        return p

    @staticmethod
    def field(parent, r, label, widget, unit=None, pady=4):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=(0, 12), pady=pady)
        widget.grid(row=r, column=1, sticky="w", pady=pady)
        if unit:
            ttk.Label(parent, text=unit, style="Muted.TLabel").grid(row=r, column=2, sticky="w", padx=(6, 0))

    @staticmethod
    def section(parent, r, text, first=False):
        ttk.Label(parent, text=text, style="Section.TLabel").grid(row=r, column=0, columnspan=3, sticky="w",
                                                                  pady=(0 if first else 14, 4))

    @staticmethod
    def note(parent, r, text, wrap=330):
        lbl = ttk.Label(parent, text=text, style="Muted.TLabel", wraplength=wrap, justify="left")
        lbl.grid(row=r, column=0, columnspan=3, sticky="w", pady=(2, 0))
        return lbl

    def build_settings(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        # Speed
        p = self.page(nb, "Speed")
        self.section(p, 0, "Clicking", first=True)
        self.cps = tk.StringVar(value="10")
        self.field(p, 1, "Clicks per second", ttk.Spinbox(p, from_=0.1, to=1000, increment=1,
                                                          textvariable=self.cps, width=8))
        self.button = tk.StringVar(value="Left")
        self.field(p, 2, "Mouse button", ttk.Combobox(p, textvariable=self.button, values=["Left", "Right"],
                                                      state="readonly", width=7))
        self.hold = tk.StringVar(value="20")
        self.field(p, 3, "Hold each click", ttk.Spinbox(p, from_=0, to=1000, textvariable=self.hold, width=8), "ms")
        self.jitter = tk.StringVar(value="0")
        self.field(p, 4, "Random offset", ttk.Spinbox(p, from_=0, to=50, textvariable=self.jitter, width=8), "± px")
        self.section(p, 5, "Click order")
        self.together = tk.BooleanVar(value=False)
        ttk.Radiobutton(p, text="One after another", variable=self.together, value=False,
                        command=self.update_speed_hint).grid(row=6, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Radiobutton(p, text="All at the same time", variable=self.together, value=True,
                        command=self.update_speed_hint).grid(row=7, column=0, columnspan=3, sticky="w", pady=2)
        self.speed_hint = self.note(p, 8, "")

        # Breaks & limits
        p = self.page(nb, "Limits")
        self.section(p, 0, "Take a break", first=True)
        self.every = tk.StringVar(value="0")
        self.field(p, 1, "After every", ttk.Spinbox(p, from_=0, to=1_000_000, textvariable=self.every, width=10),
                   "clicks")
        self.pause = tk.StringVar(value="5")
        self.field(p, 2, "Wait for", ttk.Spinbox(p, from_=0, to=86400, increment=0.5, textvariable=self.pause,
                                                 width=10), "seconds")
        self.note(p, 3, "0 clicks = never take a break.")
        self.section(p, 4, "Stop automatically")
        self.limit = tk.StringVar(value="0")
        self.field(p, 5, "Stop after", ttk.Spinbox(p, from_=0, to=10_000_000, textvariable=self.limit, width=10),
                   "clicks")
        self.note(p, 6, "0 = keep going until you press Stop.\n\n"
                        "In “All at the same time” mode, both of these count rounds (one click on every point).")

        # Browser tabs
        p = self.page(nb, "Browser tabs")
        self.note(p, 0, "Launch a separate browser that this app controls. Every tab in it can be clicked, "
                        "even tabs that aren't showing, and the window can sit on another desktop.")
        self.section(p, 1, "Automation browser")
        self.browser_name = tk.StringVar(value="Brave")
        self.field(p, 2, "Browser", ttk.Combobox(p, textvariable=self.browser_name, values=list(BROWSERS),
                                                 state="readonly", width=10))
        self.cdp_lbl = ttk.Label(p, style="Muted.TLabel")
        self.field(p, 3, "Status", self.cdp_lbl)
        ttk.Button(p, text="Launch automation browser", style="Accent.TButton",
                   command=self.launch_automation).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 4))
        self.section(p, 5, "Clicking tabs")
        self.tab_method = tk.StringVar(value=TAB_REAL)
        self.field(p, 6, "Method", ttk.Combobox(p, textvariable=self.tab_method, values=[TAB_REAL, TAB_JS],
                                                state="readonly", width=28))
        self.tabs_note = self.note(p, 7, "")

        # Window points
        p = self.page(nb, "Windows")
        self.section(p, 0, "Window points (any app or browser)", first=True)
        self.background = tk.BooleanVar(value=True)
        ttk.Radiobutton(p, text="Background", variable=self.background,
                        value=True).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))
        ttk.Label(p, text="Window can be behind others, your mouse stays free",
                  style="Muted.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", padx=(24, 0))
        ttk.Radiobutton(p, text="Foreground", variable=self.background,
                        value=False).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(p, text="Moves your real mouse, works with everything",
                  style="Muted.TLabel").grid(row=4, column=0, columnspan=3, sticky="w", padx=(24, 0))
        self.section(p, 5, "Advanced")
        self.method = tk.StringVar(value=METHOD_AUTO)
        self.field(p, 6, "Send clicks to", ttk.Combobox(p, textvariable=self.method,
                                                        values=[METHOD_AUTO, METHOD_MAIN, METHOD_CHILD],
                                                        state="readonly", width=22))
        self.reload_method = tk.StringVar(value=RELOAD_CMD)
        self.field(p, 7, "Reload using", ttk.Combobox(p, textvariable=self.reload_method,
                                                      values=[RELOAD_CMD, RELOAD_F5], state="readonly", width=22))
        ttk.Button(p, text="Restart browser with background clicking",
                   command=self.launch_browser).grid(row=8, column=0, columnspan=3, sticky="w", pady=(12, 4))
        self.note(p, 9, "Stops the browser from pausing pages you can't see. Uses the browser chosen on "
                        "the Browser tabs page.")

        # Hotkeys
        p = self.page(nb, "Hotkeys")
        self.section(p, 0, "Hotkeys", first=True)
        self.hotkey_btns = {}
        for r, (action, label) in enumerate(HOTKEY_ACTIONS, start=1):
            ttk.Label(p, text=label).grid(row=r, column=0, sticky="w", padx=(0, 12), pady=4)
            self.hotkey_btns[action] = ttk.Button(p, width=14, command=lambda a=action: self.start_capture(a))
            self.hotkey_btns[action].grid(row=r, column=1, sticky="w", pady=4)
            ttk.Button(p, text="Clear", style="Ghost.TButton", width=6,
                       command=lambda a=action: self.set_hotkey(a, None)).grid(row=r, column=2, sticky="w",
                                                                              padx=(4, 0))
        ttk.Button(p, text="Reset to F6 / F7 / F8",
                   command=self.reset_hotkeys).grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 4))
        self.section(p, 5, "Start / stop key")
        ttk.Radiobutton(p, text="Toggle: press to start, press again to stop", variable=self.hold_mode,
                        value=False, command=self.hold_mode_changed).grid(row=6, column=0, columnspan=3,
                                                                          sticky="w", pady=2)
        ttk.Radiobutton(p, text="Hold: clicks only while you hold the key down", variable=self.hold_mode,
                        value=True, command=self.hold_mode_changed).grid(row=7, column=0, columnspan=3,
                                                                         sticky="w", pady=2)
        self.hotkey_msg = ttk.Label(p, style="Warn.TLabel", wraplength=330, justify="left")
        self.hotkey_msg.grid(row=8, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.note(p, 9, "Click a hotkey, then press the new key. Combinations with Ctrl, Shift and Alt work, "
                        "and so do the middle and side mouse buttons. Esc cancels.\n\n"
                        "Hotkeys work even when this window isn't focused, so pick keys you don't need in "
                        "other apps. Letter and number hotkeys are ignored while you type in this window.")

        self.update_speed_hint()

    def set_icon(self):
        try:
            # Own taskbar entry, so Windows shows our icon instead of Python's
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GhostAutoClicker")
        except Exception:
            pass
        try:
            self.icons = [tk.PhotoImage(data=GHOST_ICON_64), tk.PhotoImage(data=GHOST_ICON_32)]
            self.root.iconphoto(True, *self.icons)
        except tk.TclError:
            pass

    # --- theme
    def apply_theme(self):
        self.colors = THEMES["dark" if self.dark else "light"]
        style_widgets(self.root, self.colors)
        set_title_bar(self.root, self.dark)
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel):
                w.configure(bg=self.colors["bg"])
                set_title_bar(w, self.dark)
        if hasattr(self, "tree"):
            self.style_tree()
            self.line.configure(bg=self.colors["border"])

    def toggle_theme(self):
        self.dark = not self.dark
        self.apply_theme()
        self.update_theme_button()

    def update_theme_button(self):
        self.theme_btn.config(text="☀  Light mode" if self.dark else "☾  Dark mode")

    def style_tree(self):
        c = self.colors
        self.tree.tag_configure("odd", background=c["stripe"])
        self.tree.tag_configure("active", background=c["active_row"])

    def update_speed_hint(self):
        if self.together.get():
            text = ("Different tabs and windows are clicked together each round; points on the same page go "
                    "one right after another. Speed counts rounds: 10 per second = each point clicked 10 "
                    "times a second.")
        else:
            text = "Speed is the total for all points: 10 per second with 2 points = 5 clicks each per second."
        self.speed_hint.config(text=text)
        self.update_summary()

    def update_summary(self):
        n = len(self.points)
        if not n:
            text = "No points · Start clicks wherever your mouse is"
        else:
            order = "all at the same time" if self.together.get() else "one after another"
            text = f"{n} point{'s' if n != 1 else ''} · clicked {order}"
        self.summary_lbl.config(text=text)

    def set_running(self, running):
        self.start_btn.config(text=STOP_TEXT if running else START_TEXT,
                              style="Stop.TButton" if running else "Start.TButton")

    # --- hotkeys (polled so they work while other apps are focused)
    def hotkey_loop(self):
        prev = {}
        held = {}                          # vk -> actions whose hotkey is held down right now
        was_capturing = False
        while True:
            capturing = self.capturing is not None
            # While picking a new hotkey, watch every key; otherwise only the bound ones
            keys = range(1, 256) if capturing else {hk[0] for hk in self.hotkeys.values() if hk}
            for vk in keys:
                down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                # On the first pass after switching modes, only record which keys are already held
                if down and not prev.get(vk) and capturing == was_capturing:
                    if capturing:
                        if vk == VK_ESCAPE:
                            self.events.put(("cancel",))
                        elif vk not in NOT_BINDABLE:
                            self.events.put(("bind", (vk, held_modifiers())))
                    else:
                        hk = (vk, held_modifiers())
                        for action, bound in self.hotkeys.items():
                            if bound == hk:
                                self.events.put(("action", action))
                                held.setdefault(vk, []).append(action)
                elif not down and prev.get(vk) and vk in held:
                    for action in held.pop(vk):
                        self.events.put(("release", action))
                prev[vk] = down
            was_capturing = capturing
            time.sleep(0.02)

    def run_hotkey(self, action):
        if self.capturing:
            return
        hk = self.hotkeys.get(action)
        if hk and types_text(hk):
            try:
                typing = isinstance(self.root.focus_get(), (ttk.Entry, tk.Entry))
            except (KeyError, tk.TclError):
                typing = False
            if typing:
                return  # the user is typing that key into one of our fields
        if action == "toggle" and self.hold_mode.get():
            if not self.clicker:
                self.holding = True
                self.toggle()
                # The key may have been let go while a message box was open
                if not self.holding and self.clicker:
                    self.clicker.stop()
        elif action == "toggle":
            self.toggle()
        elif action == "add":
            self.add_point_at_cursor()
        elif action == "remove":
            if self.points and not self.clicker:
                self.points.pop()
                self.refresh_points()

    def release_hotkey(self, action):
        if action == "toggle" and self.hold_mode.get():
            self.holding = False
            if self.clicker:
                self.clicker.stop()

    def hold_mode_changed(self):
        save_hold_mode(self.hold_mode.get())
        self.update_key_texts()

    def start_capture(self, action):
        was = self.capturing
        self.stop_capture()
        if was == action:
            return  # clicking the same button again cancels
        self.capturing = action
        self.hotkey_btns[action].config(text="Press a key…", style="Accent.TButton")
        self.hotkey_msg.config(text="")

    def stop_capture(self):
        self.capturing = None
        self.update_key_texts()

    def set_hotkey(self, action, hk):
        hotkeys = dict(self.hotkeys)
        msg = ""
        if hk:
            for other, label in HOTKEY_ACTIONS:
                if other != action and hotkeys[other] == hk:
                    hotkeys[other] = None
                    msg = f"{hotkey_name(hk)} was the hotkey for “{label}”, which now has none."
        hotkeys[action] = hk
        self.hotkeys = hotkeys             # swapped in one go; the hotkey thread reads it
        save_hotkeys(hotkeys)
        self.stop_capture()
        self.hotkey_msg.config(text=msg)

    def reset_hotkeys(self):
        self.hotkeys = dict(DEFAULT_HOTKEYS)
        save_hotkeys(self.hotkeys)
        self.stop_capture()
        self.hotkey_msg.config(text="")

    def add_hint(self):
        hk = self.hotkeys.get("add")
        return f"press {hotkey_name(hk)}" if hk else "use “Add point”"

    def update_key_texts(self):
        for action, lbl in self.key_lbls.items():
            lbl.config(text=hotkey_name(self.hotkeys[action]))
        self.key_texts["toggle"].config(text="hold to click" if self.hold_mode.get() else "start / stop")
        for action, btn in self.hotkey_btns.items():
            if action != self.capturing:
                btn.config(text=hotkey_name(self.hotkeys[action]), style="TButton")
        start = self.hotkeys.get("toggle")
        if not start:
            start = "Press Start"
        elif self.hold_mode.get():
            start = f"Hold {hotkey_name(start)} (or press Start)"
        else:
            start = f"Press {hotkey_name(start)} or Start"
        if self.hotkeys.get("add"):
            add = f"hover over each spot and {self.add_hint()},\nor use “Add point” for a 3 second countdown."
        else:
            add = "use “Add point” (3 second countdown)."
        empty = (f"No click points: {start} to click wherever your mouse is.\n\n"
                 f"To click fixed spots instead, {add}")
        self.empty_lbl.config(text=empty)
        self.tabs_note.config(text="1. Launch it and log in to your sites once (it's a separate profile).\n"
                                   "2. Open each page in its own tab.\n"
                                   f"3. Hover the spot in each tab and {self.add_hint()}.")

    def ui_loop(self):
        while not self.events.empty():
            ev = self.events.get()
            if ev[0] == "bind":
                if self.capturing:
                    self.set_hotkey(self.capturing, ev[1])
            elif ev[0] == "cancel":
                if self.capturing:
                    self.stop_capture()
            elif ev[0] == "release":
                self.release_hotkey(ev[1])
            else:
                self.run_hotkey(ev[1])
        if self.browser.up:
            n = self.browser.tab_count
            self.cdp_lbl.config(text=f"● Connected · {n} tab{'s' if n != 1 else ''}", style="Good.TLabel")
        else:
            self.cdp_lbl.config(text="○ Not running", style="Muted.TLabel")
        cl = self.clicker
        if cl:
            n = len(cl.cfg["points"])
            if cl.cfg["points"][0].kind == "cursor":
                where = "at the mouse cursor"
            elif cl.cfg["together"]:
                where = f"all {n} points"
            else:
                where = f"point {cl.current + 1} of {n}"
            self.count_lbl.config(text=f"{cl.clicks:,}")
            self.status_lbl.config(text=f"{cl.status} · {where}")
            self.err_lbl.config(text=f"⚠ {cl.last_error}" if cl.last_error else "")
            self.show_point_clicks(cl)
            self.mark_active(None if cl.cfg["together"] else cl.current)
            if not cl.is_alive():
                self.status_lbl.config(text=cl.status)
                self.clicker = None
                self.browser.paused = False
                self.set_running(False)
                self.mark_active(None)
        self.root.after(100, self.ui_loop)

    def show_point_clicks(self, cl):
        counts = getattr(cl, "per_point", None)
        if not counts:
            return
        for i, (t, c) in enumerate(zip(cl.cfg["points"], counts)):
            if c != t.clicks:
                t.clicks = c
                if self.tree.exists(str(i)):
                    self.tree.set(str(i), "clicks", f"{c:,}")

    def mark_active(self, i):
        if i == self.active_row:
            return
        for row in (self.active_row, i):
            if row is not None and self.tree.exists(str(row)):
                self.tree.item(str(row), tags=self.row_tags(row, active=row == i))
        self.active_row = i

    @staticmethod
    def row_tags(i, active=False):
        return ("active",) if active else (("odd",) if i % 2 else ())

    # --- points
    def refresh_points(self, select=None):
        self.tree.delete(*self.tree.get_children())
        self.active_row = None
        for i, t in enumerate(self.points):
            title = t.title if len(t.title) <= 48 else t.title[:47] + "…"
            if t.reload_every:
                every = "each click" if t.reload_every == 1 else f"every {t.reload_every}"
                kind = "URL " if t.reload_url else ""
                reload_txt = f"{kind}{every} · {t.reload_wait:g}s"
            else:
                reload_txt = "—"
            clicks = f"{t.clicks:,}" if t.clicks else "—"
            self.tree.insert("", "end", iid=str(i), tags=self.row_tags(i),
                             values=(i + 1, "Tab" if t.kind == "tab" else "Window", f"{t.sx}, {t.sy}",
                                     reload_txt, clicks, title))
        if self.points:
            self.empty_lbl.place_forget()
        else:
            self.empty_lbl.place(relx=0.5, rely=0.55, anchor="center")
        self.update_summary()
        if select is None:
            return
        rows = [str(i) for i in ([select] if isinstance(select, int) else select)
                if 0 <= i < len(self.points)]
        if rows:
            self.tree.selection_set(rows)
            self.tree.see(rows[0])

    def flash(self, text):
        self.pick_lbl.config(text=text, style="Warn.TLabel")
        if self.flash_job:
            self.root.after_cancel(self.flash_job)
        self.flash_job = self.root.after(5000, lambda: self.pick_lbl.config(text=HINT, style="Muted.TLabel"))

    def add_point_at_cursor(self):
        if self.clicker:
            return  # don't change the list while running
        sx, sy = cursor_pos()
        point = None
        if self.browser.up:
            root_hwnd = root_window_at(sx, sy)
            if root_hwnd and class_name(root_hwnd).startswith("Chrome_WidgetWin"):
                try:
                    picked = self.browser.pick()
                except Exception:
                    picked = None
                if picked:
                    x, y, tid, title, url = picked
                    win_title = window_text(root_hwnd)
                    same_window = (self.browser.pid and window_pid(root_hwnd) == self.browser.pid) or \
                                  (title and win_title.startswith(title[:25]))
                    if same_window:
                        point = TabPoint(self.browser, tid, x, y, title, url)
                elif self.browser.pid and window_pid(root_hwnd) == self.browser.pid:
                    self.flash("Move the mouse a little over the page, then add the point again.")
                    return
        if point is None:
            point = WindowPoint(sx, sy)
        self.points.append(point)
        self.refresh_points(select=len(self.points) - 1)

    def selected_indices(self):
        return sorted(int(s) for s in self.tree.selection())

    def edit_point(self, event=None):
        idxs = self.selected_indices()
        if not idxs:
            if self.points:
                messagebox.showinfo("Auto Clicker", "Select one or more points in the list first.")
            return
        if self.clicker:
            messagebox.showinfo("Auto Clicker", "Stop the clicker before editing points.")
            return
        pts = [self.points[i] for i in idxs]
        multi = len(pts) > 1
        has_tabs = any(p.kind == "tab" for p in pts)

        def common(get):
            vals = {get(p) for p in pts}
            return vals.pop() if len(vals) == 1 else None

        on_v = common(lambda p: p.reload_every > 0)
        every_v = common(lambda p: p.reload_every)
        wait_v = common(lambda p: p.reload_wait)
        url_v = common(lambda p: p.reload_url)
        own_v = has_tabs and all(p.kind == "tab" and p.reload_url and p.reload_url == p.url for p in pts)
        if own_v and multi:
            mode_v = "own"
        else:
            mode_v = common(lambda p: "url" if p.reload_url else "refresh")

        win = tk.Toplevel(self.root)
        win.title(f"Edit {len(pts)} points" if multi else f"Point {idxs[0] + 1} settings")
        win.transient(self.root)
        win.resizable(False, False)
        win.configure(bg=self.colors["bg"])
        body = ttk.Frame(win, padding=(6, 4))
        body.pack(fill="both", expand=True)

        if on_v is None:
            reload_state = tk.StringVar(value=KEEP)
        else:
            reload_state = tk.StringVar(value="On" if on_v else "Off")
        every = tk.StringVar(value=str(every_v) if every_v else ("" if multi and every_v is None else "1"))
        wait = tk.StringVar(value=f"{wait_v:g}" if wait_v is not None else "")
        mode = tk.StringVar(value=mode_v or "")
        if url_v and mode_v == "url":
            url_start = url_v
        elif not multi and pts[0].kind == "tab":
            url_start = pts[0].url
        else:
            url_start = ""
        url = tk.StringVar(value=url_start)

        if multi:
            nums = ", ".join(str(i + 1) for i in idxs)
            head = (f"Editing points {nums}.\n"
                    "Empty fields and “keep” options leave each point's own value unchanged.")
        else:
            t = pts[0]
            head = f"Point {idxs[0] + 1}: ({t.sx}, {t.sy}) in “{t.title[:45]}”"
        ttk.Label(body, text=head, style="Muted.TLabel").grid(row=0, column=0, columnspan=3, sticky="w",
                                                          padx=10, pady=(10, 6))

        ttk.Label(body, text="Reload page after clicking:").grid(row=1, column=0, sticky="w", padx=10, pady=(0, 4))
        ttk.Combobox(body, textvariable=reload_state, state="readonly", width=24,
                     values=["On", "Off"] + ([KEEP] if multi else [])).grid(row=1, column=1, columnspan=2,
                                                                          sticky="w", pady=(0, 4))
        ttk.Label(body, text="Reload every").grid(row=2, column=0, sticky="w", padx=(30, 4), pady=2)
        ttk.Spinbox(body, from_=1, to=1_000_000, textvariable=every, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(body, text="clicks on each point").grid(row=2, column=2, sticky="w", padx=(4, 10))
        ttk.Label(body, text="Then wait").grid(row=3, column=0, sticky="w", padx=(30, 4), pady=2)
        ttk.Spinbox(body, from_=0, to=3600, increment=0.5, textvariable=wait, width=8).grid(row=3, column=1, sticky="w")
        ttk.Label(body, text="seconds for the page to load").grid(row=3, column=2, sticky="w", padx=(4, 10))

        ttk.Label(body, text="How:").grid(row=4, column=0, sticky="w", padx=(30, 4), pady=(8, 2))
        r = 4
        ttk.Radiobutton(body, text="Refresh the current page", variable=mode,
                        value="refresh").grid(row=r, column=1, columnspan=2, sticky="w", pady=(8, 2))
        if has_tabs:
            r += 1
            own_txt = "Open each tab's own address (the page it was on when added)"
            if any(p.kind == "window" for p in pts):
                own_txt += " — window points keep theirs"
            ttk.Radiobutton(body, text=own_txt, variable=mode, value="own").grid(row=r, column=1, columnspan=2,
                                                                                 sticky="w")
        r += 1
        ttk.Radiobutton(body, text="Open this URL:", variable=mode,
                        value="url").grid(row=r, column=1, columnspan=2, sticky="w")
        if multi:
            r += 1
            ttk.Radiobutton(body, text=KEEP, variable=mode, value="").grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1
        url_entry = ttk.Entry(body, textvariable=url, width=56)
        url_entry.grid(row=r, column=0, columnspan=3, sticky="w", padx=(30, 10), pady=(2, 0))
        url_entry.bind("<FocusIn>", lambda e: mode.set("url"))
        r += 1
        ttk.Label(body, text="Opening a URL helps if your clicks take you to another page and a refresh\n"
                            "would land on the wrong one.",
                  style="Muted.TLabel").grid(row=r, column=0, columnspan=3, sticky="w", padx=(30, 10), pady=(2, 0))

        def parse(text, conv, minimum, label):
            text = text.strip()
            if not text:
                if multi:
                    return None
                raise ValueError(f"Enter a value for “{label}”.")
            v = conv(float(text))
            if v < minimum:
                raise ValueError(f"“{label}” must be at least {minimum}.")
            return v

        def save():
            try:
                e = parse(every.get(), int, 1, "Reload every")
                w = parse(wait.get(), float, 0, "Then wait")
            except ValueError as err:
                msg = str(err) if str(err).startswith(("Enter", "“")) else "Please enter valid numbers."
                messagebox.showerror("Auto Clicker", msg, parent=win)
                return
            m = mode.get()
            u = url.get().strip()
            if m == "url":
                if u and "://" not in u:
                    u = "https://" + u
                if not u and any(not p.reload_url for p in pts):
                    messagebox.showerror("Auto Clicker", "Enter the URL to open, or choose another option.",
                                         parent=win)
                    return
            state = reload_state.get()
            for p in pts:
                if state == "On":
                    p.reload_every = e if e is not None else (p.reload_every or 1)
                elif state == "Off":
                    p.reload_every = 0
                elif e is not None and p.reload_every:
                    p.reload_every = e
                if w is not None:
                    p.reload_wait = w
                if m == "refresh":
                    p.reload_url = ""
                elif m == "url" and u:
                    p.reload_url = u
                elif m == "own" and p.kind == "tab":
                    p.reload_url = p.url
            self.refresh_points(select=idxs)
            win.destroy()

        btns = ttk.Frame(body)
        btns.grid(row=r + 1, column=0, columnspan=3, sticky="e", padx=10, pady=(10, 10))
        ttk.Button(btns, text="Save", style="Accent.TButton", command=save).pack(side="left")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="left", padx=(6, 0))
        win.bind("<Return>", lambda e: save())
        win.bind("<Escape>", lambda e: win.destroy())
        set_title_bar(win, self.dark)
        win.grab_set()

    def remove_selected(self):
        idxs = self.selected_indices()
        if not idxs or self.clicker:
            return
        for i in reversed(idxs):
            del self.points[i]
        self.refresh_points(select=min(idxs[0], len(self.points) - 1))

    def move(self, d):
        idxs = self.selected_indices()
        if not idxs or self.clicker:
            return
        if (d < 0 and idxs[0] == 0) or (d > 0 and idxs[-1] == len(self.points) - 1):
            return
        for i in (idxs if d < 0 else reversed(idxs)):
            self.points[i], self.points[i + d] = self.points[i + d], self.points[i]
        self.refresh_points(select=[i + d for i in idxs])

    def clear_points(self):
        if self.clicker:
            return
        self.points.clear()
        self.refresh_points()

    def start_pick(self):
        self.countdown = 3
        self.pick_btn.config(state="disabled")
        self.pick_tick()

    def pick_tick(self):
        if self.countdown > 0:
            self.pick_lbl.config(text=f"Hover over the target… {self.countdown}", style="TLabel")
            self.countdown -= 1
            self.root.after(1000, self.pick_tick)
        else:
            self.pick_lbl.config(text=HINT, style="Muted.TLabel")
            self.add_point_at_cursor()
            self.pick_btn.config(state="normal")

    # --- browsers
    def launch_automation(self):
        name = self.browser_name.get()
        if self.browser.up:
            messagebox.showinfo("Auto Clicker", "The automation browser is already running.")
            return
        path = find_browser(name)
        if not path:
            messagebox.showerror("Auto Clicker", f"Couldn't find {name} on this computer.")
            return
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        profile = os.path.join(base, "AutoClicker", f"{name}-profile")
        os.makedirs(profile, exist_ok=True)
        try:
            p = subprocess.Popen([path, f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={profile}",
                                  "--no-first-run", "--no-default-browser-check", *BACKGROUND_FLAGS])
            self.browser.pid = p.pid
        except OSError as e:
            messagebox.showerror("Auto Clicker", f"Couldn't start {name}: {e}")
            return
        messagebox.showinfo(
            "Auto Clicker",
            f"An automation {name} window is opening. It's a separate profile, so your normal {name} "
            "stays as it is, and you'll need to log in to your sites once in this one.\n\n"
            f"Open your pages as tabs in that window, hover the spot to click in each tab and {self.add_hint()}.")

    def launch_browser(self):
        name = self.browser_name.get()
        exe = BROWSERS[name][0]
        path = find_browser(name)
        if not path:
            messagebox.showerror("Auto Clicker", f"Couldn't find {name} on this computer.")
            return
        if process_running(exe):
            ok = messagebox.askyesno(
                "Auto Clicker",
                f"This restarts your normal {name} with background clicking enabled (for window points).\n\n"
                f"Close all {name} windows now and reopen it? Your tabs should come back "
                f"(click 'Restore' if {name} asks).\n\nNote: this also closes the automation browser.")
            if not ok:
                return
            subprocess.run(["taskkill", "/IM", exe, "/F"], capture_output=True, creationflags=NO_WINDOW)
            time.sleep(1.5)
        subprocess.Popen([path, "--restore-last-session", *BACKGROUND_FLAGS])
        messagebox.showinfo(
            "Auto Clicker",
            f"{name} started. Remove any old window points for it and add them again.")

    # --- start / stop
    def toggle(self):
        if self.clicker:
            self.clicker.stop()
            return
        try:
            cfg = {
                "cps": float(self.cps.get()),
                "every": int(float(self.every.get() or 0)),
                "pause": float(self.pause.get() or 0),
                "limit": int(float(self.limit.get() or 0)),
                "hold": float(self.hold.get() or 0) / 1000.0,
                "jitter": int(float(self.jitter.get() or 0)),
            }
            if min(cfg.values()) < 0 or cfg["cps"] <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Auto Clicker", "Please enter valid positive numbers.")
            return
        try:
            own = user32.GetAncestor(self.root.winfo_id(), GA_ROOT)
        except Exception:
            own = None
        cfg.update(points=list(self.points) or [CursorPoint(own)], right=self.button.get() == "Right",
                   background=self.background.get(), method=self.method.get(),
                   reload_method=self.reload_method.get(), tab_method=self.tab_method.get(),
                   together=self.together.get())

        has_window = any(t.kind == "window" for t in cfg["points"])
        has_tab = any(t.kind == "tab" for t in cfg["points"])
        if has_window and cfg["background"]:
            for i, t in enumerate(cfg["points"]):
                if t.kind == "window" and not user32.IsWindow(t.endpoint(cfg["method"])[0]):
                    messagebox.showerror("Auto Clicker",
                                         f"The window for point {i + 1} no longer exists. Remove it and add it again.")
                    return
        if has_tab:
            try:
                ids = {p["id"] for p in self.browser.pages()}
            except Exception:
                messagebox.showerror("Auto Clicker", "The automation browser isn't running. "
                                                     "Launch it, then re-add its tab points.")
                return
            for i, t in enumerate(cfg["points"]):
                if t.kind == "tab" and t.tid not in ids:
                    messagebox.showerror("Auto Clicker",
                                         f"The tab for point {i + 1} was closed. Remove it and add it again.")
                    return
        if has_window and not cfg["background"] and not getattr(self, "fg_warned", False):
            if not messagebox.askokcancel(
                    "Auto Clicker",
                    "Foreground mode moves your real mouse and clicks whatever is on screen.\n"
                    "If you switch to another desktop or a game, it will click THERE.\n\n"
                    "Use Background mode or tab points to click on desktop 2 while you play on desktop 1."):
                return
            self.fg_warned = True
        self.browser.paused = True
        for t in self.points:
            t.clicks = 0
        self.refresh_points(select=self.selected_indices())
        self.count_lbl.config(text="0")
        self.err_lbl.config(text="")
        self.clicker = Clicker(cfg)
        self.clicker.start()
        self.set_running(True)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
