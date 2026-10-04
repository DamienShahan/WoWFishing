"""Visible WoW windows and checked foreground keyboard input (Windows only)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class GameWindow:
    handle: int
    pid: int
    title: str

    @property
    def label(self):
        return f"{self.title}  ·  {self.pid} / {self.handle}"


def list_windows():
    import win32gui
    import win32process
    result = []

    def collect(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if win32gui.IsWindowVisible(hwnd) and "world of warcraft" in title.lower():
            result.append(GameWindow(hwnd, win32process.GetWindowThreadProcessId(hwnd)[1], title))
    win32gui.EnumWindows(collect, None)
    return sorted(result, key=lambda item: (item.title, item.pid, item.handle))


class Keyboard:
    def __init__(self, window):
        self.window = window

    def press(self, key, cancelled, wait):
        import pyautogui
        import win32con
        import win32gui
        import win32process
        if cancelled():
            return False
        hwnd = self.window.handle
        if (not win32gui.IsWindow(hwnd)
                or win32process.GetWindowThreadProcessId(hwnd)[1] != self.window.pid
                or win32gui.GetWindowText(hwnd) != self.window.title):
            raise RuntimeError("The selected game window closed or changed. Refresh windows and select it again.")
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        if win32gui.GetForegroundWindow() != hwnd:
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception as exc:
                raise RuntimeError("Could not focus WoW. Bring the game forward and try again.") from exc
            if wait(.15):
                return False
        if cancelled():
            return False
        if win32gui.GetForegroundWindow() != hwnd:
            raise RuntimeError("WoW is not in the foreground; no key was sent.")
        # Keep PyAutoGUI's corner fail-safe enabled. No held modifier keys.
        pyautogui.press(key, _pause=False)
        return True
