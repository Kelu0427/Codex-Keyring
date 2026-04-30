from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paths import account_auth_path, accounts_store_path, legacy_account_auth_path, legacy_accounts_store_path


def default_config() -> dict[str, Any]:
    return {
        "autoRefreshInterval": 30,
        "codexPath": "codex",
        "closeBehavior": "ask",
        "theme": "dark",
        "hasInitialized": False,
        "autoRestartCodexOnSwitch": False,
        "skipSwitchRestartConfirm": False,
        "telegramBotToken": "",
        "telegramChatId": "",
        "notifyOnSwitch": False,
        "notifyOnRefresh": False,
        "notifyOnExpirySoon": False,
        "notifyOnFiveHourReset": False,
        "notifyOnWeeklyReset": False,
        "notifyFiveHourThreshold": "off",
        "notifyWeeklyThreshold": "off",
    }


def default_store() -> dict[str, Any]:
    return {"version": "1.0.0", "accounts": [], "config": default_config()}


def read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_account_auth(account_id: str, auth_config: dict[str, Any]) -> None:
    write_json_file(account_auth_path(account_id), auth_config)


def load_account_auth(account_id: str) -> dict[str, Any]:
    path = account_auth_path(account_id)
    if path.exists():
        return read_json_file(path)

    legacy_path = legacy_account_auth_path(account_id)
    if legacy_path.exists():
        auth_config = read_json_file(legacy_path)
        save_account_auth(account_id, auth_config)
        return auth_config

    return read_json_file(path)


def delete_account_auth(account_id: str) -> None:
    path = account_auth_path(account_id)
    if path.exists():
        path.unlink()


def load_store() -> dict[str, Any]:
    path = accounts_store_path()
    if not path.exists():
        legacy_path = legacy_accounts_store_path()
        if legacy_path.exists():
            store = read_json_file(legacy_path)
            save_store(store)
            return load_store()
        return default_store()

    store = read_json_file(path)
    config = default_config()
    config.update(store.get("config") or {})
    for removed in ("proxyEnabled", "proxyUrl"):
        config.pop(removed, None)

    accounts = []
    needs_save = False
    for account in store.get("accounts") or []:
        legacy_auth = account.pop("authConfig", None)
        if legacy_auth:
            save_account_auth(account["id"], legacy_auth)
            needs_save = True
        accounts.append(account)

    normalized = {
        "version": store.get("version") or "1.0.0",
        "accounts": accounts,
        "config": config,
    }
    if needs_save:
        save_store(normalized)
    return normalized


def save_store(store: dict[str, Any]) -> None:
    config = default_config()
    config.update(store.get("config") or {})
    config.pop("proxyEnabled", None)
    config.pop("proxyUrl", None)
    write_json_file(accounts_store_path(), {**store, "config": config})
