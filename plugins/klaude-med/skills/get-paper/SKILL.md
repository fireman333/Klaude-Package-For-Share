---
name: get-paper
description: "合法下載期刊全文 PDF：Unpaywall（開放取用 OA）優先，fallback 走你自己機構的授權入口（機構 VPN / 圖書館 EZproxy 登入網址）。觸發關鍵詞：/get-paper、/getpaper、/gp、下載這篇 paper、抓這篇全文、給我這篇 PDF、fetch this paper、download this PDF、ezproxy 下載、圖書館下載、給我 DOI 全文。即使只丟一個 DOI / 期刊網址並說「幫我抓」「給我這篇」「下載這篇」也應觸發。"
---

# get-paper — 合法全文下載器

只走合法路徑：
1. **Unpaywall API / Europe PMC** — 開放取用（OA）論文，不需任何設定（只要一個 email）
2. **你自己機構的授權入口**（選用，需設定一次）：
   - `direct`：連上機構 VPN（或自備的 SOCKS/HTTP proxy），用機構 IP 直接抓
   - `prefix`：圖書館的 EZproxy 登入網址前綴（`proxy_prefix`）
   - `ezproxy`：改寫主機名稱型的 EZproxy（`proxy_host_suffix`）

## 快速開始（只要 OA）

```bash
pip3 install requests beautifulsoup4          # 一次性
export UNPAYWALL_EMAIL="you@example.com"      # 任何真實 email；Unpaywall 要求禮貌識別，不會寄信
python3 ${CLAUDE_SKILL_DIR}/scripts/get_paper.py 10.1371/journal.pmed.1000097 -v
```

PDF 預設存到 `~/Downloads/papers/<doi-safe>.pdf`。沒有 `config.json` 也能跑（OA-only）。

## 機構入口設定（選用）

1. 複製設定範本：`cp ${CLAUDE_SKILL_DIR}/config.example.json ${CLAUDE_SKILL_DIR}/config.json`（或放別處，用環境變數 `GET_PAPER_CONFIG=/path/to/config.json` 指定；外掛更新時 skill 資料夾可能被覆蓋，建議用後者）。
2. 依你的機構挑一種：

### A. 圖書館 EZproxy 登入網址（`mode: "prefix"`，最常見）

大多數醫院 / 大學圖書館都有「校外連線 / Off-campus access」頁面。找法：
- 圖書館網站搜尋「EZproxy」「校外連線」「proxy」「remote access」。
- 或：在任一期刊頁面（已知有訂閱）點圖書館提供的 bookmarklet / 「Access via library」連結，登入後觀察網址列：通常長得像 `https://<your-library-proxy>/login?url=https://www.nejm.org/...`。`url=` 之前（含 `url=`）就是 `proxy_prefix`。
- 設定：`"mode": "prefix", "proxy_prefix": "https://<your-library-proxy>/login?url="`。
- 匯出登入 cookies：Chrome 裝「Get cookies.txt LOCALLY」→ 先登入圖書館 proxy 並打開任一期刊頁 → 匯出 Netscape 格式 `cookies.txt`，路徑填在 `cookies_path`（預設 skill 資料夾內 `cookies.txt`）。cookies 約一週過期，過期重匯。**cookies.txt 等於你的圖書館登入身分，不要上傳、不要分享。**

若期刊網址變成 `www-nejm-org.<your-suffix>` 這種「點換成橫線」的形式，是主機改寫型：`"mode": "ezproxy", "proxy_host_suffix": "<your-suffix>", "proxy_port": null`，同樣需要 cookies.txt。

### B. 機構 VPN（`mode: "direct"`）

你的機構若只提供 VPN（沒有 EZproxy）：
- 全機 VPN：連上 VPN 後直接 `python3 .../get_paper.py <DOI> --direct`，script 偵測到 VPN 隧道（`utun` 預設路由）就照跑。
- 只讓這一步走 VPN（進階）：自己起一個 SOCKS/HTTP proxy（例如 userspace VPN 客戶端提供 `127.0.0.1:1080`），填 `"socks_proxy": "socks5h://127.0.0.1:1080"` 或 `"http_proxy": "http://127.0.0.1:8080"`。OA 與 doi.org 仍直連，只有機構那一步走 proxy。
- 也可用環境變數 `ALL_PROXY` / `HTTPS_PROXY`。
- 都沒有時，script 會在打出版社之前以 exit 7 提示，不會亂打。

