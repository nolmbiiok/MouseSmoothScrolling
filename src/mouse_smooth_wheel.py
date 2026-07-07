r"""
MouseSmoothWheel

Windows-only prototype.
- Global mouse wheel hook
- Inertia-style synthetic wheel tail
- Native Windows tray icon with preset menu and Exit
- No external Python dependencies

Run:
    python src\mouse_smooth_wheel.py

Stop:
    Right-click tray icon -> Exit
    or Ctrl + C in the terminal
"""

import argparse
import ctypes
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass


if sys.platform != "win32":
    raise SystemExit("MouseSmoothWheel currently supports Windows only.")


# ============================================================
# Windows constants
# ============================================================


GA_ROOT = 2

WH_MOUSE_LL = 14
HC_ACTION = 0

WH_KEYBOARD_LL = 13

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

LLKHF_LOWER_IL_INJECTED = 0x00000002
LLKHF_INJECTED = 0x00000010


WM_MOUSEWHEEL = 0x020A
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

ID_SCROLL_LOW = 1001
ID_SCROLL_NORMAL = 1002
ID_SCROLL_STRONG = 1003
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
    gain: float = 0.14
    friction: float = 0.90
    tick_rate: int = 120
    stop_velocity: float = 0.5
    preset: str = "Low"
    quiet: bool = False

    keyboard_soft_stop_friction: float = 0.68
    keyboard_soft_stop_velocity_scale: float = 0.35

    same_direction_kick_enabled: bool = False
    same_direction_kick_multiplier: float = 0.0
    same_direction_kick_max_delta: int = 0

    repeat_wheel_boost: float = 6.0
    repeat_wheel_boost_step: float = 2.0
    repeat_wheel_boost_max: float = 16.0
    repeat_wheel_chain_seconds: float = 0.55
    max_velocity: float = 12000.0
    max_boosted_delta_per_tick: int = 1200


    intercept_physical_wheel: bool = True

    smooth_step_gain: float = 0.12
    smooth_step_friction: float = 0.72
    smooth_min_send_delta: int = 4
    smooth_max_delta_per_tick: int = 36

    no_inertia_events: int = 3
    gesture_reset_seconds: float = 0.10

    cancel_on_window_change: bool = True


    tail_velocity_threshold: float = 20.0
    tail_friction: float = 0.92
    tail_min_send_delta: int = 1
    tail_max_delta_per_tick: int = 24



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
    short_smoothing: bool = False

    wheel_event_count: int = 0
    last_wheel_time: float = 0.0


PRESETS = {
    "Low": {
        "gain": 0.04,
        "friction": 0.94,
        "min_send_delta": 4,
        "max_delta_per_tick": 36,
    },
    "Normal": {
        "gain": 0.04,
        "friction": 0.94,
        "min_send_delta": 4,
        "max_delta_per_tick": 36,
    },
    "Strong": {
        "gain": 0.08,
        "friction": 0.95,
        "min_send_delta": 4,
        "max_delta_per_tick": 36,
    }
}

COMMAND_TO_PRESET = {
    ID_SCROLL_LOW: "Low",
    ID_SCROLL_NORMAL: "Normal",
    ID_SCROLL_STRONG: "Strong",
}

config = Config()
state = RuntimeState()
state_lock = threading.Lock()
hook_handle = None
keyboard_hook_handle = None
tray_app = None


# ============================================================
# Utility functions
# ============================================================

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
    state.short_smoothing = False

    state.repeat_boost_count = 0
    state.last_repeat_boost_time = 0.0
    state.last_wheel_direction = 0

def has_active_inertia_locked() -> bool:
    active_min_delta = (
        config.smooth_min_send_delta
        if state.short_smoothing
        else config.min_send_delta
    )

    return (
        abs(state.velocity) >= config.stop_velocity
        or abs(state.accumulator) >= active_min_delta
    )


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


