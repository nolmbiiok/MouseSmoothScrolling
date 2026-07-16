r"""
MouseSmoothWheel

Windows-only prototype.
- Global mouse wheel hook
- Inertia-style synthetic wheel tail
- Native Windows tray icon with Settings and Exit
- No external Python dependencies

Run:
    python src\mouse_smooth_wheel.py

Stop:
    Right-click tray icon -> Exit
    or Ctrl + C in the terminal
"""

import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass

try:
    import tkinter as tk
    from tkinter import messagebox
except Exception:
    tk = None
    messagebox = None


if sys.platform != "win32":
    raise SystemExit("MouseSmoothWheel currently supports Windows only.")


# ============================================================
# Windows constants
# ============================================================

IMAGE_ICON = 1

LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040
GA_ROOT = 2

WH_MOUSE_LL = 14
HC_ACTION = 0

WH_KEYBOARD_LL = 13

WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104


LLKHF_LOWER_IL_INJECTED = 0x00000002
LLKHF_INJECTED = 0x00000010


WM_MOUSEWHEEL = 0x020A
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_XBUTTONDOWN = 0x020B
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUIT = 0x0012
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 1
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_CONTEXTMENU = 0x007B

PM_REMOVE = 0x0001

LLMHF_INJECTED = 0x00000001
LLMHF_LOWER_IL_INJECTED = 0x00000002

INPUT_MOUSE = 0
MOUSEEVENTF_WHEEL = 0x0800

NIM_ADD = 0x00000000
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
MF_UNCHECKED = 0x00000000

TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

IDI_APPLICATION = 32512

ID_SETTINGS = 1001
ID_EXIT = 1099


# ============================================================
# WinAPI setup
# ============================================================

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
UINT_PTR = ctypes.c_size_t
HCURSOR = ctypes.c_void_p

WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

LowLevelMouseProc = ctypes.WINFUNCTYPE(
    LRESULT,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    LRESULT,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


user32.WindowFromPoint.argtypes = [POINT]
user32.WindowFromPoint.restype = wintypes.HWND

user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.DWORD,
]


user32.SetWindowsHookExW.restype = ctypes.c_void_p

user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.CallNextHookEx.restype = LRESULT

user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.SendInput.argtypes = [
    wintypes.UINT,
    ctypes.POINTER(INPUT),
    ctypes.c_int,
]
user32.SendInput.restype = wintypes.UINT

user32.PeekMessageW.argtypes = [
    ctypes.POINTER(MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
]
user32.PeekMessageW.restype = wintypes.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = wintypes.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT

user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM

user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND

user32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.DefWindowProcW.restype = LRESULT

user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL

user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None

user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON

user32.LoadImageW.argtypes = [
    wintypes.HINSTANCE,
    wintypes.LPCWSTR,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.LoadImageW.restype = wintypes.HANDLE

user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wintypes.HMENU

user32.AppendMenuW.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    UINT_PTR,
    wintypes.LPCWSTR,
]
user32.AppendMenuW.restype = wintypes.BOOL

user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    ctypes.c_void_p,
]
user32.TrackPopupMenu.restype = wintypes.UINT

user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL

user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL

user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND


kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE

shell32.Shell_NotifyIconW.argtypes = [
    wintypes.DWORD,
    ctypes.POINTER(NOTIFYICONDATAW),
]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL


# ============================================================
# Configuration and runtime state
# ============================================================

@dataclass
class Config:
    # Default values are close to the previous Normal preset.
    gain: float = 0.3
    friction: float = 0.94
    tick_rate: int = 240
    stop_velocity: float = 0.5
    quiet: bool = False

    # Synthetic wheel output limits.
    min_send_delta: int = 1
    max_delta_per_tick: int = 20

    keyboard_soft_stop_friction: float = 0.94
    keyboard_soft_stop_velocity_scale: float = 0.35

    initial_inertia_boost: float = 1.0
    initial_inertia_min_velocity: float = 10.0

    repeat_wheel_boost: float = 0.1
    repeat_wheel_boost_step: float = 0.1
    repeat_wheel_boost_max: float = 4.0


    repeat_wheel_chain_seconds: float = 0.6
    max_velocity: float = 12000.0
    max_boosted_delta_per_tick: int = 300

    intercept_physical_wheel: bool = True

    # Before inertia starts, keep the first N wheel events as normal wheel input.
    no_inertia_events_up: int = 2
    no_inertia_events_down: int = 2
    gesture_reset_seconds: float = 0.10

    cancel_on_window_change: bool = True

    tail_velocity_threshold: float = 20.0
    tail_friction: float = 0.94
    tail_min_send_delta: int = 1
    tail_max_delta_per_tick: int = 24

    final_fade_velocity_threshold: float = 6.0
    final_fade_seconds: float = 0.16



