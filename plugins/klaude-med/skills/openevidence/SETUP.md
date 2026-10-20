# OpenEvidence MCP 安裝說明（給朋友）

`openevidence` / `medq` / `oe-triangulate` 等 skill 需要一個 **OpenEvidence MCP server**。這個 server **不包含在本外掛裡**，也**不是 OpenEvidence 官方產品**，需要你自行安裝。沒裝也不會壞：skill 會告訴你缺少 OpenEvidence，`medq` 與 `oe-triangulate` 會自動降級（見各自 SKILL.md）。

## 它是什麼

社群開源專案 [`htlin222/openevidence-mcp`](https://github.com/htlin222/openevidence-mcp)（Apache-2.0，非官方）。原理：透過你瀏覽器中**已登入的 OpenEvidence 分頁**代為發出請求（以一個小型瀏覽器擴充功能當橋接），所以**不需要 API key**，你的瀏覽器登入就是唯一憑證。需要你本來就有合法的 OpenEvidence 帳號（免費註冊的醫療人員帳號即可）。

## 前置需求

- Node.js 20 以上、git、make
- Chromium 系瀏覽器（Chrome / Edge / Brave / Arc）
- 已註冊並可登入的 [openevidence.com](https://www.openevidence.com) 帳號
- Claude Code（`claude` CLI）

## 安裝步驟

```bash
git clone https://github.com/htlin222/openevidence-mcp.git
cd openevidence-mcp
make all      # 安裝依賴、編譯 server 與擴充功能、並註冊到 Claude Code（有裝 Codex 也會註冊）
```

然後做一次無法自動化的瀏覽器步驟：

1. 開 `chrome://extensions` → 開啟「開發人員模式」→「載入未封裝項目」→ 選擇專案裡的 `extension/dist` 資料夾。
2. 在同一個瀏覽器登入 [openevidence.com](https://www.openevidence.com)，並**保持一個 OpenEvidence 分頁開著**（這個登入就是認證）。
3. 重啟 Claude Code，輸入 `/mcp` 確認 `openevidence` 為 connected。

驗證：

```bash
curl -s http://127.0.0.1:8787/health     # 預期看到 {"ok":true,"connected":true,...}
```

之後在 Claude Code 說「用 OE 查 …」，或直接 `/openevidence`、`/medq`。

## 更新 / 移除

```bash
make update      # 拉最新版、重新編譯與註冊（之後到 chrome://extensions 按 Reload）
make uninstall
```

## 常見問題

- **tool 找不到 `mcp__openevidence__*`**：沒註冊成功或沒重啟。重跑 `make all`、重啟 Claude Code。
- **auth 失敗 / connected:false**：OpenEvidence 分頁沒開、登出了、或擴充功能沒載入。
- 回應要 30–120 秒屬正常；回應很大時 Claude Code 會把結果存成 `.txt`，skill 會用 `scripts/parse_oe.py` 解析。
- 安裝細節與最新指令以專案 README 為準。

## 選用：citation 稽核

想逐條稽核 OpenEvidence 的引用是否真實，可另外安裝上游的 skill：`npx skills add htlin222/audit-oe-skill`（本外掛不內建）。
