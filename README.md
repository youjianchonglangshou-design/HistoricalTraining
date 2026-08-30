# Crypto S-state Learning Engine v3 — DMI Expert

這個儲存庫用 Pionex 歷史 4H K 線逐根重播正式 S-state 引擎，然後把每個歷史決策點的未來結果結算成 JSON 參數，供 Crypto Monitor / HTML 使用。

## 核心契約

- `engine/scoring_rules.py`：**不由訓練程式改寫**。S0 / S0.5 / S1 / S2 / S3 仍由正式引擎判斷。
- `models/probability_model.json`：訓練結果；會隨歷史與每日新行情持續進化。
- Replay 與即時系統必須使用同版 S-state 引擎。
- LLM 不發明機率；機率來自已結算歷史樣本。


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

為避免把樣本切得過碎，DMI **不硬疊成 Level 6、7、8**。模型使用四個獨立 Expert facets：

1. `lead_axis`：誰領先 + 20 軸結構 + 距離 20 軸
2. `cross_momentum`：誰領先 + 剛交叉/維持多久 + Gap 變化
3. `line_motion`：DI+ 與 DI- 各自正在上升或下降的相對位置
4. `trend_strength`：DI 差距 + ADX 強度 + ADX 變化

數值大小不是手寫「多少算強」。每個 S-state 都從自己的歷史分布學習 tercile（LOW / MID / HIGH）。最後 DMI Expert 以 state baseline 為基準，對既有 Level 1～5 的四分類機率做保守修正。

訓練後 `reports/training_report.json` 會新增 `dmi_expert_72h`，直接列出每個 S-state 各 facet 歷史上最有利與最不利的 DMI 組合、樣本數、成功率、存活率與真失敗率。

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
- `reports/training_report.json` → 應有 `primary_72h_outcomes` 與 `dmi_expert_72h`

## Daily S-state Learning

後續 `Daily S-state Learning` 不需要另外換邏輯，它會直接呼叫同一個 v3：

```text
最新 Pionex 4H
→ 合併既有 cache
→ 同一顆 S-state 引擎 Replay
→ v2 四分類 Settlement
→ 重建 probability_model.json
→ GitHub commit / push
```

所以仍是：**引擎固定，JSON 參數持續進化。**
