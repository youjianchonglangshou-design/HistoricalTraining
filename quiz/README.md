# S-State 歷史行情考題｜Trading Replay + R2 Champion CCI PRIMARY

> QUIZ v4.0｜CCI-PRIMARY-PATH

`quiz/index.html` 讀取本 repository 的 `data/cache/4h/*.csv` 真實歷史資料，並使用 `quiz/model_timeline/*.json` 還原每一個歷史日當下的正式 S-state + CCI PRIMARY replay 特徵。

## 這版改了什麼

- 移除畫面上的 ADX / DMI 副圖，改成與 SStateMarketTerminal 同語意的 **CCI20 / SMA14**。
- 白線：CCI20（`hlc3`）。
- SMA14 smoothingMA：上升＝黃階梯；下降＝紫階梯。
- CCI 膠囊：`CCI > SMA` 綠色；`CCI < SMA` 紅色；相等/無資料維持中性。
- CCI 路徑評語與 Terminal 使用同一套規則，例如 `高檔回踩｜中軌仍上斜`、`右V共振｜二次上穿・中軌改善`、`健康回踩｜CCI守住黃階梯`。
- 模型改為 **Schema 5 CCI PRIMARY path tree**：S-state 只選擇考題；CCI/SMA 路徑 + BB 中軌路徑 + HA context 直接輸出 4-way probability。
- Quiz 每次載入都從 Worker `/api/model/active` 讀取目前 **R2 Active Champion**，不是把 model_id 寫死在前端。

## 模型 HUD

每播放到一個交易日，使用當日 `quiz/model_timeline/<SYMBOL>.json` 的正式 replay features，套目前 Active Champion 72H (`18 x 4H`) path tree，顯示：

- 3日成功率
- 真失敗率
- 結構存活率
- Path 樣本數
- Path Level（S0.5 / S2 最深可 L6；S1 / S3 最深 L5，實際以 Active model 為準）

若該日是 S0 / OTHER，仍顯示 CCI 路徑評語，但不偽造正式機率。

## CCI 路徑評語色系

- SSR 金黃：`strong`
- SR 紫：`positive`
- R 藍：`setup`
- N 灰白：`neutral`
- 警戒橘：`caution`
- 危險紅：`risk`

## 歷史資料契約

`quiz/model_timeline` 是由 `run_training.py` 同一輪 HistoricalTraining replay 產生，已包含：

- `cci`, `cci_smoothing_ma`, `cci_smoothing_direction`, `cci_sma_relation`
- first / second cross cycle、days since cross、cross zone
- approaching / separating gap、retest / reclaim
- CCI / SMA slopes + acceleration
- BB midline path phase / slopes
- divergence
- HA context / market_type

因此 Quiz 不在瀏覽器猜測 CCI path features；前端只負責把正式 replay feature 套進目前 Champion path tree。

## 操作

部署 GitHub Pages 後開啟 `/quiz/`：

1. 隨機抽真實歷史片段。
2. 每按一次「播放下一天」只增加 1 天。
3. 觀察 S-state、BB/HA、CCI path comment、SMA/CCI 膠囊與 Champion 機率。
4. 看到進場點才按做多/做空；之後自行決定平倉。
5. 平倉後才計入本頁 session 勝負與累積損益；重新整理歸零。

這個 Quiz 不修改 Champion、不修改 `engine/scoring_rules.py`，也不把使用者答案寫回模型。
