import ctypes
import ctypes.wintypes
import threading
import os

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
kernel32 = ctypes.windll.kernel32

# 64-bit safe types
LRESULT = ctypes.c_ssize_t  # pointer-sized signed int
WPARAM = ctypes.c_size_t    # pointer-sized unsigned int
LPARAM = ctypes.c_ssize_t   # pointer-sized signed int

# Set DefWindowProcW types for 64-bit safety
user32.DefWindowProcW.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


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
DWM_TNP_VISIBLE = 0x00000008
DWM_TNP_SOURCECLIENTAREAONLY = 0x00000010

WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOOLWINDOW = 0x00000080  # hide from taskbar
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_SIZE = 0x0005
CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001
COLOR_BACKGROUND = 1
CW_USEDEFAULT = 0x80000000
IDC_ARROW = 32512

WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    ctypes.wintypes.HWND,
    ctypes.c_uint,
    WPARAM,
    LPARAM,
)


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
    """Find a window handle by its exact title within our process."""
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


def get_monitors():
    """Return list of monitor dicts: {name, x, y, width, height, is_primary}."""
    monitors = []

    @ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.wintypes.HMONITOR,
        ctypes.wintypes.HDC,
        ctypes.POINTER(RECT),
        ctypes.wintypes.LPARAM,
    )
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
            "x": r.left,
            "y": r.top,
            "width": r.right - r.left,
            "height": r.bottom - r.top,
            "is_primary": bool(info.dwFlags & 1),
        })
        return True

    user32.EnumDisplayMonitors(None, None, enum_callback, 0)
    return monitors


class MirrorWindow:
    def __init__(self, source_hwnd, monitor):
        self._source_hwnd = source_hwnd
        self._monitor = monitor  # dict with x, y, width, height
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
            WS_EX_TOOLWINDOW,
            _CLASS_NAME,
            "Mirror",
            WS_POPUP | WS_VISIBLE,
            m["x"], m["y"], m["width"], m["height"],
            None, None, hinstance, None,
        )

        if not self._hwnd:
            return

        # Register DWM thumbnail
        hr = dwmapi.DwmRegisterThumbnail(
            self._hwnd, self._source_hwnd, ctypes.byref(self._thumbnail_id)
        )
        if hr != 0:
            user32.DestroyWindow(self._hwnd)
            return

        # Set thumbnail to fill the mirror window
        props = DWM_THUMBNAIL_PROPERTIES()
        props.dwFlags = DWM_TNP_RECTDESTINATION | DWM_TNP_VISIBLE | DWM_TNP_SOURCECLIENTAREAONLY
        props.rcDestination = RECT(0, 0, m["width"], m["height"])
        props.fVisible = True
        props.fSourceClientAreaOnly = True
        dwmapi.DwmUpdateThumbnailProperties(self._thumbnail_id, ctypes.byref(props))

        user32.ShowWindow(self._hwnd, 3)  # SW_MAXIMIZE — ensure fullscreen
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
