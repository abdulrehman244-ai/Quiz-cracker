"""
╔══════════════════════════════════════════════════════════════════╗
║  Quiz Cracker — Mouse-Move MCQ Assistant Overlay                ║
║  Wiggle your mouse → Auto-captures screen → Subtle corner popup ║
║  Supports ALL major AI API keys (Gemini, OpenAI, Claude, Groq,  ║
║  OpenRouter, Mistral, Grok, NVIDIA, Together, Ollama & more!)   ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import io
import json
import time
import threading
import webbrowser
import ctypes
from ctypes import wintypes
from pathlib import Path
from datetime import datetime
from collections import deque

import tkinter as tk
from tkinter import ttk

import mss
from PIL import Image, ImageGrab

from ai_providers import (
    PROVIDERS,
    PROVIDER_ORDER,
    clean_api_key,
    detect_provider_from_key,
    parse_mcq_response,
    solve_mcq_with_provider,
    test_provider_key,
)


# ═══════════════════════════════════════════════════════════════
# Windows DPI Awareness (must be set before creating Tk root)
# ═══════════════════════════════════════════════════════════════

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# Constants & Configuration
# ═══════════════════════════════════════════════════════════════

APP_NAME = "Quiz Cracker"
MUTEX_NAME = "Local\\QuizCrackerOverlaySingleInstance_v2"
WAKEUP_EVENT_NAME = "Local\\QuizCrackerOverlayWakeup_v2"
CONFIG_PATH = Path.home() / ".quiz_cracker_config.json"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICON_PATH = ASSETS_DIR / "quiz_cracker.ico"

MAX_HISTORY = 10

SENSITIVITY_PRESETS = {
    "high":   {"min_swing": 45, "required_flips": 3, "window_sec": 1.0},
    "medium": {"min_swing": 65, "required_flips": 3, "window_sec": 0.9},
    "low":    {"min_swing": 95, "required_flips": 4, "window_sec": 0.9},
}

DEFAULT_CONFIG = {
    "provider": "auto",
    "api_key": "",
    "provider_keys": {},
    "model": "",
    "custom_base_url": "http://localhost:11434/v1",
    "wiggle_enabled": True,
    "corner_trigger_enabled": False,
    "sensitivity": "medium",
    "corner": "bottom-right",
    "auto_collapse_sec": 10,
    "popup_opacity": 0.65,
    "idle_style": "dot",   # "dot" (tiny subtle dot) | "pill" (small muted pill)
}

# Subtle low-glare dark theme palette
COLORS = {
    "bg": "#10141a",
    "dialog_bg": "#0d1117",
    "surface": "#161b22",
    "surface_hover": "#21262d",
    "border": "#242b35",
    "border_dialog": "#30363d",
    "border_scan": "#3b6ea5",
    "border_ok": "#265936",
    "border_err": "#7d2b2b",
    "text": "#cfd8e3",
    "text_bright": "#f0f6fc",
    "text_muted": "#7d8590",
    "text_dim": "#586069",
    "green": "#4ea864",
    "green_bg": "#13261b",
    "green_btn": "#238636",
    "green_btn_hover": "#2ea043",
    "blue": "#58a6ff",
    "amber": "#c69026",
    "amber_bg": "#292011",
    "red": "#d9534f",
    "red_bg": "#2e1518",
}


class ConfigManager:
    """Persistent JSON configuration storage with multi-provider key support."""

    @staticmethod
    def load() -> dict:
        cfg = dict(DEFAULT_CONFIG)
        cfg["provider_keys"] = {}
        try:
            if CONFIG_PATH.exists():
                saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    cfg.update(saved)
                    if not isinstance(cfg.get("provider_keys"), dict):
                        cfg["provider_keys"] = {}
        except Exception:
            pass
        return cfg

    @staticmethod
    def save(data: dict) -> None:
        cfg = ConfigManager.load()
        cfg.update(data)
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    @staticmethod
    def get(key: str, default=None):
        return ConfigManager.load().get(key, DEFAULT_CONFIG.get(key, default))

    @staticmethod
    def has_valid_setup() -> bool:
        cfg = ConfigManager.load()
        if cfg.get("provider") == "custom" and cfg.get("custom_base_url", "").strip():
            return True
        if clean_api_key(cfg.get("api_key", "")):
            return True
        for k in cfg.get("provider_keys", {}).values():
            if clean_api_key(k):
                return True
        return False


# ═══════════════════════════════════════════════════════════════
# Win32 Helpers (Global Cursor, Work Area, Non-Focus Overlay)
# ═══════════════════════════════════════════════════════════════

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def get_cursor_pos() -> tuple:
    """Get global mouse cursor position (x, y) across all monitors."""
    pt = POINT()
    if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
        return int(pt.x), int(pt.y)
    return 0, 0


def get_work_area() -> tuple:
    """Return primary monitor work area (left, top, right, bottom) excluding taskbar."""
    rect = RECT()
    SPI_GETWORKAREA = 0x0030
    if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    return 0, 0, 1920, 1040


def _open_mss():
    """Return an mss screenshot context manager compatible with mss 9.x and 10.x."""
    factory = getattr(mss, "MSS", mss.mss)
    return factory()


def get_screen_bounds_at(x: int, y: int) -> tuple:
    """Return (left, top, right, bottom) of the monitor containing (x, y)."""
    try:
        with _open_mss() as sct:
            for mon in sct.monitors[1:]:
                if (mon["left"] <= x < mon["left"] + mon["width"] and
                        mon["top"] <= y < mon["top"] + mon["height"]):
                    return (
                        mon["left"],
                        mon["top"],
                        mon["left"] + mon["width"],
                        mon["top"] + mon["height"],
                    )
            m = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            return m["left"], m["top"], m["left"] + m["width"], m["top"] + m["height"]
    except Exception:
        return get_work_area()


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.SetEvent.argtypes = [wintypes.HANDLE]
_kernel32.SetEvent.restype = wintypes.BOOL
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetParent.argtypes = [wintypes.HWND]
_user32.GetParent.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL


def apply_win32_overlay_style(tk_window: tk.Tk):
    """
    Configure native Windows overlay flags:
      - WS_EX_TOOLWINDOW: hides from taskbar & Alt+Tab
      - WS_EX_NOACTIVATE: popping up NEVER steals focus from active app
      - DWMWA_WINDOW_CORNER_PREFERENCE: smooth Windows 11 rounded corners
    """
    try:
        tk_window.update_idletasks()
        hwnd = _user32.GetParent(tk_window.winfo_id()) or tk_window.winfo_id()

        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_APPWINDOW = 0x00040000

        style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
        _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

        # Windows 11 rounded corners (safe no-op on Windows 10)
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(DWMWCP_ROUND),
            ctypes.sizeof(DWMWCP_ROUND),
        )
    except Exception:
        pass


def make_normal_activatable_dialog(win: tk.Toplevel):
    """Ensure Settings dialog is a normal, focusable taskbar window."""
    try:
        win.update_idletasks()
        hwnd = _user32.GetParent(win.winfo_id()) or win.winfo_id()

        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_APPWINDOW = 0x00040000

        style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_APPWINDOW) & ~WS_EX_NOACTIVATE & ~WS_EX_TOOLWINDOW
        _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        win.attributes("-topmost", True)
        win.lift()
        _user32.SetForegroundWindow(hwnd)
        win.after(150, lambda: win.winfo_exists() and win.attributes("-topmost", False))
    except Exception:
        pass


def read_win32_clipboard_text() -> str:
    """Reliable Windows clipboard reader fallback."""
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(0):
        return ""
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        kernel32.GlobalLock.restype = ctypes.c_void_p
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def acquire_single_instance():
    """
    Return (mutex_handle, wakeup_event_handle) if this is the first instance.
    If another instance is already running, signal its wakeup event and return (None, None).
    """
    try:
        ERROR_ALREADY_EXISTS = 183
        mutex = _kernel32.CreateMutexW(None, False, MUTEX_NAME)
        already = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        wakeup_evt = _kernel32.CreateEventW(None, False, False, WAKEUP_EVENT_NAME)

        if already:
            if wakeup_evt:
                _kernel32.SetEvent(wakeup_evt)
                _kernel32.CloseHandle(wakeup_evt)
            if mutex:
                _kernel32.CloseHandle(mutex)
            return None, None
        return mutex, wakeup_evt
    except Exception:
        return True, None


def poll_wakeup_event(wakeup_evt) -> bool:
    """Non-blocking check if a second launch requested us to open Settings."""
    if not wakeup_evt or wakeup_evt is True:
        return False
    try:
        return _kernel32.WaitForSingleObject(wakeup_evt, 0) == 0
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# Mouse Movement Gesture Detector (Zero Clicks!)
# ═══════════════════════════════════════════════════════════════

class MouseGestureWatcher:
    """
    Detects mouse-only gestures without any clicks or keyboard hooks:
      1. Mouse Wiggle / Shake ("move mouse here and there"):
         Rapid left-right (or up-down) direction reversals within ~0.9s.
      2. Optional Top-Right Corner Dwell:
         Holding cursor in the top-right corner for 0.65s.
    """

    def __init__(self):
        self.enabled = True
        self.wiggle_enabled = True
        self.corner_enabled = False
        self.sensitivity = "medium"
        self.cooldown_sec = 3.2

        self._cooldown_until = 0.0
        self._reset_tracking()

    def apply_config(self, cfg: dict):
        self.wiggle_enabled = bool(cfg.get("wiggle_enabled", True))
        self.corner_enabled = bool(cfg.get("corner_trigger_enabled", False))
        sens = cfg.get("sensitivity", "medium")
        self.sensitivity = sens if sens in SENSITIVITY_PRESETS else "medium"
        self._reset_tracking()

    def set_cooldown(self, seconds: float = None):
        wait = self.cooldown_sec if seconds is None else seconds
        self._cooldown_until = time.monotonic() + wait
        self._reset_tracking()

    def _reset_tracking(self):
        self._ext_x = None
        self._dir_x = 0
        self._flips_x = deque()

        self._ext_y = None
        self._dir_y = 0
        self._flips_y = deque()

        self._corner_enter_time = None

    def feed_position(self, x: int, y: int, now: float, screen_bounds: tuple = None):
        """
        Pure, testable gesture step. Returns gesture name ('wiggle' / 'corner')
        when triggered, otherwise None.
        """
        if not self.enabled or now < self._cooldown_until:
            return None

        # ── 1. Mouse Wiggle / Shake detection ──
        if self.wiggle_enabled:
            preset = SENSITIVITY_PRESETS.get(self.sensitivity, SENSITIVITY_PRESETS["medium"])
            min_swing = preset["min_swing"]
            req_flips = preset["required_flips"]
            window = preset["window_sec"]

            # Track X oscillation
            if self._ext_x is None:
                self._ext_x = x
            else:
                dx = x - self._ext_x
                if self._dir_x == 0:
                    if abs(dx) >= min_swing:
                        self._dir_x = 1 if dx > 0 else -1
                        self._ext_x = x
                elif self._dir_x == 1:
                    if x > self._ext_x:
                        self._ext_x = x
                    elif self._ext_x - x >= min_swing:
                        self._dir_x = -1
                        self._ext_x = x
                        self._flips_x.append(now)
                elif self._dir_x == -1:
                    if x < self._ext_x:
                        self._ext_x = x
                    elif x - self._ext_x >= min_swing:
                        self._dir_x = 1
                        self._ext_x = x
                        self._flips_x.append(now)

            # Track Y oscillation
            if self._ext_y is None:
                self._ext_y = y
            else:
                dy = y - self._ext_y
                if self._dir_y == 0:
                    if abs(dy) >= min_swing:
                        self._dir_y = 1 if dy > 0 else -1
                        self._ext_y = y
                elif self._dir_y == 1:
                    if y > self._ext_y:
                        self._ext_y = y
                    elif self._ext_y - y >= min_swing:
                        self._dir_y = -1
                        self._ext_y = y
                        self._flips_y.append(now)
                elif self._dir_y == -1:
                    if y < self._ext_y:
                        self._ext_y = y
                    elif y - self._ext_y >= min_swing:
                        self._dir_y = 1
                        self._ext_y = y
                        self._flips_y.append(now)

            cutoff = now - window
            while self._flips_x and self._flips_x[0] < cutoff:
                self._flips_x.popleft()
            while self._flips_y and self._flips_y[0] < cutoff:
                self._flips_y.popleft()

            if len(self._flips_x) >= req_flips or len(self._flips_y) >= req_flips:
                self._cooldown_until = now + self.cooldown_sec
                self._reset_tracking()
                return "wiggle"

        # ── 2. Optional Top-Right Corner Dwell ──
        if self.corner_enabled and screen_bounds is not None:
            left, top, right, bottom = screen_bounds
            in_corner = (x >= right - 14) and (y <= top + 14)
            if in_corner:
                if self._corner_enter_time is None:
                    self._corner_enter_time = now
                elif now - self._corner_enter_time >= 0.65:
                    self._cooldown_until = now + self.cooldown_sec
                    self._reset_tracking()
                    return "corner"
            else:
                self._corner_enter_time = None

        return None


# ═══════════════════════════════════════════════════════════════
# Fast Screen Capture Helpers
# ═══════════════════════════════════════════════════════════════

def encode_pil_to_jpeg(img: Image.Image, max_width: int = 1920, quality: int = 88) -> bytes:
    """Resize huge 4K screens gently and encode as sharp, compact JPEG."""
    if img.width > max_width:
        ratio = max_width / float(img.width)
        new_size = (max_width, max(1, int(img.height * ratio)))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def capture_monitor_at_cursor() -> bytes:
    """Capture the full display where the mouse cursor currently is."""
    cx, cy = get_cursor_pos()
    target = None
    try:
        with _open_mss() as sct:
            target = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            for mon in sct.monitors[1:]:
                if (mon["left"] <= cx < mon["left"] + mon["width"] and
                        mon["top"] <= cy < mon["top"] + mon["height"]):
                    target = mon
                    break
            shot = sct.grab(target)
            img = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
            return encode_pil_to_jpeg(img)
    except Exception:
        bbox = None
        if target:
            bbox = (
                target["left"],
                target["top"],
                target["left"] + target["width"],
                target["top"] + target["height"],
            )
        img = ImageGrab.grab(bbox=bbox, all_screens=True).convert("RGB")
        return encode_pil_to_jpeg(img)


def capture_region(x: int, y: int, w: int, h: int) -> bytes:
    """Capture a specific rectangular region in global screen coordinates."""
    try:
        with _open_mss() as sct:
            shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
            img = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
            return encode_pil_to_jpeg(img)
    except Exception:
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
        return encode_pil_to_jpeg(img)


# ═══════════════════════════════════════════════════════════════
# Optional Manual Region Selector Overlay
# ═══════════════════════════════════════════════════════════════

class RegionSelector(tk.Toplevel):
    """Full-screen translucent selector when user picks 🎯 manual region capture."""

    def __init__(self, master, on_selected, on_cancelled):
        super().__init__(master)
        self.on_selected = on_selected
        self.on_cancelled = on_cancelled

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.28)
        self.configure(bg="#000000")

        with _open_mss() as sct:
            v = sct.monitors[0]
            self.vx, self.vy, self.vw, self.vh = v["left"], v["top"], v["width"], v["height"]

        self.geometry(f"{self.vw}x{self.vh}+{self.vx}+{self.vy}")

        self.canvas = tk.Canvas(
            self, bg="#000000", highlightthickness=0, cursor="crosshair"
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.hint_id = self.canvas.create_text(
            self.vw // 2,
            self.vh // 2,
            text="Drag to select the question  •  Right-click or Esc to cancel",
            fill="#ffffff",
            font=("Segoe UI", 14, "bold"),
        )

        self.start_x = None
        self.start_y = None
        self.rect_id = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonPress-3>", self._cancel)
        self.bind("<Escape>", self._cancel)
        self.focus_force()

    def _on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.hint_id:
            self.canvas.delete(self.hint_id)
            self.hint_id = None
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#58a6ff", width=2, fill="#1f6feb", stipple="gray25",
        )

    def _on_drag(self, event):
        if self.rect_id is not None:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def _on_release(self, event):
        if self.start_x is None:
            self._cancel()
            return
        x1 = min(self.start_x, event.x) + self.vx
        y1 = min(self.start_y, event.y) + self.vy
        w = abs(event.x - self.start_x)
        h = abs(event.y - self.start_y)
        self.destroy()
        if w > 20 and h > 20:
            self.on_selected((x1, y1, w, h))
        else:
            self.on_cancelled()

    def _cancel(self, event=None):
        self.destroy()
        self.on_cancelled()


# ═══════════════════════════════════════════════════════════════
# Universal API Key & Settings Dialog (All Providers + Auto-Detect!)
# ═══════════════════════════════════════════════════════════════

class SettingsDialog(tk.Toplevel):
    """
    Universal AI Provider & Settings window:
      - Paste ANY AI API key (Gemini, OpenAI, Claude, Groq, OpenRouter, Mistral,
        xAI Grok, NVIDIA NIM, Together, Fireworks, SambaNova, HuggingFace, Ollama)
      - Auto-detects provider from key prefix & discovers working models live
      - Saves keys per provider so automatic backup failover works seamlessly
      - Auto-sizes cleanly for any Windows DPI scaling (100%-200%)
    """

    def __init__(self, master, on_saved):
        super().__init__(master)
        self.on_saved = on_saved
        self.title(f"{APP_NAME} — Universal AI Setup & Settings")
        self.configure(bg=COLORS["dialog_bg"])
        self.resizable(True, True)

        if ICON_PATH.exists():
            try:
                self.iconbitmap(str(ICON_PATH))
            except Exception:
                pass

        self.cfg = ConfigManager.load()
        self.provider_keys = dict(self.cfg.get("provider_keys", {}))
        self._suppress_trace = False

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Dark.TCombobox",
            fieldbackground=COLORS["surface"],
            background=COLORS["surface_hover"],
            foreground=COLORS["text_bright"],
            bordercolor=COLORS["border_dialog"],
            arrowcolor=COLORS["text_muted"],
            padding=4,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", COLORS["surface"])],
            foreground=[("readonly", COLORS["text_bright"])],
            selectbackground=[("readonly", COLORS["surface"])],
            selectforeground=[("readonly", COLORS["text_bright"])],
        )

        outer = tk.Frame(self, bg=COLORS["dialog_bg"])
        outer.pack(fill=tk.BOTH, expand=True, padx=22, pady=16)

        # ── Header ──
        header_row = tk.Frame(outer, bg=COLORS["dialog_bg"])
        header_row.pack(fill=tk.X, pady=(0, 10))
        tk.Label(
            header_row, text="🧠  Quiz Cracker — Universal AI Setup",
            bg=COLORS["dialog_bg"], fg=COLORS["text_bright"],
            font=("Segoe UI", 13, "bold"), anchor="w",
        ).pack(side=tk.LEFT)

        # ── SECTION 1: UNIVERSAL PROVIDER & API KEY CARD ──
        api_card = tk.Frame(
            outer, bg=COLORS["surface"],
            highlightthickness=1, highlightbackground=COLORS["border_dialog"],
            padx=14, pady=12,
        )
        api_card.pack(fill=tk.X, pady=(0, 12))

        top_api = tk.Frame(api_card, bg=COLORS["surface"])
        top_api.pack(fill=tk.X, pady=(0, 6))
        tk.Label(
            top_api, text="1. AI Provider & API Key (Works with ALL major models)",
            bg=COLORS["surface"], fg=COLORS["text_bright"],
            font=("Segoe UI", 10, "bold"), anchor="w",
        ).pack(side=tk.LEFT)

        self.get_key_btn = tk.Button(
            top_api, text="🌐 Get API Key", command=self._open_api_page,
            bg="#1f3a5f", fg="#8ec5ff",
            activebackground="#294e80", activeforeground="#ffffff",
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 8, "bold"),
            padx=9, pady=3,
        )
        self.get_key_btn.pack(side=tk.RIGHT)

        # Provider selector row
        prov_row = tk.Frame(api_card, bg=COLORS["surface"])
        prov_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            prov_row, text="Provider:", bg=COLORS["surface"], fg=COLORS["text_muted"],
            font=("Segoe UI", 9), width=9, anchor="w",
        ).pack(side=tk.LEFT)

        self.provider_label_to_id = {PROVIDERS[pid]["name"]: pid for pid in PROVIDER_ORDER}
        self.provider_id_to_label = {pid: PROVIDERS[pid]["name"] for pid in PROVIDER_ORDER}

        cur_pid = self.cfg.get("provider", "auto")
        if cur_pid not in PROVIDERS:
            cur_pid = "auto"

        self.provider_var = tk.StringVar(value=self.provider_id_to_label[cur_pid])
        self.provider_combo = ttk.Combobox(
            prov_row,
            textvariable=self.provider_var,
            values=[self.provider_id_to_label[pid] for pid in PROVIDER_ORDER],
            state="readonly",
            style="Dark.TCombobox",
        )
        self.provider_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.provider_combo.bind("<<ComboboxSelected>>", self._on_provider_changed)

        # API key input
        key_lbl_row = tk.Frame(api_card, bg=COLORS["surface"])
        key_lbl_row.pack(fill=tk.X, pady=(0, 4))
        tk.Label(
            key_lbl_row,
            text="Paste ANY key (Gemini AIza..., Groq gsk_..., OpenRouter sk-or-..., OpenAI sk-..., Claude sk-ant-..., etc.):",
            bg=COLORS["surface"], fg=COLORS["text_muted"],
            font=("Segoe UI", 8), anchor="w",
        ).pack(side=tk.LEFT)

        initial_key = self.cfg.get("api_key", "")
        if not initial_key and cur_pid in self.provider_keys:
            initial_key = self.provider_keys[cur_pid]

        self.key_var = tk.StringVar(value=initial_key)
        self._showing_key = not bool(initial_key)
        self.key_entry = tk.Entry(
            api_card,
            textvariable=self.key_var,
            show="" if self._showing_key else "•",
            bg=COLORS["dialog_bg"], fg=COLORS["text_bright"],
            insertbackground=COLORS["text_bright"],
            relief=tk.FLAT, highlightthickness=1,
            highlightbackground=COLORS["border_dialog"], highlightcolor=COLORS["blue"],
            font=("Consolas", 10),
        )
        self.key_entry.pack(fill=tk.X, ipady=6, pady=(0, 8))
        self.key_var.trace_add("write", self._on_key_edited)

        entry_menu = tk.Menu(self, tearoff=0, bg=COLORS["surface"], fg=COLORS["text_bright"])
        entry_menu.add_command(label="Paste", command=self._paste_key)
        entry_menu.add_command(label="Clear", command=self._clear_key)
        self.key_entry.bind("<Button-3>", lambda e: entry_menu.tk_popup(e.x_root, e.y_root))
        self.key_entry.bind("<Return>", lambda e: self._save())

        # Custom Base URL row (only shown for Custom / Local Ollama)
        self.custom_url_row = tk.Frame(api_card, bg=COLORS["surface"])
        tk.Label(
            self.custom_url_row, text="Base URL:", bg=COLORS["surface"], fg=COLORS["text_muted"],
            font=("Segoe UI", 9), width=9, anchor="w",
        ).pack(side=tk.LEFT)
        self.custom_url_var = tk.StringVar(
            value=self.cfg.get("custom_base_url", "http://localhost:11434/v1")
        )
        self.custom_url_entry = tk.Entry(
            self.custom_url_row,
            textvariable=self.custom_url_var,
            bg=COLORS["dialog_bg"], fg=COLORS["text_bright"],
            insertbackground=COLORS["text_bright"],
            relief=tk.FLAT, highlightthickness=1,
            highlightbackground=COLORS["border_dialog"], highlightcolor=COLORS["blue"],
            font=("Consolas", 9),
        )
        self.custom_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)

        # Model row (dynamically populated per provider + live discovery!)
        model_row = tk.Frame(api_card, bg=COLORS["surface"])
        model_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            model_row, text="Model:", bg=COLORS["surface"], fg=COLORS["text_muted"],
            font=("Segoe UI", 9), width=9, anchor="w",
        ).pack(side=tk.LEFT)
        self.model_var = tk.StringVar(value=self.cfg.get("model", ""))
        self.model_combo = ttk.Combobox(
            model_row,
            textvariable=self.model_var,
            values=self._models_for_provider(cur_pid),
            style="Dark.TCombobox",
        )
        self.model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Action buttons row
        btn_row = tk.Frame(api_card, bg=COLORS["surface"])
        btn_row.pack(fill=tk.X)

        def make_action_btn(parent, text, cmd, fg=COLORS["text_bright"], bg=COLORS["surface_hover"]):
            return tk.Button(
                parent, text=text, command=cmd,
                bg=bg, fg=fg,
                activebackground=COLORS["border_dialog"], activeforeground="#ffffff",
                relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 9),
                padx=10, pady=4,
            )

        self.paste_btn = make_action_btn(btn_row, "📋 Paste", self._paste_key)
        self.paste_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.test_btn = make_action_btn(btn_row, "🔍 Test & Detect", self._test_key, fg=COLORS["blue"])
        self.test_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.show_btn = make_action_btn(
            btn_row,
            "🔒 Hide" if self._showing_key else "👁 Show",
            self._toggle_key,
            fg=COLORS["text_muted"],
        )
        self.show_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.clear_btn = make_action_btn(btn_row, "✕ Clear", self._clear_key, fg=COLORS["text_muted"])
        self.clear_btn.pack(side=tk.LEFT)

        # Status feedback line
        saved_count = sum(1 for v in self.provider_keys.values() if clean_api_key(v))
        if initial_key:
            extra = f"  •  {saved_count} saved key(s) for auto-failover" if saved_count > 1 else ""
            init_msg = f"✓ Ready ({PROVIDERS[cur_pid]['name']}){extra}"
            init_fg = COLORS["green"]
        else:
            init_msg = "Paste any AI API key above and click 'Test & Detect' — model is configured automatically."
            init_fg = COLORS["text_muted"]

        self.status_lbl = tk.Label(
            api_card, text=init_msg,
            bg=COLORS["surface"], fg=init_fg,
            font=("Segoe UI", 8), anchor="w", justify=tk.LEFT, wraplength=480,
        )
        self.status_lbl.pack(fill=tk.X, pady=(8, 0))

        # Show custom URL row if custom selected
        self._sync_custom_url_visibility()

        # ── SECTION 2: TRIGGERS & VISIBILITY ──
        tk.Label(
            outer, text="2. Mouse Trigger & Subtle Popup Appearance",
            bg=COLORS["dialog_bg"], fg=COLORS["text_bright"],
            font=("Segoe UI", 10, "bold"), anchor="w",
        ).pack(fill=tk.X, pady=(0, 6))

        self.wiggle_var = tk.BooleanVar(value=bool(self.cfg.get("wiggle_enabled", True)))
        tk.Checkbutton(
            outer, text="Mouse Wiggle trigger  (move mouse left-right to auto-solve)",
            variable=self.wiggle_var,
            bg=COLORS["dialog_bg"], fg=COLORS["text"],
            selectcolor=COLORS["surface"],
            activebackground=COLORS["dialog_bg"], activeforeground=COLORS["text_bright"],
            font=("Segoe UI", 9), anchor="w", cursor="hand2",
        ).pack(fill=tk.X, pady=(0, 2))

        self.corner_trig_var = tk.BooleanVar(value=bool(self.cfg.get("corner_trigger_enabled", False)))
        tk.Checkbutton(
            outer, text="Top-Right corner hover trigger  (hold cursor in corner 0.6s)",
            variable=self.corner_trig_var,
            bg=COLORS["dialog_bg"], fg=COLORS["text"],
            selectcolor=COLORS["surface"],
            activebackground=COLORS["dialog_bg"], activeforeground=COLORS["text_bright"],
            font=("Segoe UI", 9), anchor="w", cursor="hand2",
        ).pack(fill=tk.X, pady=(0, 8))

        # Compact 2-column appearance grid
        grid = tk.Frame(outer, bg=COLORS["dialog_bg"])
        grid.pack(fill=tk.X)
        grid.columnconfigure(1, weight=1)

        def add_row(row_idx, label, widget):
            tk.Label(
                grid, text=label, bg=COLORS["dialog_bg"], fg=COLORS["text_muted"],
                font=("Segoe UI", 9), anchor="w",
            ).grid(row=row_idx, column=0, sticky="w", pady=4, padx=(0, 14))
            widget.grid(row=row_idx, column=1, sticky="ew", pady=4)

        self.opacity_map = {
            "Very Subtle  (45%)": 0.45,
            "Subtle  (65% — recommended)": 0.65,
            "Medium  (78%)": 0.78,
            "Clear  (90%)": 0.90,
        }
        cur_op = float(self.cfg.get("popup_opacity", 0.65))
        best_op_label = min(self.opacity_map.keys(), key=lambda k: abs(self.opacity_map[k] - cur_op))
        self.opacity_var = tk.StringVar(value=best_op_label)
        add_row(0, "Popup Visibility:", ttk.Combobox(
            grid, textvariable=self.opacity_var, values=list(self.opacity_map.keys()),
            state="readonly", style="Dark.TCombobox",
        ))

        self.idle_map = {
            "Tiny subtle dot  (least visible)": "dot",
            "Small muted pill": "pill",
        }
        inv_idle = {v: k for k, v in self.idle_map.items()}
        self.idle_var = tk.StringVar(value=inv_idle.get(self.cfg.get("idle_style", "dot"), "Tiny subtle dot  (least visible)"))
        add_row(1, "Idle Corner Icon:", ttk.Combobox(
            grid, textvariable=self.idle_var, values=list(self.idle_map.keys()),
            state="readonly", style="Dark.TCombobox",
        ))

        self.sens_map = {
            "High  (easy small wiggle)": "high",
            "Medium  (balanced — recommended)": "medium",
            "Low  (stronger shake only)": "low",
        }
        inv_sens = {v: k for k, v in self.sens_map.items()}
        self.sens_var = tk.StringVar(value=inv_sens.get(self.cfg.get("sensitivity", "medium")))
        add_row(2, "Wiggle Sensitivity:", ttk.Combobox(
            grid, textvariable=self.sens_var, values=list(self.sens_map.keys()),
            state="readonly", style="Dark.TCombobox",
        ))

        self.corner_map = {
            "Bottom-Right": "bottom-right",
            "Bottom-Left": "bottom-left",
            "Top-Right": "top-right",
            "Top-Left": "top-left",
        }
        inv_corner = {v: k for k, v in self.corner_map.items()}
        self.corner_var = tk.StringVar(value=inv_corner.get(self.cfg.get("corner", "bottom-right")))
        add_row(3, "Popup Corner:", ttk.Combobox(
            grid, textvariable=self.corner_var, values=list(self.corner_map.keys()),
            state="readonly", style="Dark.TCombobox",
        ))

        self.collapse_map = {
            "6 seconds": 6,
            "10 seconds  (recommended)": 10,
            "15 seconds": 15,
            "Never auto-hide": 0,
        }
        inv_col = {v: k for k, v in self.collapse_map.items()}
        cur_col = int(self.cfg.get("auto_collapse_sec", 10))
        best_col_label = min(self.collapse_map.keys(), key=lambda k: abs(self.collapse_map[k] - cur_col))
        self.collapse_var = tk.StringVar(value=inv_col.get(cur_col, best_col_label))
        add_row(4, "Auto-Hide Answer:", ttk.Combobox(
            grid, textvariable=self.collapse_var, values=list(self.collapse_map.keys()),
            state="readonly", style="Dark.TCombobox",
        ))

        # ── Footer Buttons ──
        footer = tk.Frame(outer, bg=COLORS["dialog_bg"])
        footer.pack(fill=tk.X, pady=(14, 0))

        cancel_btn = tk.Button(
            footer, text="Cancel", command=self.destroy,
            bg=COLORS["surface_hover"], fg=COLORS["text"],
            activebackground=COLORS["border_dialog"], activeforeground="#ffffff",
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 10),
            padx=16, pady=8,
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

        save_btn = tk.Button(
            footer, text="💾  Save & Close", command=self._save,
            bg=COLORS["green_btn"], fg="#ffffff",
            activebackground=COLORS["green_btn_hover"], activeforeground="#ffffff",
            relief=tk.FLAT, cursor="hand2", font=("Segoe UI", 10, "bold"),
            padx=20, pady=8,
        )
        save_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        # Auto-fit window size safely for ANY Windows DPI scaling!
        self._fit_window()

        make_normal_activatable_dialog(self)
        self.lift()
        self.focus_force()
        self.key_entry.focus_set()

    def _current_provider_id(self) -> str:
        return self.provider_label_to_id.get(self.provider_var.get(), "auto")

    def _models_for_provider(self, pid: str) -> list:
        if pid == "auto":
            detected = detect_provider_from_key(self.key_var.get()) if hasattr(self, "key_var") else ""
            if detected and detected in PROVIDERS:
                return [""] + list(PROVIDERS[detected]["default_models"])
            return [""]
        return list(PROVIDERS.get(pid, {}).get("default_models", []))

    def _fit_window(self):
        self.update_idletasks()
        req_w = max(540, self.winfo_reqwidth() + 18)
        req_h = self.winfo_reqheight() + 14
        l, t, r, b = get_work_area()
        w = min(req_w, max(460, (r - l) - 40))
        h = min(req_h, max(440, (b - t) - 40))
        cx = l + (r - l - w) // 2
        cy = t + (b - t - h) // 2
        self.geometry(f"{w}x{h}+{cx}+{cy}")
        self.minsize(480, min(req_h, (b - t) - 40))

    def _sync_custom_url_visibility(self):
        pid = self._current_provider_id()
        if pid == "custom":
            self.custom_url_row.pack(fill=tk.X, pady=(0, 8), after=self.key_entry)
        else:
            self.custom_url_row.pack_forget()

    def _set_provider_ui(self, pid: str, models_list: list = None, pick_model: str = None):
        if pid not in PROVIDERS:
            return
        self.provider_var.set(self.provider_id_to_label[pid])
        models = models_list if models_list else self._models_for_provider(pid)
        self.model_combo.configure(values=models)
        if pick_model is not None:
            self.model_var.set(pick_model)
        elif models:
            self.model_var.set(models[0])
        else:
            self.model_var.set("")
        self._sync_custom_url_visibility()

    def _on_provider_changed(self, event=None):
        pid = self._current_provider_id()
        self._sync_custom_url_visibility()
        models = self._models_for_provider(pid)
        self.model_combo.configure(values=models)
        if models and self.model_var.get() not in models:
            self.model_var.set(models[0])

        # Load saved key for this provider if available
        if pid != "auto" and pid in self.provider_keys and self.provider_keys[pid]:
            self._suppress_trace = True
            self.key_var.set(self.provider_keys[pid])
            self._suppress_trace = False
            self.status_lbl.configure(
                text=f"Loaded saved key for {PROVIDERS[pid]['name']}.",
                fg=COLORS["green"],
            )
        elif pid == "custom":
            self.status_lbl.configure(
                text="Custom / Local mode: enter Base URL (e.g. http://localhost:11434/v1 for Ollama). Key optional.",
                fg=COLORS["blue"],
            )
        else:
            self.status_lbl.configure(
                text=f"Selected {PROVIDERS[pid]['name']}. Paste your key or click 'Get API Key'.",
                fg=COLORS["text_muted"],
            )
        self._fit_window()

    def _on_key_edited(self, *args):
        if self._suppress_trace:
            return
        key = clean_api_key(self.key_var.get())
        detected = detect_provider_from_key(key)
        cur_pid = self._current_provider_id()
        if detected and cur_pid != "custom" and detected != cur_pid:
            # Automatically switch provider & vision models to match pasted key!
            self._set_provider_ui(detected)
            self.status_lbl.configure(
                text=f"✨ Auto-detected: {PROVIDERS[detected]['name']} — click 'Test & Detect' or 'Save & Close'.",
                fg=COLORS["blue"],
            )

    def _open_api_page(self):
        pid = self._current_provider_id()
        url = PROVIDERS.get(pid, PROVIDERS["gemini"]).get("key_url", "https://aistudio.google.com/apikey")
        webbrowser.open(url)
        self.status_lbl.configure(
            text=f"🌐 Opened {url} in your browser — copy your key, then click Paste.",
            fg=COLORS["blue"],
        )

    def _toggle_key(self):
        self._showing_key = not self._showing_key
        self.key_entry.configure(show="" if self._showing_key else "•")
        self.show_btn.configure(text="🔒 Hide" if self._showing_key else "👁 Show")

    def _clear_key(self):
        self._suppress_trace = True
        self.key_var.set("")
        self._suppress_trace = False
        self.key_entry.focus_set()
        self.status_lbl.configure(text="Cleared. Paste any AI API key above.", fg=COLORS["text_muted"])

    def _paste_key(self):
        clip = ""
        try:
            clip = self.clipboard_get()
        except Exception:
            pass
        if not clip:
            clip = read_win32_clipboard_text()

        cleaned = clean_api_key(clip)
        if cleaned:
            self.key_var.set(cleaned)
            self.key_entry.icursor(tk.END)
            detected = detect_provider_from_key(cleaned)
            if detected:
                self.status_lbl.configure(
                    text=f"✨ Pasted & detected {PROVIDERS[detected]['name']} ({len(cleaned)} chars). Click 'Test & Detect' or 'Save'.",
                    fg=COLORS["green"],
                )
            else:
                self.status_lbl.configure(
                    text=f"📋 Pasted key ({len(cleaned)} chars). Click 'Test & Detect' to auto-identify provider & model.",
                    fg=COLORS["blue"],
                )
        else:
            self.status_lbl.configure(
                text="⚠ Clipboard is empty — copy your API key first.",
                fg=COLORS["amber"],
            )

    def _test_key(self):
        pid = self._current_provider_id()
        key = clean_api_key(self.key_var.get())
        self._suppress_trace = True
        self.key_var.set(key)
        self._suppress_trace = False

        if not key and pid != "custom":
            self.status_lbl.configure(text="⚠ Paste an API key first.", fg=COLORS["amber"])
            return

        self.test_btn.configure(state=tk.DISABLED)
        self.status_lbl.configure(
            text="🔄 Testing API key & discovering working vision models...",
            fg=COLORS["blue"],
        )
        model = self.model_var.get().strip()
        custom_url = self.custom_url_var.get().strip()

        def worker():
            ok, resolved_pid, working_model, models, msg = test_provider_key(
                pid, key, model, custom_url
            )
            try:
                self.after(0, lambda: self._on_test_done(ok, resolved_pid, working_model, models, msg))
            except tk.TclError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _on_test_done(self, ok: bool, resolved_pid: str, working_model: str, models: list, msg: str):
        if not self.winfo_exists():
            return
        self.test_btn.configure(state=tk.NORMAL)
        if ok:
            if resolved_pid in PROVIDERS and resolved_pid != "auto":
                self._set_provider_ui(resolved_pid, models_list=models or None, pick_model=working_model)
                key = clean_api_key(self.key_var.get())
                if key:
                    self.provider_keys[resolved_pid] = key
            self.status_lbl.configure(text=f"✅  {msg}", fg=COLORS["green"])
        else:
            if models:
                self.model_combo.configure(values=models)
            self.status_lbl.configure(text=f"❌  {msg}", fg=COLORS["red"])

    def _save(self):
        pid = self._current_provider_id()
        key = clean_api_key(self.key_var.get())

        if pid == "auto" and key:
            detected = detect_provider_from_key(key)
            if detected:
                pid = detected

        if pid != "auto" and key:
            self.provider_keys[pid] = key

        ConfigManager.save({
            "provider": pid,
            "api_key": key,
            "provider_keys": self.provider_keys,
            "model": self.model_var.get().strip(),
            "custom_base_url": self.custom_url_var.get().strip() or "http://localhost:11434/v1",
            "wiggle_enabled": self.wiggle_var.get(),
            "corner_trigger_enabled": self.corner_trig_var.get(),
            "sensitivity": self.sens_map.get(self.sens_var.get(), "medium"),
            "corner": self.corner_map.get(self.corner_var.get(), "bottom-right"),
            "auto_collapse_sec": self.collapse_map.get(self.collapse_var.get(), 10),
            "popup_opacity": self.opacity_map.get(self.opacity_var.get(), 0.65),
            "idle_style": self.idle_map.get(self.idle_var.get(), "dot"),
        })
        self.on_saved()
        self.destroy()


# ═══════════════════════════════════════════════════════════════
# Subtle Compact Corner Overlay Application
# ═══════════════════════════════════════════════════════════════

class QuizCrackerApp:
    """
    Subtle, compact, non-focus-stealing corner overlay powered by mouse movement.
    - Idle: tiny low-opacity corner dot (or small muted pill) — barely noticeable
    - Scanning: compact translucent badge
    - Answer: small soft-contrast corner card with option badge + brief explanation
    """

    def __init__(self, root: tk.Tk, wakeup_evt=None):
        self.root = root
        self.wakeup_evt = wakeup_evt

        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=COLORS["border"])

        if ICON_PATH.exists():
            try:
                self.root.iconbitmap(str(ICON_PATH))
            except Exception:
                pass

        # App state
        self.mode = "idle"     # "idle" | "scanning" | "answer" | "error"
        self.is_paused = False
        self.is_hovered = False
        self.history_visible = False
        self.history = []
        self.custom_pos = None
        self._drag_offset = None
        self._collapse_after_id = None
        self._anim_after_id = None
        self._anim_dots = 0
        self._settings_win = None

        # Gesture detector
        self.watcher = MouseGestureWatcher()

        # Build UI
        self._build_ui()
        self._build_context_menu()
        self._apply_config()

        # Native Windows non-focus-stealing & rounded corners
        apply_win32_overlay_style(self.root)

        # Initial subtle idle state anchored to corner
        self._set_mode("idle")

        # Start mouse-move polling loop (30ms = 33Hz)
        self.root.after(30, self._poll_mouse)

        # Open API Key & Settings on first run if no key yet; otherwise show brief Ready pill
        self.root.after(450, self._check_first_run)

    # ───────────────────────────────────────────────────
    # Dynamic Subtle Opacity Helper
    # ───────────────────────────────────────────────────

    def _update_alpha(self):
        popup_op = float(ConfigManager.get("popup_opacity", 0.65))
        popup_op = max(0.35, min(0.95, popup_op))

        if self.mode == "idle":
            alpha = 0.86 if self.is_hovered else 0.34
        elif self.mode == "scanning":
            alpha = max(0.45, popup_op - 0.08)
        elif self.mode == "answer":
            alpha = min(0.92, popup_op + 0.16) if (self.is_hovered or self.history_visible) else popup_op
        else:  # error
            alpha = min(0.92, popup_op + 0.15)

        try:
            self.root.attributes("-alpha", alpha)
        except Exception:
            pass

    # ───────────────────────────────────────────────────
    # UI Construction
    # ───────────────────────────────────────────────────

    def _make_mini_btn(self, parent, text, tip_cmd, hover_bg=None):
        hbg = hover_bg or COLORS["surface_hover"]
        lbl = tk.Label(
            parent, text=text,
            bg=COLORS["bg"], fg=COLORS["text_muted"],
            font=("Segoe UI", 8), padx=3, pady=1, cursor="hand2",
        )
        lbl.bind("<Enter>", lambda e: lbl.configure(bg=hbg, fg=COLORS["text_bright"]))
        lbl.bind("<Leave>", lambda e: lbl.configure(bg=COLORS["bg"], fg=COLORS["text_muted"]))
        lbl.bind("<Button-1>", lambda e: tip_cmd())
        return lbl

    def _build_ui(self):
        self.outer = tk.Frame(self.root, bg=COLORS["border"], padx=1, pady=1)
        self.outer.pack(fill=tk.BOTH, expand=True)

        self.inner = tk.Frame(self.outer, bg=COLORS["bg"], padx=6, pady=4)
        self.inner.pack(fill=tk.BOTH, expand=True)

        self.root.bind("<Enter>", self._on_enter)
        self.root.bind("<Leave>", self._on_leave)
        self.inner.bind("<ButtonPress-1>", self._start_drag)
        self.inner.bind("<B1-Motion>", self._on_drag)
        self.inner.bind("<ButtonRelease-1>", self._end_drag)
        self.root.bind("<Button-3>", self._show_context_menu)

        # ── 1. IDLE VIEW ──
        self.idle_frame = tk.Frame(self.inner, bg=COLORS["bg"])

        self.dot_lbl = tk.Label(
            self.idle_frame, text="●", bg=COLORS["bg"], fg=COLORS["green"],
            font=("Segoe UI", 7), padx=1,
        )
        self.dot_lbl.pack(side=tk.LEFT)

        self.idle_lbl = tk.Label(
            self.idle_frame, text="Wiggle",
            bg=COLORS["bg"], fg=COLORS["text_muted"],
            font=("Segoe UI", 8), padx=3,
        )

        for w in (self.dot_lbl, self.idle_lbl):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<ButtonRelease-1>", self._end_drag)

        self.idle_tools = tk.Frame(self.idle_frame, bg=COLORS["bg"])
        self._make_mini_btn(self.idle_tools, "⚡", self._trigger_fullscreen_scan).pack(side=tk.LEFT)
        self._make_mini_btn(self.idle_tools, "🎯", self._start_manual_region).pack(side=tk.LEFT)
        self._make_mini_btn(self.idle_tools, "⚙", self._open_settings).pack(side=tk.LEFT)
        self._make_mini_btn(self.idle_tools, "✕", self._quit, COLORS["border_err"]).pack(side=tk.LEFT)

        # ── 2. SCANNING VIEW ──
        self.scan_frame = tk.Frame(self.inner, bg=COLORS["bg"])
        self.scan_lbl = tk.Label(
            self.scan_frame, text="Solving...",
            bg=COLORS["bg"], fg=COLORS["blue"],
            font=("Segoe UI", 8, "bold"), padx=4, pady=1,
        )
        self.scan_lbl.pack(side=tk.LEFT)

        # ── 3. COMPACT ANSWER / ERROR CARD ──
        self.card_frame = tk.Frame(self.inner, bg=COLORS["bg"])

        body = tk.Frame(self.card_frame, bg=COLORS["bg"])
        body.pack(fill=tk.X)

        self.badge_lbl = tk.Label(
            body, text="A",
            bg=COLORS["green_bg"], fg=COLORS["green"],
            font=("Segoe UI", 11, "bold"),
            width=2, padx=4, pady=2,
            highlightthickness=1, highlightbackground=COLORS["border_ok"],
        )
        self.badge_lbl.pack(side=tk.LEFT, anchor="n", padx=(0, 8))

        text_col = tk.Frame(body, bg=COLORS["bg"])
        text_col.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.ans_title = tk.Label(
            text_col, text="", bg=COLORS["bg"], fg=COLORS["text"],
            font=("Segoe UI", 9, "bold"), anchor="w", justify=tk.LEFT,
            wraplength=175,
        )
        self.ans_title.pack(fill=tk.X)

        self.ans_reason = tk.Label(
            text_col, text="", bg=COLORS["bg"], fg=COLORS["text_muted"],
            font=("Segoe UI", 8), anchor="w", justify=tk.LEFT,
            wraplength=175,
        )
        self.ans_reason.pack(fill=tk.X, pady=(1, 0))

        for w in (self.badge_lbl, self.ans_title, self.ans_reason):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<ButtonRelease-1>", self._end_drag)

        self.card_tools = tk.Frame(self.card_frame, bg=COLORS["bg"])
        self.meta_lbl = tk.Label(
            self.card_tools, text="Wiggle for next",
            bg=COLORS["bg"], fg=COLORS["text_dim"], font=("Segoe UI", 7),
        )
        self.meta_lbl.pack(side=tk.LEFT)

        self._make_mini_btn(self.card_tools, "─", lambda: self._set_mode("idle")).pack(side=tk.RIGHT)
        self._make_mini_btn(self.card_tools, "⚙", self._open_settings).pack(side=tk.RIGHT)
        self._make_mini_btn(self.card_tools, "🎯", self._start_manual_region).pack(side=tk.RIGHT)
        self._make_mini_btn(self.card_tools, "📜", self._toggle_history).pack(side=tk.RIGHT)
        self.copy_btn = self._make_mini_btn(self.card_tools, "📋", self._copy_answer)
        self.copy_btn.pack(side=tk.RIGHT)

        self.history_frame = tk.Frame(self.card_frame, bg=COLORS["bg"])

    def _build_context_menu(self):
        self.ctx_menu = tk.Menu(
            self.root, tearoff=0,
            bg=COLORS["surface"], fg=COLORS["text_bright"],
            activebackground=COLORS["surface_hover"], activeforeground=COLORS["text_bright"],
            bd=1, font=("Segoe UI", 9),
        )
        self.ctx_menu.add_command(label="⚡  Scan Screen Now", command=self._trigger_fullscreen_scan)
        self.ctx_menu.add_command(label="🎯  Manual Region Capture", command=self._start_manual_region)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="⏸  Pause / Resume Wiggle", command=self._toggle_pause)
        self.ctx_menu.add_command(label="📌  Snap Back to Corner", command=self._reset_position)
        self.ctx_menu.add_command(label="⚙   API Keys & Settings", command=self._open_settings)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="✕   Quit Quiz Cracker", command=self._quit)

    def _show_context_menu(self, event):
        try:
            self.ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.ctx_menu.grab_release()

    # ───────────────────────────────────────────────────
    # State Transitions & Corner Anchoring
    # ───────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self.mode = mode
        for f in (self.idle_frame, self.scan_frame, self.card_frame):
            f.pack_forget()

        if mode == "idle":
            self.history_visible = False
            self.history_frame.pack_forget()
            self.card_tools.pack_forget()
            self.inner.configure(padx=5, pady=3)
            self.outer.configure(bg=COLORS["border"])
            self._update_idle_indicator()
            self.idle_frame.pack(fill=tk.BOTH, expand=True)

            idle_style = ConfigManager.get("idle_style", "dot")
            if idle_style == "pill" or self.is_hovered or self.is_paused:
                self.idle_lbl.pack(side=tk.LEFT)
            else:
                self.idle_lbl.pack_forget()

            if self.is_hovered:
                self.idle_tools.pack(side=tk.LEFT, padx=(4, 0))
            else:
                self.idle_tools.pack_forget()

        elif mode == "scanning":
            self.inner.configure(padx=7, pady=4)
            self.outer.configure(bg=COLORS["border_scan"])
            self.scan_frame.pack(fill=tk.BOTH, expand=True)

        elif mode == "answer":
            self.inner.configure(padx=8, pady=6)
            self.outer.configure(bg=COLORS["border_ok"])
            self.card_frame.pack(fill=tk.BOTH, expand=True)
            if self.is_hovered or self.history_visible:
                self.card_tools.pack(fill=tk.X, pady=(5, 0))
            else:
                self.card_tools.pack_forget()

        elif mode == "error":
            self.inner.configure(padx=8, pady=6)
            self.outer.configure(bg=COLORS["border_err"])
            self.card_frame.pack(fill=tk.BOTH, expand=True)
            self.card_tools.pack(fill=tk.X, pady=(5, 0))

        self._update_alpha()
        self._anchor_to_corner()

    def _update_idle_indicator(self):
        if self.is_paused:
            self.dot_lbl.configure(fg=COLORS["amber"])
            self.idle_lbl.configure(text="Paused")
        else:
            self.dot_lbl.configure(fg=COLORS["green"])
            self.idle_lbl.configure(text="Wiggle")

    def _anchor_to_corner(self):
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        h = self.root.winfo_reqheight()

        if self.custom_pos is not None:
            x, y = self.custom_pos
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            return

        left, top, right, bottom = get_work_area()
        margin = 14
        corner = ConfigManager.get("corner", "bottom-right")

        if corner == "bottom-left":
            x, y = left + margin, bottom - h - margin
        elif corner == "top-right":
            x, y = right - w - margin, top + margin
        elif corner == "top-left":
            x, y = left + margin, top + margin
        else:  # bottom-right
            x, y = right - w - margin, bottom - h - margin

        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ───────────────────────────────────────────────────
    # Hover & Drag
    # ───────────────────────────────────────────────────

    def _on_enter(self, event=None):
        if self.is_hovered:
            return
        self.is_hovered = True
        self._cancel_collapse_timer()
        if self.mode == "idle":
            self.idle_lbl.pack(side=tk.LEFT)
            self.idle_tools.pack(side=tk.LEFT, padx=(4, 0))
            self._update_alpha()
            self._anchor_to_corner()
        elif self.mode == "answer":
            self.card_tools.pack(fill=tk.X, pady=(5, 0))
            self._update_alpha()
            self._anchor_to_corner()

    def _on_leave(self, event=None):
        mx, my = get_cursor_pos()
        rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        if rx <= mx <= rx + rw and ry <= my <= ry + rh:
            return

        self.is_hovered = False
        if self.mode == "idle":
            self.idle_tools.pack_forget()
            if ConfigManager.get("idle_style", "dot") == "dot" and not self.is_paused:
                self.idle_lbl.pack_forget()
            self._update_alpha()
            self._anchor_to_corner()
        elif self.mode == "answer":
            if not self.history_visible:
                self.card_tools.pack_forget()
                self._anchor_to_corner()
            self._update_alpha()
            self._schedule_auto_collapse()

    def _start_drag(self, event):
        self._drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _on_drag(self, event):
        if self._drag_offset:
            nx = event.x_root - self._drag_offset[0]
            ny = event.y_root - self._drag_offset[1]
            self.custom_pos = (nx, ny)
            self.root.geometry(f"+{nx}+{ny}")

    def _end_drag(self, event):
        self._drag_offset = None

    def _reset_position(self):
        self.custom_pos = None
        self._anchor_to_corner()

    # ───────────────────────────────────────────────────
    # Mouse Movement & Wakeup Polling Loop
    # ───────────────────────────────────────────────────

    def _poll_mouse(self):
        try:
            if poll_wakeup_event(self.wakeup_evt):
                self._open_settings()

            if not self.is_paused and self.mode != "scanning":
                x, y = get_cursor_pos()
                bounds = get_screen_bounds_at(x, y) if self.watcher.corner_enabled else None
                gesture = self.watcher.feed_position(x, y, time.monotonic(), bounds)
                if gesture:
                    self._trigger_fullscreen_scan()
        except Exception:
            pass
        self.root.after(30, self._poll_mouse)

    # ───────────────────────────────────────────────────
    # Capture & Solve Flows
    # ───────────────────────────────────────────────────

    def _trigger_fullscreen_scan(self):
        if self.mode == "scanning":
            return

        if not ConfigManager.has_valid_setup():
            self._show_error("API key needed", "Click ⚙ to add any AI API key.")
            return

        self._cancel_collapse_timer()
        self.root.withdraw()
        self.root.update()
        self.root.after(70, self._do_fullscreen_capture)

    def _do_fullscreen_capture(self):
        try:
            image_bytes = capture_monitor_at_cursor()
        except Exception as e:
            self.root.deiconify()
            self._show_error("Capture failed", str(e)[:80])
            return
        self._start_solving(image_bytes)

    def _start_manual_region(self):
        if self.mode == "scanning":
            return
        if not ConfigManager.has_valid_setup():
            self._open_settings()
            return

        self._cancel_collapse_timer()
        self.watcher.enabled = False
        self.root.withdraw()
        self.root.update()
        self.root.after(100, self._open_region_selector)

    def _open_region_selector(self):
        RegionSelector(self.root, self._on_region_selected, self._on_region_cancelled)

    def _on_region_selected(self, region: tuple):
        self.watcher.enabled = not self.is_paused
        self.root.after(100, lambda: self._do_region_capture(region))

    def _on_region_cancelled(self):
        self.watcher.enabled = not self.is_paused
        self.root.deiconify()
        self._anchor_to_corner()

    def _do_region_capture(self, region: tuple):
        try:
            image_bytes = capture_region(*region)
        except Exception as e:
            self.root.deiconify()
            self._show_error("Capture failed", str(e)[:80])
            return
        self._start_solving(image_bytes)

    def _start_solving(self, image_bytes: bytes):
        self._anim_dots = 0
        self.scan_lbl.configure(text="Solving...")
        self._set_mode("scanning")
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self._start_anim()

        cfg = ConfigManager.load()
        provider = cfg.get("provider", "auto")
        api_key = cfg.get("api_key", "")
        model = cfg.get("model", "")
        custom_url = cfg.get("custom_base_url", "")
        backup_keys = cfg.get("provider_keys", {})

        def worker():
            try:
                result = solve_mcq_with_provider(
                    image_bytes=image_bytes,
                    provider_id=provider,
                    api_key=api_key,
                    model=model,
                    custom_base_url=custom_url,
                    backup_keys=backup_keys,
                )
                self.root.after(0, lambda: self._on_answer_ready(result))
            except Exception as exc:
                err_msg = str(exc)
                self.root.after(0, lambda: self._on_solve_error(err_msg))

        threading.Thread(target=worker, daemon=True).start()

    def _start_anim(self):
        self._stop_anim()
        self._tick_anim()

    def _tick_anim(self):
        if self.mode != "scanning":
            return
        self._anim_dots = (self._anim_dots + 1) % 4
        self.scan_lbl.configure(text=f"Solving{'.' * self._anim_dots}")
        self._anim_after_id = self.root.after(320, self._tick_anim)

    def _stop_anim(self):
        if self._anim_after_id is not None:
            try:
                self.root.after_cancel(self._anim_after_id)
            except Exception:
                pass
            self._anim_after_id = None

    def _on_answer_ready(self, result: dict):
        self._stop_anim()
        self.watcher.set_cooldown(2.5)

        opt = result.get("option", "?")
        ans = result.get("answer", "")
        reason = result.get("reason", "")

        if opt in ("—", "?", ""):
            self.badge_lbl.configure(
                bg=COLORS["amber_bg"], fg=COLORS["amber"],
                highlightbackground=COLORS["amber"],
            )
        else:
            self.badge_lbl.configure(
                bg=COLORS["green_bg"], fg=COLORS["green"],
                highlightbackground=COLORS["border_ok"],
            )

        font_sz = 11 if len(opt) <= 2 else (9 if len(opt) <= 5 else 7)
        self.badge_lbl.configure(text=opt, font=("Segoe UI", font_sz, "bold"))

        self.ans_title.configure(text=ans or f"Option {opt}")
        if reason:
            self.ans_reason.configure(text=reason)
            self.ans_reason.pack(fill=tk.X, pady=(1, 0))
        else:
            self.ans_reason.pack_forget()

        prov_used = result.get("provider", "")
        if prov_used and prov_used in PROVIDERS:
            self.meta_lbl.configure(text=f"{prov_used} • wiggle for next")
        else:
            self.meta_lbl.configure(text="Wiggle for next")

        self._set_mode("answer")
        self.root.deiconify()
        self.root.attributes("-topmost", True)

        if opt not in ("—", ""):
            summary = f"{opt} — {ans}" if ans else opt
            ts = datetime.now().strftime("%H:%M")
            self.history.insert(0, {"summary": summary, "time": ts})
            self.history = self.history[:MAX_HISTORY]
            self._refresh_history()

        self._schedule_auto_collapse()

    def _on_solve_error(self, msg: str):
        self._stop_anim()
        self.watcher.set_cooldown(2.0)
        self._show_error("Could not solve", msg)

    def _show_error(self, title: str, detail: str):
        self.badge_lbl.configure(
            text="!", font=("Segoe UI", 11, "bold"),
            bg=COLORS["red_bg"], fg=COLORS["red"],
            highlightbackground=COLORS["border_err"],
        )
        self.ans_title.configure(text=title)
        self.ans_reason.configure(text=detail)
        self.ans_reason.pack(fill=tk.X, pady=(1, 0))
        self._set_mode("error")
        self.root.deiconify()
        self.root.attributes("-topmost", True)

    # ───────────────────────────────────────────────────
    # Auto-Collapse, Copy, History, Settings
    # ───────────────────────────────────────────────────

    def _schedule_auto_collapse(self):
        self._cancel_collapse_timer()
        sec = int(ConfigManager.get("auto_collapse_sec", 10))
        if sec > 0 and not self.is_hovered and not self.history_visible:
            self._collapse_after_id = self.root.after(sec * 1000, self._auto_collapse)

    def _cancel_collapse_timer(self):
        if self._collapse_after_id is not None:
            try:
                self.root.after_cancel(self._collapse_after_id)
            except Exception:
                pass
            self._collapse_after_id = None

    def _auto_collapse(self):
        self._collapse_after_id = None
        if self.mode == "answer" and not self.is_hovered and not self.history_visible:
            self._set_mode("idle")

    def _copy_answer(self):
        text = f"{self.badge_lbl.cget('text')}: {self.ans_title.cget('text')}"
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.copy_btn.configure(text="✓", fg=COLORS["green"])
        self.root.after(1200, lambda: self.copy_btn.configure(text="📋", fg=COLORS["text_muted"]))

    def _toggle_history(self):
        self.history_visible = not self.history_visible
        if self.history_visible:
            self._cancel_collapse_timer()
            self._refresh_history()
            self.history_frame.pack(fill=tk.X, pady=(5, 0))
        else:
            self.history_frame.pack_forget()
        self._update_alpha()
        self._anchor_to_corner()

    def _refresh_history(self):
        for child in self.history_frame.winfo_children():
            child.destroy()

        if not self.history:
            tk.Label(
                self.history_frame, text="No answers yet",
                bg=COLORS["bg"], fg=COLORS["text_dim"], font=("Segoe UI", 7),
                anchor="w",
            ).pack(fill=tk.X)
            return

        for entry in self.history[:5]:
            txt = entry["summary"]
            if len(txt) > 36:
                txt = txt[:33] + "..."
            tk.Label(
                self.history_frame, text=f"{entry['time']}  •  {txt}",
                bg=COLORS["surface"], fg=COLORS["text_muted"],
                font=("Segoe UI", 7), anchor="w", padx=5, pady=2,
            ).pack(fill=tk.X, pady=1)

    def _toggle_pause(self):
        self.is_paused = not self.is_paused
        self.watcher.enabled = not self.is_paused
        self._set_mode(self.mode)

    def _apply_config(self):
        cfg = ConfigManager.load()
        self.watcher.apply_config(cfg)
        self.custom_pos = None
        self._set_mode(self.mode)

    def _check_first_run(self):
        if not ConfigManager.has_valid_setup():
            self._open_settings()
        else:
            self._show_startup_ready_hint()

    def _show_startup_ready_hint(self):
        if self.mode != "idle" or self.is_hovered or self.is_paused:
            return
        self.idle_lbl.configure(text="Ready • Wiggle")
        self.idle_lbl.pack(side=tk.LEFT)
        self.root.attributes("-alpha", 0.72)
        self._anchor_to_corner()
        self.root.after(3500, self._hide_startup_ready_hint)

    def _hide_startup_ready_hint(self):
        if self.mode == "idle" and not self.is_hovered and not self.is_paused:
            self._update_idle_indicator()
            if ConfigManager.get("idle_style", "dot") == "dot":
                self.idle_lbl.pack_forget()
            self._update_alpha()
            self._anchor_to_corner()

    def _open_settings(self):
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.deiconify()
            self._settings_win.lift()
            make_normal_activatable_dialog(self._settings_win)
            return
        self.watcher.enabled = False

        def on_saved():
            self._apply_config()
            if self.mode == "error":
                self._set_mode("idle")
            self.watcher.enabled = not self.is_paused

        dlg = SettingsDialog(self.root, on_saved)

        def on_destroy(event):
            if event.widget is dlg:
                self._on_settings_closed()

        dlg.bind("<Destroy>", on_destroy)
        self._settings_win = dlg

    def _on_settings_closed(self):
        self._settings_win = None
        self.watcher.enabled = not self.is_paused

    def _quit(self):
        self._stop_anim()
        self._cancel_collapse_timer()
        self.root.destroy()


# ═══════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════

def main():
    mutex, wakeup_evt = acquire_single_instance()
    if mutex is None:
        sys.exit(0)

    root = tk.Tk()
    QuizCrackerApp(root, wakeup_evt=wakeup_evt)
    try:
        root.mainloop()
    finally:
        for h in (mutex, wakeup_evt):
            if isinstance(h, int) and h:
                try:
                    _kernel32.CloseHandle(h)
                except Exception:
                    pass


if __name__ == "__main__":
    main()
