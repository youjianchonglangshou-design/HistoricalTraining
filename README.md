# SState Market Terminal

### v0.1.37 GLM response parser + reasoning retry 修正

這版修正 v0.1.35 的關鍵 bug：Cloudflare GLM-4.7-Flash 回傳的是 chat-completions wrapper，真正 JSON 在 `choices[0].message.content`。v0.1.35 把 wrapper 本身當 JSON，所以即使 GLM 已選出事件，最後仍被寫成 `selected_count: 0`。

另外 GLM 偶爾會把 completion token 全花在 reasoning，造成 `message.content = null`。v0.1.37 先使用 `reasoning_effort: low`，若仍沒有 final JSON，自動以精簡候選資料重試一次；兩次都失敗才回 502，而且不寫入 24H 快取。

### v0.1.35 Tavily 廣搜 + GLM-4.7-Flash 語意篩選 / 繁中

- Pionex 美股/RWA token 先解析「代幣 → underlying ticker → 正式名稱/別名 → asset_type」，補齊目前 active/pending 清單中原先只剩 ticker 的公司、ETF 與商品。
- Tavily 搜尋依 public/private company、ETF、commodity 分流，不再拿同一套「公司財報」Prompt 查 USO / WTI / 黃金 / 半導體 ETF。
- 搜尋仍維持 `search_depth=basic`、最多 10 則；`include_answer=advanced` 只用來取得更完整的繁中 Answer。
- Worker 新增 `summary_zh_tw`、`display_title_zh_tw`、`display_detail_zh_tw`；主 UI 優先顯示繁體中文，原始英文標題只保留在查證來源。
- 新 pipeline 會使舊 Tavily 24H cache 失效一次，下一次點擊會重新取得新格式資料。

**版本：`TERMINAL v0.1.37｜GLM-PARSER-RETRY`**

#### v0.1.35 新聞管線

```text
點擊 S3 / S0.5 / S1 新聞
  ↓
資產 Profile：派網代幣 → underlying / 公司或資產別名 / asset_type
  ↓
Tavily Basic Search（topic=news、week、max_results=20、chunks_per_source=3）
  ↓
Cloudflare Workers AI：@cf/zai-org/glm-4.7-flash
  ↓
依原始搜尋指令判斷所有候選：保留真正重大事件、淘汰舊事件/索引頁/投資評論/無關內容
  ↓
產出繁中 summary_zh_tw + display_title_zh_tw + display_detail_zh_tw
  ↓
每則事件綁定 Tavily source_index；只使用原候選 URL 做查證
  ↓
R2 24H cache.json + latest.json
```

注意：Tavily Search API 的 `max_results` 官方上限是 20，所以 v0.1.35 是「不再限制 10 則」，直接使用 API 可取的最大 20 則；若省略此參數反而會回到預設 5。GLM 不設定固定最終事件數，有幾則真正符合就保留幾則。

Cloudflare Worker 必須新增 **Workers AI binding**，名稱固定為 `AI`；`TAVILY_API_KEY` Secret 與 `JSON_BUCKET` R2 binding 照舊。

Streamlit 脫殼 Stage 1：GitHub Pages 靜態 HTML/JS/CSS + Cloudflare Worker/R2 + GitHub Actions Python 引擎。

## 已完成的資料流

```text
GitHub Pages
  ├─ 開站：只讀 R2 最後一次 snapshot + 已查詢新聞快取
  ├─ 完整分析：POST Cloudflare Worker → full-analysis.yml → Pionex + S-state + R2
  └─ S3 / S0.5 / S1 卡片「🔎 等待查詢」：使用者點擊單一標的
                                     ↓
                         Cloudflare Worker 直接呼叫 Tavily
                                     ↓
                         Basic Search 廣搜最多 10 則
                                     ↓
                         資產 Profile → GLM-4.7-Flash 語意篩選 + 繁中
                                     ↓
                         該標的固定 24H Cache + research R2
```

新聞查詢與完整分析是兩條完全獨立的事件。完整分析與自動排程都不會自動查新聞。

Stage 1 **不使用 D1**。Runtime 最新 JSON 以 R2 為唯一 source of truth；GitHub 只負責程式碼與 Actions。

## Repo 主要檔案

- `index.html`：GitHub Pages 主畫面
- `styles.css`：Streamlit 視覺脫殼版
- `app.js`：讀 latest / 完整分析 / polling / JSON 下載 / SVG 圖表
- `config.js`：只需填 Worker URL
- `engine/`：由原 Streamlit 拆出的 headless Python S-state engine
- `.github/workflows/full-analysis.yml`：Cloudflare 呼叫的完整分析
- `.github/workflows/deploy-pages.yml`：GitHub Pages
- `cloudflare/worker.js`：R2 + GitHub dispatch + 單一標的 Tavily 廣搜 / GLM-4.7-Flash 篩選 / 公司別名
- `cloudflare/wrangler.toml.example`：R2 binding / Worker vars
- `data/bootstrap/`：R2 尚未設定時的最後一次畫面 fallback

## 第一次部署順序

### 1. 把整包內容上傳到 `SStateMarketTerminal`

保留目錄層級。原本 GitHub 自動建立的 `README.md` 可以直接用本檔覆蓋。

### 2. GitHub Pages

Repository → Settings → Pages → Source 選 **GitHub Actions**。

`Deploy GitHub Pages` workflow 會部署根目錄的 `index.html`。

### 3. Cloudflare 建 R2

建議 bucket：

```text
sstate-market-data
```

Worker 的 R2 binding 固定叫：