def apply_preset(name: str) -> None:
    if name not in PRESETS:
        return

    values = PRESETS[name]

    with state_lock:
        config.preset = name
        config.gain = values["gain"]
        config.friction = values["friction"]
        config.min_send_delta = values["min_send_delta"]
        config.max_delta_per_tick = values["max_delta_per_tick"]

        # Preset switch should feel immediate and predictable.
        state.velocity = 0.0
        state.accumulator = 0.0

    if not config.quiet:
        print(
            f"Preset changed: {name} "
            f"(gain={config.gain}, friction={config.friction})"
        )


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
        wndclass.hIcon = None
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
        icon_resource = ctypes.cast(ctypes.c_void_p(IDI_APPLICATION), wintypes.LPCWSTR)
        icon_handle = user32.LoadIconW(None, icon_resource)

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = icon_handle
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
                self._cycle_preset()
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
            self._append_preset_menu_item(menu, ID_SCROLL_LOW, "Low", "Low")
            self._append_preset_menu_item(menu, ID_SCROLL_NORMAL, "Normal", "Normal")
            self._append_preset_menu_item(menu, ID_SCROLL_STRONG, "Strong", "Strong")

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

    def _append_preset_menu_item(
        self,
        menu,
        command_id: int,
        text: str,
        preset_name: str,
    ) -> None:
        checked = MF_CHECKED if config.preset == preset_name else MF_UNCHECKED
        user32.AppendMenuW(menu, MF_STRING | checked, command_id, text)

    def _handle_command(self, command_id: int) -> None:
        if command_id in COMMAND_TO_PRESET:
            apply_preset(COMMAND_TO_PRESET[command_id])
            return

        if command_id == ID_EXIT:
            state.running = False
            self._remove_tray_icon()
            user32.PostQuitMessage(0)
            return

    def _cycle_preset(self) -> None:
        order = ["Low", "Normal", "Strong"]

        try:
            index = order.index(config.preset)
        except ValueError:
            index = 1

        next_name = order[(index + 1) % len(order)]
        apply_preset(next_name)


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
                # not "first 3 no-inertia events" again.
                if is_new_gesture and not was_inertia_active:
                    state.wheel_event_count = 0
                    state.velocity = 0.0
                    state.accumulator = 0.0
                    state.short_smoothing = False

                # If inertia is alive, force the counter past the no-inertia phase.
                if was_inertia_active:
                    state.wheel_event_count = max(
                        state.wheel_event_count,
                        config.no_inertia_events,
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
                    and state.wheel_event_count <= config.no_inertia_events
                )

                if is_no_inertia_phase:
                    # First N wheel events pass through as normal physical wheel input.
                    # No inertia, no smoothing, no synthetic wheel.
                    state.short_smoothing = False
                    state.velocity = 0.0
                    state.accumulator = 0.0

                    return user32.CallNextHookEx(hook_handle, n_code, w_param, l_param)
                else:
                    state.short_smoothing = False

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

                    if was_inertia_active and same_direction:
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
    tick_interval = 1.0 / max(1, config.tick_rate)

    while state.running:
        send_delta = 0

        with state_lock:
            inertia_min_delta = (
                config.tail_min_send_delta
                if (
                    not state.short_smoothing
                    and abs(state.velocity) < config.tail_velocity_threshold
                )
                else (
                    config.smooth_min_send_delta
                    if state.short_smoothing
                    else config.min_send_delta
                )
            )

            has_active_inertia = (
                abs(state.velocity) >= config.stop_velocity
                or abs(state.accumulator) >= inertia_min_delta
            )

        # Target window guard:
        # If the mouse cursor moved to another top-level window during inertia,
        # stop the inertia before sending any synthetic wheel input.
        if has_active_inertia:
            with state_lock:
                should_check_window = bool(state.target_hwnd or state.target_root_hwnd)

            if should_check_window and should_cancel_inertia_for_window_change():
                with state_lock:
                    cancel_inertia()

                time.sleep(tick_interval)
                continue

        with state_lock:
            is_tail_phase = (
                not state.short_smoothing
                and not state.soft_stopping
                and abs(state.velocity) < config.tail_velocity_threshold
            )

            if state.short_smoothing:
                active_min_delta = config.smooth_min_send_delta
            elif is_tail_phase:
                active_min_delta = config.tail_min_send_delta
            else:
                active_min_delta = config.min_send_delta

            if (
                abs(state.velocity) < config.stop_velocity
                and abs(state.accumulator) < active_min_delta
            ):
                state.velocity = 0.0
                state.accumulator = 0.0
                state.soft_stopping = False
                state.short_smoothing = False
            else:
                if state.soft_stopping:
                    # Keyboard input occurred during inertia.
                    # Do not send synthetic wheel anymore, because it may combine
                    # with Ctrl/Shift/Alt/etc. Just decay internally.
                    state.velocity *= config.keyboard_soft_stop_friction
                    state.accumulator = 0.0
                    send_delta = 0
                else:
                    if state.short_smoothing:
                        current_friction = config.smooth_step_friction
                    elif is_tail_phase:
                        current_friction = config.tail_friction
                    else:
                        current_friction = config.friction

                    state.velocity *= current_friction
                    state.accumulator += state.velocity

                    if abs(state.accumulator) >= active_min_delta:
                        if state.short_smoothing:
                            dynamic_max_delta = config.smooth_max_delta_per_tick
                        elif is_tail_phase:
                            dynamic_max_delta = config.tail_max_delta_per_tick
                        else:
                            dynamic_max_delta = min(
                                config.max_boosted_delta_per_tick,
                                max(
                                    config.max_delta_per_tick,
                                    int(abs(state.velocity)),
                                ),
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

        time.sleep(tick_interval)


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
        "--preset",
        choices=["Low", "Normal", "Strong"],
        default="Low",
        help="Initial inertia preset. Default: Low",
    )

    parser.add_argument(
        "--tick-rate",
        type=int,
        default=120,
        help="Worker update rate per second. Default: 120",
    )

    parser.add_argument(
        "--stop-velocity",
        type=float,
        default=0.5,
        help="Velocity threshold for stopping inertia. Default: 0.5",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress console messages.",
    )

    args = parser.parse_args()

    new_config = Config(
        tick_rate=max(1, args.tick_rate),
        stop_velocity=max(0.0, args.stop_velocity),
        preset=args.preset,
        quiet=args.quiet,
    )

    preset_values = PRESETS[args.preset]
    new_config.gain = preset_values["gain"]
    new_config.friction = preset_values["friction"]
    new_config.min_send_delta = preset_values["min_send_delta"]
    new_config.max_delta_per_tick = preset_values["max_delta_per_tick"]

    return new_config


def print_banner() -> None:
    if config.quiet:
        return

    print("MouseSmoothWheel is running.")
    print("Right-click the tray icon to change scroll tail or exit.")
    print("Double-click the tray icon to cycle preset.")
    print("Press Ctrl + C in this terminal to stop.")
    print()
    print("Current settings:")
    print(f"  preset             = {config.preset}")
    print(f"  gain               = {config.gain}")
    print(f"  friction           = {config.friction}")
    print(f"  tick_rate          = {config.tick_rate}")
    print(f"  min_send_delta     = {config.min_send_delta}")
    print(f"  max_delta_per_tick = {config.max_delta_per_tick}")
    print(f"  stop_velocity      = {config.stop_velocity}")
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