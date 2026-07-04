from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from constants import APP_NAME, MAX_VALID_EPOCH_MS, MIN_VALID_EPOCH_MS
from storage import load_account_auth
from time_utils import format_reset_time, now_ms


WHAM_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
WHAM_RESET_CREDITS_URL = "https://chatgpt.com/backend-api/wham/rate-limit-reset-credits"


def json_number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def json_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(round(float(value)))
    except Exception:
        return None


def normalize_unix_timestamp_ms(timestamp: int) -> int:
    if timestamp <= 0:
        raise ValueError("Invalid reset timestamp")
    ms = timestamp if timestamp >= 1_000_000_000_000 else timestamp * 1000
    if ms < MIN_VALID_EPOCH_MS or ms > MAX_VALID_EPOCH_MS:
        raise ValueError("Reset timestamp out of valid range")
    return ms


def extract_reset_time_ms(value: dict[str, Any]) -> int | None:
    for field in ("reset_at_ms", "resets_at_ms", "reset_time_ms", "reset_at", "resets_at", "reset"):
        raw = json_int(value.get(field))
        if raw:
            return raw
    for field in ("reset_in_seconds", "reset_after_seconds", "reset_in"):
        seconds = json_int(value.get(field))
        if seconds:
            return int(time.time() * 1000) + seconds * 1000
    return None


def parse_rate_limit_entry(value: dict[str, Any]) -> dict[str, Any]:
    used_percent = json_number(value.get("used_percent", value.get("usedPercent")))
    used = json_number(value.get("used"))
    remaining = json_number(value.get("remaining"))
    limit = json_number(value.get("limit", value.get("total", value.get("capacity"))))
    if used_percent is not None:
        if used_percent <= 1 and used_percent != int(used_percent):
            used_percent *= 100
        percent_left = 100 - used_percent
    elif remaining is not None and limit:
        percent_left = remaining / limit * 100
    elif used is not None and limit:
        percent_left = 100 - used / limit * 100
    else:
        raise ValueError("Missing usage fields")

    raw_reset = extract_reset_time_ms(value)
    if raw_reset is None:
        raise ValueError("Missing reset timestamp")

    window_minutes = json_int(value.get("window_minutes"))
    if window_minutes is None:
        seconds = json_int(value.get("window_seconds", value.get("limit_window_seconds")))
        window_minutes = seconds // 60 if seconds else None

    return {
        "percent_left": max(0, min(100, percent_left)),
        "reset_time_ms": normalize_unix_timestamp_ms(raw_reset),
        "window_minutes": window_minutes,
    }


def detect_limit_kind(entry: dict[str, Any], window_minutes: int | None) -> str | None:
    kind = str(entry.get("type") or entry.get("name") or "").lower()
    if "week" in kind:
        return "weekly"
    if "five" in kind or "5h" in kind or "hour" in kind:
        return "five_hour"
    if window_minutes is not None:
        if window_minutes <= 360:
            return "five_hour"
        if window_minutes >= 10080:
            return "weekly"
    return None


def parse_rate_limits(value: Any) -> dict[str, Any]:
    limits: dict[str, Any] = {"five_hour": None, "weekly": None}
    entries: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key in ("primary", "secondary", "primary_window", "secondary_window"):
            entry = value.get(key)
            if isinstance(entry, dict):
                entries.append(entry)
        if not entries:
            raw_entries = value.get("limits")
            if isinstance(raw_entries, list):
                entries = [item for item in raw_entries if isinstance(item, dict)]
    elif isinstance(value, list):
        entries = [item for item in value if isinstance(item, dict)]

    for entry in entries:
        parsed = parse_rate_limit_entry(entry)
        kind = detect_limit_kind(entry, parsed.get("window_minutes"))
        if kind and limits[kind] is None:
            limits[kind] = parsed
        elif limits["five_hour"] is None:
            limits["five_hour"] = parsed
        elif limits["weekly"] is None:
            limits["weekly"] = parsed

    if not limits["five_hour"] and not limits["weekly"]:
        raise ValueError("Missing usable rate limit data")
    return limits