@dataclass
class RuntimeState:
    velocity: float = 0.0
    accumulator: float = 0.0
    target_hwnd: int = 0
    target_root_hwnd: int = 0
    target_foreground_hwnd: int = 0
    running: bool = True

    repeat_boost_count: int = 0
    last_repeat_boost_time: float = 0.0
    last_wheel_direction: int = 0

    soft_stopping: bool = False    

    wheel_event_count: int = 0
    last_wheel_time: float = 0.0


SETTING_DEFINITIONS = [
    {
        "key": "no_inertia_events_up",
        "label": "Wheel up normal count",
        "type": int,
        "min": 0,
        "max": 20,
        "help": "Wheel-up inputs that stay normal before inertia starts.",
    },
    {
        "key": "no_inertia_events_down",
        "label": "Wheel down normal count",
        "type": int,
        "min": 0,
        "max": 20,
        "help": "Wheel-down inputs that stay normal before inertia starts.",
    },
    {
        "key": "tick_rate",
        "label": "Worker update rate",
        "type": int,
        "min": 60,
        "max": 500,
        "help": "Physics update frequency. 240 Hz is recommended.",
    },
    {
        "key": "gain",
        "label": "Speed gain",
        "type": float,
        "min": 0.01,
        "max": 1.00,
        "help": "Higher value means faster inertia acceleration.",
    },
    {
        "key": "friction",
        "label": "Friction / deceleration",
        "type": float,
        "min": 0.50,
        "max": 0.99,
        "help": "Higher value means slower deceleration and a longer tail.",
    },
    {
        "key": "initial_inertia_boost",
        "label": "Initial inertia boost",
        "type": float,
        "min": 0.001,
        "max": 30.00,
        "help": "One-time boost when inertia first starts.",
    },
    {
        "key": "repeat_wheel_boost",
        "label": "Repeat wheel boost",
        "type": float,
        "min": 0.01,
        "max": 5.00,
        "help": "Acceleration scale for wheel input during active inertia.",
    },
    {
        "key": "repeat_wheel_boost_step",
        "label": "Repeat boost step",
        "type": float,
        "min": 0.00,
        "max": 10.00,
        "help": "Extra boost added for chained wheel inputs.",
    },
    {
        "key": "repeat_wheel_boost_max",
        "label": "Max repeat boost",
        "type": float,
        "min": 0.001,
        "max": 5.00,
        "help": "Maximum acceleration scale during active inertia.",
    },

    {
    "key": "repeat_wheel_chain_seconds",
    "label": "Repeat boost chain time",
    "type": float,
    "min": 0.05,
    "max": 3.00,
    "help": "Time allowed between wheel inputs to continue repeat acceleration.",
    },
    {
        "key": "max_velocity",
        "label": "Maximum velocity",
        "type": float,
        "min": 100.0,
        "max": 50000.0,
        "help": "Maximum accumulated inertia velocity.",
    },
    {
        "key": "max_boosted_delta_per_tick",
        "label": "Maximum boosted output",
        "type": int,
        "min": 20,
        "max": 2000,
        "help": "Maximum wheel output per tick during high-speed inertia.",
    },
    {
        "key": "max_delta_per_tick",
        "label": "Max output per tick",
        "type": int,
        "min": 1,
        "max": 240,
        "help": "Limits synthetic wheel output per worker tick.",
    },
    {
        "key": "tail_friction",
        "label": "Tail friction",
        "type": float,
        "min": 0.50,
        "max": 0.99,
        "help": "Higher value makes the final scroll tail longer.",
    },
]

SETTING_KEYS = {item["key"] for item in SETTING_DEFINITIONS}

config = Config()
state = RuntimeState()
state_lock = threading.Lock()
hook_handle = None
keyboard_hook_handle = None
tray_app = None


# ============================================================
# Utility functions
# ============================================================

def get_app_icon_path() -> Path:
    current_file = Path(__file__).resolve()

    # Case 1:
    #   MouseSmoothWheel/src/mouse_smooth_wheel.py
    #   MouseSmoothWheel/assets/mousesmoothwheel.ico
    if current_file.parent.name == "src":
        project_root = current_file.parents[1]
    else:
        # Case 2:
        #   MouseSmoothWheel/mouse_smooth_wheel.py
        #   MouseSmoothWheel/assets/mousesmoothwheel.ico
        project_root = current_file.parent

    return project_root / "assets" / "mousesmoothwheel.ico"


def load_app_icon():
    icon_path = get_app_icon_path()

    if icon_path.exists():
        icon_handle = user32.LoadImageW(
            None,
            str(icon_path),
            IMAGE_ICON,
            0,
            0,
            LR_LOADFROMFILE | LR_DEFAULTSIZE,
        )

        if icon_handle:
            return icon_handle

    # Fallback: Windows default application icon
    icon_resource = ctypes.cast(ctypes.c_void_p(IDI_APPLICATION), wintypes.LPCWSTR)
    return user32.LoadIconW(None, icon_resource)



def get_root_window_from_point(point: POINT) -> int:

    
    hwnd = user32.WindowFromPoint(point)

    if not hwnd:
        return 0

    root_hwnd = user32.GetAncestor(hwnd, GA_ROOT)

    if root_hwnd:
        return int(root_hwnd)

    return int(hwnd)

