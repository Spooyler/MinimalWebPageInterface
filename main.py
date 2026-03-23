import os
import sys
import threading
import webview
import pystray
from PIL import Image
from manager import WindowManager


def create_tray_icon(manager, management_window):
    image = Image.new("RGB", (64, 64), color=(80, 140, 200))

    def show_window(icon, item):
        manager.show_from_tray()

    def exit_app(icon, item):
        icon.stop()
        manager._shutting_down = True
        # Destroy all child windows
        with manager._lock:
            windows = list(manager._windows.values())
            ext_mirrors = list(manager._external_mirrors.values())
            manager._windows.clear()
            manager._external_mirrors.clear()
        for entry in windows:
            if entry["mirror"]:
                entry["mirror"].stop()
            try:
                entry["window"].destroy()
            except Exception:
                pass
        for ext in ext_mirrors:
            ext["mirror"].stop()
        # Destroy manager window — this ends webview.start()
        try:
            management_window.destroy()
        except Exception:
            pass
        # Force exit if webview loop doesn't end
        os._exit(0)

    icon = pystray.Icon(
        "WebPageManager",
        image,
        "Web Page Manager",
        menu=pystray.Menu(
            pystray.MenuItem("Show", show_window, default=True),
            pystray.MenuItem("Exit", exit_app),
        ),
    )
    return icon


def main():
    manager = WindowManager()
    manager._tray_mode = True

    ui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")

    management_window = webview.create_window(
        title="Web Page Manager",
        url=ui_path,
        js_api=manager,
        width=700,
        height=600,
        resizable=True,
    )
    manager.set_manager_window(management_window)

    # Minimize to tray or close depending on setting
    def on_closing():
        try:
            tray_enabled = manager.get_config("minimize_to_tray")
        except Exception:
            tray_enabled = True

        if tray_enabled is not False:
            manager.minimize_to_tray()
            return False  # Prevent actual close

        # Tray disabled — clean up child windows/mirrors, then let the close proceed
        manager._shutting_down = True
        with manager._lock:
            windows = list(manager._windows.values())
            ext_mirrors = list(manager._external_mirrors.values())
            manager._windows.clear()
            manager._external_mirrors.clear()
            manager._window_order.clear()
        for entry in windows:
            if entry["mirror"]:
                entry["mirror"].stop()
            try:
                entry["window"].destroy()
            except Exception:
                pass
        for ext in ext_mirrors:
            ext["mirror"].stop()
        # Return True (or None) to allow the window to close naturally

    management_window.events.closing += on_closing

    # Auto-launch presets after window loads
    def on_loaded():
        manager.auto_launch_presets()

    management_window.events.loaded += on_loaded

    # Start tray icon in background thread
    tray_icon = create_tray_icon(manager, management_window)
    tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
    tray_thread.start()

    webview.start(debug=False)


if __name__ == "__main__":
    main()