def parse_optional_rate_limit(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        for key in ("primary", "primary_window"):
            if isinstance(value.get(key), dict):
                try:
                    return parse_rate_limit_entry(value[key])
                except Exception:
                    return None
        try:
            return parse_rate_limit_entry(value)
        except Exception:
            return None
    return None


def request_json(url: str, token: str, timeout: int = 30) -> tuple[int, Any, str]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"{APP_NAME} Python",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else None, body
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = None
        return error.code, parsed, body


def utc_timestamp_to_local(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
            timestamp = float(value)
            if timestamp >= 1_000_000_000_000:
                timestamp /= 1000
            date = datetime.fromtimestamp(timestamp, timezone.utc)
        else:
            raw = str(value).strip()
            date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            else:
                date = date.astimezone(timezone.utc)
        return date.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def _text_field(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def parse_reset_credits(value: Any) -> dict[str, Any]:
    available_count: int | None = None
    entries: list[Any] = []
    if isinstance(value, dict):
        available_count = json_int(value.get("available_count", value.get("availableCount")))
        for key in ("credits", "items", "data", "reset_credits", "resetCredits"):
            raw_entries = value.get(key)
            if isinstance(raw_entries, list):
                entries = raw_entries
                break
    elif isinstance(value, list):
        entries = value

    credits = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        credits.append(
            {
                "status": _text_field(item.get("status")),
                "title": _text_field(item.get("title", item.get("name"))),
                "grantedAt": utc_timestamp_to_local(item.get("granted_at", item.get("grantedAt"))),
                "expiresAt": utc_timestamp_to_local(item.get("expires_at", item.get("expiresAt"))),
            }
        )

    if available_count is None:
        available_count = sum(1 for item in credits if (item.get("status") or "").lower() in ("available", "active", "granted"))

    return {"available_count": available_count, "credits": credits}


def get_reset_credits_payload(token: str, fallback: Any = None) -> Any:
    status, value, _body = request_json(WHAM_RESET_CREDITS_URL, token)
    if 200 <= status < 300 and isinstance(value, (dict, list)):
        return value
    return fallback


def get_codex_reset_credits(account_id: str) -> dict[str, Any]:
    try:
        auth_config = load_account_auth(account_id)
    except Exception as exc:
        return {"status": "missing_token", "message": str(exc), "reset_credits": None}

    tokens = auth_config.get("tokens") or {}
    token = tokens.get("access_token")
    if not token:
        return {"status": "missing_token", "message": "缺少 access token", "reset_credits": None}

    status, value, _body = request_json(WHAM_RESET_CREDITS_URL, token)
    if status == 401:
        return {"status": "stale_token", "message": "憑證失效或沒有帶 Authorization header", "reset_credits": None}
    if status == 403:
        return {"status": "forbidden", "message": "沒有權限查詢重置額度", "reset_credits": None}
    if status < 200 or status >= 300 or not isinstance(value, (dict, list)):
        return {"status": "error", "message": f"重置額度請求失敗: {status}", "reset_credits": None}

    return {"status": "ok", "message": None, "reset_credits": parse_reset_credits(value), "last_updated": now_ms()}


def build_usage_info(result: dict[str, Any]) -> dict[str, Any]:
    usage = result.get("usage") or {}
    info: dict[str, Any] = {
        "status": "ok",
        "planType": result.get("plan_type"),
        "lastUpdated": usage.get("last_updated") or now_ms(),
    }
    if usage.get("five_hour_percent_left") is not None and usage.get("five_hour_reset_time_ms"):
        info["fiveHourLimit"] = {
            "percentLeft": round(float(usage["five_hour_percent_left"])),
            "resetTime": format_reset_time(int(usage["five_hour_reset_time_ms"]), False),
        }
    if usage.get("weekly_percent_left") is not None and usage.get("weekly_reset_time_ms"):
        info["weeklyLimit"] = {
            "percentLeft": round(float(usage["weekly_percent_left"])),
            "resetTime": format_reset_time(int(usage["weekly_reset_time_ms"]), True),
        }
    if usage.get("code_review_percent_left") is not None and usage.get("code_review_reset_time_ms"):
        info["codeReviewLimit"] = {
            "percentLeft": round(float(usage["code_review_percent_left"])),
            "resetTime": format_reset_time(int(usage["code_review_reset_time_ms"]), False),
        }
    reset_credits = usage.get("reset_credits")
    if isinstance(reset_credits, dict):
        info["resetCredits"] = {
            "availableCount": reset_credits.get("available_count"),
            "credits": reset_credits.get("credits") or [],
        }
    return info


def get_codex_wham_usage(account_id: str) -> dict[str, Any]:
    try:
        auth_config = load_account_auth(account_id)
    except Exception as exc:
        return {"status": "missing_token", "message": str(exc), "plan_type": None, "usage": None}

    tokens = auth_config.get("tokens") or {}
    token = tokens.get("access_token")
    if not token:
        return {"status": "missing_token", "message": "缺少 access token", "plan_type": None, "usage": None}

    status, value, _body = request_json(WHAM_USAGE_URL, token)
    if status in (401, 403):
        state = "stale_token" if status == 401 else "forbidden"
        return {"status": state, "message": "token 已失效或沒有權限", "plan_type": None, "usage": None}
    if status < 200 or status >= 300 or not isinstance(value, dict):
        return {"status": "error", "message": f"wham/usage 請求失敗: {status}", "plan_type": None, "usage": None}

    plan_type = value.get("plan_type")
    rate_limit = value.get("rate_limit", value.get("rate_limits"))
    if rate_limit is None:
        return {"status": "no_usage", "message": "回應中沒有 rate_limit", "plan_type": plan_type, "usage": None}

    try:
        limits = parse_rate_limits(rate_limit)
    except Exception as exc:
        return {"status": "no_usage", "message": str(exc), "plan_type": plan_type, "usage": None}

    code_review = parse_optional_rate_limit(value.get("code_review_rate_limit"))
    reset_credits = get_reset_credits_payload(token, value.get("rate_limit_reset_credits"))
    usage = {
        "five_hour_percent_left": limits["five_hour"]["percent_left"] if limits.get("five_hour") else None,
        "five_hour_reset_time_ms": limits["five_hour"]["reset_time_ms"] if limits.get("five_hour") else None,
        "weekly_percent_left": limits["weekly"]["percent_left"] if limits.get("weekly") else None,
        "weekly_reset_time_ms": limits["weekly"]["reset_time_ms"] if limits.get("weekly") else None,
        "code_review_percent_left": code_review["percent_left"] if code_review else None,
        "code_review_reset_time_ms": code_review["reset_time_ms"] if code_review else None,
        "reset_credits": parse_reset_credits(reset_credits) if reset_credits is not None else None,
        "last_updated": now_ms(),
        "source_file": None,
    }
    return {"status": "ok", "message": None, "plan_type": plan_type, "usage": usage}
