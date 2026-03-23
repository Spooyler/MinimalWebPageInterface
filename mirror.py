import ctypes
import ctypes.wintypes
import threading
import os

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
kernel32 = ctypes.windll.kernel32

# Make process per-monitor DPI aware — ensures our windows use physical pixels
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

# 64-bit safe types
LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t

# Set DefWindowProcW types for 64-bit safety
user32.DefWindowProcW.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT

# DWM function signatures
dwmapi.DwmRegisterThumbnail.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.HANDLE)]
dwmapi.DwmRegisterThumbnail.restype = ctypes.c_long
dwmapi.DwmUpdateThumbnailProperties.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_void_p]
dwmapi.DwmUpdateThumbnailProperties.restype = ctypes.c_long
dwmapi.DwmUnregisterThumbnail.argtypes = [ctypes.wintypes.HANDLE]
dwmapi.DwmUnregisterThumbnail.restype = ctypes.c_long

# Additional Win32 function signatures
user32.IsWindowVisible.restype = ctypes.wintypes.BOOL
user32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
user32.GetWindow.restype = ctypes.wintypes.HWND
user32.GetWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]

user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = ctypes.wintypes.BOOL


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
    _fields_ = [
        ("dwFlags", ctypes.wintypes.DWORD),
        ("rcDestination", RECT),
        ("rcSource", RECT),
        ("opacity", ctypes.c_byte),
        ("fVisible", ctypes.wintypes.BOOL),
        ("fSourceClientAreaOnly", ctypes.wintypes.BOOL),
    ]


DWM_TNP_RECTDESTINATION = 0x00000001
DWM_TNP_RECTSOURCE = 0x00000002
DWM_TNP_VISIBLE = 0x00000008
DWM_TNP_SOURCECLIENTAREAONLY = 0x00000010

WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
GW_OWNER = 4
GWL_EXSTYLE = -20
SW_RESTORE = 9
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001
COLOR_BACKGROUND = 1
IDC_ARROW = 32512

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.wintypes.HWND, ctypes.c_uint, WPARAM, LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.wintypes.HANDLE),
        ("hbrBackground", ctypes.wintypes.HBRUSH),
        ("lpszMenuName", ctypes.wintypes.LPCWSTR),
        ("lpszClassName", ctypes.wintypes.LPCWSTR),
        ("hIconSm", ctypes.wintypes.HICON),
    ]


def _wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


_wnd_proc_cb = WNDPROC(_wnd_proc)
_class_registered = False
_CLASS_NAME = "MirrorWindowClass"


def _ensure_class_registered():
    global _class_registered
    if _class_registered:
        return
    hinstance = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.style = CS_HREDRAW | CS_VREDRAW
    wc.lpfnWndProc = _wnd_proc_cb
    wc.hInstance = hinstance
    wc.hCursor = user32.LoadCursorW(None, IDC_ARROW)
    wc.hbrBackground = ctypes.wintypes.HBRUSH(COLOR_BACKGROUND + 1)
    wc.lpszClassName = _CLASS_NAME
    user32.RegisterClassExW(ctypes.byref(wc))
    _class_registered = True


def find_hwnd_by_title(title):
    result = []
    our_pid = os.getpid()

    @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_callback(hwnd, _lparam):
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == our_pid:
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if buf.value == title:
                    result.append(hwnd)
        return True

    user32.EnumWindows(enum_callback, 0)
    return result[0] if result else None


def bring_to_front(hwnd):
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)


def get_system_windows():
    windows = []
    our_pid = os.getpid()
    DWMWA_CLOAKED = 14

    @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if (ex_style & WS_EX_TOOLWINDOW) and not (ex_style & WS_EX_APPWINDOW):
            return True
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value != 0:
            return True
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if (rect.right - rect.left) <= 0 or (rect.bottom - rect.top) <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if title in ("Program Manager", "MSCTFIME UI", "Default IME", ""):
            return True
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        windows.append({
            "hwnd_int": int(hwnd) if isinstance(hwnd, int) else ctypes.cast(hwnd, ctypes.c_void_p).value or 0,
            "title": title,
            "is_ours": pid.value == our_pid,
        })
        return True

    user32.EnumWindows(enum_callback, 0)
    return windows


