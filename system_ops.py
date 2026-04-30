from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    import winreg

STARTUP_APP_NAME = "CodexKeyring"


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
                "message": f"codex login 結束碼 {completed.returncode}",
                "command": " ".join(invocation),
            }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "codex login 等待逾時"}
    except FileNotFoundError as exc:
        return {
            "status": "process_error",
            "message": f"找不到 Codex CLI：{exc.filename or codex_path or 'codex'}。請到設定填入 codex.cmd 或 codex.exe 的完整路徑。",
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
    root = Path(__file__).resolve().parent
    app_script = root / "app.py"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{runner}" "{app_script}"'


def is_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, STARTUP_APP_NAME)
            return bool(str(value).strip())
    except FileNotFoundError:
        return False
    except OSError:
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
