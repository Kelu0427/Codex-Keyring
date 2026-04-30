from __future__ import annotations

from typing import Any

from auth import (
    generate_id,
    identity_from_account,
    identity_from_auth,
    normalize_email,
    parse_account_info,
    read_codex_auth,
    write_codex_auth,
)
from storage import load_account_auth, load_store, save_account_auth, save_store
from time_utils import now_iso


def match_rank(a: dict[str, str | None], b: dict[str, str | None]) -> int:
    if a["accountId"] and b["accountId"] and a["accountId"] != b["accountId"]:
        return 0
    if a["accountId"] and b["accountId"] and a["userId"] and b["userId"] and a["userId"] == b["userId"]:
        return 5
    if a["accountId"] and b["accountId"] and a["email"] and b["email"] and a["email"] == b["email"]:
        return 4
    if a["userId"] and b["userId"] and a["userId"] == b["userId"]:
        return 3
    if a["email"] and b["email"] and a["email"] == b["email"]:
        return 2
    if a["accountId"] and b["accountId"] and a["accountId"] == b["accountId"]:
        return 1
    return 0


def best_match(accounts: list[dict[str, Any]], identity: dict[str, str | None]) -> int:
    best_index = -1
    best_rank = 0
    best_updated = ""
    for index, account in enumerate(accounts):
        rank = match_rank(identity_from_account(account.get("accountInfo") or {}), identity)
        if rank > best_rank or (rank == best_rank and rank > 0 and account.get("updatedAt", "") > best_updated):
            best_rank = rank
            best_index = index
            best_updated = account.get("updatedAt", "")
    return best_index if best_rank >= 2 else -1


def fallback_account_info(identity: dict[str, str | None]) -> dict[str, Any]:
    return {
        "email": identity["email"] or "Unknown",
        "planType": "free",
        "accountId": identity["accountId"] or "",
        "userId": identity["userId"] or "",
        "organizations": [],
    }


def add_account_to_store(
    auth_config: dict[str, Any],
    alias: str | None = None,
    allow_missing_identity: bool = False,
) -> dict[str, Any]:
    store = load_store()
    try:
        account_info = parse_account_info(auth_config)
    except Exception:
        identity = identity_from_auth(auth_config)
        if not allow_missing_identity and not (identity.get("email") or identity.get("userId")):
            raise ValueError("missing_account_identity")
        account_info = fallback_account_info(identity)

    identity = identity_from_account(account_info)
    if not allow_missing_identity and not (identity.get("email") or identity.get("userId")):
        raise ValueError("missing_account_identity")

    accounts = store["accounts"]
    now = now_iso()
    existing_index = best_match(accounts, identity)
    if existing_index >= 0:
        account = accounts[existing_index]
        save_account_auth(account["id"], auth_config)
        account["accountInfo"] = {**account.get("accountInfo", {}), **account_info}
        if alias:
            account["alias"] = alias
        account["updatedAt"] = now
        save_store(store)
        return account

    email = account_info.get("email") or "Unknown"
    base_alias = alias or email.split("@")[0]
    if not alias and normalize_email(email):
        same_email = any(
            normalize_email((account.get("accountInfo") or {}).get("email")) == normalize_email(email)
            for account in accounts
        )
        if same_email:
            base_alias = f"{base_alias} ({str(account_info.get('planType') or 'free').title()})"

    account = {
        "id": generate_id(),
        "alias": base_alias,
        "accountInfo": account_info,
        "isActive": len(accounts) == 0,
        "createdAt": now,
        "updatedAt": now,
    }
    save_account_auth(account["id"], auth_config)
    accounts.append(account)
    save_store(store)
    return account


def set_active_account(account_id: str | None) -> None:
    store = load_store()
    for account in store["accounts"]:
        account["isActive"] = bool(account_id and account["id"] == account_id)
    save_store(store)


def sync_current_account() -> str | None:
    try:
        auth_config = read_codex_auth()
        identity = identity_from_auth(auth_config)
    except Exception:
        set_active_account(None)
        return None

    if not any(identity.values()):
        set_active_account(None)
        return None

    store = load_store()
    index = best_match(store["accounts"], identity)
    if index < 0:
        set_active_account(None)
        return None

    account_id = store["accounts"][index]["id"]
    set_active_account(account_id)
    try:
        save_account_auth(account_id, auth_config)
    except Exception:
        pass
    return account_id


def switch_to_account(account_id: str) -> None:
    sync_current_account()
    auth_config = load_account_auth(account_id)
    write_codex_auth(auth_config)
    set_active_account(account_id)