def get_monitors():
    monitors = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.wintypes.HMONITOR, ctypes.wintypes.HDC, ctypes.POINTER(RECT), ctypes.wintypes.LPARAM)
    def enum_callback(hmonitor, hdc, lprect, lparam):
        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", ctypes.wintypes.DWORD),
                ("szDevice", ctypes.c_wchar * 32),
            ]
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
        r = info.rcMonitor
        monitors.append({
            "name": info.szDevice.rstrip("\x00"),
            "x": r.left, "y": r.top,
            "width": r.right - r.left, "height": r.bottom - r.top,
            "is_primary": bool(info.dwFlags & 1),
        })
        return True

    user32.EnumDisplayMonitors(None, None, enum_callback, 0)
    return monitors


class MirrorWindow:
    def __init__(self, source_hwnd, monitor, crop_rect=None):
        self._source_hwnd = source_hwnd
        self._monitor = monitor
        self._crop_rect = crop_rect  # (left, top, right, bottom) or None
        self._hwnd = None
        self._thumbnail_id = ctypes.wintypes.HANDLE()
        self._thread = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)

    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()

    def _run(self):
        _ensure_class_registered()
        hinstance = kernel32.GetModuleHandleW(None)
        m = self._monitor

        self._hwnd = user32.CreateWindowExW(
            WS_EX_TOOLWINDOW, _CLASS_NAME, "Mirror", WS_POPUP | WS_VISIBLE,
            m["x"], m["y"], m["width"], m["height"],
            None, None, hinstance, None,
        )
        if not self._hwnd:
            return

        source = self._source_hwnd
        if isinstance(source, int):
            source = ctypes.wintypes.HWND(source)

        hr = dwmapi.DwmRegisterThumbnail(self._hwnd, source, ctypes.byref(self._thumbnail_id))
        if hr != 0:
            user32.DestroyWindow(self._hwnd)
            return

        # Determine source dimensions (crop region or full window)
        if self._crop_rect:
            src_w = self._crop_rect[2] - self._crop_rect[0]
            src_h = self._crop_rect[3] - self._crop_rect[1]
        else:
            src_size = SIZE()
            dwmapi.DwmQueryThumbnailSourceSize(self._thumbnail_id, ctypes.byref(src_size))
            src_w = src_size.cx
            src_h = src_size.cy

        dest_w = m["width"]
        dest_h = m["height"]

        # Calculate destination rect preserving aspect ratio (letterbox)
        if src_w > 0 and src_h > 0:
            scale = min(dest_w / src_w, dest_h / src_h)
            scaled_w = int(src_w * scale)
            scaled_h = int(src_h * scale)
            offset_x = (dest_w - scaled_w) // 2
            offset_y = (dest_h - scaled_h) // 2
        else:
            offset_x, offset_y = 0, 0
            scaled_w, scaled_h = dest_w, dest_h

        props = DWM_THUMBNAIL_PROPERTIES()
        props.dwFlags = DWM_TNP_RECTDESTINATION | DWM_TNP_VISIBLE | DWM_TNP_SOURCECLIENTAREAONLY
        props.rcDestination = RECT(offset_x, offset_y, offset_x + scaled_w, offset_y + scaled_h)
        props.fVisible = True
        props.fSourceClientAreaOnly = True

        if self._crop_rect:
            props.dwFlags |= DWM_TNP_RECTSOURCE
            props.rcSource = RECT(*self._crop_rect)

        dwmapi.DwmUpdateThumbnailProperties(self._thumbnail_id, ctypes.byref(props))

        user32.ShowWindow(self._hwnd, 3)
        user32.UpdateWindow(self._hwnd)

        # Message pump
        msg = ctypes.wintypes.MSG()
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup
        if self._thumbnail_id.value:
            dwmapi.DwmUnregisterThumbnail(self._thumbnail_id)
            self._thumbnail_id = ctypes.wintypes.HANDLE()
        if self._hwnd:
            try:
                user32.DestroyWindow(self._hwnd)
            except Exception:
                pass
            self._hwnd = None
