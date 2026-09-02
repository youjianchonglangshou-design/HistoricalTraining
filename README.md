## v3.6.0｜08:25 Formal Champion Exam + Daily-Confirmed Settlement

正式語意改成「每天只考一次，而且每天只批一次完整日週期」：

```text
00:01 / 04:01 / 12:01 / 16:01 / 20:01  → Live Monitor
08:01                                  → 不再跑 pair（避免和正式考試重複）
08:25                                  → Terminal 正式 Champion Crypto + 美股分析
                                          ↓
                                  兩邊 checkpoint 都寫入 R2
                                          ↓
                                  自動觸發 HistoricalTraining
                                          ↓
                           凍結今天考卷 + 批改昨天以前考卷
```

正式 R2 checkpoint：`runs/champion/YYYY-MM-DD_0825/`。

- 一天仍維持 **6 次 pair 分析**：00:01、04:01、08:25、12:01、16:01、20:01。
- 六次 Live 過程中任何暫時 S-state 都**不能**決定考卷成功。
- `12H` 只做盤中觀察，不進正式命中率。
- `24H / 48H / 72H` 只比較後續每天正式 08:25 checkpoint。
- S2 盤中曾閃成 S3、隔天 08:25 還是 S2：判定 **ALIVE / 尚未成功**，不是 SUCCESS。
- S3 隔天 08:25 退回 S2：`趨勢延續` 題判定 **TRUE_FAIL**。
- 舊 v3.5 的 intraday settlement 會重新批改；Frozen Prediction 本身不做賽後回算。若同一天已有舊 04:01 考卷且能取得新的 08:25 正式考卷，當天舊考卷會被正式 08:25 考卷取代。
- 歷史模型 Replay 同步改成每日完整收線案例；內部仍逐根 4H 計算 ADX / DMI / state-age features，但模型只從每日確認點建立 decision case，避免下一代繼續學盤中假突破。
- R2 Sharded Ledger、120 筆 Evolution Review → Policy → Adaptive Retraining 閉環維持。

> v3.4 / v3.5 的 04:01 checkpoint 內容只保留作版本歷史，已不是現行契約。

## v3.5.0｜R2 Sharded Frozen Ledger + Error-Driven Evolution Engine

### 1. Frozen Ledger 改為 R2 Generation / 日期分片

`data/champion/ledger.jsonl` 不再是長期資料庫。第一次 v3.5 每日流程會在 R2 尚未有 ledger 時，使用舊 `ledger.jsonl` 做一次 migration seed；成功上傳 R2 後，workflow 會把 GitHub 的舊 ledger 移除。

正式來源：

```text
champion/ledger/
├─ GEN001/
│  ├─ 2026-09-01.json
│  ├─ 2026-09-02.json
│  └─ ...
├─ GEN002/
│  └─ ...
└─ ...
```

同一天的 shard 會隨 12H / 24H / 48H / 72H 結算更新同一個 R2 key，不建立重複考卷。

08:25 HistoricalTraining 開始時，只從 R2 下載最近 90 日 rolling ledger 到 `/tmp`，用來追蹤尚未結算與本代學習；長期歷史由 R2 shards 永久保存。`performance.json` 與 Evolution review/policy 也會同步到 R2。

### 2. evolution_review 正式成為下一代訓練輸入

以前 120 筆到達後只是「同一套 10x live reinforcement 再跑一次」。v3.5 改成：

```text
Frozen 72H 真實考卷
→ evolution_review.json
→ 找出高信心失敗、低信心成功、State / 市場 / ADX regime / ADX turn 校準偏差
→ evolution_policy.json
→ 每一筆 live case 產生不同 reinforcement weight
→ run_training.py
→ 下一代 Champion
```

主要規則：

- 預估成功 ≥65% 卻沒有成功：最高優先錯題。
- TRUE_FAIL 且原本成功率偏高：提高錯題權重。
- 預估 ≤45% 卻成功：保留被 Champion 低估的正面案例。
- 同一 `S-state + DMI/ADX regime` 或 `S-state + ADX turn` 若反覆校準偏差，整組 live evidence 會提高學習權重。
- 所有 adaptive weight 都有上限（50x），避免少數異常行情摧毀約 20 萬筆歷史基準。
- `engine/scoring_rules.py` 仍禁止自動改寫；Evolution Engine 調整的是下一代模型如何吸收真實錯題，不會自行發明新的 S-state 定義。

