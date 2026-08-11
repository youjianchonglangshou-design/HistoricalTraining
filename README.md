# Crypto S-state Learning Engine

這個儲存庫只做一件事：**用 Pionex 歷史 4H K 線逐根重播目前正式的 S-state 引擎，結算未來結果，產生可被即時 Crypto Monitor 讀取的 `probability_model.json`。**

## 核心契約

- `engine/scoring_rules.py`：由原系統直接複製，**S0 / S0.5 / S1 / S2 / S3 規則不由訓練程式改寫**。
- `models/probability_model.json`：會隨歷史與新行情持續重新統計、進化。
- 歷史 Replay 與未來即時系統必須使用同一份 `scoring_rules.py`。
- AI/LLM 不負責發明機率。機率由已結算歷史樣本計算。

## 第一版四個問題

| 現在狀態 | 統計目標 |
|---|---|
| S0.5 | 未來是否進入 S1 或更高的上攻階段 |
| S1 | HA Band Position 是否突破 0.75 |
| S2 | 未來是否進入 S3 |
| S3 | HA Band Position 是否突破 0.75 |

一次同時計算 4 個 horizon：3 / 6 / 12 / 18 根 4H，也就是 12 / 24 / 48 / 72 小時。

## 防止偷看未來

Replay 在歷史第 `i` 根 4H 時，只能用 `<= i` 的 K 線建立當時的 S-state 與特徵。`i+1...` 只允許 Settlement 階段用來判定 WIN/LOSS，因此避免 look-ahead bias。

另外，歷史 4H 會被依 UTC 00:00 聚合成當時「尚未走完的日 K」，用來模擬目前 `main.py` 在盤中看到的 1D 結構，而不是直接拿完整收盤日 K 偷看。

## Pionex 歷史抓取

使用 public endpoint：

`GET https://api.pionex.com/api/v1/market/klines`

參數：`symbol`、`interval=4H`、`endTime`、`limit<=500`。程式利用 `endTime` 向前分頁；第一次從 Pionex 可回填最多 10,000 根。之後每日把最新 4H 追加到本地 CSV，所以本地學習資料可以繼續往未來累積，不被第一次回填上限卡住。

## 主要檔案

```text
engine/
  scoring_rules.py          正式 S-state 引擎（原檔）
  runtime_core.py           從 main.py 抽出的無 Streamlit 計算層
  ha_threshold.py
  symbols_config.py

training/
  pionex_history.py         歷史 4H 下載 / endTime 分頁 / CSV 合併
  replay.py                 逐根歷史重播 + Settlement
  features.py               轉成機率模型特徵
  model_builder.py          統計、平滑、Fallback 規則

models/
  probability_model.json    最後要導入 Crypto Monitor 的 JSON 參數

reports/
  training_report.json      每次訓練摘要

data/cache/4h/
  BTC.csv ...               GitHub 持續累積的歷史 4H
```

## 第一次在 GitHub 操作

1. 把整包內容上傳到新的 GitHub Repository 根目錄。
2. 到 **Actions → Historical S-state Training → Run workflow**。
3. 第一次建議：
   - `symbols = ALL`
   - `max_records = 5000`
   - `step_bars = 1`
   - `full_refresh = true`
4. 執行完成後查看：
   - `models/probability_model.json`
   - `reports/training_report.json`
   - `data/cache/4h/*.csv`

## 每天如何繼續學

`Daily S-state Learning` 已設定每天台灣時間約 08:25 自動執行，也可以手動 Run workflow。

每日流程：

```text
抓各幣最新 500 根 4H
→ 與 data/cache/4h 舊資料依 timestamp 合併去重（每日流程的本地容量預設 20,000 根/幣）
→ 用完整歷史重新 Replay 同一顆 S-state 引擎
→ 新行情自然成為新的已結算案例
→ 重建 probability_model.json
→ GitHub Actions 自動 commit / push
```

因此不是 Python 去修改 `scoring_rules.py`，而是固定引擎、持續進化 JSON 參數。

## probability_model.json 的 Fallback

同一個 S3 不會全部只套一個勝率。模型會依序嘗試更精細的歷史條件，例如：

```text
S3 + 中軌狀態 + BandPos 區間 + T-stage + 布林寬度趨勢 + 狀態年齡
↓ 如果樣本 >= 50，使用該組機率
↓ 不足則退回較粗條件
↓ 最後退回所有 S3 的 baseline
```

條件小樣本的機率還會向該 S-state baseline 做 empirical-Bayes 收縮，避免 7 勝 1 負就顯示誇張的 87.5%。

## 接回目前 Crypto Monitor 時

目前 Repo 不需要先改。等這個學習 Repo 真的產生模型後，再把：

- `models/probability_model.json`
- `predict_from_model.py` 的 lookup 邏輯
- `training/features.py` 的同版 feature extraction

導入 Crypto Monitor。正式畫面就能顯示例如：

```text
PEPE  S3
強勢延續機率 78.4%
樣本 263｜24H
```

而是否進場仍由人決定。

## 歷史 vs Live 驗證

第一次 `full_refresh=true` 成功後，`data/learning_meta.json` 會鎖住當下最後一根已結算 4H 的時間。之後每天新增的案例會被報告標成 Live/out-of-sample。這個切割點不會因為每天 retrain 被重設，因此之後可以直接比較「歷史回測機率」與「真正上線後命中率」。
