# HistoricalTraining v3.8.0 — CCI PRIMARY Path Tree

這版把 CCI 從「舊 BB/HA 機率的修正器」改成真正的主模型。

## 核心規則

S-state 只負責定義考題：

- S0.5：72H 內能否到 S1 或更高。
- S1：72H 內能否完成上攻 / BandPos > 0.75。
- S2：72H 內能否到 S3。
- S3：72H 內能否續強 / BandPos > 0.75。

最後的成功 / 還活著 / 真失敗 / 其他機率，直接由 CCI PRIMARY Path Tree 回答；Schema 5 不再先用舊 Level 1-5 BB/HA probability 當 base 再讓 CCI 小幅修正。

模型合約：

`CCI-PRIMARY-v2-PATH-TREE-HLC3-20-SMA14`

Schema：`5`

CCI 公式不變：`hlc3 -> CCI20 -> SMA14 smoothingMA`。

## 模型現在會看「怎麼走到今天」

每個正式日收線 case 都保留 30 日 CCI / SMA / BB / HA 路徑，包括：

- 最近 21 日是第一次或第二次以上金叉 / 死叉。
- 距離最近一次交叉幾天。
- 最近一次交叉發生在哪個 CCI 區域。
- 交叉當時 SMA 是黃 / 紫。
- 交叉當時 BB 中軌是上升加速、上升減速、平緩、下斜改善、下斜惡化。
- CCI 與 SMA gap 是正在接近、拉開、上方回踩或上方擴張。
- 黃 SMA 回踩、短暫跌破後 reclaim；以及紫 SMA 的鏡像狀態。
- CCI / SMA 1日、3日斜率與加速度。
- BB 中軌 1日、3日斜率與斜率變化。
- Price HH + CCI LH / Price LL + CCI HL 背離。
- HA 黃紫與連續長度。
- Crypto / US-stock 市場類型。

這些不是硬寫「哪一種一定漲」。每個 S-state 的樹會依歷史 outcome 自己選出最有辨識力的 split。

## S0.5 / S2 對應使用目的

模型現在有能力把原本會混在一起的案例拆開：

- S0.5：第一次深位金叉 + 中軌仍陡降，與後續第二次金叉 + 中軌下斜改善 / 平緩，不再只是同一個 `CCI_CROSS_UP`。
- S0.5：CCI 把 SMA 帶黃後的回踩 / reclaim 可獨立成路徑特徵。
- S2：高位第一次死叉 + BB 中軌仍強上斜，可與第二次死叉 + 中軌減速 / 平緩 / 下斜 + 頂背離拆開學習。
- 中軌平緩本身不會被硬判失敗；CCI 重新接近 / 金叉與衰竭死叉會由歷史結果決定不同分支。

## ALL 現在真的包含美股/RWA

v3.7 的 `--symbols ALL` 實際只使用 Crypto `EXAM_SYMBOLS`。v3.8.0 修正為：

`ALL = 90 個 Crypto + 目前已解鎖 US-stock/RWA`

目前設定共 206 個標的。每筆 case 保留 `market_type`，樹可以自己學同一個 CCI 路徑在 Crypto / US-stock 是否有不同結果。

若 Pionex 單一 continuation request 暫時失敗，但 repository 已有有效 cache，Full Rebuild 會使用既有 cache 繼續 replay，不會直接丟掉該標的。

## 正式 HistoricalTraining Action

到 GitHub Actions 執行：

`Manual Historical CCI PRIMARY Path Full Rebuild v3.8.0`

預設：

- `symbols = ALL`
- `max_records = 20000`
- `step_bars = 1`
- `full_refresh = false`

Action 會：

1. compile + 21 個 unit tests。
2. replay Crypto + US-stock/RWA 完整歷史 cache。
3. 建立 Schema 5 CCI PRIMARY Path Tree。
4. 產生 70/15/15 chronological walk-forward diagnostic。
5. 驗證 US-stock/RWA 確實產生 supervised cases。
6. 產生新的 model_id。
7. 直接開新的 Champion generation，近期 performance 歸零。
8. commit 新模型 / report / generation / performance。
9. PUT 新模型到 R2 Active。
10. 驗證 Active model_id = 新模型、snapshots=0、recent_records=0。

因此這個 Action 成功後，新模型就是新的 Active Champion，不需要另外跑 Publish Current Model。

## 訓練報告

重點看：

`reports/training_report.json`

- `cci_primary_72h`：每個 S-state 的 root split、最強 / 最弱歷史路徑、樣本與機率。
- `walk_forward.validation`
- `walk_forward.holdout`
- `crypto_case_count`
- `us_stock_case_count`

這次不要只看 in-sample 高機率。`walk_forward.holdout` 才用來檢查新的 CCI path 邏輯在後段沒看過的歷史是否仍有改善。

## Champion 之後仍會自己檢討進化

每 120 筆正式 72H Frozen settlement 後，Evolution Review 除了 state / market / CCI regime，現在也會分析：

- `state_cross_cycle`
- `state_midline_phase`
- `state_retest`
- `state_divergence`

下一代會對這些實際高估 / 低估的路徑提高 live feedback reinforcement，再重新訓練。

## 本次新 Champion 的第一份 9/4 考卷

早上 08:25 已經存在的 checkpoint 是舊 Champion 產生的，不能直接掛到新 model_id；`champion_daily.py` 會拒絕模型 ID 不一致的 Frozen Snapshot。

所以正確順序是：

1. 先部署 HistoricalTraining v3.8.0 與支援 Schema 5 的 Terminal v0.1.81。
2. 跑 `Manual Historical CCI PRIMARY Path Full Rebuild v3.8.0`，確認新 Active Champion、performance=0。
3. 到 SStateMarketTerminal → Actions → `Auto Market Batch` 手動重跑同一個 9/4 完整日收線：
   - `mode = pair`
   - `batch_id = cci_primary_20260904`
   - `checkpoint_date_tw = 2026-09-04`
   - `run_learning_after = true`
4. 這次會用新的 Active Champion 重算 9/4 Crypto + US-stock checkpoint，並自動觸發 HistoricalTraining Daily Champion freeze。
5. 回 performance.html 更新戰績；9/4 應成為新世代第一份 Frozen Snapshot，72H 尚未到期則維持待結算。

不要把舊 Champion 的早上 checkpoint 直接補寫到新世代。