因此閉環現在是：

```text
Champion
→ 08:25 Formal Frozen
→ 12H Observation + 24/48/72H Daily-Confirmed Settlement
→ 120 筆
→ Error Review
→ Evolution Policy
→ Adaptive Retraining
→ Next Champion
→ 0/120 重新考試
```

## v3.4.0｜04:01 Terminal 真實 Champion Checkpoint → 08:25 結算

- 正式 Frozen Snapshot 不再由 08:25 HistoricalTraining 重新計算預測。
- Terminal 每天台灣 **04:01** 的 Crypto + 美股分析會保存到 R2 `runs/champion/YYYY-MM-DD_0401/`。
- 08:25 由 Cloudflare Worker 觸發 HistoricalTraining，先讀取當天 04:01 checkpoint，再把「04:01 當時真正顯示過的 Champion 機率／S-state／ADX／DI」凍結進 ledger。
- 08:25 仍會更新 Pionex 4H cache，但只用來回頭結算舊 Frozen Snapshot 的 12H / 24H / 48H / 72H 路徑；不再拿 08:25 的 partial Daily 狀態建立新預測。
- 04:01 checkpoint 的 `generated_at_taiwan` 會向下對齊到真正的 4H candle cutoff（04:00）作為 settlement key，同時保留 `checkpoint_time_tw` 顯示實際 04:01 分析時間。
- 若 04:01 checkpoint 的 model_id 與 08:25 Active Champion 不一致，該 checkpoint 不會被錯掛到另一個 Generation。
- 120 筆世代門檻、Crypto + 美股、10x live reinforcement 規則維持不變。

# Crypto S-state Learning Engine v3.2 — Champion Frozen Settlement / ADX 1DP Sticky

這個儲存庫用 Pionex 歷史 4H K 線逐根重播正式 S-state 引擎，然後把每個歷史決策點的未來結果結算成 JSON 參數，供 Crypto Monitor / HTML 使用。

## 核心契約

- `engine/scoring_rules.py`：**不由訓練程式改寫**。S0 / S0.5 / S1 / S2 / S3 仍由正式引擎判斷。
- `models/probability_model.json`：訓練結果；會隨歷史與每日新行情持續進化。
- Replay 與即時系統必須使用同版 S-state 引擎。
- LLM 不發明機率；機率來自已結算歷史樣本。



## v3.2：改成 Champion → Frozen Snapshot → Settlement → Evolution

這一版正式移除 Champion / Challenger 競賽主流程。系統只追蹤目前正式 Champion。

目前基準世代：

```text
Generation 001
Champion = a9a998d93ea396e4
```

每天台灣時間 **08:25** 由 **Cloudflare Worker** 觸發 GitHub Actions 的 `Daily Champion Settlement & Evolution`；HistoricalTraining 本身不另外建立 08:25 cron：

```text
下載 R2 Active Champion
→ 更新 Pionex 4H cache
→ 把今天 Champion 對 S0.5 / S1 / S2 / S3 的正式預測凍結
→ 回頭結算之前凍結快照的 12H / 24H / 48H / 72H 真實路徑
→ 更新 data/champion/performance.json
→ 累積足夠 72H 正式結算後觸發 Evolution Review
→ 重訓下一代模型
→ 直接發布為新的 Champion / Active
```

### Frozen Snapshot 契約

凍結後永遠不回算。每筆至少保存：

- Champion model id / Generation
- 標的、決策時間、S-state、目標
- 當時成功率、慢速存活率、結構存活率、真失敗率、其他率
- 當時 ADX / DI / DMI regime 等 features
- 之後逐步追加 12H / 24H / 48H / 72H settlement
- 72H 實際 state path，例如 `S2 → S3`

歷史 Replay 仍可因模型公式升級而重新計算；R2 `champion/ledger/GENxxx/YYYY-MM-DD.json` 的 Frozen Prediction 不允許被新模型改寫。

### 戰績輸出

`data/champion/performance.json` 會直接提供後續 SStateMarketTerminal「近期戰績」頁需要的資料：

