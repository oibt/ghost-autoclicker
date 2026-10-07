# Ghost Auto Clicker (Windows)

A single-file auto clicker that can click in the background: on windows sitting behind others, on hidden browser tabs, and on other Windows virtual desktops.

- **File:** `autoclicker.py`
- **Requires:** Windows and Python 3.8+. It uses only the standard library (tkinter, ctypes, sockets), so there's nothing to install.

```
python autoclicker.py
```

Optional standalone exe:

```
pyinstaller --onefile --noconsole autoclicker.py
```

## Features

- A list of click points, clicked in order (one after another) or all at the same time.
- Clicks per second, hold time (ms), random offset (± px), left or right button.
- "After every N clicks, wait X seconds" pause, and an optional total click limit.
- Per-point reload: after every N clicks on a point, refresh the page or open a URL (one you type, or for tab points the tab's own address), then wait X seconds.
- Select several points in the list to edit their settings together. Blank fields and "keep" options leave each point's own value unchanged.
- Global hotkeys, which work while other apps are focused (polled with `GetAsyncKeyState`):

  | Key | Action |
  |-----|--------|
  | F6  | Start / stop |
  | F7  | Add a point under the mouse |
  | F8  | Remove the last point |

## Two kinds of points

### Window points (`WindowPoint`): any app

- **Background mode** posts `WM_MOUSEMOVE` / `WM_LBUTTONDOWN` / `WM_LBUTTONUP` to the window. For Chromium windows, the "Auto" send-to option posts to the top-level `Chrome_WidgetWin_1` and not to `Chrome_RenderWidgetHostHWND`. Posting to the child registered only the first click on many sites.
- **Foreground mode** uses `SetCursorPos` + `mouse_event`, which takes over the real mouse.
- **Reload** sends `WM_APPCOMMAND` browser refresh or a posted F5. "Open URL" posts F6 (focus the omnibox), sends `WM_CHAR` for each character, then Delete (drops autocomplete) and Enter. It waits 0.35 s after F6 so that "/" doesn't go to the page.
- **"Restart browser with background clicking enabled"** relaunches the browser with flags that stop it pausing hidden or covered windows. This also works across Windows virtual desktops.

### Tab points (`TabPoint`): tabs in the automation browser

The app can launch an "automation browser" (Brave, Chrome or Edge) with `--remote-debugging-port=9222` and a separate profile in `%LOCALAPPDATA%\AutoClicker\<Browser>-profile`. All of its tabs can be clicked, including hidden tabs in a single window.

- Talks to the browser over the Chrome DevTools Protocol, through a minimal stdlib WebSocket client (`WebSocket`, `CDPTab`, `Browser`).
- **Clicking:** `Input.dispatchMouseEvent`, sent fire-and-forget (`CDPTab.send`). Hidden tabs can take about 1 s to acknowledge input even though the click lands immediately, so clicks never wait for the reply.
- **Picking:** a tracker thread injects JS into every tab that records the last mousemove (clientX/Y + timestamp). F7 picks the visible tab with the most recent position.
- **Reload:** `Page.reload` / `Page.navigate` (exact URL, no typing). The point waits until `document.readyState` is `"complete"` and the wait time has passed.
- **"JavaScript click"** is a fallback method that dispatches pointer/mouse events via `Runtime.evaluate` (`isTrusted=false`).

## Design decisions (learned from bugs)

- Reloads run in a background pool and the clicker moves straight on to other points. A reloading point, and every point on the same page, is skipped until the page is ready.
- **"All at the same time":** different pages run in parallel, but points on the *same* page (same tab id or window root) are clicked one after another within a round. Interleaving presses on one page made clicks land on the page background, and sent one site back to its main page.
- In "together" mode, CPS is per point (each point is clicked CPS times a second). In order, CPS is the total for all points.
- Only one URL typing or reload runs at a time per page (per-page lock), with at most one reload per page per round.

## Testing

The UI can't be tested without Windows. The browser/CDP logic was tested against headless Chromium on Linux: the "browser connection" through "UI" sections of the file were exec'd with `user32`/`winmm` stubbed by `MagicMock`, against test pages that count clicks and log mouse events.
