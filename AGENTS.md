# Repository Guidelines

## Project Structure & Module Organization
- Root Python modules:
  - `app.py`: desktop app entrypoint (pywebview window, tray, scheduler bootstrap).
  - `api.py`: JS-bridge API called from the frontend.
  - `accounts.py`, `auth.py`, `usage.py`, `telegram_notify.py`: core business logic.
  - `storage.py`, `paths.py`, `constants.py`, `system_ops.py`: persistence, paths, config, OS operations.
- Frontend assets: `web/` (`index.html`, `app.js`, `style.css`).
- Local media: `img/` (screenshots and icon assets; icons are ignored by Git).
- Documentation: `README.md`, `AGENTS.md`, `LICENSE`.

## Build, Test, and Development Commands
- Run locally:
  - `python app.py` — start the desktop app.
- Basic syntax check:
  - `python -m py_compile app.py api.py telegram_notify.py system_ops.py`
- Install dependencies:
  - `python -m pip install -r requirements.txt`
- Package EXE (Windows):
  - `python -m PyInstaller --noconfirm --clean --windowed --onefile --name Codex-Keyring --icon img\icon.ico --add-data "web;web" --add-data "img;img" app.py`

## Coding Style & Naming Conventions
- Python: 4-space indentation, type hints preferred, small focused functions.
- JavaScript: keep existing plain JS style in `web/app.js`; avoid introducing frameworks.
- Naming:
  - Python files/functions: `snake_case`
  - JS variables/functions: `camelCase`
  - Constants: `UPPER_SNAKE_CASE`
- Keep UI copy in Traditional Chinese unless a task explicitly requests otherwise.

## Testing Guidelines
- No formal test framework is configured yet.
- Minimum requirement for changes:
  1. `py_compile` passes for edited Python files.
  2. Manual smoke test of affected flows (account switch, refresh, Telegram notice, startup behavior).
- If adding tests later, place them under `tests/` and use `test_*.py`.

## Commit & Pull Request Guidelines
- Follow existing commit style seen in history: `feat:`, `fix:`, `docs:`, `chore:`.
- Keep commits scoped and descriptive (one logical change per commit when possible).
- PRs should include:
  - What changed and why
  - User-visible impact (screenshots for UI changes)
  - Verification steps (commands + manual checks)

## Security & Configuration Tips
- Never commit tokens, chat IDs, or local auth JSON content.
- Do not commit build artifacts (`build/`, `dist/`, `*.spec`, release zips).

---

# 儲存庫指南（中文版）

## 專案結構與模組
- 根目錄 Python 模組：
  - `app.py`：桌面程式入口（pywebview 視窗、系統匣、背景排程）。
  - `api.py`：前端呼叫的 JS bridge API。
  - `accounts.py`、`auth.py`、`usage.py`、`telegram_notify.py`：核心業務邏輯。
  - `storage.py`、`paths.py`、`constants.py`、`system_ops.py`：資料儲存、路徑、常數與系統操作。
- 前端資源：`web/`（`index.html`、`app.js`、`style.css`）。
- 圖片資源：`img/`（截圖與圖示，圖示檔不進版控）。
- 文件：`README.md`、`AGENTS.md`、`LICENSE`。

## 建置、測試與開發指令
- 本機啟動：`python app.py`
- 語法檢查：`python -m py_compile app.py api.py telegram_notify.py system_ops.py`
- 安裝相依：`python -m pip install -r requirements.txt`
- Windows 打包 EXE：
  - `python -m PyInstaller --noconfirm --clean --windowed --onefile --name Codex-Keyring --icon img\icon.ico --add-data "web;web" --add-data "img;img" app.py`

## 程式風格與命名
- Python 使用 4 空白縮排，建議保留型別註記與小函式設計。
- 前端維持 `web/app.js` 既有的原生 JS 風格，不引入新框架。
- 命名規則：
  - Python 檔案/函式：`snake_case`
  - JS 變數/函式：`camelCase`
  - 常數：`UPPER_SNAKE_CASE`
- UI 文案預設使用繁中，除非需求明確指定其他語言。

## 測試準則
- 目前未配置正式測試框架。
- 變更最低驗證要求：
  1. 相關 Python 檔通過 `py_compile`
  2. 手動 smoke test（帳號切換、用量刷新、Telegram 通知、開機啟動）
- 若未來新增測試，請放在 `tests/`，檔名採 `test_*.py`。

## Commit 與 PR 規範
- 延續既有提交風格：`feat:`、`fix:`、`docs:`、`chore:`。
- 每個 commit 盡量聚焦單一邏輯變更。
- PR 建議包含：
  - 變更內容與原因
  - 使用者可見影響（UI 變更附截圖）
  - 驗證方式（指令與手動檢查步驟）

## 安全與設定注意事項
- 禁止提交 token、chat id、本機 auth JSON 等敏感資訊。
- 禁止提交打包產物（`build/`、`dist/`、`*.spec`、release zip）。
