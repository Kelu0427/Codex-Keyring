from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import webview

from api import Api
from constants import APP_NAME
from storage import load_store

try:
    import pystray
    from PIL import Image
except Exception:  # pragma: no cover - optional runtime dependency
    pystray = None
    Image = None


class TrayController:
    def __init__(self, window: webview.Window, root: Path) -> None:
        self.window = window
        self.root = root
        self.icon = None
        self.allow_close = False

    def _load_icon_image(self):
        if Image is None:
            return None
        icon_path = self.root / "img" / "icon.ico"
        if icon_path.exists():
            return Image.open(icon_path)
        return Image.new("RGBA", (64, 64), (42, 42, 42, 255))

    def _show_window(self):
        self.window.show()
        if self.icon:
            self.icon.stop()
            self.icon = None

    def _quit_app(self):
        self.allow_close = True
        if self.icon:
            self.icon.stop()
            self.icon = None
        self.window.destroy()

    def _run_tray(self):
        if pystray is None:
            self.window.minimize()
            return

        image = self._load_icon_image()
        if image is None:
            self.window.minimize()
            return

        menu = pystray.Menu(
            pystray.MenuItem("開啟", lambda icon, item: self._show_window()),
            pystray.MenuItem("結束", lambda icon, item: self._quit_app()),
        )
        self.icon = pystray.Icon("codex-keyring", image, APP_NAME, menu)
        self.icon.run()

    def hide_to_tray(self):
        self.window.hide()
        self.start_tray_icon()

    def start_tray_icon(self):
        if self.icon is None:
            threading.Thread(target=self._run_tray, daemon=True).start()

    def on_closing(self):
        if self.allow_close:
            return True
        close_behavior = ((load_store().get("config") or {}).get("closeBehavior") or "ask").strip().lower()
        if close_behavior == "tray":
            self.hide_to_tray()
            return False
        return True


class AutoRefresher:
    def __init__(self, api: Api) -> None:
        self.api = api
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_run_at = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                store = load_store()
                config = store.get("config") or {}
                accounts = store.get("accounts") or []
                interval_minutes = int(config.get("autoRefreshInterval") or 0)
                if interval_minutes > 0 and accounts:
                    interval_seconds = interval_minutes * 60
                    now = time.time()
                    if (now - self._last_run_at) >= interval_seconds:
                        self.api.refresh_all_usage("auto")
                        self._last_run_at = now
            except Exception:
                pass
            self._stop.wait(10)


def main() -> None:
    root = Path(__file__).resolve().parent
    startup_launch = "--startup" in sys.argv[1:]
    launch_mode = str(((load_store().get("config") or {}).get("startupLaunchMode") or "show")).strip().lower()
    launch_to_tray = startup_launch and launch_mode == "tray"
    api = Api()
    window = webview.create_window(
        APP_NAME,
        str(root / "web" / "index.html"),
        js_api=api,
        width=1240,
        height=820,
        min_size=(940, 640),
        hidden=launch_to_tray,
    )
    tray = TrayController(window, root)
    refresher = AutoRefresher(api)
    refresher.start()
    window.events.closing += tray.on_closing
    if launch_to_tray:
        webview.start(func=tray.start_tray_icon, debug=False)
        return
    webview.start(debug=False)


if __name__ == "__main__":
    main()
