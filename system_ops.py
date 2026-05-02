from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    import winreg

STARTUP_APP_NAME = "CodexKeyring"
RELEASE_API_URL = "https://api.github.com/repos/Kelu0427/Codex-Keyring/releases/latest"
TAGS_API_URL = "https://api.github.com/repos/Kelu0427/Codex-Keyring/tags"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _normalize_version(text: str | None) -> tuple[int, ...]:
    raw = (text or "").strip().lower().lstrip("v").replace("-py", "")
    numbers = [int(item) for item in re.findall(r"\d+", raw)]
    return tuple(numbers or [0])


def _fetch_json(url: str) -> object:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Codex-Keyring-Updater"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_latest_release() -> dict[str, str]:
    payload = _fetch_json(RELEASE_API_URL)
    if not isinstance(payload, dict):
        raise ValueError("release payload invalid")
    tag = str(payload.get("tag_name") or "").strip()
    release_url = str(payload.get("html_url") or "").strip()
    assets = payload.get("assets") or []
    download_url = ""
    asset_name = ""
    if isinstance(assets, list) and assets:
        exe_asset = next((item for item in assets if str(item.get("name", "")).lower().endswith(".exe")), None)
        if isinstance(exe_asset, dict):
            download_url = str(exe_asset.get("browser_download_url") or "").strip()
            asset_name = str(exe_asset.get("name") or "").strip()
    return {
        "tag": tag,
        "release_url": release_url,
        "download_url": download_url,
        "asset_name": asset_name,
    }


def _fetch_latest_tag() -> dict[str, str]:
    payload = _fetch_json(TAGS_API_URL)
    if not isinstance(payload, list) or not payload:
        raise ValueError("no tags found")
    first = payload[0] if isinstance(payload[0], dict) else {}
    tag = str(first.get("name") or "").strip()
    return {
        "tag": tag,
        "release_url": "https://github.com/Kelu0427/Codex-Keyring/releases",
        "download_url": "",
        "asset_name": "",
    }