def get_window_from_point(point: POINT) -> int:
    hwnd = user32.WindowFromPoint(point)

    if not hwnd:
        return 0

    return int(hwnd)

def get_root_window_under_cursor() -> int:
    point = POINT()

    if not user32.GetCursorPos(ctypes.byref(point)):
        return 0

    return get_root_window_from_point(point)


def get_window_under_cursor() -> int:
    point = POINT()

    if not user32.GetCursorPos(ctypes.byref(point)):
        return 0

    return get_window_from_point(point)


def get_foreground_root_window() -> int:
    hwnd = user32.GetForegroundWindow()

    if not hwnd:
        return 0

    root_hwnd = user32.GetAncestor(hwnd, GA_ROOT)

    if root_hwnd:
        return int(root_hwnd)

    return int(hwnd)


def cancel_inertia() -> None:
    state.velocity = 0.0
    state.accumulator = 0.0
    state.target_hwnd = 0
    state.target_root_hwnd = 0
    state.target_foreground_hwnd = 0
    state.soft_stopping = False

    state.wheel_event_count = 0
    state.last_wheel_time = 0.0

    state.repeat_boost_count = 0
    state.last_repeat_boost_time = 0.0
    state.last_wheel_direction = 0

    
def has_active_inertia_locked() -> bool:
    return (
        abs(state.velocity) > 0.001
        or abs(state.accumulator) >= config.tail_min_send_delta
    )


def get_no_inertia_events_for_direction(direction: int) -> int:
    """
    Windows wheel delta:
        direction > 0: wheel up
        direction < 0: wheel down
    """
    if direction > 0:
        return config.no_inertia_events_up

    return config.no_inertia_events_down


def should_cancel_inertia_for_window_change() -> bool:
    if not config.cancel_on_window_change:
        return False

    target_hwnd = state.target_hwnd
    target_root_hwnd = state.target_root_hwnd
    target_foreground_hwnd = state.target_foreground_hwnd

    current_hwnd = get_window_under_cursor()
    current_root_hwnd = get_root_window_under_cursor()
    current_foreground_hwnd = get_foreground_root_window()

    # Most sensitive guard:
    # If the exact window/control under the cursor changed, stop inertia.
    if target_hwnd and current_hwnd and current_hwnd != target_hwnd:
        return True

    # Fallback guard:
    # If the top-level root window changed, stop inertia.
    if target_root_hwnd and current_root_hwnd and current_root_hwnd != target_root_hwnd:
        return True

    # Fallback guard:
    # If the active foreground window changed, stop inertia.
    if (
        target_foreground_hwnd
        and current_foreground_hwnd
        and current_foreground_hwnd != target_foreground_hwnd
    ):
        return True

    return False

def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def get_last_error_message() -> str:
    error_code = ctypes.get_last_error()
    return f"WinAPI error code: {error_code}"


def wheel_delta_from_mouse_data(mouse_data: int) -> int:
    high_word = (mouse_data >> 16) & 0xFFFF

    if high_word & 0x8000:
        high_word -= 0x10000

    return high_word


def is_injected_mouse_event(flags: int) -> bool:
    return bool(flags & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED))

def is_injected_keyboard_event(flags: int) -> bool:
    return bool(flags & (LLKHF_INJECTED | LLKHF_LOWER_IL_INJECTED))


def get_settings_path() -> Path:
    appdata = os.environ.get("APPDATA")

    if appdata:
        base_dir = Path(appdata)
    else:
        base_dir = Path.home() / "AppData" / "Roaming"

    return base_dir / "MouseSmoothWheel" / "settings.json"


def format_setting_value(value) -> str:
    if isinstance(value, float):
        return f"{value:.4g}"

    return str(value)


def parse_setting_value(definition: dict, raw_value: str):
    key = definition["key"]
    value_type = definition["type"]
    min_value = definition["min"]
    max_value = definition["max"]

    try:
        if value_type is int:
            value = int(raw_value.strip())
        else:
            value = float(raw_value.strip())
    except ValueError as exc:
        raise ValueError(f"{definition['label']} must be a number.") from exc

    if value < min_value or value > max_value:
        raise ValueError(
            f"{definition['label']} must be between {min_value} and {max_value}."
        )

    return value


def config_settings_to_dict(source: Config) -> dict:
    return {
        definition["key"]: getattr(source, definition["key"])
        for definition in SETTING_DEFINITIONS
    }


def apply_settings_dict(values: dict, *, reset_motion: bool = True) -> None:
    with state_lock:
        for definition in SETTING_DEFINITIONS:
            key = definition["key"]

            if key not in values:
                continue

            setattr(config, key, values[key])

        # Keep this relationship valid even if the user lowers the max boost later.
        if config.repeat_wheel_boost_max < config.repeat_wheel_boost:
            config.repeat_wheel_boost_max = config.repeat_wheel_boost

        if reset_motion:
            cancel_inertia()


