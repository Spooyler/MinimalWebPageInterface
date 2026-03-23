import uuid
import threading
import os
import webview
import psutil
from mirror import find_hwnd_by_title, get_monitors, MirrorWindow


class WindowManager:
    def __init__(self):
        self._windows = {}  # id -> {window, url, mirror}
        self._manager_window = None
        self._lock = threading.Lock()
        self._closing_programmatically = set()
        self._shutting_down = False
        self._process = psutil.Process(os.getpid())
        self._start_resource_monitor()

    def set_manager_window(self, window):
        self._manager_window = window
        window.events.closing += self._on_manager_closing

    def add_url(self, url, fullscreen=True):
        url = self._normalize_url(url)
        window_id = uuid.uuid4().hex[:8]

        if fullscreen:
            window = webview.create_window(
                title=url,
                url=url,
                fullscreen=True,
            )
        else:
            window = webview.create_window(
                title=url,
                url=url,
                width=1024,
                height=768,
                resizable=True,
            )

        window.events.closed += lambda: self._on_webpage_closed(window_id)

        with self._lock:
            self._windows[window_id] = {"window": window, "url": url, "mirror": None}

        return {"id": window_id, "url": url}

    def close_page(self, window_id):
        with self._lock:
            entry = self._windows.pop(window_id, None)
            if entry:
                self._closing_programmatically.add(window_id)
        if entry:
            if entry["mirror"]:
                entry["mirror"].stop()
            try:
                entry["window"].destroy()
            except Exception:
                pass
        return True

    def get_open_pages(self):
        with self._lock:
            pages = []
            for wid, entry in self._windows.items():
                title = entry["url"]
                try:
                    title = entry["window"].title or entry["url"]
                except Exception:
                    pass
                pages.append({
                    "id": wid,
                    "url": entry["url"],
                    "title": title,
                    "mirrored": entry["mirror"] is not None and entry["mirror"].is_alive(),
                })
            return pages

    def get_screens(self):
        monitors = get_monitors()
        return [
            {"index": i, "name": m["name"], "width": m["width"], "height": m["height"], "is_primary": m["is_primary"]}
            for i, m in enumerate(monitors)
        ]

    def mirror_page(self, window_id, screen_index):
        monitors = get_monitors()
        if screen_index < 0 or screen_index >= len(monitors):
            return False

        with self._lock:
            entry = self._windows.get(window_id)
            if not entry:
                return False
            # Stop existing mirror if any
            if entry["mirror"] and entry["mirror"].is_alive():
                entry["mirror"].stop()
                entry["mirror"] = None

        # Find the HWND of the source webview window
        source_title = entry["window"].title or entry["url"]
        source_hwnd = find_hwnd_by_title(source_title)
        if not source_hwnd:
            return False

        target_monitor = monitors[screen_index]
        mirror = MirrorWindow(source_hwnd, target_monitor)
        mirror.start()

        with self._lock:
            if window_id in self._windows:
                self._windows[window_id]["mirror"] = mirror

        return True

    def stop_mirror(self, window_id):
        with self._lock:
            entry = self._windows.get(window_id)
            if not entry or not entry["mirror"]:
                return False
            mirror = entry["mirror"]
            entry["mirror"] = None
        mirror.stop()
        return True

    def get_resource_usage(self):
        try:
            cpu = self._process.cpu_percent(interval=0)
            mem = self._process.memory_info()
            mem_mb = mem.rss / (1024 * 1024)

            children = self._process.children(recursive=True)
            for child in children:
                try:
                    cpu += child.cpu_percent(interval=0)
                    child_mem = child.memory_info()
                    mem_mb += child_mem.rss / (1024 * 1024)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            gpu_percent = self._get_gpu_usage()

            return {
                "cpu": round(cpu, 1),
                "ram": round(mem_mb, 1),
                "gpu": gpu_percent,
            }
        except Exception:
            return {"cpu": 0, "ram": 0, "gpu": None}

    def _get_gpu_usage(self):
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-Counter '\\GPU Engine(*)\\Utilization Percentage').CounterSamples | "
                 "Where-Object { $_.InstanceName -match 'engtype_3d' } | "
                 "Measure-Object -Property CookedValue -Sum | "
                 "Select-Object -ExpandProperty Sum"],
                capture_output=True, text=True, timeout=5,
                creationflags=0x08000000,
            )
            if result.returncode == 0 and result.stdout.strip():
                val = float(result.stdout.strip().replace(",", "."))
                return round(min(val, 100.0), 1)
        except Exception:
            pass
        return None

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

        if entry and entry["mirror"]:
            entry["mirror"].stop()

        if not was_programmatic:
            self._refresh_manager_ui()

    def _on_manager_closing(self):
        self._shutting_down = True
        with self._lock:
            windows = list(self._windows.values())
            self._windows.clear()
        for entry in windows:
            if entry["mirror"]:
                entry["mirror"].stop()
            try:
                entry["window"].destroy()
            except Exception:
                pass

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
            while not self._shutting_down:
                try:
                    stats = self.get_resource_usage()
                    if self._manager_window and not self._shutting_down:
                        js = "updateResourceStats({cpu}, {ram}, {gpu})".format(
                            cpu=stats["cpu"],
                            ram=stats["ram"],
                            gpu="null" if stats["gpu"] is None else stats["gpu"],
                        )
                        self._manager_window.evaluate_js(js)
                except Exception:
                    pass
                import time
                time.sleep(2)

        t = threading.Thread(target=monitor, daemon=True)
        t.start()
