from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import webview

from accounts import add_account_to_store, switch_to_account, sync_current_account
from auth import read_codex_auth
from constants import APP_NAME, APP_VERSION, BACKUP_FORMAT, LEGACY_BACKUP_FORMAT
from paths import accounts_store_path, app_data_dir, auth_store_dir, codex_auth_path, manager_dir
from storage import delete_account_auth, load_account_auth, load_store, save_store
from system_ops import (
    apply_update,
    check_for_updates,
    is_startup_enabled,
    open_folder,
    restart_codex_processes,
    run_codex_login,
    set_startup_enabled,
)
from telegram_notify import (
    build_notification_messages,
    build_sample_notifications,
    build_switch_message,
    send_telegram_message,
    telegram_ready,
)
from time_utils import now_iso, now_ms
from usage import build_usage_info, get_codex_wham_usage


class Api:
    def __init__(self) -> None:
        self._refresh_lock = threading.RLock()
        self._last_auto_refresh_at = 0.0

    def get_initial_state(self) -> dict[str, Any]:
        sync_current_account()
        store = load_store()
        startup_enabled = is_startup_enabled()
        if startup_enabled:
            # refresh startup command format (includes --startup flag)
            startup_enabled = set_startup_enabled(True)
        store["config"]["autoLaunchOnStartup"] = startup_enabled
        return {
            "name": APP_NAME,
            "store": store,
            "version": APP_VERSION,
            "storage": self.get_storage_locations(),
        }

    def load_accounts(self) -> dict[str, Any]:
        sync_current_account()
        return load_store()

    def get_storage_locations(self) -> dict[str, str]:
        return {
            "appDataDir": str(app_data_dir()),
            "managerDir": str(manager_dir()),
            "accountsFile": str(accounts_store_path()),
            "authStoreDir": str(auth_store_dir()),
            "currentCodexAuth": str(codex_auth_path()),
        }

    def open_storage_folder(self, key: str = "appDataDir") -> dict[str, object]:
        locations = self.get_storage_locations()
        path = locations.get(key)
        if not path:
            raise ValueError(f"unknown storage location: {key}")
        target = Path(path)
        folder = target if target.suffix == "" else target.parent
        return open_folder(str(folder))

    def add_account_json(
        self,
        auth_json: str,
        alias: str | None = None,
        allow_missing_identity: bool = False,
    ) -> dict[str, Any]:
        auth_config = json.loads(auth_json)
        account = add_account_to_store(auth_config, alias, allow_missing_identity)
        return {"account": account, "store": load_store()}

    def import_current_auth(self, allow_missing_identity: bool = False) -> dict[str, Any]:
        account = add_account_to_store(read_codex_auth(), None, allow_missing_identity)
        sync_current_account()
        return {"account": account, "store": load_store()}

    def switch_account(self, account_id: str, restart: bool = False) -> dict[str, Any]:
        switch_to_account(account_id)
        store = load_store()
        notification = None
        for account in store.get("accounts") or []:
            if account.get("id") == account_id:
                message = build_switch_message(account, store.get("config") or {})
                if message:
                    notification = send_telegram_message(store.get("config") or {}, message)
                break
        result = (
            restart_codex_processes((store.get("config") or {}).get("codexPath") or "codex")
            if restart
            else None
        )
        return {"store": load_store(), "restart": result, "notification": notification}

    def remove_account(self, account_id: str) -> dict[str, Any]:
        store = load_store()
        removed_active = False
        next_accounts = []
        for account in store["accounts"]:
            if account["id"] == account_id:
                removed_active = bool(account.get("isActive"))
            else:
                next_accounts.append(account)
        if removed_active and next_accounts and not any(account.get("isActive") for account in next_accounts):
            next_accounts[0]["isActive"] = True
        store["accounts"] = next_accounts
        save_store(store)
        delete_account_auth(account_id)
        return load_store()

    def update_config(self, config: dict[str, Any]) -> dict[str, Any]:
        store = load_store()
        allowed = {
            "autoRefreshInterval",
            "codexPath",
            "closeBehavior",
            "theme",
            "hasInitialized",
            "autoRestartCodexOnSwitch",
            "skipSwitchRestartConfirm",
            "autoLaunchOnStartup",
            "startupLaunchMode",
            "telegramBotToken",
            "telegramChatId",
            "notifyOnSwitch",
            "notifyOnRefresh",
            "notifyOnExpirySoon",
            "notifyOnFiveHourReset",
            "notifyOnWeeklyReset",
            "notifyFiveHourThreshold",
            "notifyWeeklyThreshold",
        }
        updates = {key: value for key, value in (config or {}).items() if key in allowed}
        store["config"].update(updates)
        if "autoLaunchOnStartup" in updates:
            store["config"]["autoLaunchOnStartup"] = set_startup_enabled(bool(updates["autoLaunchOnStartup"]))
        save_store(store)
        return load_store()

    def test_telegram_notification(self) -> dict[str, Any]:
        config = load_store().get("config") or {}
        return send_telegram_message(config, "Codex Keyring: Telegram 通知測試成功")

    def send_all_notification_samples(self) -> dict[str, Any]:
        store = load_store()
        config = store.get("config") or {}
        if not telegram_ready(config):
            return {"ok": False, "message": "Telegram token 或 chat id 未設定", "sent": 0, "results": []}

        account = next((item for item in store.get("accounts") or [] if item.get("isActive")), None)
        if account is None:
            account = (store.get("accounts") or [None])[0]
        if not account:
            return {"ok": False, "message": "沒有可用帳號可產生通知樣本", "sent": 0, "results": []}

        messages = build_sample_notifications(account)
        results = [send_telegram_message(config, message) for message in messages]
        sent = sum(1 for item in results if item.get("ok"))
        return {"ok": sent == len(results), "sent": sent, "total": len(results), "results": results}

    def refresh_usage(self, account_id: str, refresh_source: str = "manual") -> dict[str, Any]:
        with self._refresh_lock:
            result = get_codex_wham_usage(account_id)
            store = load_store()
            notification_results = []
            for account in store["accounts"]:
                if account["id"] == account_id:
                    previous_usage = dict(account.get("usageInfo") or {})
                    account["usageInfo"] = (
                        build_usage_info(result)
                        if result["status"] == "ok"
                        else {
                            "status": result["status"],
                            "message": result.get("message"),
                            "planType": result.get("plan_type"),
                            "lastUpdated": now_iso(),
                        }
                    )
                    account["updatedAt"] = now_iso()
                    messages = build_notification_messages(
                        account,
                        previous_usage,
                        result,
                        store.get("config") or {},
                        refresh_source,
                    )
                    for message in messages:
                        notification_results.append(send_telegram_message(store.get("config") or {}, message))
            save_store(store)
            return {"result": result, "store": load_store(), "notifications": notification_results}

    def refresh_all_usage(self, refresh_source: str = "manual") -> dict[str, Any]:
        with self._refresh_lock:
            now = time.time()
            if refresh_source == "auto":
                # Debounce duplicate auto refresh calls (UI timer + background thread or multi-instance overlap).
                if now - self._last_auto_refresh_at < 30:
                    return {"updated": 0, "missing": 0, "store": load_store(), "skipped": True}
                self._last_auto_refresh_at = now

            updated = 0
            missing = 0
            store = load_store()
            for account in list(store["accounts"]):
                response = self.refresh_usage(account["id"], refresh_source)
                if response["result"]["status"] == "ok":
                    updated += 1
                else:
                    missing += 1
                time.sleep(0.25)
            return {"updated": updated, "missing": missing, "store": load_store()}

    def choose_import_file(self) -> dict[str, Any] | None:
        paths = webview.windows[0].create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=("JSON Files (*.json)",),
        )
        if not paths:
            return None
        path = Path(paths[0] if isinstance(paths, (list, tuple)) else paths)
        return {"path": str(path), "content": path.read_text(encoding="utf-8")}

    def choose_backup_import_file(self) -> dict[str, Any] | None:
        selected = self.choose_import_file()
        if not selected:
            return None
        backup = json.loads(selected["content"])
        if backup.get("format") not in (BACKUP_FORMAT, LEGACY_BACKUP_FORMAT) or not isinstance(backup.get("accounts"), list):
            raise ValueError(f"不是有效的 {APP_NAME} 備份檔")
        imported = 0
        for item in backup["accounts"]:
            add_account_to_store(item["authConfig"], item.get("alias"), True)
            imported += 1
        return {"importedCount": imported, "store": load_store()}

    def export_backup(self) -> dict[str, Any] | None:
        path = webview.windows[0].create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=f"codex-keyring-backup-{datetime.now().date().isoformat()}.json",
            file_types=("JSON Files (*.json)",),
        )
        if not path:
            return None
        output_path = Path(path[0] if isinstance(path, (list, tuple)) else path)
        store = load_store()
        backup = {
            "format": BACKUP_FORMAT,
            "version": "1.0.0",
            "exportedAt": now_iso(),
            "accounts": [
                {"alias": account.get("alias"), "authConfig": load_account_auth(account["id"])}
                for account in store["accounts"]
            ],
        }
        output_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"path": str(output_path)}

    def start_codex_login(self) -> dict[str, Any]:
        before = codex_auth_path().read_text(encoding="utf-8") if codex_auth_path().exists() else None
        command = ((load_store().get("config") or {}).get("codexPath") or "codex").strip().strip('"').strip("'")
        result = run_codex_login(command, timeout_seconds=180)
        if result.get("status") != "success":
            return result

        try:
            content = codex_auth_path().read_text(encoding="utf-8")
        except Exception as exc:
            return {"status": "process_error", "message": str(exc)}

        if content == before:
            return {"status": "timeout", "message": "auth.json 沒有變更"}
        return {"status": "success", "authJson": content, "changedAt": now_ms()}

    def restart_codex_processes(self) -> dict[str, bool]:
        return restart_codex_processes((load_store().get("config") or {}).get("codexPath") or "codex")

    def check_update(self) -> dict[str, object]:
        return check_for_updates()

    def apply_update(self) -> dict[str, object]:
        return apply_update()