def load_saved_settings(target_config: Config) -> None:
    settings_path = get_settings_path()

    if not settings_path.exists():
        return

    try:
        saved_values = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as exc:
        if not target_config.quiet:
            print(f"[WARN] Failed to read settings file: {exc}")
        return

    for definition in SETTING_DEFINITIONS:
        key = definition["key"]

        if key not in saved_values:
            continue

        try:
            value = parse_setting_value(definition, str(saved_values[key]))
        except ValueError as exc:
            if not target_config.quiet:
                print(f"[WARN] Ignoring invalid setting '{key}': {exc}")
            continue

        setattr(target_config, key, value)


def save_current_settings() -> None:
    settings_path = get_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    with state_lock:
        data = config_settings_to_dict(config)

    settings_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if not config.quiet:
        print(f"Settings saved: {settings_path}")


def reset_settings_to_defaults() -> None:
    default_config = Config()
    default_values = config_settings_to_dict(default_config)
    apply_settings_dict(default_values)


settings_dialog_lock = threading.Lock()
settings_dialog_open = False


def open_settings_window() -> None:
    global settings_dialog_open

    if tk is None:
        if not config.quiet:
            print("[WARN] tkinter is not available. Settings window cannot be opened.")
        return

    with settings_dialog_lock:
        if settings_dialog_open:
            return

        settings_dialog_open = True

    thread = threading.Thread(
        target=_settings_window_thread,
        name="MouseSmoothWheelSettingsWindow",
        daemon=True,
    )
    thread.start()


def _settings_window_thread() -> None:
    global settings_dialog_open

    try:
        show_settings_window()
    finally:
        with settings_dialog_lock:
            settings_dialog_open = False


def show_settings_window() -> None:
    root = tk.Tk()
    root.title("MouseSmoothWheel Settings")
    root.resizable(False, False)

    with state_lock:
        current_values = config_settings_to_dict(config)

    entries = {}

    title = tk.Label(
        root,
        text="MouseSmoothWheel Settings",
        font=("Segoe UI", 11, "bold"),
    )
    title.grid(row=0, column=0, columnspan=3, padx=14, pady=(12, 6), sticky="w")

    description = tk.Label(
        root,
        text="Set exact values instead of using Low / Normal / Strong presets.",
        justify="left",
    )
    description.grid(row=1, column=0, columnspan=3, padx=14, pady=(0, 10), sticky="w")

    for index, definition in enumerate(SETTING_DEFINITIONS, start=2):
        key = definition["key"]

        label = tk.Label(root, text=definition["label"])
        label.grid(row=index, column=0, padx=(14, 8), pady=4, sticky="e")

        entry = tk.Entry(root, width=12)
        entry.insert(0, format_setting_value(current_values[key]))
        entry.grid(row=index, column=1, padx=4, pady=4, sticky="w")
        entries[key] = entry

        help_label = tk.Label(
            root,
            text=definition["help"],
            foreground="#555555",
            justify="left",
        )
        help_label.grid(row=index, column=2, padx=(8, 14), pady=4, sticky="w")

    def collect_values() -> dict:
        values = {}

        for definition in SETTING_DEFINITIONS:
            key = definition["key"]
            values[key] = parse_setting_value(definition, entries[key].get())

        if values["repeat_wheel_boost_max"] < values["repeat_wheel_boost"]:
            raise ValueError("Max repeat boost must be greater than or equal to Repeat wheel boost.")

        return values

    def apply_from_entries(*, save: bool) -> None:
        try:
            values = collect_values()
            apply_settings_dict(values)

            if save:
                save_current_settings()

        except ValueError as exc:
            messagebox.showerror("Invalid setting", str(exc), parent=root)
            return
        except Exception as exc:
            messagebox.showerror("Settings error", str(exc), parent=root)
            return

        if save:
            root.destroy()
        else:
            messagebox.showinfo("Applied", "Settings applied for the current session.", parent=root)

    def reset_entries() -> None:
        default_values = config_settings_to_dict(Config())

        for definition in SETTING_DEFINITIONS:
            key = definition["key"]
            entries[key].delete(0, tk.END)
            entries[key].insert(0, format_setting_value(default_values[key]))

    button_row = len(SETTING_DEFINITIONS) + 3

    buttons = tk.Frame(root)
    buttons.grid(row=button_row, column=0, columnspan=3, padx=14, pady=(12, 14), sticky="e")

    tk.Button(buttons, text="Reset", width=10, command=reset_entries).pack(side="left", padx=(0, 6))
    tk.Button(buttons, text="Apply", width=10, command=lambda: apply_from_entries(save=False)).pack(side="left", padx=6)
    tk.Button(buttons, text="Save", width=10, command=lambda: apply_from_entries(save=True)).pack(side="left", padx=6)
    tk.Button(buttons, text="Cancel", width=10, command=root.destroy).pack(side="left", padx=(6, 0))

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


