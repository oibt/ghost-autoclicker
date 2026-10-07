"""
Auto Clicker (Windows) - v6
---------------------------
Run:   python autoclicker.py        (Python 3.8+, no extra packages needed)

Hotkeys (work even when this window isn't focused):
  F6  = Start / Stop
  F7  = Add a click point where your mouse is right now
  F8  = Remove the last point

Two kinds of click points:
  Window points - any app or browser window. Background mode posts clicks to
                  the window; Foreground mode moves your real mouse.
  Tab points    - tabs in the "automation browser" (launched from this app).
                  Every tab can be clicked, even tabs that aren't showing,
                  in one single browser window.

Points are clicked in order (1, 2, 3, ... then back to 1).
"""
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
VK_F6, VK_F7, VK_F8 = 0x75, 0x76, 0x77

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
        per_point = [0] * n
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
        per_point = [0] * n
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
                    if self.stop_evt.wait(0.5):
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


# ---------------------------------------------------------------- UI
HINT = "F7 add · F8 remove last · double-click to edit · Ctrl/Shift+click to edit several"
KEEP = "(keep each point's own)"


class App:
    def __init__(self, root):
        self.root = root
        self.points = []
        self.clicker = None
        self.events = queue.Queue()
        self.countdown = 0
        self.browser = Browser()

        root.title("Auto Clicker")
        root.resizable(False, False)
        pad = {"padx": 8, "pady": 4}

        # Click points
        f = ttk.LabelFrame(root, text="Click points (clicked in order, then repeats)")
        f.pack(fill="x", **pad)
        self.tree = ttk.Treeview(f, columns=("n", "x", "y", "reload", "win"), show="headings", height=6,
                                 selectmode="extended")
        for col, text, w in (("n", "#", 30), ("x", "X", 55), ("y", "Y", 55),
                             ("reload", "Reload page", 120), ("win", "Window / tab", 230)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor="w" if col == "win" else "center", stretch=False)
        self.tree.pack(fill="x", padx=6, pady=(4, 2))
        self.tree.bind("<Double-1>", self.edit_point)
        self.tree.bind("<Delete>", lambda e: self.remove_selected())
        self.tree.bind("<Control-a>", lambda e: (self.tree.selection_set(self.tree.get_children()), "break")[1])

        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=(2, 2))
        self.pick_btn = ttk.Button(row, text="Add (3 s countdown)", command=self.start_pick)
        self.pick_btn.pack(side="left")
        ttk.Button(row, text="Edit…", command=self.edit_point).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Remove", command=self.remove_selected).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="▲", width=3, command=lambda: self.move(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="▼", width=3, command=lambda: self.move(1)).pack(side="left", padx=(2, 0))
        ttk.Button(row, text="Select all", command=lambda: self.tree.selection_set(self.tree.get_children())).pack(side="left", padx=(6, 0))
        ttk.Button(row, text="Clear all", command=self.clear_points).pack(side="left", padx=(6, 0))
        self.pick_lbl = ttk.Label(f, text=HINT, foreground="gray")
        self.pick_lbl.pack(anchor="w", padx=6, pady=(0, 6))

        # Speed
        f = ttk.LabelFrame(root, text="Speed")
        f.pack(fill="x", **pad)
        ttk.Label(f, text="Clicks per second:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.cps = tk.StringVar(value="10")
        ttk.Spinbox(f, from_=0.1, to=1000, increment=1, textvariable=self.cps, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(f, text="Button:").grid(row=0, column=2, sticky="w", padx=(16, 4))
        self.button = tk.StringVar(value="Left")
        ttk.Combobox(f, textvariable=self.button, values=["Left", "Right"], state="readonly",
                     width=7).grid(row=0, column=3, sticky="w", padx=(0, 6))
        ttk.Label(f, text="Hold (ms):").grid(row=1, column=0, sticky="w", padx=6, pady=(0, 4))
        self.hold = tk.StringVar(value="20")
        ttk.Spinbox(f, from_=0, to=1000, textvariable=self.hold, width=8).grid(row=1, column=1, sticky="w", pady=(0, 4))
        ttk.Label(f, text="Random offset (± px):").grid(row=1, column=2, sticky="w", padx=(16, 4), pady=(0, 4))
        self.jitter = tk.StringVar(value="0")
        ttk.Spinbox(f, from_=0, to=50, textvariable=self.jitter, width=5).grid(row=1, column=3, sticky="w", pady=(0, 4))
        ttk.Label(f, text="Click order:").grid(row=2, column=0, sticky="w", padx=6, pady=(0, 2))
        self.together = tk.BooleanVar(value=False)
        order = ttk.Frame(f)
        order.grid(row=2, column=1, columnspan=3, sticky="w", pady=(0, 2))
        ttk.Radiobutton(order, text="One after another", variable=self.together, value=False,
                        command=self.update_speed_hint).pack(side="left")
        ttk.Radiobutton(order, text="All at the same time", variable=self.together, value=True,
                        command=self.update_speed_hint).pack(side="left", padx=(10, 0))
        self.speed_hint = ttk.Label(f, foreground="gray")
        self.speed_hint.grid(row=3, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 4))
        self.update_speed_hint()

        # Pause
        f = ttk.LabelFrame(root, text="Delay after a set amount of clicks")
        f.pack(fill="x", **pad)
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=4)
        ttk.Label(row, text="After every").pack(side="left")
        self.every = tk.StringVar(value="0")
        ttk.Spinbox(row, from_=0, to=1_000_000, textvariable=self.every, width=8).pack(side="left", padx=4)
        ttk.Label(row, text="clicks, wait").pack(side="left")
        self.pause = tk.StringVar(value="5")
        ttk.Spinbox(row, from_=0, to=86400, increment=0.5, textvariable=self.pause, width=6).pack(side="left", padx=4)
        ttk.Label(row, text="seconds   (0 = never)").pack(side="left")
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(row, text="Stop completely after").pack(side="left")
        self.limit = tk.StringVar(value="0")
        ttk.Spinbox(row, from_=0, to=10_000_000, textvariable=self.limit, width=10).pack(side="left", padx=4)
        ttk.Label(row, text="clicks   (0 = run forever)").pack(side="left")

        # Browser tabs
        f = ttk.LabelFrame(root, text="Browser tabs — click every tab in ONE browser, even hidden tabs")
        f.pack(fill="x", **pad)
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=(4, 2))
        self.browser_name = tk.StringVar(value="Brave")
        ttk.Combobox(row, textvariable=self.browser_name, values=list(BROWSERS), state="readonly",
                     width=8).pack(side="left")
        ttk.Button(row, text="Launch automation browser", command=self.launch_automation).pack(side="left", padx=6)
        self.cdp_lbl = ttk.Label(row, text="", foreground="gray")
        self.cdp_lbl.pack(side="left", padx=4)
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=(2, 2))
        ttk.Label(row, text="Tab click method:").pack(side="left")
        self.tab_method = tk.StringVar(value=TAB_REAL)
        ttk.Combobox(row, textvariable=self.tab_method, values=[TAB_REAL, TAB_JS], state="readonly",
                     width=28).pack(side="left", padx=4)
        ttk.Label(f, text="Open your pages as tabs in the automation browser, hover a spot in a tab and press F7.\n"
                          "Its tabs can then stay hidden, and the window can sit on another desktop.",
                  foreground="gray").pack(anchor="w", padx=6, pady=(0, 6))

        # Windows
        f = ttk.LabelFrame(root, text="Window points (any app / other browsers)")
        f.pack(fill="x", **pad)
        self.background = tk.BooleanVar(value=True)
        ttk.Radiobutton(f, text="Background — window can be behind others, mouse stays free",
                        variable=self.background, value=True).pack(anchor="w", padx=6, pady=(4, 0))
        ttk.Radiobutton(f, text="Foreground — moves your real mouse (works with everything)",
                        variable=self.background, value=False).pack(anchor="w", padx=6, pady=(0, 4))
        adv = ttk.Frame(f)
        adv.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Label(adv, text="Send clicks to:").grid(row=0, column=0, sticky="w")
        self.method = tk.StringVar(value=METHOD_AUTO)
        ttk.Combobox(adv, textvariable=self.method, values=[METHOD_AUTO, METHOD_MAIN, METHOD_CHILD],
                     state="readonly", width=22).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(adv, text="Reload using:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.reload_method = tk.StringVar(value=RELOAD_CMD)
        ttk.Combobox(adv, textvariable=self.reload_method, values=[RELOAD_CMD, RELOAD_F5],
                     state="readonly", width=22).grid(row=1, column=1, sticky="w", padx=4, pady=(4, 0))
        row = ttk.Frame(f)
        row.pack(fill="x", padx=6, pady=(2, 6))
        ttk.Button(row, text="Restart browser with background clicking enabled",
                   command=self.launch_browser).pack(side="left")
        ttk.Label(row, text="(uses the browser picked above)", foreground="gray").pack(side="left", padx=6)

        # Start / status
        f = ttk.Frame(root)
        f.pack(fill="x", padx=8, pady=(4, 10))
        self.start_btn = ttk.Button(f, text="Start (F6)", command=self.toggle, width=16)
        self.start_btn.pack(side="left")
        self.topmost = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="On top", variable=self.topmost,
                        command=lambda: root.attributes("-topmost", self.topmost.get())).pack(side="right")
        self.status_lbl = ttk.Label(f, text="Idle", width=60)
        self.status_lbl.pack(side="left", padx=10)

        threading.Thread(target=self.hotkey_loop, daemon=True).start()
        self.ui_loop()

    def update_speed_hint(self):
        if self.together.get():
            text = ("Different tabs/windows are clicked together each round; points on the same page go one\n"
                    "right after another. Speed counts rounds (10 CPS = each point clicked 10 times a second).")
        else:
            text = "Speed is the total for all points: 10 CPS with 2 points = 5 clicks each per second."
        self.speed_hint.config(text=text)

    # --- hotkeys (polled so they work while other apps are focused)
    def hotkey_loop(self):
        prev = {VK_F6: False, VK_F7: False, VK_F8: False}
        while True:
            for vk in prev:
                down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                if down and not prev[vk]:
                    self.events.put(vk)
                prev[vk] = down
            time.sleep(0.02)

    def ui_loop(self):
        while not self.events.empty():
            vk = self.events.get()
            if vk == VK_F6:
                self.toggle()
            elif vk == VK_F7:
                self.add_point_at_cursor()
            elif vk == VK_F8:
                if self.points and not self.clicker:
                    self.points.pop()
                    self.refresh_points()
        if self.browser.up:
            self.cdp_lbl.config(text=f"● Connected — {self.browser.tab_count} tab(s)", foreground="green")
        else:
            self.cdp_lbl.config(text="Not running", foreground="gray")
        if self.clicker:
            n = len(self.clicker.cfg["points"])
            err = f"   ⚠ {self.clicker.last_error}" if self.clicker.last_error else ""
            where = (f"all {n} points" if self.clicker.cfg["together"]
                     else f"point {self.clicker.current + 1}/{n}")
            self.status_lbl.config(
                text=f"{self.clicker.status} — {where} — {self.clicker.clicks:,} clicks{err}")
            if not self.clicker.is_alive():
                self.status_lbl.config(text=f"{self.clicker.status} — {self.clicker.clicks:,} clicks{err}")
                self.clicker = None
                self.browser.paused = False
                self.start_btn.config(text="Start (F6)")
        self.root.after(100, self.ui_loop)

    # --- points
    def refresh_points(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for i, t in enumerate(self.points):
            title = t.title if len(t.title) <= 36 else t.title[:35] + "…"
            if t.reload_every:
                every = "each click" if t.reload_every == 1 else f"every {t.reload_every}"
                kind = "URL " if t.reload_url else ""
                reload_txt = f"{kind}{every} · {t.reload_wait:g}s"
            else:
                reload_txt = "—"
            self.tree.insert("", "end", iid=str(i), values=(i + 1, t.sx, t.sy, reload_txt, title))
        if select is None:
            return
        rows = [str(i) for i in ([select] if isinstance(select, int) else select)
                if 0 <= i < len(self.points)]
        if rows:
            self.tree.selection_set(rows)
            self.tree.see(rows[0])

    def flash(self, text, color="red"):
        self.pick_lbl.config(text=text, foreground=color)
        self.root.after(5000, lambda: self.pick_lbl.config(text=HINT, foreground="gray"))

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
                    self.flash("Move the mouse a little over the page, then press F7 again.")
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
            messagebox.showinfo("Auto Clicker", "Stop the clicker (F6) before editing points.")
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
        ttk.Label(win, text=head, foreground="gray").grid(row=0, column=0, columnspan=3, sticky="w",
                                                          padx=10, pady=(10, 6))

        ttk.Label(win, text="Reload page after clicking:").grid(row=1, column=0, sticky="w", padx=10, pady=(0, 4))
        ttk.Combobox(win, textvariable=reload_state, state="readonly", width=24,
                     values=["On", "Off"] + ([KEEP] if multi else [])).grid(row=1, column=1, columnspan=2,
                                                                          sticky="w", pady=(0, 4))
        ttk.Label(win, text="Reload every").grid(row=2, column=0, sticky="w", padx=(30, 4), pady=2)
        ttk.Spinbox(win, from_=1, to=1_000_000, textvariable=every, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(win, text="clicks on each point").grid(row=2, column=2, sticky="w", padx=(4, 10))
        ttk.Label(win, text="Then wait").grid(row=3, column=0, sticky="w", padx=(30, 4), pady=2)
        ttk.Spinbox(win, from_=0, to=3600, increment=0.5, textvariable=wait, width=8).grid(row=3, column=1, sticky="w")
        ttk.Label(win, text="seconds for the page to load").grid(row=3, column=2, sticky="w", padx=(4, 10))

        ttk.Label(win, text="How:").grid(row=4, column=0, sticky="w", padx=(30, 4), pady=(8, 2))
        r = 4
        ttk.Radiobutton(win, text="Refresh the current page", variable=mode,
                        value="refresh").grid(row=r, column=1, columnspan=2, sticky="w", pady=(8, 2))
        if has_tabs:
            r += 1
            own_txt = "Open each tab's own address (the page it was on when added)"
            if any(p.kind == "window" for p in pts):
                own_txt += " — window points keep theirs"
            ttk.Radiobutton(win, text=own_txt, variable=mode, value="own").grid(row=r, column=1, columnspan=2,
                                                                                 sticky="w")
        r += 1
        ttk.Radiobutton(win, text="Open this URL:", variable=mode,
                        value="url").grid(row=r, column=1, columnspan=2, sticky="w")
        if multi:
            r += 1
            ttk.Radiobutton(win, text=KEEP, variable=mode, value="").grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1
        url_entry = ttk.Entry(win, textvariable=url, width=56)
        url_entry.grid(row=r, column=0, columnspan=3, sticky="w", padx=(30, 10), pady=(2, 0))
        url_entry.bind("<FocusIn>", lambda e: mode.set("url"))
        r += 1
        ttk.Label(win, text="Opening a URL helps if your clicks take you to another page and a refresh\n"
                            "would land on the wrong one.",
                  foreground="gray").grid(row=r, column=0, columnspan=3, sticky="w", padx=(30, 10), pady=(2, 0))

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

        btns = ttk.Frame(win)
        btns.grid(row=r + 1, column=0, columnspan=3, sticky="e", padx=10, pady=(10, 10))
        ttk.Button(btns, text="Save", command=save).pack(side="left")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="left", padx=(6, 0))
        win.bind("<Return>", lambda e: save())
        win.bind("<Escape>", lambda e: win.destroy())
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
            self.pick_lbl.config(text=f"Hover over the target… {self.countdown}", foreground="")
            self.countdown -= 1
            self.root.after(1000, self.pick_tick)
        else:
            self.pick_lbl.config(text=HINT, foreground="gray")
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
            "Open your pages as tabs in that window, hover the spot to click in each tab and press F7.")

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
        if not self.points:
            messagebox.showwarning("Auto Clicker", "Add at least one click point first (Add or F7).")
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
        cfg.update(points=list(self.points), right=self.button.get() == "Right",
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
        self.clicker = Clicker(cfg)
        self.clicker.start()
        self.start_btn.config(text="Stop (F6)")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