```text
JSON_BUCKET
```

### 4. 建 Cloudflare Worker

把 `cloudflare/worker.js` 貼進 Worker，並綁定上面的 R2 bucket。

Worker Variables：

```text
GITHUB_REPOSITORY = youjianchonglangshou-design/SStateMarketTerminal
GITHUB_BRANCH = main
ALLOWED_ORIGIN = https://youjianchonglangshou-design.github.io
```

Worker Secrets：

```text
GITHUB_TOKEN
CALLBACK_TOKEN
TAVILY_API_KEY
```

`TAVILY_API_KEY` 只放在 Cloudflare Worker Secret。GitHub Pages 不會拿到這把 Key。

`GITHUB_TOKEN` 建議用 fine-grained token，只授權此 repo，Repository permissions → **Actions: Read and write**。

`CALLBACK_TOKEN` 自己產生一串長隨機字串，例如 40+ 字元；它只用於 GitHub Actions 回寫 Worker。

### 5. GitHub Actions Secrets

SStateMarketTerminal → Settings → Secrets and variables → Actions：

```text
WORKER_BASE_URL
WORKER_CALLBACK_TOKEN
```

其中：

```text
WORKER_BASE_URL = https://你的-worker.workers.dev
WORKER_CALLBACK_TOKEN = 與 Cloudflare CALLBACK_TOKEN 完全相同
```

### 6. `config.js` 填 Worker URL

```js
window.SSTATE_CONFIG = {
  workerUrl: "https://你的-worker.workers.dev",
  ...
};
```

前端**不放 GitHub Token，也不放 CALLBACK_TOKEN**。

### 7. 第一次 Seed R2（推薦）

Windows PowerShell 在 repo 根目錄：

```powershell
.\tools\seed-r2.ps1 `
  -WorkerUrl "https://你的-worker.workers.dev" `
  -CallbackToken "你的 CALLBACK_TOKEN"
```

會把：

```text
engine/models/probability_model.json
→ models/active/probability_model.json

data/bootstrap/snapshot_ai.json
→ latest/crypto/snapshot_ai.json

data/bootstrap/snapshot_us_stock_ai.json
→ latest/us-stock/snapshot_us_stock_ai.json
```

如果不 seed，網站仍會先讀 repo bootstrap；第一次完整分析成功後，R2 snapshot 會自動建立。Active model 若 R2 尚不存在，Action 會先用 repo 內的模型 fallback。

## 網站行為

### 開啟網站

不抓 Pionex、不跑 Python：

```text
GET /api/snapshot?market=crypto
```

只呈現 R2 最後一次成功資料。

### 按「完整分析」

```text
POST /api/analysis/start
```

Worker 建 `run_id` → 呼叫 `full-analysis.yml` → Python 重新抓 Pionex → S-state → Level 5 → R2。

### S3 / S0.5 / S1 卡片的「🔎 等待查詢」

只有目前 S-state 為 `S3` / `S0.5` / `S1` 的美股代幣會顯示呼吸光暈查詢膠囊。**不點就完全不呼叫 Tavily。**

點單一標的：

```text
POST /api/research/us-stock/symbol
{ "symbol": "MSFTX" }
```

Worker 先讀 R2 最新美股 snapshot 核對該標的與 S-state，再執行：

```text
Tavily Basic Search（最多 10 個候選）
→ Cloudflare Workers AI GLM-4.7-Flash 依原始指令做語意過濾、事件判斷與繁中整理
→ research/us-stock/cache.json
→ research/us-stock/latest.json
```

成功結果在 24 小時內固定不換：再次點擊同一標的只回傳既有 Cache，不重新搜尋、不覆蓋。重新整理頁面後仍從 R2 載入同一份結果。

完整分析與 Auto Batch **不包含新聞研究 step**，因此市場排程不會消耗 Tavily credits。

### 右上角 JSON

市場 JSON 下載的是目前頁面同一份 R2 snapshot。`⬇ 新聞 JSON` 則下載 `research/us-stock/latest.json`，內容只包含使用者曾主動查詢並成功寫入 R2 的新聞結果。

## R2 Key v1

```text
latest/crypto/snapshot_ai.json
latest/us-stock/snapshot_us_stock_ai.json
runs/<run_id>/status.json
runs/<run_id>/snapshot_ai.json
runs/<run_id>/snapshot_us_stock_ai.json
models/active/probability_model.json
```

## Stage 2（尚未接）

下一階段才接 `HistoricalTraining`：

```text
Cloudflare Cron
  ↓
Daily S-state Learning
  ↓
Candidate probability model
  ↓
Champion / Challenger evaluation
  ↓
通過 promotion gate
  ↓
R2 models/active/probability_model.json
```

不採用「每天產生新模型就直接覆蓋 active」。


## v0.1.37 LLAMA-JSONMODE

- 修正 v0.1.36：GLM-4.7-Flash 可能只回 reasoning、沒有 final JSON，造成 502。
- 不再使用 GLM 作新聞語意篩選器。
- Primary：`@cf/meta/llama-3.1-8b-instruct-fast`
- Fallback：`@cf/meta/llama-3.3-70b-instruct-fp8-fast`
- 兩者皆走 Workers AI JSON Mode `json_schema`。
- Parser 同時支援 Workers AI JSON Mode 的 `{ response: {...} }` 物件輸出。
- Tavily 仍負責廣搜最多 20 個候選；AI 負責事件過濾與 zh-TW 改寫。
- Primary 失敗才啟用 70B fallback；兩層失敗才回 502，而且不寫入 24H cache。