def send_wheel_delta(delta: int) -> None:
    mouse_input = MOUSEINPUT(
        dx=0,
        dy=0,
        mouseData=ctypes.c_uint32(delta & 0xFFFFFFFF).value,
        dwFlags=MOUSEEVENTF_WHEEL,
        time=0,
        dwExtraInfo=0,
    )

    input_event = INPUT(
        type=INPUT_MOUSE,
        union=INPUT_UNION(mi=mouse_input),
    )

    input_array = (INPUT * 1)(input_event)

    sent = user32.SendInput(
        1,
        input_array,
        ctypes.sizeof(INPUT),
    )

    if sent != 1 and not config.quiet:
        print(f"[WARN] SendInput failed. {get_last_error_message()}")


# ============================================================
# Tray app
# ============================================================

class TrayApp:
    def __init__(self) -> None:
        self.class_name = "MouseSmoothWheelTrayWindow"
        self.window_title = "MouseSmoothWheel"
        self.hinstance = kernel32.GetModuleHandleW(None)
        self.hwnd = None
        self.icon_added = False
        self.icon_handle = load_app_icon()

        # Keep callback alive. If this gets garbage-collected, Windows can crash the process.
        self._wnd_proc = WNDPROC(self._handle_window_message)

    def create(self) -> None:
        self._register_window_class()
        self._create_hidden_window()
        self._add_tray_icon()

    def destroy(self) -> None:
        self._remove_tray_icon()

        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None

    def _register_window_class(self) -> None:
        wndclass = WNDCLASSW()
        wndclass.style = 0
        wndclass.lpfnWndProc = self._wnd_proc
        wndclass.cbClsExtra = 0
        wndclass.cbWndExtra = 0
        wndclass.hInstance = self.hinstance
        wndclass.hIcon = self.icon_handle
        wndclass.hCursor = None
        wndclass.hbrBackground = None
        wndclass.lpszMenuName = None
        wndclass.lpszClassName = self.class_name

        user32.RegisterClassW(ctypes.byref(wndclass))

    def _create_hidden_window(self) -> None:
        self.hwnd = user32.CreateWindowExW(
            0,
            self.class_name,
            self.window_title,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            self.hinstance,
            None,
        )

        if not self.hwnd:
            raise RuntimeError(f"Failed to create tray window. {get_last_error_message()}")

    def _add_tray_icon(self) -> None:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self.icon_handle
        nid.szTip = "MouseSmoothWheel"

        ok = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        if not ok:
            raise RuntimeError(f"Failed to add tray icon. {get_last_error_message()}")

        self.icon_added = True

    def _remove_tray_icon(self) -> None:
        if not self.icon_added or not self.hwnd:
            return

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1

        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        self.icon_added = False

    def _handle_window_message(self, hwnd, message, wparam, lparam):
        if message == WM_TRAYICON:
            if lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_context_menu()
                return 0

            if lparam == WM_LBUTTONDBLCLK:
                open_settings_window()
                return 0

        if message == WM_COMMAND:
            command_id = int(wparam) & 0xFFFF
            self._handle_command(command_id)
            return 0

        if message in (WM_CLOSE, WM_DESTROY):
            state.running = False
            self._remove_tray_icon()
            user32.PostQuitMessage(0)
            return 0

        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _show_context_menu(self) -> None:
        menu = user32.CreatePopupMenu()
        if not menu:
            return

        try:
            user32.AppendMenuW(menu, MF_STRING, ID_SETTINGS, "Settings...")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, ID_EXIT, "Exit")

            cursor = POINT()
            user32.GetCursorPos(ctypes.byref(cursor))
            user32.SetForegroundWindow(self.hwnd)

            command_id = user32.TrackPopupMenu(
                menu,
                TPM_RIGHTBUTTON | TPM_RETURNCMD,
                cursor.x,
                cursor.y,
                0,
                self.hwnd,
                None,
            )

            if command_id:
                self._handle_command(command_id)

        finally:
            user32.DestroyMenu(menu)

    def _handle_command(self, command_id: int) -> None:
        if command_id == ID_SETTINGS:
            open_settings_window()
            return

        if command_id == ID_EXIT:
            state.running = False
            self._remove_tray_icon()
            user32.PostQuitMessage(0)
            return


