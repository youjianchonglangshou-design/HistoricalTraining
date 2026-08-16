# S-State 歷史行情考題

`quiz/index.html` 直接從本 repository 的 `data/cache/4h/*.csv` 讀取真實歷史資料，因此 Daily S-state Learning 每天更新 cache 後，考題自動使用最新歷史，不需要另外重建題庫 JSON。

## 使用

部署 GitHub Pages 後開啟：

```text
/quiz/
```

不要直接用 `file://.../quiz/index.html` 雙擊開啟，瀏覽器會阻擋相對路徑 `fetch()` CSV。若本機測試，可在 repository 根目錄執行：

```bash
python -m http.server 8000
```

再開啟：

```text
http://localhost:8000/quiz/
```

## 圖表契約

- 普通日 K：4H cache 依 UTC 日聚合，與 `engine/runtime_core.py::aggregate_4h_to_daily()` 相同。
- BB20：普通日 K close、20 日、母體標準差、±2σ。
- 平均 K：與 `engine/runtime_core.py::calculate_heikin_ashi()` 相同。
- 黃階梯：HA close > HA open。
- 紫階梯：HA close < HA open。
- 題目：30 日已知結構，未來 3/7/12 天隱藏。
- 使用者先選做多 / 觀望 / 做空，再逐日播放未來。
- 方向命中率：只統計做多/做空，固定以第 3 天收盤相對判斷點收盤的方向判定；觀望不計分。

這個頁面不修改 `engine/scoring_rules.py`、不改 S-state 公式，也不把考題結果寫回模型。
