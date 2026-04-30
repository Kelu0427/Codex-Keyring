const state = {
  store: { accounts: [], config: {} },
  storage: {},
  appName: "Codex Keyring",
  currentView: "accounts",
  filters: { plan: "all", expiry: "all", hourly: "all", weekly: "all" },
  busy: false,
  autoRefreshTimer: null,
};

const $ = (id) => document.getElementById(id);

function askConfirm({ title, message, confirmText = "確認", cancelText = "取消", danger = false }) {
  return new Promise((resolve) => {
    const dialog = $("confirmDialog");
    const okButton = $("confirmOkBtn");
    const cancelButton = $("confirmCancelBtn");

    $("confirmTitle").textContent = title;
    $("confirmMessage").textContent = message;
    okButton.textContent = confirmText;
    cancelButton.textContent = cancelText;
    okButton.classList.toggle("danger-button", danger);

    const cleanup = (result) => {
      okButton.removeEventListener("click", onOk);
      cancelButton.removeEventListener("click", onCancel);
      dialog.removeEventListener("cancel", onCancel);
      dialog.removeEventListener("close", onClose);
      if (dialog.open) dialog.close();
      resolve(result);
    };
    const onOk = () => cleanup(true);
    const onCancel = (event) => {
      event?.preventDefault?.();
      cleanup(false);
    };
    const onClose = () => cleanup(false);

    okButton.addEventListener("click", onOk);
    cancelButton.addEventListener("click", onCancel);
    dialog.addEventListener("cancel", onCancel);
    dialog.addEventListener("close", onClose);
    dialog.showModal();
  });
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    node.hidden = true;
  }, 2600);
}

function setBusy(value) {
  state.busy = value;
  document.querySelectorAll("button").forEach((button) => {
    if (!button.closest("dialog")) button.disabled = value;
  });
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme === "light" ? "light" : "dark";
}

function showView(view) {
  state.currentView = view;
  $("accountsView").hidden = view !== "accounts";
  $("settingsView").hidden = view !== "settings";
  $("accountsNavBtn").classList.toggle("active", view === "accounts");
  $("settingsNavBtn").classList.toggle("active", view === "settings");
}

async function apiCall(name, ...args) {
  if (!window.pywebview?.api) {
    throw new Error("pywebview API 尚未就緒");
  }
  return window.pywebview.api[name](...args);
}

function planLabel(plan) {
  return ({ free: "Free", plus: "Plus", pro: "Pro", team: "Team" }[plan] || plan || "Free");
}

function displayName(account) {
  const info = account.accountInfo || {};
  const email = info.email || "Unknown";
  const prefix = email.split("@")[0];
  const alias = (account.alias || "").trim();
  const teamName = (info.workspaceName || "").trim();
  if (info.planType === "team" && teamName && teamName !== email) return teamName;
  if (alias && alias !== prefix && alias !== `${prefix} (${planLabel(info.planType)})`) return alias;
  return prefix;
}

function parseDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const numeric = /^\d+$/.test(raw) ? Number(raw) : NaN;
  const timestamp = Number.isFinite(numeric) ? (numeric < 1_000_000_000_000 ? numeric * 1000 : numeric) : Date.parse(raw);
  if (!Number.isFinite(timestamp)) return null;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDate(value) {
  const date = parseDate(value);
  if (!date) return "未取得";
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function expiryBucket(account) {
  if (account.usageInfo?.status === "expired") return "expired";
  const date = parseDate(account.accountInfo?.subscriptionActiveUntil);
  if (!date) return "missing";
  const diff = date.getTime() - Date.now();
  if (diff <= 0) return "expired";
  if (diff <= 24 * 60 * 60 * 1000) return "within-24h";
  if (diff <= 7 * 24 * 60 * 60 * 1000) return "within-7d";
  if (diff <= 30 * 24 * 60 * 60 * 1000) return "within-30d";
  return "active";
}

function expiryText(account) {
  const date = parseDate(account.accountInfo?.subscriptionActiveUntil);
  if (!date) return { label: "未取得", percent: 0 };
  const diff = date.getTime() - Date.now();
  if (diff <= 0) return { label: "已到期", percent: 0 };
  const days = Math.ceil(diff / (24 * 60 * 60 * 1000));
  return {
    label: days > 99 ? "99+ 天" : `${days} 天`,
    percent: Math.max(6, Math.min(100, Math.round(diff / (30 * 24 * 60 * 60 * 1000) * 100))),
  };
}

function matchesLimit(value, filter) {
  if (filter === "all") return true;
  if (typeof value !== "number") return false;
  if (filter === "0-33") return value <= 33;
  if (filter === "33-66") return value > 33 && value <= 66;
  return value > 66;
}

function filteredAccounts() {
  return (state.store.accounts || []).filter((account) => {
    const info = account.accountInfo || {};
    const usage = account.usageInfo || {};
    if (state.filters.plan !== "all" && info.planType !== state.filters.plan) return false;
    if (state.filters.expiry !== "all" && expiryBucket(account) !== state.filters.expiry) return false;
    if (!matchesLimit(usage.fiveHourLimit?.percentLeft, state.filters.hourly)) return false;
    if (!matchesLimit(usage.weeklyLimit?.percentLeft, state.filters.weekly)) return false;
    return true;
  });
}

function barClass(percent) {
  if (percent <= 20) return "bad";
  if (percent <= 45) return "warn";
  return "";
}

function usageLine(label, limit) {
  const percent = typeof limit?.percentLeft === "number" ? limit.percentLeft : null;
  const reset = limit?.resetTime ? ` · ${limit.resetTime}` : "";
  return `
    <div class="usage-line">
      <div class="usage-top"><span>${label}${reset}</span><strong>${percent === null ? "--" : `${percent}%`}</strong></div>
      <div class="bar"><span class="${percent === null ? "" : barClass(percent)}" style="width:${percent === null ? 0 : percent}%"></span></div>
    </div>
  `;
}

function renderSummary() {
  const total = (state.store.accounts || []).length;
  const visible = filteredAccounts().length;
  $("accountSummary").textContent = total === visible ? `目前顯示 ${total} 個帳號` : `目前顯示 ${visible} / ${total} 個帳號`;
  $("subtitle").textContent = total ? "管理多個 Codex 登入帳號" : "尚未加入帳號";
}

function renderAccounts() {
  const root = $("accounts");
  const accounts = filteredAccounts();
  $("empty").style.display = (state.store.accounts || []).length ? "none" : "block";
  root.innerHTML = accounts.map((account) => {
    const info = account.accountInfo || {};
    const usage = account.usageInfo || {};
    const expiry = expiryText(account);
    const status = usage.status && usage.status !== "ok" ? `<span class="pill danger">${usage.status}</span>` : "";
    const bucket = expiryBucket(account);
    const accountTags = [
      account.isActive ? `<span class="status-tag active-tag">目前使用</span>` : "",
      bucket === "expired" ? `<span class="status-tag danger-tag">已到期</span>` : "",
      ["within-24h", "within-7d"].includes(bucket) ? `<span class="status-tag warning-tag">即將到期</span>` : "",
    ].join("");
    return `
      <article class="account-card ${account.isActive ? "active" : ""}" data-id="${account.id}">
        <div class="card-head">
          <div class="identity">
            <div class="title-row">
              <span class="account-title" title="${displayName(account)}">${displayName(account)}</span>
              <span class="pill">${planLabel(info.planType)}</span>
              ${status}
            </div>
            <div class="email" title="${info.email || ""}">${info.email || "Unknown"}</div>
          </div>
        </div>
        ${accountTags ? `<div class="status-tags">${accountTags}</div>` : ""}
        <div class="usage">
          ${usageLine("5h 用量", usage.fiveHourLimit)}
          ${usageLine("每週用量", usage.weeklyLimit)}
          ${usageLine("Code Review", usage.codeReviewLimit)}
          <div class="usage-line">
            <div class="usage-top"><span>訂閱到期 · ${formatDate(info.subscriptionActiveUntil)}</span><strong>${expiry.label}</strong></div>
            <div class="bar"><span class="${barClass(expiry.percent)}" style="width:${expiry.percent}%"></span></div>
          </div>
          ${usage.message ? `<div class="meta">${usage.message}</div>` : ""}
          ${usage.lastUpdated ? `<div class="meta">最後更新：${formatDate(usage.lastUpdated)}</div>` : ""}
        </div>
        <div class="card-actions">
          ${account.isActive ? "" : `<button data-action="switch">切換</button>`}
          <button data-action="refresh">更新</button>
          <button data-action="delete">刪除</button>
        </div>
      </article>
    `;
  }).join("");
}

function render() {
  applyTheme(state.store.config?.theme);
  renderSummary();
  renderAccounts();
  scheduleAutoRefresh();
}

function syncSettingsForm() {
  const config = state.store.config || {};
  $("codexPathInput").value = config.codexPath || "codex";
  $("refreshIntervalInput").value = config.autoRefreshInterval ?? 30;
  $("closeBehaviorInput").value = config.closeBehavior || "ask";
  $("autoRestartInput").checked = !!config.autoRestartCodexOnSwitch;
  $("skipRestartConfirmInput").checked = !!config.skipSwitchRestartConfirm;
  $("accountsFilePath").value = state.storage.accountsFile || "";
  $("authStorePath").value = state.storage.authStoreDir || "";
  $("currentAuthPath").value = state.storage.currentCodexAuth || "";
}

function scheduleAutoRefresh() {
  if (state.autoRefreshTimer) {
    clearInterval(state.autoRefreshTimer);
    state.autoRefreshTimer = null;
  }
  const minutes = Number(state.store.config?.autoRefreshInterval || 0);
  if (!Number.isFinite(minutes) || minutes <= 0) return;
  state.autoRefreshTimer = setInterval(() => {
    if (state.busy || !(state.store.accounts || []).length) return;
    guarded("自動更新", async () => {
      const result = await apiCall("refresh_all_usage");
      state.store = result.store;
      render();
    });
  }, minutes * 60 * 1000);
}

async function reload() {
  const store = await apiCall("load_accounts");
  state.store = store;
  render();
}

async function guarded(label, fn) {
  try {
    setBusy(true);
    await fn();
  } catch (error) {
    toast(`${label}失敗：${error?.message || error}`);
  } finally {
    setBusy(false);
  }
}

async function openStorageFolder(key) {
  await guarded("開啟資料夾", async () => {
    const result = await apiCall("open_storage_folder", key);
    if (result?.path) toast(`已開啟：${result.path}`);
  });
}

async function init() {
  await new Promise((resolve) => {
    if (window.pywebview?.api) resolve();
    else window.addEventListener("pywebviewready", resolve, { once: true });
  });
  const initial = await apiCall("get_initial_state");
  state.appName = initial.name || "Codex Keyring";
  state.store = initial.store;
  state.storage = initial.storage || {};
  $("appTitle").textContent = state.appName;
  syncSettingsForm();
  showView("accounts");
  render();
}

$("themeToggle").addEventListener("click", () => guarded("切換主題", async () => {
  const next = state.store.config?.theme === "light" ? "dark" : "light";
  state.store = await apiCall("update_config", { theme: next });
  render();
}));

$("accountsNavBtn").addEventListener("click", () => {
  showView("accounts");
});

$("settingsNavBtn").addEventListener("click", () => {
  syncSettingsForm();
  showView("settings");
});

document.querySelector(".nav-dropdown__panel")?.addEventListener("click", (event) => {
  if (event.target.closest("button")) {
    event.currentTarget.closest("details")?.removeAttribute("open");
  }
});

$("saveSettingsBtn").addEventListener("click", () => guarded("儲存設定", async () => {
  state.store = await apiCall("update_config", {
    codexPath: $("codexPathInput").value.trim() || "codex",
    autoRefreshInterval: Number($("refreshIntervalInput").value || 0),
    closeBehavior: $("closeBehaviorInput").value,
    autoRestartCodexOnSwitch: $("autoRestartInput").checked,
    skipSwitchRestartConfirm: $("skipRestartConfirmInput").checked,
  });
  syncSettingsForm();
  render();
  toast("設定已儲存");
}));

$("openAccountsFolderBtn").addEventListener("click", () => openStorageFolder("accountsFile"));
$("openAuthFolderBtn").addEventListener("click", () => openStorageFolder("authStoreDir"));
$("openCurrentAuthFolderBtn").addEventListener("click", () => openStorageFolder("currentCodexAuth"));

$("importCurrentBtn").addEventListener("click", () => guarded("匯入目前 auth", async () => {
  try {
    const result = await apiCall("import_current_auth", false);
    state.store = result.store;
    render();
    toast("已匯入目前 auth");
  } catch (error) {
    const shouldImportMissingIdentity =
      String(error?.message || error).includes("missing_account_identity") &&
      await askConfirm({
        title: "帳號資訊不完整",
        message: "這份 auth 沒有可辨識的帳號資訊，仍要匯入嗎？",
        confirmText: "仍要匯入",
      });
    if (shouldImportMissingIdentity) {
      const result = await apiCall("import_current_auth", true);
      state.store = result.store;
      render();
      toast("已匯入目前 auth");
      return;
    }
    throw error;
  }
}));

$("quickLoginBtn").addEventListener("click", () => guarded("登入 Codex", async () => {
  toast("正在啟動 codex login，請依視窗提示完成登入");
  const login = await apiCall("start_codex_login");
  if (login.status !== "success") throw new Error(login.message || login.status);
  const result = await apiCall("add_account_json", login.authJson, null, true);
  await apiCall("import_current_auth", true);
  state.store = result.store;
  await reload();
  toast("Codex 登入完成");
}));

$("backupImportBtn").addEventListener("click", () => guarded("匯入備份", async () => {
  const result = await apiCall("choose_backup_import_file");
  if (!result) return;
  state.store = result.store;
  render();
  toast(`已匯入 ${result.importedCount} 個帳號`);
}));

$("backupExportBtn").addEventListener("click", () => guarded("匯出備份", async () => {
  const result = await apiCall("export_backup");
  if (result) toast(`備份已匯出：${result.path}`);
}));

$("refreshAllBtn").addEventListener("click", () => guarded("更新全部", async () => {
  const result = await apiCall("refresh_all_usage");
  state.store = result.store;
  render();
  toast(`更新完成：成功 ${result.updated}，未更新 ${result.missing}`);
}));

$("restartBtn").addEventListener("click", () => guarded("重新啟動 Codex", async () => {
  const result = await apiCall("restart_codex_processes");
  toast(result.appRestarted ? "已重新啟動 Codex" : "沒有找到可重新啟動的 Codex 程式");
}));

$("accounts").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const card = button.closest(".account-card");
  const id = card?.dataset.id;
  if (!id) return;
  const action = button.dataset.action;
  guarded("帳號操作", async () => {
    if (action === "switch") {
      const restart =
        !!state.store.config?.autoRestartCodexOnSwitch &&
        (state.store.config?.skipSwitchRestartConfirm ||
          await askConfirm({
            title: "重新啟動 Codex",
            message: "切換帳號後要重新啟動 Codex 嗎？",
            confirmText: "重新啟動並切換",
          }));
      const result = await apiCall("switch_account", id, restart);
      state.store = result.store;
      render();
      toast("已切換帳號");
    }
    if (action === "refresh") {
      const result = await apiCall("refresh_usage", id);
      state.store = result.store;
      render();
      toast(result.result.status === "ok" ? "用量已更新" : `用量更新失敗：${result.result.message || result.result.status}`);
    }
    if (
      action === "delete" &&
      await askConfirm({
        title: "刪除帳號",
        message: "確定要刪除這個帳號嗎？此操作會移除本機保存的 auth 備份。",
        confirmText: "刪除",
        danger: true,
      })
    ) {
      state.store = await apiCall("remove_account", id);
      render();
      toast("帳號已刪除");
    }
  });
});

for (const [id, key] of [["planFilter", "plan"], ["expiryFilter", "expiry"], ["hourlyFilter", "hourly"], ["weeklyFilter", "weekly"]]) {
  $(id).addEventListener("change", (event) => {
    state.filters[key] = event.target.value;
    render();
  });
}

$("clearFiltersBtn").addEventListener("click", () => {
  state.filters = { plan: "all", expiry: "all", hourly: "all", weekly: "all" };
  $("planFilter").value = "all";
  $("expiryFilter").value = "all";
  $("hourlyFilter").value = "all";
  $("weeklyFilter").value = "all";
  render();
});

init().catch((error) => {
  toast(`啟動失敗：${error?.message || error}`);
});
