from __future__ import annotations

import os
from pathlib import Path

from constants import APP_DIR_NAME, LEGACY_APP_DIR_NAME, LEGACY_MANAGER_DIR_NAME, MANAGER_DIR_NAME


def home_dir() -> Path:
    return Path.home()


def local_app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base)
    return home_dir() / "AppData" / "Local"


def app_data_dir() -> Path:
    path = local_app_data_dir() / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_app_data_dir() -> Path:
    return local_app_data_dir() / LEGACY_APP_DIR_NAME


def manager_dir() -> Path:
    path = home_dir() / MANAGER_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_manager_dir() -> Path:
    return home_dir() / LEGACY_MANAGER_DIR_NAME


def auth_store_dir() -> Path:
    path = manager_dir() / "auths"
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_auth_store_dir() -> Path:
    return legacy_manager_dir() / "auths"


def accounts_store_path() -> Path:
    return app_data_dir() / "accounts.json"


def legacy_accounts_store_path() -> Path:
    return legacy_app_data_dir() / "accounts.json"


def codex_auth_path() -> Path:
    return home_dir() / ".codex" / "auth.json"


def account_auth_path(account_id: str) -> Path:
    return auth_store_dir() / f"{account_id}.json"


def legacy_account_auth_path(account_id: str) -> Path:
    return legacy_auth_store_dir() / f"{account_id}.json"
