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


def usage_indicator(percent: int | None) -> str:
    if percent is None:
        return "⚪"
    if percent > 66:
        return "🟢"
    if percent > 33:
        return "🟡"
    return "🔴"


def usage_indicator_for_limit(limit: dict[str, Any] | None) -> str:
    return usage_indicator(percent_value(limit))


def build_usage_notification(
    account: dict[str, Any],
    title: str = "Codex 使用量通知",
    limit_key: str = "fiveHourLimit",
    limit_name: str = "5 小時",
) -> str:
    usage = account.get("usageInfo") or {}
    limit = usage.get(limit_key) or {}
    percent = percent_value(limit)
    reset_time = reset_value(limit) or "未取得"
    indicator = usage_indicator(percent)
    percent_text = f"{percent}%" if percent is not None else "--"

    return "\n".join(
        [
            title,
            f"目前使用帳號：{account_label(account)}",
            f"{indicator} 剩餘使用量：{percent_text}",
            f"下次刷新時間：{reset_time} ({limit_name})",
        ]
    )


def usage_summary(account: dict[str, Any]) -> str:
    usage = account.get("usageInfo") or {}
    info = account.get("accountInfo") or {}
    lines = [f"帳號：{account_label(account)}"]
    email = info.get("email")
    if email:
        lines.append(f"Email：{email}")
    plan = info.get("planType")
    if plan:
        lines.append(f"方案：{plan}")

    for label, key in (("5 小時", "fiveHourLimit"), ("每週", "weeklyLimit"), ("Code Review", "codeReviewLimit")):
        limit = usage.get(key)
        percent = percent_value(limit)
        reset = reset_value(limit)
        if percent is not None:
            suffix = f"，重置 {reset}" if reset else ""
            lines.append(f"{usage_indicator_for_limit(limit)} {label}剩餘：{percent}%{suffix}")

    expiry = parse_expiry(info.get("subscriptionActiveUntil"))
    if expiry:
        lines.append(f"訂閱到期：{expiry.astimezone().strftime('%Y-%m-%d %H:%M')}")

    status = usage.get("status")
    if status and status != "ok":
        lines.append(f"狀態：{status}")
    if usage.get("message"):
        lines.append(f"訊息：{usage['message']}")

    return "\n".join(lines)


def build_switch_message(account: dict[str, Any], config: dict[str, Any]) -> str | None:
    if not telegram_ready(config) or not config.get("notifyOnSwitch"):
        return None
    return "Codex Keyring: 已切換帳號\n" + usage_summary(account)


def build_sample_notifications(account: dict[str, Any]) -> list[str]:
    info = account.get("accountInfo") or {}
    expiry = parse_expiry(info.get("subscriptionActiveUntil"))
    expiry_text = expiry.astimezone().strftime("%Y-%m-%d %H:%M") if expiry else "未取得"
    return [
        build_usage_notification(account, "Codex 使用量通知（重整）", "fiveHourLimit", "5 小時"),
        build_usage_notification(account, "Codex 使用量通知（5 小時刷新）", "fiveHourLimit", "5 小時"),
        build_usage_notification(account, "Codex 使用量通知（每週刷新）", "weeklyLimit", "每週"),
        build_usage_notification(account, "Codex 使用量通知（5 小時門檻）", "fiveHourLimit", "5 小時"),
        build_usage_notification(account, "Codex 使用量通知（每週門檻）", "weeklyLimit", "每週"),
        "\n".join(
            [
                "Codex 訂閱提醒通知",
                f"目前使用帳號：{account_label(account)}",
                f"到期時間：{expiry_text}",
            ]
        ),
        "Codex Keyring: 已切換帳號\n" + usage_summary(account),
    ]


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
            messages.append(build_usage_notification(account, "Codex 使用量通知（手動刷新）", "fiveHourLimit", "5 小時"))
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
                messages.append(
                    "\n".join(
                        [
                            "Codex 訂閱提醒通知",
                            f"目前使用帳號：{label}",
                            f"訂閱將在 {days} 天內到期",
                            f"到期時間：{expiry.astimezone().strftime('%Y-%m-%d %H:%M')}",
                        ]
                    )
                )
                state["expirySoon"] = expiry_key
            elif seconds_left > 7 * 24 * 60 * 60:
                state.pop("expirySoon", None)

    if config.get("notifyOnFiveHourReset"):
        old_reset = reset_value(previous_usage.get("fiveHourLimit"))
        new_reset = reset_value(usage.get("fiveHourLimit"))
        if old_reset and new_reset and old_reset != new_reset and state.get("fiveHourReset") != new_reset:
            messages.append(build_usage_notification(account, "Codex 使用量通知（5 小時已刷新）", "fiveHourLimit", "5 小時"))
            state["fiveHourReset"] = new_reset

    if config.get("notifyOnWeeklyReset"):
        old_reset = reset_value(previous_usage.get("weeklyLimit"))
        new_reset = reset_value(usage.get("weeklyLimit"))
        if old_reset and new_reset and old_reset != new_reset and state.get("weeklyReset") != new_reset:
            messages.append(build_usage_notification(account, "Codex 使用量通知（每週已刷新）", "weeklyLimit", "每週"))
            state["weeklyReset"] = new_reset

    five_threshold = parse_threshold(config.get("notifyFiveHourThreshold"))
    five_percent = percent_value(usage.get("fiveHourLimit"))
    if five_threshold is not None and five_percent is not None:
        if five_percent <= five_threshold and state.get("fiveHourThreshold") != five_threshold:
            messages.append(build_usage_notification(account, f"Codex 使用量通知（5 小時低於 {five_threshold}%）", "fiveHourLimit", "5 小時"))
            state["fiveHourThreshold"] = five_threshold
        elif five_percent > five_threshold:
            state.pop("fiveHourThreshold", None)

    weekly_threshold = parse_threshold(config.get("notifyWeeklyThreshold"))
    weekly_percent = percent_value(usage.get("weeklyLimit"))
    if weekly_threshold is not None and weekly_percent is not None:
        if weekly_percent <= weekly_threshold and state.get("weeklyThreshold") != weekly_threshold:
            messages.append(build_usage_notification(account, f"Codex 使用量通知（每週低於 {weekly_threshold}%）", "weeklyLimit", "每週"))
            state["weeklyThreshold"] = weekly_threshold
        elif weekly_percent > weekly_threshold:
            state.pop("weeklyThreshold", None)

    return messages