- 近 7 / 14 / 30 / 90 日 / 全部
- S0.5 / S1 / S2 / S3 分別的成功、存活、真失敗、其他
- 成功率、結構存活率、真失敗率
- 預估成功率 ≥60% / ≥65% / ≥70% 的實際成功率
- 最近逐筆凍結紀錄與 72H 實際 state path

預設當本代 Champion 累積 **120 筆 72H 正式結算** 時觸發一次 Evolution Review。新 Champion 上線後會建立下一代，計數重新從 0/120 開始；不會變成 120 筆之後每天多幾筆就重訓。門檻保存在 `data/champion/generation.json`，可再調整。

## DMI Expert v3：ADX 1 位小數 + 同值延續正式進入歷史學習

Terminal 的 ADX 階梯定義直接照 Pine / 前端顯示：

```text
先將 ADX 四捨五入到小數 1 位
目前 1dp > 前一個日 1dp  → RISING / 綠色階梯
目前 1dp < 前一個日 1dp  → FALLING / 紅色階梯
目前 1dp = 前一個日 1dp  → 延續上一個有效 RISING / FALLING，不建立灰色 FLAT
```

**綠色不等於多方、紅色不等於空方。** 多空方向仍由 `DI+ / DI-` 誰主導決定。因此歷史案例會形成：

```text
PLUS_RISING    DI+ 主導 + ADX 增強
PLUS_FALLING   DI+ 主導 + ADX 衰退
MINUS_RISING   DI- 主導 + ADX 增強
MINUS_FALLING  DI- 主導 + ADX 衰退
```

每個 S-state 自己學這四種狀態的成功 / 存活 / 真失敗率，不寫死「PLUS_RISING 一定好」或「MINUS_RISING 一定壞」。這一點對 S2 特別重要：`DI-` 暫時接管可能只是正常回檔，也可能正在形成真正空方趨勢，必須交給歷史樣本判斷。

新增的歷史特徵包括：

```text
adx_step_direction    RISING / FALLING（1dp 相等時延續上一方向）
adx_step_age_days     目前紅/綠階梯連續幾個日階
adx_step_age_bin      1 / 2_3 / 4_6 / 7_PLUS
adx_turn_event        RED_TO_GREEN / GREEN_TO_RED / OTHER_TURN / NONE
adx_axis_zone         BELOW_20 / ABOVE_20 / TOUCHING_20
dmi_adx_regime        PLUS_RISING / PLUS_FALLING / MINUS_RISING / MINUS_FALLING
```

模型新增三個獨立 facets，避免硬疊成 Level 6+ 導致樣本碎裂：

1. `adx_step_regime`：DI 主導 + ADX 紅綠階梯 + ADX 是否在 20 以下/以上
2. `adx_step_persistence`：誰主導 + 紅綠階梯已持續多久
3. `adx_turn_handover`：DI 主導/交叉年齡 + ADX 是否剛紅轉綠或綠轉紅

訓練後 `reports/training_report.json` 除了原本 `dmi_expert_72h`，還會新增 **`adx_step_regime_72h`**，專門列出 S0.5 / S1 / S2 / S3 各自最有利、最不利的紅綠階梯組合與樣本數。

### 時間語意

HistoricalTraining 每 4H 建立 decision case；ADX 階梯會先把「當時可見的當日日 ADX」與「前一日日 ADX」各自四捨五入到小數 1 位再比較，若相同則延續上一個有效紅／綠方向，因此與 Terminal / Pine 的新版 stepline 語意一致。當日日 K 在歷史 cutoff 仍是 partial candle，不會偷看當天未來尚未發生的 4H。

遷移期間每筆 replay 也保留 `*_legacy` 的 v2 完整小數 ADX 階梯特徵，讓尚未升級的 R2 Active v2 模型仍可用原語意匹配；新 v3 模型只使用新版 generic ADX Step 特徵。

## v3：DMI Expert 不改 S-state，只修正「這個 S-state 能不能真的走上去」

`S0.5 / S1 / S2 / S3` 的定義仍完全由 `engine/scoring_rules.py` 決定。v3 新增的 DI+ / DI- / ADX 只作為**第二層歷史證據**，用來修正原本 BB + HA 黃紫階梯模型的成功率、結構存活率與真失敗率。