## CLI

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/get_paper.py <DOI或含DOI的網址> [選項]
#  --oa-only      只試開放取用，不碰機構入口
#  --proxy-only   跳過 OA，直接走機構
#  --direct       強制 direct（VPN/proxy）
#  --proxy        強制圖書館 proxy（有 proxy_prefix 走 prefix，否則 ezproxy）
#  -o PATH        指定輸出
#  -f             已存在也重抓（預設跳過，避免重複打出版社）
#  -v             除錯輸出
```

### Exit codes

| Exit | 意義 |
|---|---|
| 0 | 成功 |
| 1 | 缺 curl / 設定不完整 |
| 2 | DOI 抽不到 / 旗標衝突 |
| 3 | OA 找不到（`--oa-only` 才會 exit 3） |
| 4 | cookies.txt 缺 / 壞 |
| 5 | publisher fetch HTTP error / PDF URL 找不到 |
| 6 | 下載到的不是 PDF（cookies 過期 / VPN 中斷 / paywall 多一層） |
| 7 | 沒有機構路由（沒設 proxy 也沒開 VPN）/ 機構入口 403（Cloudflare bot challenge） |

## Claude 使用時的流程

1. **抽 DOI** — 使用者丟 DOI / 網址就直接抽；只給標題 → 用 PubMed MCP / `pubmed-search` / `openevidence` 先拿 DOI。
2. **先跑 OA**：`python3 ${CLAUDE_SKILL_DIR}/scripts/get_paper.py <DOI> --oa-only -v`。成功就結束。
3. **OA 失敗才走機構入口**：確認 `config.json` 已設定；direct 模式先確認使用者已連上 VPN / proxy。沒設定 → 告訴使用者怎麼設（見上），或請他用圖書館網站手動下載，不要亂試。
4. **打開檢視** — macOS `open <path>` 讓使用者確認抓對篇。

## 已知坑

- **為何用 curl 不用 `requests`**：Cloudflare 會擋 `requests` 的 TLS 指紋；script 對出版社一律走系統 curl（doi.org / Unpaywall API 例外）。
- **OA 優先走 Europe PMC render endpoint**（`europepmc.org/articles/<PMCID>?pdf=render`）：`pmc.ncbi.nlm.nih.gov` PDF、BMC `/counter/pdf/`、部分機構 repository 會回 HTTP 200 + 一頁 bot-check HTML 或 Cloudflare 403，而不是錯誤碼；script 以 `%PDF-` magic bytes 驗證，失敗不留假檔。
- **Unpaywall `best_oa_location.url_for_pdf` 常為 None**（即使 `is_oa=True`，PLOS 常見）：script 掃全部 `oa_locations`。
- **PMCID 查詢有備援**：NCBI ID Converter 限流（429）時改查 Europe PMC。
- **部分出版社對 curl 也會 Cloudflare 403**（常見：OUP、Mary Ann Liebert、SAGE、JAMA 系列有時也會；Elsevier ScienceDirect 的 landing page 純 JS、Cochrane `/pdf/full` 回 HTML）：此時用瀏覽器手動下載（圖書館連結 → Download PDF）。出版社相容性依你的機構訂閱與當時反爬規則而異，以實測為準。
- **`find_pdf_url` 是 DOI-aware**：長 review 的 references 常含他篇 `.pdf` 連結，anchor fallback 優先選 URL 含目前 DOI 者；`citation_pdf_url` meta 永遠最優先。
- **HttpOnly cookies** 無法用 `document.cookie` 取得，所以本 skill 靠瀏覽器擴充功能匯出的 cookies.txt。

## 合法性

- 只在**使用者所屬機構有訂閱**的期刊走機構入口；VPN / EZproxy 是圖書館的合法授權機制。
- **不要**用來繞過授權（借用別人的帳號、爬未訂閱期刊、繞付費牆）；OA 以外沒有訂閱就請改走圖書館館際合作（ILL）或聯絡作者。
- 大量自動下載可能違反期刊 ToS 或觸發 IP 封鎖：單次手動使用，同一出版社一次一篇、間隔數分鐘，不要批次 loop 抓數百篇。
