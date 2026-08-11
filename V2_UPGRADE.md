# v2 升級後第一次操作

這個 Repository 已有歷史 `data/cache/4h/*.csv`，所以升級 v2 後：

1. GitHub → Actions → **Historical S-state Training v2**
2. `symbols = ALL`
3. `max_records = 10000`
4. `step_bars = 1`
5. `full_refresh = false`（**不要勾**）
6. Run workflow

完成後確認：

- `models/probability_model.json` 的 `schema_version = 2`
- `reports/training_report.json` 有 `primary_72h_outcomes`

v2 主結果：

- `SUCCESS_WITHIN_HORIZON` = 3日內成功（72H 主 horizon）
- `ALIVE_SLOW` = 還活著只是慢
- `TRUE_FAIL` = 真失敗（沿用 S-state 引擎硬失效線）
- `OTHER` = 其他／路徑模糊

四項合計 100%。

之後 `Daily S-state Learning` 會自動沿用同一套 v2，不需再手動改。