DMI 公式與 SStateMarketTerminal 完全同源：Period 14、TR/DM 採 Pine 原式遞迴平滑，`DI+ / DI- / DX` 依原式計算，`ADX = SMA14(DX)`。歷史 replay 在每一根 4H cutoff 只用當時已經出現的資料，當日 K 仍是當時尚未收完的 partial daily candle，因此不偷看未來。

每一筆歷史案例會保存原始值與動態：

```text
DI+ / DI- / Gap
誰領先（PLUS / MINUS / TIE）
雙方相對 20 軸的位置
距離 20 軸有多近
領先關係已維持幾根 4H（可辨認剛交叉）
DI+ / DI- / Gap 最近 3 日斜率
ADX / ADX 最近 3 日斜率
```

為避免把樣本切得過碎，DMI **不硬疊成 Level 6、7、8**。模型保留原本四個 DMI facets，並由 v2 再加入三個 ADX Step facets：

1. `lead_axis`：誰領先 + 20 軸結構 + 距離 20 軸
2. `cross_momentum`：誰領先 + 剛交叉/維持多久 + Gap 變化
3. `line_motion`：DI+ 與 DI- 各自正在上升或下降的相對位置
4. `trend_strength`：DI 差距 + ADX 強度 + ADX 變化

數值大小不是手寫「多少算強」。每個 S-state 都從自己的歷史分布學習 tercile（LOW / MID / HIGH）。最後 DMI Expert 以 state baseline 為基準，對既有 Level 1～5 的四分類機率做保守修正。

訓練後 `reports/training_report.json` 會保留 `dmi_expert_72h`，並新增 `adx_step_regime_72h`，直接列出每個 S-state 各 facet 歷史上最有利與最不利的 DMI / ADX 階梯組合、樣本數、成功率、存活率與真失敗率。

## v2：不再把「沒在期限內達標」全部叫 LOSS

每一個 horizon 都拆成四個互斥結果，合計固定 100%：

```text
SUCCESS_WITHIN_HORIZON  期限內成功
ALIVE_SLOW              還活著只是慢
TRUE_FAIL               真失敗
OTHER                    其他／已離開原路徑但尚未觸發硬失效
```

主波段判定仍以 `18 根 4H = 72H = 3天` 為核心。例如最後可以得到：

```text
S3 相似樣本 1,171
3日內成功       48%
還活著只是慢    30%
真失敗          12%
其他            10%
-------------------
合計           100%

結構存活率 = 成功 + 還活著 = 78%
```

### TRUE_FAIL 不使用新發明的跌幅門檻

直接沿用正式引擎已有的硬失效線：

- S2 / S3：`S2_BREAKDOWN_FLOOR_BANDPOS`
- S0.5 / S1：`BREAKOUT_INVALIDATE_BANDPOS`

因此 v2 只改 **Settlement / 統計方式**，不改 S-state。

### ALIVE_SLOW 的意思

期限內沒有達成目標，但：

1. 沒有觸發引擎硬失效線；
2. 72H 結束時仍處於可恢復的同一波段幾何。

S3 回到 S2 不是自動判失敗；正常回踩仍可屬於 `ALIVE_SLOW`。

### OTHER 的意思

沒有成功、也沒有碰到硬失效，但已離開原本可明確追蹤的路徑。保留 `OTHER` 是為了避免把所有「沒死」都硬算成「還活著」。

## 四個 S-state 預測目標

| 現在狀態 | 目標 |
|---|---|
| S0.5 | 進入 S1 或更高上攻階段 |
| S1 | HA Band Position > 0.75 |
| S2 | 進入 S3 |
| S3 | HA Band Position > 0.75 |

同時計算 3 / 6 / 12 / 18 根 4H，也就是 12 / 24 / 48 / 72 小時。UI 主判斷建議用 72H，24H / 48H 當速度參考。

另外 v2 會額外記錄 `late_success_4_7d`：三天內沒成功的案例，如果資料完整，再觀察第 4～7 天是否最後才成功。這個欄位只作解釋，不會改掉 72H 四分類結果。

## 防止偷看未來

Replay 在歷史第 `i` 根 4H 時，只能用 `<= i` 的 K 線建立當時 S-state 與特徵；未來 K 只允許 Settlement 階段讀取。

