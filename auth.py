from __future__ import annotations

import base64
import json
import random
import time
from typing import Any

from paths import codex_auth_path
from storage import read_json_file, write_json_file


def b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("不是有效的 JWT token")
    return json.loads(b64url_decode(parts[1]).decode("utf-8"))


def parse_account_info(auth_config: dict[str, Any]) -> dict[str, Any]:
    tokens = auth_config.get("tokens") or {}
    payload = decode_jwt_payload(tokens.get("id_token") or "")
    auth_data = payload.get("https://api.openai.com/auth")
    if not isinstance(auth_data, dict):
        raise ValueError("token 缺少 OpenAI auth 資訊")

    plan = auth_data.get("chatgpt_plan_type") or "free"
    if plan not in ("free", "plus", "pro", "team"):
        plan = "free"

    return {
        "email": payload.get("email") or "Unknown",
        "planType": plan,
        "accountId": auth_data.get("chatgpt_account_id") or tokens.get("account_id") or "",
        "userId": auth_data.get("chatgpt_user_id") or "",
        "accountUserId": auth_data.get("chatgpt_account_user_id"),
        "accountStructure": None,
        "workspaceName": None,
        "subscriptionActiveUntil": auth_data.get("chatgpt_subscription_active_until"),
        "organizations": auth_data.get("organizations") or [],
    }


def generate_id() -> str:
    return f"{int(time.time() * 1000):x}-{random.randrange(36**7):07x}"


def normalize_email(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    if not value or value == "unknown" or "@" not in value:
        return None
    return value


def identity_from_account(account_info: dict[str, Any]) -> dict[str, str | None]:
    return {
        "accountId": (account_info.get("accountId") or "").strip() or None,
        "userId": (account_info.get("userId") or "").strip() or None,
        "email": normalize_email(account_info.get("email")),
    }


def identity_from_auth(auth_config: dict[str, Any]) -> dict[str, str | None]:
    try:
        info = parse_account_info(auth_config)
    except Exception:
        info = {}
    tokens = auth_config.get("tokens") or {}
    return {
        "accountId": (info.get("accountId") or tokens.get("account_id") or "").strip() or None,
        "userId": (info.get("userId") or "").strip() or None,
        "email": normalize_email(info.get("email")),
    }


def read_codex_auth() -> dict[str, Any]:
    path = codex_auth_path()
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}")
    return read_json_file(path)


def write_codex_auth(auth_config: dict[str, Any]) -> None:
    write_json_file(codex_auth_path(), auth_config)