# ============================================================
# Mouse hook
# ============================================================
@LowLevelMouseProc
def mouse_hook_proc(n_code, w_param, l_param):
    global hook_handle

    handled_physical_wheel = False

    if n_code == HC_ACTION and w_param == WM_MOUSEWHEEL:
        info = ctypes.cast(
            l_param,
            ctypes.POINTER(MSLLHOOKSTRUCT),
        ).contents

        if is_injected_mouse_event(info.flags):
            return user32.CallNextHookEx(hook_handle, n_code, w_param, l_param)

        delta = wheel_delta_from_mouse_data(info.mouseData)

        if delta != 0:
            handled_physical_wheel = config.intercept_physical_wheel

            target_hwnd = get_window_from_point(info.pt)
            root_hwnd = get_root_window_from_point(info.pt)
            foreground_hwnd = get_foreground_root_window()
            now = time.monotonic()

            with state_lock:
                was_inertia_active = has_active_inertia_locked()
                is_new_gesture = (
                    now - state.last_wheel_time > config.gesture_reset_seconds
                )

                wheel_direction = 1 if delta > 0 else -1

                no_inertia_events = get_no_inertia_events_for_direction(wheel_direction)


                active_motion_direction = 0
                if abs(state.velocity) >= config.stop_velocity:
                    active_motion_direction = 1 if state.velocity > 0 else -1
                elif abs(state.accumulator) > 0:
                    active_motion_direction = 1 if state.accumulator > 0 else -1

                opposite_direction_during_inertia = (
                    was_inertia_active
                    and active_motion_direction != 0
                    and active_motion_direction != wheel_direction
                )

                if opposite_direction_during_inertia:
                    cancel_inertia()
                    return 1


                # New gesture reset should only happen when inertia is already dead.
                # If inertia is still alive, additional wheel input means acceleration,
                # not the no-inertia phase again.
                if is_new_gesture and not was_inertia_active:
                    state.wheel_event_count = 0
                    state.velocity = 0.0
                    state.accumulator = 0.0

                # If inertia is alive, force the counter past the no-inertia phase.
                if was_inertia_active:
                    state.wheel_event_count = max(
                        state.wheel_event_count,
                        no_inertia_events,
                    )

                state.last_wheel_time = now
                state.wheel_event_count += 1
                state.target_hwnd = target_hwnd
                state.target_root_hwnd = root_hwnd
                state.target_foreground_hwnd = foreground_hwnd

                # A new physical wheel input means the user is intentionally scrolling again.
                state.soft_stopping = False

                is_no_inertia_phase = (
                    not was_inertia_active
                    and state.wheel_event_count <= no_inertia_events
                )

                is_initial_inertia_entry = (
                    not was_inertia_active
                    and state.wheel_event_count == no_inertia_events + 1
                )


                if is_no_inertia_phase:
                    # First N wheel events pass through as normal physical wheel input.
                    # No inertia, no smoothing, no synthetic wheel.
                    state.velocity = 0.0
                    state.accumulator = 0.0

                    return user32.CallNextHookEx(hook_handle, n_code, w_param, l_param)
                else:

                    # If the user wheels again in the same direction while inertia is alive,
                    # treat it as intentional acceleration.
                    same_direction = (
                        state.velocity == 0.0
                        or (state.velocity > 0) == (delta > 0)
                    )
                    direction = 1 if delta > 0 else -1

                    can_chain_repeat_boost = (
                        was_inertia_active
                        and same_direction
                        and state.last_wheel_direction == direction
                        and now - state.last_repeat_boost_time <= config.repeat_wheel_chain_seconds
                    )

                    if is_initial_inertia_entry:
                        # First wheel event after the no-inertia phase.
                        # Give it a one-time stronger push so inertia starts immediately.
                        boost = config.initial_inertia_boost

                        state.repeat_boost_count = 0
                        state.last_repeat_boost_time = now
                        state.last_wheel_direction = direction

                    elif was_inertia_active and same_direction:
                        if can_chain_repeat_boost:
                            state.repeat_boost_count += 1
                        else:
                            state.repeat_boost_count = 1

                        boost = min(
                            config.repeat_wheel_boost_max,
                            config.repeat_wheel_boost
                            + (state.repeat_boost_count - 1) * config.repeat_wheel_boost_step,
                        )

                        state.last_repeat_boost_time = now
                        state.last_wheel_direction = direction

                    else:
                        state.repeat_boost_count = 0
                        state.last_repeat_boost_time = 0.0
                        state.last_wheel_direction = direction
                        boost = 1.0
                    state.velocity += delta * config.gain * boost

                    if is_initial_inertia_entry:
                        state.velocity = direction * max(
                            abs(state.velocity),
                            config.initial_inertia_min_velocity,
                        )

                    state.velocity = clamp(
                        state.velocity,
                        -config.max_velocity,
                        config.max_velocity,
                    )

    if handled_physical_wheel:
        # Block the original physical wheel event.
        # Otherwise the app receives the raw one-line wheel first,
        # and the scroll still looks stepped.
        return 1
    

    return user32.CallNextHookEx(hook_handle, n_code, w_param, l_param)

@LowLevelKeyboardProc
def keyboard_hook_proc(n_code, w_param, l_param):
    global keyboard_hook_handle

    if n_code == HC_ACTION and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
        info = ctypes.cast(
            l_param,
            ctypes.POINTER(KBDLLHOOKSTRUCT),
        ).contents

        if not is_injected_keyboard_event(info.flags):
            with state_lock:
                if has_active_inertia_locked():
                    # Do not allow synthetic wheel to combine with keyboard state.
                    # Enter soft-stop mode and drain the remaining inertia internally.
                    state.soft_stopping = True
                    state.velocity *= config.keyboard_soft_stop_velocity_scale
                    state.accumulator = 0.0

    return user32.CallNextHookEx(
        keyboard_hook_handle,
        n_code,
        w_param,
        l_param,
    )