歷史 4H 也會聚合成當時「尚未走完的日 K」，避免拿完整收盤日 K 回頭判斷盤中狀態。

## 主要檔案

```text
engine/
  scoring_rules.py          正式 S-state 引擎（固定）
  runtime_core.py           無 Streamlit 計算層

training/
  pionex_history.py         Pionex 4H cache
  replay.py                 逐根 Replay + Settlement
  outcomes.py               v2 四分類結果判定
  features.py               模型特徵
  model_builder.py          四分類統計、平滑、Fallback

models/
  probability_model.json    JSON 模型參數

reports/
  training_report.json      訓練摘要，含 72H 四分類 baseline
```

## probability_model.json v3

為了不讓目前 Streamlit 立刻壞掉，舊欄位仍保留：

```json
"probability": 0.48,
"samples": 1171,
"wins": 562
```

其中 `probability` 仍表示「期限內成功率」。

v2 起同時保留：

```json
"outcomes": {
  "SUCCESS_WITHIN_HORIZON": {"probability": 0.48},
  "ALIVE_SLOW": {"probability": 0.30},
  "TRUE_FAIL": {"probability": 0.12},
  "OTHER": {"probability": 0.10}
},
"structural_survival_probability": 0.78,
"true_fail_probability": 0.12
```

原本條件規則仍使用 Level 1～5 + Fallback；樣本不足 50 就退回較粗層級。v3 另外加入獨立 DMI Expert facets，不改 Level 1～5。四分類使用同一個 empirical-Bayes prior 做多分類平滑，避免小樣本出現假 90%。

## 你現在這個 Repository 已經有 10,000 根歷史 cache 時怎麼操作

**如果你的 90 隻幣 `data/cache/4h/*.csv` 已經完整，就不要重新下載完整 Pionex 歷史。**

上傳 v2 後：

1. Actions → **Historical S-state Training v2** → Run workflow
2. `symbols = ALL`
3. `max_records = 10000`
4. `step_bars = 1`
5. **`full_refresh = false`，不要勾**

程式會使用既有 `data/cache/4h/*.csv`，抓最新一頁合併後，重新 Replay / Settlement，然後把舊的二元模型重建成 v2 四分類模型。

第一次 v3 重跑成功後，檢查：

- `models/probability_model.json` → `schema_version` 應為 `3`
- `models/probability_model.json` → 應有 `dmi_expert_contract`
- `models/probability_model.json` → `dmi_expert_contract.version` 應為 `DMI-EXPERT-v3-ADX-1DP-STICKY`
- `reports/training_report.json` → 應有 `primary_72h_outcomes`、`dmi_expert_72h` 與 `adx_step_regime_72h`

## Daily Champion Settlement & Evolution

日常流程不再每天無條件重建一個 Challenger。每天 08:25 的工作只有兩件主事：

1. **考試**：凍結當日 Champion 的正式預測，回頭結算先前的真實路徑。
2. **進化**：只有本代累積到指定 72H 正式結算門檻時，才重訓並直接發布下一代 Champion。

因此「每天新增 6 根 4H 就建立一個幾乎一樣的 Challenger」的流程已取消。


## v3.3.0｜120 筆世代循環 + 美股 Live Learning

- 每一代 Champion 只使用「本代新產生」的 Frozen Snapshot 計數；滿 **120 筆正式 72H 結算**才觸發一次 Evolution。新 Champion 上線後，下一代從 0/120 重新累積，不會每天少量重訓。
- 每日 08:25 Cloudflare 觸發不變。`champion_daily.py --symbols ALL` 現在同時追蹤 Crypto 與已解鎖的 Pionex 美股/RWA 標的。
- 美股不做深度歷史 backfill；只維護足以計算當下 S-state/ADX/DI 與後續 72H 結算的近期 4H cache。
- Frozen Snapshot 永久保存 `market_type=CRYPTO/US_STOCK`，戰績 JSON 同時提供整體與分市場成績。
- 進化時，本代已結算 Frozen cases 會以預設 **10x live reinforcement** 加入下一代訓練，使 120 筆真實考卷不會被約 20 萬筆歷史樣本完全稀釋。美股 Frozen cases 因此也會正式參與下一代模型學習。
