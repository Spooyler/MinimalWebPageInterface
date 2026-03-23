import os
import webview
from manager import WindowManager


def main():
    manager = WindowManager()

    ui_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")

    management_window = webview.create_window(
        title="Web Page Manager",
        url=ui_path,
        js_api=manager,
        width=600,
        height=500,
        resizable=True,
    )
    manager.set_manager_window(management_window)

    webview.start(debug=False)


if __name__ == "__main__":
    main()
