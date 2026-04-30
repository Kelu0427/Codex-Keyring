# Codex Keyring

Codex Keyring 是一個 Windows 桌面工具，用來管理多個 OpenAI Codex 登入帳號。它會把不同帳號的 `auth.json` 備份在本機，並在切換帳號時寫回 `%USERPROFILE%\.codex\auth.json`。

此版本使用 Python + pywebview 製作。

## 主要功能

- 多帳號管理：保存多個 Codex 帳號，並標示目前正在使用的帳號。
- 快速切換：選擇帳號後自動更新 `.codex\auth.json`。
- Codex 登入匯入：可啟動 `codex login`，完成後匯入目前登入帳號。
- 匯入目前 auth：直接讀取 `%USERPROFILE%\.codex\auth.json` 加入清單。
- 備份匯入 / 匯出：可將所有帳號 auth 匯出成 JSON，也可從備份還原。
- 用量檢視：更新並顯示 5 小時、每週與 Code Review 剩餘比例。
- 篩選帳號：依方案、到期狀態、5 小時用量與每週用量篩選。
- Telegram 通知：可設定 Bot Token 與 Chat ID，依重整、到期、用量刷新或剩餘百分比門檻發送通知。
- 本機資料位置：設定頁會顯示資料檔位置，並可直接開啟資料夾。
- 外觀設定：支援深色 / 淺色主題切換。

## 技術架構

- 後端：Python
- 桌面視窗：pywebview
- 前端：HTML、CSS、JavaScript
- HTTP 請求：Python 標準函式庫與 `requests`

## 環境需求

- Windows 10 / 11
- Python 3.10 以上
- 已安裝 Codex CLI，並可在命令列執行 `codex`

若 `codex` 不在 PATH 中，可以在設定頁調整 Codex CLI 路徑。

## 快速開始

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## 使用方式

### 新增帳號

可使用左側「登入 Codex」選單中的操作：

- 登入 Codex：啟動 `codex login`，登入完成後自動匯入。
- 匯入目前 auth：讀取目前 `%USERPROFILE%\.codex\auth.json`。
- 匯入備份：選擇先前匯出的備份 JSON。

### 切換帳號

在帳號卡片上按「切換」，程式會將該帳號的 auth 寫入：

```text
%USERPROFILE%\.codex\auth.json
```

若設定中啟用「切換帳號後自動重新啟動 Codex」，切換時會一併嘗試重新啟動 Codex 程式。

### 更新用量

- 單一帳號：按帳號卡片上的「更新」。
- 全部帳號：按左側「更新全部用量」。

用量資料來自：

```text
https://chatgpt.com/backend-api/wham/usage
```

若 token 失效、帳號沒有權限或網路不可用，卡片會顯示對應錯誤狀態。

### 設定

設定頁分為三類：

- 一般：Codex CLI 路徑、自動更新間隔、關閉視窗行為、主題。
- 帳號切換：切換後是否自動重新啟動 Codex，以及是否略過確認。
- Telegram 通知：設定 Bot Token、Chat ID、通知時機與用量百分比門檻。
- 本機資料：顯示設定檔、帳號 auth 備份、目前 Codex auth 的路徑，並可開啟所在資料夾。

## 本機資料與隱私

Codex Keyring 的資料都儲存在本機，不會上傳到第三方伺服器。需要更新用量時，程式會使用本機保存的 token 呼叫 ChatGPT 的 `wham/usage` API。

目前資料以明文 JSON 保存，請避免把這些檔案分享給他人。

主要路徑：

```text
帳號列表與設定：
%LOCALAPPDATA%\codex-keyring\accounts.json

帳號 auth 備份：
%USERPROFILE%\.codex_keyring\auths\{accountId}.json

目前 Codex auth：
%USERPROFILE%\.codex\auth.json
```

## 專案結構

```text
Codex-Keyring/
├── app.py              # pywebview 入口
├── api.py              # 前端呼叫的 Python API
├── accounts.py         # 帳號新增、比對、切換
├── auth.py             # Codex auth 讀寫與解析
├── storage.py          # 本機資料讀寫
├── usage.py            # 用量 API 解析
├── system_ops.py       # Codex 登入、重啟、開啟資料夾
├── paths.py            # 本機路徑定義
├── web/
│   ├── index.html
│   ├── app.js
│   └── style.css
└── requirements.txt
```

## 已知限制

- 用量查詢依賴 `wham/usage` API 與帳號 token，OpenAI 端介面變動時可能需要更新解析邏輯。
- auth 檔案目前是明文保存，安全性取決於本機帳號與檔案權限。
- 自動重啟 Codex 主要針對 Windows 環境設計。

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
