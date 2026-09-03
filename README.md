# HistoricalTraining v3.7.0 — CCI20 + SMA14 Champion Full Rebuild

這版的目的只有一個：用 CCI 取代原本 ADX/DMI Expert，重新跑完整 HistoricalTraining，Action 完成後直接把新模型發布成新的 Champion。

## CCI 同源公式

- Source：`hlc3`
- CCI：20
- smoothingMA：SMA14
- smoothingMA 上升：YELLOW
- smoothingMA 下降：PURPLE
- 參考位置：-100 / 0 / +100
- CCI 的 -120～-80 區域被保留成明確位置特徵，但模型不會被硬寫成「此區一定上漲」。
- BB 中軌的 `midline_slope_5d` 與 `midline_improvement` 一起交給模型，讓模型自行學「仍下斜但下斜正在減速」是否有意義。
- HA 黃紫、CCI 是否穿越 smoothingMA、smoothingMA 黃紫轉換與持續時間也都進模型。

模型合約：

`CCI-EXPERT-v1-HLC3-20-SMA14`

Schema：

`4`

## 沒有改 S-state

S0.5 / S1 / S2 / S3 的原本定義、BB/HA Level 1～5、24H/48H/72H 結算方式都不改。

CCI 是第二層歷史證據，用來取代原本 ADX/DMI Expert 對機率的修正角色。

## 正式重訓 Action

GitHub Actions：

`Manual Historical S-state CCI Full Rebuild v3.7`

預設直接使用：

- `symbols = ALL`
- `max_records = 20000`
- `step_bars = 1`
- `full_refresh = false`

Action 會依序：

1. 跑 Python compile + unit tests。
2. 用現有 HistoricalTraining cache 做完整歷史 replay。
3. 產生 Schema 4 CCI 模型。
4. 驗證 `CCI-EXPERT-v1-HLC3-20-SMA14`。
5. 新模型 ID 開一個全新的 Champion generation。
6. 把新 generation 的近期戰績重設為 0。
7. Commit 新模型、training report、generation/performance。
8. 直接 PUT 到 R2 Active，Action 完成時新模型就是 Champion。
9. 同步上傳空白的新 generation performance / evolution review / policy。
10. 驗證 R2 Active model_id 等於剛產生的新模型，且 recent records = 0。

因此不需要再額外跑 `Publish Current Model as Champion`；該 workflow 只保留作為手動補發備援。

## 新模型會學哪些 CCI 規律

CCI Expert 使用六組獨立 facets，不改 S-state：

1. `position_cross`
   - CCI 位置區域
   - CCI / smoothingMA 交叉
   - CCI 在 smoothingMA 上方或下方

2. `smoothing_step`
   - smoothingMA 黃 / 紫
   - 階梯持續時間
   - 紫→黃 / 黃→紫

3. `momentum`
   - CCI 位置
   - CCI 斜率
   - CCI 與 smoothingMA 距離

4. `bb_slope_context`
   - CCI 位置 / 交叉
   - BB 中軌斜率
   - BB 中軌斜率改善幅度

5. `right_side_confirm`
   - CCI 是否在黃色 smoothingMA 上形成上穿確認
   - smoothingMA 顏色
   - HA 顏色 / 連續長度

6. `cci_regime`
   - ABOVE/BELOW × YELLOW/PURPLE
   - smoothingMA 斜率
   - BB 中軌斜率

訓練後請看：

`reports/training_report.json -> cci_expert_72h`

裡面會列每個 S-state、每個 facet 的 strongest_positive / strongest_negative、樣本數、成功率、結構存活率與真失敗率。這份報告才用來決定 Terminal 原本判斷膠囊下一版要改寫成什麼。

## 近期戰績重置

Full Rebuild 不會刪除舊世代歷史，而是：

- 舊 Champion generation 關閉並存入 `data/champion/generations.json`
- 新 CCI Champion generation 從 0 開始
- `data/champion/performance.json` 的新世代 snapshots / recent_records = 0
- R2 舊 ledger shards 保留，但不會計入新的 generation

這樣既能「洗掉近期戰績重新考試」，又不破壞舊世代稽核資料。

## 9/3 第一份新考卷

等 CCI Full Rebuild Action 成功、R2 Active 已是新 CCI Champion 後，再到 SStateMarketTerminal 手動跑正式 Champion checkpoint，日期指定 `2026-09-03`。這會讓 9/3 成為新 generation 的第一份正式考卷。

Terminal 必須使用支援 Schema 4 / CCI Expert 的 probability reader，否則只會讀到 base Level 1～5，無法套用 CCI Expert 修正。
