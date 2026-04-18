import uuid
import json
import threading
import os
import ctypes
import webview
import psutil
from mirror import find_hwnd_by_title, get_monitors, MirrorWindow, get_system_windows, bring_to_front

import sys as _sys

# When running as a PyInstaller exe, store config next to the exe (writable).
# When running from source, store it next to this file.
if getattr(_sys, "frozen", False):
    _BASE_DIR = os.path.dirname(os.path.abspath(_sys.executable))
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_PRESETS_FILE = os.path.join(_BASE_DIR, "presets.json")
_CONFIG_FILE = os.path.join(_BASE_DIR, "config.json")


class WindowManager:
    def __init__(self):
        self._windows = {}
        self._window_order = []
        self._external_mirrors = {}
        self._manager_window = None
        self._lock = threading.Lock()
        self._closing_programmatically = set()
        self._shutting_down = False
        self._tray_mode = False
        self._process = psutil.Process(os.getpid())
        self._start_resource_monitor()

    def set_manager_window(self, window):
        self._manager_window = window

    # ── Config ──

    def get_config(self, key):
        try:
            if os.path.exists(_CONFIG_FILE):
                with open(_CONFIG_FILE, "r") as f:
                    return json.load(f).get(key)
        except (json.JSONDecodeError, IOError):
            pass
        return None

    def set_config(self, key, value):
        config = {}
        try:
            if os.path.exists(_CONFIG_FILE):
                with open(_CONFIG_FILE, "r") as f:
                    config = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
        config[key] = value
        with open(_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        return True

    # ── Webpage management ──

    def add_url(self, url, fullscreen=True, fps_limit=0):
        url = self._normalize_url(url)
        window_id = uuid.uuid4().hex[:8]

        if fullscreen:
            window = webview.create_window(title=url, url=url, js_api=self, fullscreen=True)
        else:
            window = webview.create_window(title=url, url=url, js_api=self, width=1024, height=768, resizable=True)

        def on_loaded():
            try:
                js_parts = []
                if fps_limit > 0:
                    js_parts.append("""
                        if (typeof canvas !== 'undefined' && canvas.app && canvas.app.ticker) {{
                            canvas.app.ticker.maxFPS = {fps};
                        }}
                        var _origRAF = window.requestAnimationFrame;
                        var _lastFrame = 0;
                        var _interval = 1000 / {fps};
                        window.requestAnimationFrame = function(cb) {{
                            return _origRAF(function(ts) {{
                                if (ts - _lastFrame >= _interval) {{ _lastFrame = ts; cb(ts); }}
                                else {{ _origRAF(cb); }}
                            }});
                        }};
                    """.format(fps=fps_limit))
                js_parts.append("""
                    document.addEventListener('keydown', function(e) {
                        if (e.key === 'Escape') { window.pywebview.api.toggle_fullscreen_for_caller(); }
                    });
                """)
                if js_parts:
                    window.evaluate_js("(function() {" + "\n".join(js_parts) + "})();")
            except Exception:
                pass
        window.events.loaded += on_loaded
        window.events.closed += lambda: self._on_webpage_closed(window_id)

        with self._lock:
            self._windows[window_id] = {"window": window, "url": url, "mirror": None, "fullscreen": fullscreen}
            self._window_order.append(window_id)

        return {"id": window_id, "url": url}

    def close_page(self, window_id):
        with self._lock:
            entry = self._windows.pop(window_id, None)
            ext = self._external_mirrors.pop(window_id, None)
            if window_id in self._window_order:
                self._window_order.remove(window_id)
            if entry:
                self._closing_programmatically.add(window_id)
        if entry:
            if entry["mirror"]:
                entry["mirror"].stop()
            try:
                entry["window"].destroy()
            except Exception:
                pass
        if ext:
            ext["mirror"].stop()
        return True

    def get_open_pages(self):
        with self._lock:
            pages = []
            for wid in self._window_order:
                entry = self._windows.get(wid)
                if not entry:
                    continue
                title = entry["url"]
                try:
                    title = entry["window"].title or entry["url"]
                except Exception:
                    pass
                pages.append({
                    "id": wid, "url": entry["url"], "title": title,
                    "mirrored": entry["mirror"] is not None and entry["mirror"].is_alive(),
                    "fullscreen": entry.get("fullscreen", True), "external": False,
                })
            for wid, ext in self._external_mirrors.items():
                pages.append({
                    "id": wid, "url": "", "title": ext["title"],
                    "mirrored": ext["mirror"].is_alive(),
                    "fullscreen": False, "external": True,
                })
            return pages

    def focus_page(self, window_id):
        with self._lock:
            entry = self._windows.get(window_id)
            ext = self._external_mirrors.get(window_id)
        if entry:
            hwnd = find_hwnd_by_title(entry["window"].title or entry["url"])
            if hwnd:
                bring_to_front(hwnd)
                return True
        if ext:
            bring_to_front(ctypes.wintypes.HWND(ext["hwnd_int"]))
            return True
        return False

    def toggle_fullscreen_page(self, window_id):
        with self._lock:
            entry = self._windows.get(window_id)
            if not entry:
                return False
        entry["window"].toggle_fullscreen()
        entry["fullscreen"] = not entry.get("fullscreen", True)
        self._refresh_manager_ui()
        return True

    def toggle_fullscreen_for_caller(self):
        fg = ctypes.windll.user32.GetForegroundWindow()
        with self._lock:
            for wid, entry in self._windows.items():
                hwnd = find_hwnd_by_title(entry["window"].title or entry["url"])
                if hwnd and int(hwnd) == int(fg):
                    entry["window"].toggle_fullscreen()
                    entry["fullscreen"] = not entry.get("fullscreen", True)
                    self._refresh_manager_ui()
                    return True
        return False

    def reorder_windows(self, from_id, to_id):
        with self._lock:
            if from_id in self._window_order and to_id in self._window_order:
                self._window_order.remove(from_id)
                idx = self._window_order.index(to_id)
                self._window_order.insert(idx, from_id)
                return True
        return False

    # ── Screen & mirror ──

    def get_screens(self):
        monitors = get_monitors()
        return [{"index": i, "name": m["name"], "width": m["width"], "height": m["height"], "is_primary": m["is_primary"]} for i, m in enumerate(monitors)]

    def mirror_page(self, window_id, screen_index, crop_rect=None):
        monitors = get_monitors()
        if screen_index < 0 or screen_index >= len(monitors):
            return False
        with self._lock:
            entry = self._windows.get(window_id)
            if not entry:
                return False
            if entry["mirror"] and entry["mirror"].is_alive():
                entry["mirror"].stop()
                entry["mirror"] = None
        source_hwnd = find_hwnd_by_title(entry["window"].title or entry["url"])
        if not source_hwnd:
            return False
        crop = tuple(int(v) for v in crop_rect) if crop_rect else None
        mirror = MirrorWindow(source_hwnd, monitors[screen_index], crop_rect=crop)
        mirror.start()
        with self._lock:
            if window_id in self._windows:
                self._windows[window_id]["mirror"] = mirror
        return True

    def stop_mirror(self, window_id):
        with self._lock:
            entry = self._windows.get(window_id)
            ext = self._external_mirrors.get(window_id)
        if entry and entry["mirror"]:
            entry["mirror"].stop()
            entry["mirror"] = None
            return True
        if ext:
            ext["mirror"].stop()
            with self._lock:
                self._external_mirrors.pop(window_id, None)
            return True
        return False

    # ── External window mirroring ──

    def get_external_windows(self):
        return [{"hwnd_int": w["hwnd_int"], "title": w["title"]} for w in get_system_windows() if not w["is_ours"]]

    def mirror_external(self, hwnd_int, screen_index, crop_rect=None):
        monitors = get_monitors()
        if screen_index < 0 or screen_index >= len(monitors):
            return False
        hwnd_int = int(hwnd_int)
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd_int)
        title = "External Window"
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd_int, buf, length + 1)
            title = buf.value
        crop = tuple(int(v) for v in crop_rect) if crop_rect else None
        mirror_id = "ext_" + uuid.uuid4().hex[:8]
        mirror = MirrorWindow(hwnd_int, monitors[screen_index], crop_rect=crop)
        mirror.start()
        with self._lock:
            self._external_mirrors[mirror_id] = {"mirror": mirror, "hwnd_int": hwnd_int, "title": title}
        return True

    # ── Presets ──

    def get_presets(self):
        if not os.path.exists(_PRESETS_FILE):
            return []
        try:
            with open(_PRESETS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save_presets(self, presets):
        with open(_PRESETS_FILE, "w") as f:
            json.dump(presets, f, indent=2)

    def save_preset(self, name, url, fullscreen=True, fps_limit=0):
        url = self._normalize_url(url)
        presets = self.get_presets()
        presets.append({"name": name, "url": url, "fullscreen": fullscreen, "fps_limit": fps_limit, "auto_launch": False})
        self._save_presets(presets)
        return True

    def delete_preset(self, index):
        presets = self.get_presets()
        if 0 <= index < len(presets):
            presets.pop(index)
            self._save_presets(presets)
            return True
        return False

    def open_preset(self, index):
        presets = self.get_presets()
        if 0 <= index < len(presets):
            p = presets[index]
            return self.add_url(p["url"], p.get("fullscreen", True), p.get("fps_limit", 0))
        return None

    def toggle_preset_auto_launch(self, index):
        presets = self.get_presets()
        if 0 <= index < len(presets):
            presets[index]["auto_launch"] = not presets[index].get("auto_launch", False)
            self._save_presets(presets)
            return True
        return False

    def reorder_presets(self, from_index, to_index):
        presets = self.get_presets()
        if 0 <= from_index < len(presets) and 0 <= to_index < len(presets):
            item = presets.pop(from_index)
            presets.insert(to_index, item)
            self._save_presets(presets)
            return True
        return False

    def auto_launch_presets(self):
        for p in self.get_presets():
            if p.get("auto_launch", False):
                self.add_url(p["url"], p.get("fullscreen", True), p.get("fps_limit", 0))

    # ── Tray ──

    def minimize_to_tray(self):
        if self._manager_window:
            self._manager_window.hide()

    def show_from_tray(self):
        if self._manager_window:
            self._manager_window.show()

    def shutdown(self):
        self._shutting_down = True
        with self._lock:
            windows = list(self._windows.values())
            ext_mirrors = list(self._external_mirrors.values())
            self._windows.clear()
            self._external_mirrors.clear()
            self._window_order.clear()
        for entry in windows:
            if entry["mirror"]:
                entry["mirror"].stop()
            try:
                entry["window"].destroy()
            except Exception:
                pass
        for ext in ext_mirrors:
            ext["mirror"].stop()
        if self._manager_window:
            try:
                self._manager_window.destroy()
            except Exception:
                pass

    # ── Resource monitoring ──

    def get_resource_usage(self):
        try:
            cpu = self._process.cpu_percent(interval=0)
            mem = self._process.memory_info()
            mem_mb = mem.rss / (1024 * 1024)
            for child in self._process.children(recursive=True):
                try:
                    cpu += child.cpu_percent(interval=0)
                    mem_mb += child.memory_info().rss / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return {"cpu": round(cpu, 1), "ram": round(mem_mb, 1), "gpu": self._get_gpu_usage()}
        except Exception:
            return {"cpu": 0, "ram": 0, "gpu": None}

    def _get_gpu_usage(self):
        try:
            import subprocess
            result = subprocess.run(
                ["typeperf", "\\GPU Engine(*)\\Utilization Percentage", "-sc", "1"],
                capture_output=True, text=True, timeout=15, creationflags=0x08000000,
            )
            if result.returncode != 0 or not result.stdout:
                return None
            lines = result.stdout.strip().splitlines()
            if len(lines) < 2:
                return None
            headers = lines[0].split('","')
            values = lines[1].split('","')
            total = 0.0
            for i, hdr in enumerate(headers):
                if "engtype_3D" in hdr or "engtype_3d" in hdr:
                    if i < len(values):
                        try:
                            total += float(values[i].strip().strip('"').replace(",", "."))
                        except (ValueError, TypeError):
                            pass
            return round(min(total, 100.0), 1)
        except Exception:
            return None

    # ── Internal ──

    def _normalize_url(self, url):
        url = url.strip()
        if not url:
            return url
        if "://" not in url:
            url = "https://" + url
        return url

    def _on_webpage_closed(self, window_id):
        if self._shutting_down:
            return
        with self._lock:
            was_programmatic = window_id in self._closing_programmatically
            self._closing_programmatically.discard(window_id)
            entry = self._windows.pop(window_id, None)
            if window_id in self._window_order:
                self._window_order.remove(window_id)
        if entry and entry["mirror"]:
            entry["mirror"].stop()
        if not was_programmatic:
            self._refresh_manager_ui()

    def _refresh_manager_ui(self):
        if self._shutting_down:
            return
        try:
            if self._manager_window:
                self._manager_window.evaluate_js("refreshWindowList()")
        except Exception:
            pass

    def _start_resource_monitor(self):
        def monitor():
            import time
            time.sleep(3)
            while not self._shutting_down:
                try:
                    stats = self.get_resource_usage()
                    if self._manager_window and not self._shutting_down:
                        js = "updateResourceStats({cpu}, {ram}, {gpu})".format(
                            cpu=stats["cpu"], ram=stats["ram"],
                            gpu="null" if stats["gpu"] is None else stats["gpu"],
                        )
                        self._manager_window.evaluate_js(js)
                except Exception:
                    pass
                time.sleep(3)
        threading.Thread(target=monitor, daemon=True).start()