# ============================================================
# Inertia worker
# ============================================================
def inertia_worker() -> None:
    # Velocity/friction values were originally tuned for a 120 Hz worker.
    # frame_scale keeps the same feel even when tick_rate or actual wake-up
    # timing changes.
    reference_hz = 120.0
    last_tick = time.perf_counter()
    next_tick = last_tick

    while state.running:
        current_tick_rate = max(1, config.tick_rate)
        tick_interval = 1.0 / current_tick_rate
        next_tick += tick_interval

        now = time.perf_counter()
        dt = clamp(now - last_tick, 0.0, 0.05)
        last_tick = now
        frame_scale = dt * reference_hz

        send_delta = 0
        cancelled_for_window_change = False

        with state_lock:
            inertia_min_delta = (
                config.tail_min_send_delta
                if abs(state.velocity) < config.tail_velocity_threshold
                else config.min_send_delta
            )

            has_active_inertia = (
                abs(state.velocity) >= config.stop_velocity
                or abs(state.accumulator) >= inertia_min_delta
            )
            if state.velocity == 0.0:
                # 1보다 작은 잔량을 마지막에 억지로 보내면
                # 오히려 마지막 한 번이 툭 튀어 보일 수 있습니다.
                if abs(state.accumulator) < config.tail_min_send_delta:
                    state.accumulator = 0.0

                state.soft_stopping = False

        # Stop before sending if the cursor or foreground target changed.
        if has_active_inertia:
            with state_lock:
                should_check_window = bool(state.target_hwnd or state.target_root_hwnd)

            if should_check_window and should_cancel_inertia_for_window_change():
                with state_lock:
                    cancel_inertia()
                cancelled_for_window_change = True

        if not cancelled_for_window_change:
            with state_lock:
                is_tail_phase = (
                    not state.soft_stopping
                    and abs(state.velocity) < config.tail_velocity_threshold
                )

                active_min_delta = (
                    config.tail_min_send_delta
                    if is_tail_phase
                    else config.min_send_delta
                )

                if state.soft_stopping:
                    # Apply the old per-120-Hz decay as a time-based decay.
                    state.velocity *= (
                        config.keyboard_soft_stop_friction ** frame_scale
                    )
                    state.accumulator = 0.0
                else:
                    start_velocity = state.velocity
                    start_speed = abs(start_velocity)

                    is_final_fade = (
                        0.0 < start_speed <= config.final_fade_velocity_threshold
                    )

                    if is_final_fade:
                        # 마지막 저속 구간에서는 exponential friction을 사용하지 않고
                        # 정해진 시간 동안 속도를 선형으로 0까지 내립니다.
                        direction = 1.0 if start_velocity > 0.0 else -1.0

                        fade_seconds = max(0.01, config.final_fade_seconds)
                        deceleration_per_second = (
                            config.final_fade_velocity_threshold / fade_seconds
                        )

                        end_speed = max(
                            0.0,
                            start_speed - deceleration_per_second * dt,
                        )
                        end_velocity = direction * end_speed

                        # 프레임 중 평균속도를 사용해 이동량을 계산합니다.
                        frame_distance = (
                            (start_velocity + end_velocity)
                            * 0.5
                            * dt
                            * reference_hz
                        )

                        state.velocity = end_velocity

                    else:
                        current_friction = (
                            config.tail_friction
                            if is_tail_phase
                            else config.friction
                        )

                        decay_factor = current_friction ** frame_scale

                        if current_friction == 1.0:
                            frame_distance = start_velocity * frame_scale
                        else:
                            frame_distance = (
                                start_velocity
                                * current_friction
                                * (1.0 - decay_factor)
                                / (1.0 - current_friction)
                            )

                        state.velocity = start_velocity * decay_factor

                    state.accumulator += frame_distance

                    if abs(state.accumulator) >= active_min_delta:
                        if is_tail_phase:
                            base_max_delta = config.tail_max_delta_per_tick
                        else:
                            base_max_delta = min(
                                config.max_boosted_delta_per_tick,
                                max(
                                    config.max_delta_per_tick,
                                    int(abs(state.velocity)),
                                ),
                            )

                        # Preserve roughly the same maximum output per second
                        # when the worker rate changes.
                        dynamic_max_delta = max(
                            1,
                            int(round(base_max_delta * frame_scale)),
                        )

                        send_delta = int(
                            clamp(
                                state.accumulator,
                                -dynamic_max_delta,
                                dynamic_max_delta,
                            )
                        )
                        state.accumulator -= send_delta

        if send_delta != 0:
            send_wheel_delta(send_delta)

        # Absolute-time scheduling avoids adding processing time to every frame.
        remaining = next_tick - time.perf_counter()
        if remaining > 0:
            time.sleep(remaining)
        else:
            # Do not replay a backlog of missed ticks after a scheduling stall.
            next_tick = time.perf_counter()
# ============================================================
# Hook install / message loop
# ============================================================