def _download_update(url: str, asset_name: str) -> Path:
    from paths import app_data_dir

    updates_dir = app_data_dir() / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(asset_name or "Codex-Keyring.exe").name
    if not filename.lower().endswith(".exe"):
        filename = "Codex-Keyring.exe"
    destination = updates_dir / filename
    partial = destination.with_suffix(destination.suffix + ".download")

    request = urllib.request.Request(url, headers={"User-Agent": "Codex-Keyring-Updater"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
        shutil.copyfileobj(response, output)
    partial.replace(destination)
    return destination


def _quote_batch_value(value: Path) -> str:
    return str(value).replace("%", "%%")


def _launch_windows_self_updater(downloaded_exe: Path) -> Path:
    from paths import app_data_dir

    current_exe = Path(sys.executable).resolve()
    updater_script = app_data_dir() / "updates" / "apply-update.cmd"
    updater_script.parent.mkdir(parents=True, exist_ok=True)
    script = f"""@echo off
setlocal
set "SOURCE={_quote_batch_value(downloaded_exe.resolve())}"
set "TARGET={_quote_batch_value(current_exe)}"
set /a tries=0
timeout /t 1 /nobreak >nul
:retry
copy /y "%SOURCE%" "%TARGET%" >nul 2>nul
if errorlevel 1 (
  set /a tries+=1
  if %tries% geq 30 exit /b 1
  timeout /t 1 /nobreak >nul
  goto retry
)
start "" "%TARGET%"
del "%SOURCE%" >nul 2>nul
del "%~f0" >nul 2>nul
"""
    updater_script.write_text(script, encoding="utf-8")
    subprocess.Popen(
        ["cmd", "/c", str(updater_script)],
        cwd=str(updater_script.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    return updater_script


def _exit_soon(delay_seconds: float = 0.5) -> None:
    def quit_process() -> None:
        time.sleep(delay_seconds)
        os._exit(0)

    threading.Thread(target=quit_process, daemon=True).start()


def normalize_codex_path(codex_path: str | None) -> str:
    return (codex_path or "codex").strip().strip('"').strip("'") or "codex"


def resolve_codex_command(codex_path: str | None) -> str:
    command = normalize_codex_path(codex_path)
    explicit_path = Path(command)
    if explicit_path.exists():
        return str(explicit_path)

    if sys.platform == "win32":
        for extension in (".cmd", ".bat", ".exe", ".ps1", ""):
            resolved = shutil.which(command if command.lower().endswith(extension) else f"{command}{extension}")
            if resolved:
                return resolved

    resolved = shutil.which(command)
    if resolved:
        return resolved

    return command


def build_codex_invocation(codex_path: str | None, *args: str) -> tuple[list[str], bool]:
    command = resolve_codex_command(codex_path)
    suffix = Path(command).suffix.lower()

    if sys.platform == "win32" and suffix in (".cmd", ".bat"):
        return ["cmd", "/c", command, *args], False

    if sys.platform == "win32" and suffix == ".ps1":
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            command,
            *args,
        ], False

    return [command, *args], False


def restart_codex_processes(codex_path: str) -> dict[str, bool]:
    if sys.platform != "win32":
        return {"appRestarted": False, "cliRestarted": False}

    subprocess.run(["taskkill", "/IM", "Codex.exe", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["taskkill", "/IM", "codex.exe", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    program = resolve_codex_command(codex_path)
    app_restarted = False
    try:
        if Path(program).exists() or shutil.which(program):
            invocation, use_shell = build_codex_invocation(program)
            subprocess.Popen(invocation, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=use_shell)
            app_restarted = True
    except Exception:
        app_restarted = False
    return {"appRestarted": app_restarted, "cliRestarted": False}


def run_codex_login(codex_path: str, timeout_seconds: int = 180) -> dict[str, object]:
    invocation, use_shell = build_codex_invocation(codex_path, "login")
    try:
        completed = subprocess.run(invocation, timeout=timeout_seconds, shell=use_shell)
        if completed.returncode != 0:
            return {
                "status": "process_error",
                "message": f"codex login failed with code {completed.returncode}",
                "command": " ".join(invocation),
            }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "codex login timed out"}
    except FileNotFoundError as exc:
        return {
            "status": "process_error",
            "message": f"Codex CLI not found: {exc.filename or codex_path or 'codex'}",
            "command": " ".join(invocation),
        }
    except Exception as exc:
        return {"status": "process_error", "message": str(exc), "command": " ".join(invocation)}
    return {"status": "success"}


def open_folder(path: str) -> dict[str, object]:
    target = Path(path).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        subprocess.Popen(["explorer", str(target)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])

    return {"opened": True, "path": str(target)}


def _startup_command() -> str:
    # PyInstaller onefile/onedir: use the built executable itself.
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}" --startup'

    # Source mode: use pythonw + app.py
    root = Path(__file__).resolve().parent
    app_script = root / "app.py"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{runner}" "{app_script}" --startup'


def is_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, STARTUP_APP_NAME)
            return bool(str(value).strip())
    except (FileNotFoundError, OSError):
        return False


def set_startup_enabled(enabled: bool) -> bool:
    if sys.platform != "win32":
        return False
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, STARTUP_APP_NAME, 0, winreg.REG_SZ, _startup_command())
            return True
        try:
            winreg.DeleteValue(key, STARTUP_APP_NAME)
        except FileNotFoundError:
            pass
        return False


def check_for_updates() -> dict[str, object]:
    from constants import APP_VERSION

    try:
        latest = _fetch_latest_release()
    except Exception as exc:
        if "404" in str(exc):
            try:
                latest = _fetch_latest_tag()
            except Exception:
                return {
                    "supported": True,
                    "available": False,
                    "message": "目前未有新版本",
                }
        else:
            return {"supported": True, "available": False, "message": "目前未有新版本"}

    current_version = APP_VERSION
    latest_version = latest.get("tag", "")
    available = _normalize_version(str(latest_version)) > _normalize_version(str(current_version))
    return {
        "supported": True,
        "available": available,
        "currentVersion": current_version,
        "latestVersion": latest_version,
        "downloadUrl": latest.get("download_url", ""),
        "releaseUrl": latest.get("release_url", ""),
        "assetName": latest.get("asset_name", ""),
        "message": "有可用更新" if available else "目前未有新版本",
    }


def apply_update() -> dict[str, object]:
    status = check_for_updates()
    if not status.get("supported"):
        return {**status, "updated": False}
    if not status.get("available"):
        return {**status, "updated": False}

    download_url = str(status.get("downloadUrl") or "").strip()
    if not download_url:
        return {"supported": True, "available": True, "updated": False, "message": "找不到可自動安裝的 EXE 更新檔"}

    try:
        downloaded_exe = _download_update(download_url, str(status.get("assetName") or "Codex-Keyring.exe"))
    except Exception as exc:
        return {"supported": True, "available": True, "updated": False, "message": f"下載更新失敗：{exc}"}

    if sys.platform == "win32" and getattr(sys, "frozen", False):
        updater_script = _launch_windows_self_updater(downloaded_exe)
        _exit_soon()
        return {
            "supported": True,
            "available": True,
            "updated": True,
            "restartRequired": True,
            "message": "更新已下載，程式即將重啟套用新版",
            "downloadPath": str(downloaded_exe),
            "updaterPath": str(updater_script),
        }

    return {
        "supported": True,
        "available": True,
        "updated": True,
        "restartRequired": False,
        "message": "開發模式已下載更新檔，未自動覆蓋目前程式",
        "downloadUrl": download_url,
        "downloadPath": str(downloaded_exe),
    }
