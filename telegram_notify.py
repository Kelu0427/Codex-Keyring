from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any


def telegram_ready(config: dict[str, Any]) -> bool:
    return bool((config.get("telegramBotToken") or "").strip() and (config.get("telegramChatId") or "").strip())


def send_telegram_message(config: dict[str, Any], text: str) -> dict[str, Any]:
    token = (config.get("telegramBotToken") or "").strip()
    chat_id = (config.get("telegramChatId") or "").strip()
    if not token or not chat_id:
        return {"ok": False, "message": "Telegram token 或 chat id 未設定"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            return {"ok": bool(payload.get("ok")), "message": payload.get("description"), "status": response.status}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def parse_threshold(value: Any) -> int | None:
    if value in (None, "", "off"):
        return None
    try:
        threshold = int(value)
    except Exception:
        return None
    return max(0, min(100, threshold))


def parse_expiry(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.isdigit():
            timestamp = int(raw)
            if timestamp < 1_000_000_000_000:
                timestamp *= 1000
            return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def account_label(account: dict[str, Any]) -> str:
    info = account.get("accountInfo") or {}
    return account.get("alias") or info.get("email") or account.get("id") or "Unknown"


def percent_value(limit: dict[str, Any] | None) -> int | None:
    value = (limit or {}).get("percentLeft")
    return value if isinstance(value, int) else None


def reset_value(limit: dict[str, Any] | None) -> str | None:
    value = (limit or {}).get("resetTime")
    return str(value) if value else None


def build_notification_messages(
    account: dict[str, Any],
    previous_usage: dict[str, Any],
    result: dict[str, Any],
    config: dict[str, Any],
) -> list[str]:
    if not telegram_ready(config):
        return []

    messages: list[str] = []
    usage = account.get("usageInfo") or {}
    info = account.get("accountInfo") or {}
    label = account_label(account)
    state = account.setdefault("notificationState", {})

    if config.get("notifyOnRefresh"):
        status = result.get("status")
        if status == "ok":
            five = percent_value(usage.get("fiveHourLimit"))
            weekly = percent_value(usage.get("weeklyLimit"))
            details = []
            if five is not None:
                details.append(f"5h {five}%")
            if weekly is not None:
                details.append(f"weekly {weekly}%")
            suffix = f" ({', '.join(details)})" if details else ""
            messages.append(f"Codex Keyring: {label} 用量已更新{suffix}")
        else:
            messages.append(f"Codex Keyring: {label} 用量更新失敗：{result.get('message') or status}")

    if config.get("notifyOnExpirySoon"):
        expiry = parse_expiry(info.get("subscriptionActiveUntil"))
        if expiry:
            now = datetime.now(timezone.utc)
            seconds_left = (expiry - now).total_seconds()
            expiry_key = expiry.date().isoformat()
            if 0 < seconds_left <= 7 * 24 * 60 * 60 and state.get("expirySoon") != expiry_key:
                days = max(1, int((seconds_left + 86399) // 86400))
                messages.append(f"Codex Keyring: {label} 訂閱將在 {days} 天內到期（{expiry_key}）")
                state["expirySoon"] = expiry_key
            elif seconds_left > 7 * 24 * 60 * 60:
                state.pop("expirySoon", None)

    if config.get("notifyOnFiveHourReset"):
        old_reset = reset_value(previous_usage.get("fiveHourLimit"))
        new_reset = reset_value(usage.get("fiveHourLimit"))
        if old_reset and new_reset and old_reset != new_reset and state.get("fiveHourReset") != new_reset:
            messages.append(f"Codex Keyring: {label} 5 小時用量已刷新，下次重置時間 {new_reset}")
            state["fiveHourReset"] = new_reset

    if config.get("notifyOnWeeklyReset"):
        old_reset = reset_value(previous_usage.get("weeklyLimit"))
        new_reset = reset_value(usage.get("weeklyLimit"))
        if old_reset and new_reset and old_reset != new_reset and state.get("weeklyReset") != new_reset:
            messages.append(f"Codex Keyring: {label} 每週用量已刷新，下次重置時間 {new_reset}")
            state["weeklyReset"] = new_reset

    five_threshold = parse_threshold(config.get("notifyFiveHourThreshold"))
    five_percent = percent_value(usage.get("fiveHourLimit"))
    if five_threshold is not None and five_percent is not None:
        if five_percent <= five_threshold and state.get("fiveHourThreshold") != five_threshold:
            messages.append(f"Codex Keyring: {label} 5 小時剩餘 {five_percent}%，已低於 {five_threshold}%")
            state["fiveHourThreshold"] = five_threshold
        elif five_percent > five_threshold:
            state.pop("fiveHourThreshold", None)

    weekly_threshold = parse_threshold(config.get("notifyWeeklyThreshold"))
    weekly_percent = percent_value(usage.get("weeklyLimit"))
    if weekly_threshold is not None and weekly_percent is not None:
        if weekly_percent <= weekly_threshold and state.get("weeklyThreshold") != weekly_threshold:
            messages.append(f"Codex Keyring: {label} 每週用量剩餘 {weekly_percent}%，已低於 {weekly_threshold}%")
            state["weeklyThreshold"] = weekly_threshold
        elif weekly_percent > weekly_threshold:
            state.pop("weeklyThreshold", None)

    return messages
