from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
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
    def __init__(self, window: webview.Window, root: Path, api: Api) -> None:
        self.window = window
        self.root = root
        self.api = api
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

    @staticmethod
    def _account_label(account: dict) -> str:
        info = account.get("accountInfo") or {}
        return account.get("alias") or info.get("email") or account.get("id") or "Unknown"

    def _switch_account_from_tray(self, account_id: str):
        config = load_store().get("config") or {}
        restart = bool(config.get("autoRestartCodexOnSwitch"))
        self.api.switch_account(account_id, restart)
        if self.icon:
            self.icon.menu = self._build_menu()
            self.icon.update_menu()

    def _build_account_menu(self):
        accounts = load_store().get("accounts") or []
        if not accounts:
            return pystray.Menu(pystray.MenuItem("尚未加入帳號", None, enabled=False))
        return pystray.Menu(
            *[
                pystray.MenuItem(
                    ("● " if account.get("isActive") else "") + self._account_label(account),
                    (lambda icon, item, account_id=account["id"]: self._switch_account_from_tray(account_id)),
                    enabled=not bool(account.get("isActive")),
                )
                for account in accounts
            ]
        )

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem("顯示視窗", lambda icon, item: self._show_window()),
            pystray.MenuItem("快速切換帳號", self._build_account_menu()),
            pystray.MenuItem("結束", lambda icon, item: self._quit_app()),
        )

    def _run_tray(self):
        if pystray is None:
            self.window.minimize()
            return

        image = self._load_icon_image()
        if image is None:
            self.window.minimize()
            return

        self.icon = pystray.Icon("codex-keyring", image, APP_NAME, self._build_menu())
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
        self._initialize_last_run_at()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    @staticmethod
    def _parse_iso_ts(value: str | None) -> float | None:
        if not value:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    def _initialize_last_run_at(self) -> None:
        """
        Bootstrap scheduler from persisted account update times so app restart
        does not always trigger an immediate auto refresh.
        """
        store = load_store()
        config = store.get("config") or {}
        interval_minutes = int(config.get("autoRefreshInterval") or 0)
        if interval_minutes <= 0:
            self._last_run_at = time.time()
            return

        latest_ts = 0.0
        for account in store.get("accounts") or []:
            usage = account.get("usageInfo") or {}
            candidates = [
                self._parse_iso_ts(account.get("updatedAt")),
                self._parse_iso_ts(usage.get("lastUpdated")),
            ]
            for ts in candidates:
                if ts and ts > latest_ts:
                    latest_ts = ts

        self._last_run_at = latest_ts if latest_ts > 0 else time.time()

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
    tray = TrayController(window, root, api)
    refresher = AutoRefresher(api)
    refresher.start()
    window.events.closing += tray.on_closing
    if launch_to_tray:
        webview.start(func=tray.start_tray_icon, debug=False)
        return
    webview.start(debug=False)


if __name__ == "__main__":
    main()