def install_mouse_hook() -> ctypes.c_void_p:
    module_handle = kernel32.GetModuleHandleW(None)

    handle = user32.SetWindowsHookExW(
        WH_MOUSE_LL,
        ctypes.cast(mouse_hook_proc, ctypes.c_void_p),
        module_handle,
        0,
    )

    if not handle:
        handle = user32.SetWindowsHookExW(
            WH_MOUSE_LL,
            ctypes.cast(mouse_hook_proc, ctypes.c_void_p),
            None,
            0,
        )

    if not handle:
        raise RuntimeError(f"Failed to install mouse hook. {get_last_error_message()}")

    return handle


def install_keyboard_hook() -> ctypes.c_void_p:
    module_handle = kernel32.GetModuleHandleW(None)

    handle = user32.SetWindowsHookExW(
        WH_KEYBOARD_LL,
        ctypes.cast(keyboard_hook_proc, ctypes.c_void_p),
        module_handle,
        0,
    )

    if not handle:
        handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            ctypes.cast(keyboard_hook_proc, ctypes.c_void_p),
            None,
            0,
        )

    if not handle:
        raise RuntimeError(f"Failed to install keyboard hook. {get_last_error_message()}")

    return handle

def pump_windows_messages() -> None:
    msg = MSG()

    while state.running:
        while user32.PeekMessageW(
            ctypes.byref(msg),
            None,
            0,
            0,
            PM_REMOVE,
        ):
            if msg.message == WM_QUIT:
                state.running = False
                break

            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        time.sleep(0.01)


# ============================================================
# CLI
# ============================================================

def parse_args() -> Config:
    parser = argparse.ArgumentParser(
        prog="MouseSmoothWheel",
        description="Adds lightweight inertia-style scrolling to a regular mouse wheel.",
    )

    parser.add_argument(
        "--stop-velocity",
        type=float,
        default=0.5,
        help="Velocity threshold for stopping inertia. Default: 0.5",
    )

    for definition in SETTING_DEFINITIONS:
        parser.add_argument(
            "--" + definition["key"].replace("_", "-"),
            type=definition["type"],
            default=None,
            help=f"Override {definition['label']} for this run.",
        )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console messages.",
    )

    args = parser.parse_args()

    new_config = Config(
        stop_velocity=max(0.0, args.stop_velocity),
        quiet=args.quiet,
    )

    load_saved_settings(new_config)

    for definition in SETTING_DEFINITIONS:
        key = definition["key"]
        arg_name = key.replace("-", "_")
        override_value = getattr(args, arg_name, None)

        if override_value is None:
            continue

        try:
            value = parse_setting_value(definition, str(override_value))
        except ValueError as exc:
            parser.error(str(exc))

        setattr(new_config, key, value)

    if new_config.repeat_wheel_boost_max < new_config.repeat_wheel_boost:
        parser.error("Max repeat boost must be greater than or equal to Repeat wheel boost.")

    return new_config

def print_banner() -> None:
    if config.quiet:
        return

    print("MouseSmoothWheel is running.")
    print("Right-click the tray icon to open Settings or Exit.")
    print("Double-click the tray icon to open Settings.")
    print("Press Ctrl + C in this terminal to stop.")
    print()
    print("Current settings:")
    print(f"  no_inertia_events_up   = {config.no_inertia_events_up}")
    print(f"  no_inertia_events_down = {config.no_inertia_events_down}")
    print(f"  gain                   = {config.gain}")
    print(f"  friction               = {config.friction}")
    print(f"  initial_inertia_boost  = {config.initial_inertia_boost}")
    print(f"  repeat_wheel_boost     = {config.repeat_wheel_boost}")
    print(f"  repeat_boost_step      = {config.repeat_wheel_boost_step}")
    print(f"  repeat_boost_max       = {config.repeat_wheel_boost_max}")
    print(f"  max_delta_per_tick     = {config.max_delta_per_tick}")
    print(f"  tail_friction          = {config.tail_friction}")
    print(f"  tick_rate              = {config.tick_rate}")
    print(f"  stop_velocity          = {config.stop_velocity}")
    print(f"  settings_path          = {get_settings_path()}")
    print()

def main() -> int:
    global config
    global hook_handle
    global keyboard_hook_handle
    global tray_app

    config = parse_args()
    print_banner()

    worker = threading.Thread(
        target=inertia_worker,
        name="MouseSmoothWheelInertiaWorker",
        daemon=True,
    )
    worker.start()

    try:
        tray_app = TrayApp()
        tray_app.create()

        hook_handle = install_mouse_hook()
        keyboard_hook_handle = install_keyboard_hook()
        pump_windows_messages()

    except KeyboardInterrupt:
        if not config.quiet:
            print("\nStopping MouseSmoothWheel...")

    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    finally:
        state.running = False

        if hook_handle:
            user32.UnhookWindowsHookEx(hook_handle)
            hook_handle = None

        if keyboard_hook_handle:
            user32.UnhookWindowsHookEx(keyboard_hook_handle)
            keyboard_hook_handle = None

        if tray_app:
            tray_app.destroy()
            tray_app = None

        worker.join(timeout=0.5)

        if not config.quiet:
            print("Stopped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())