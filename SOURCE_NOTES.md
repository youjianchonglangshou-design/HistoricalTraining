# Source notes

本 Repo 由使用者提供的 `crypto-monitor-main(10).zip` 拆分而來：

- `engine/scoring_rules.py`：原檔直接複製，不修改 S-state 規則。
- `engine/ha_threshold.py`：原檔直接複製。
- `engine/symbols_config.py`：原檔直接複製，沿用原考試幣清單與 Pionex symbol mapping。
- `engine/runtime_core.py`：將原 `main.py` 中 Kline → HA → BB20 → 30D hidden fields 的必要邏輯抽成 headless Python，移除 Streamlit/UI 依賴。
- `engine/ORIGINAL_ENGINE_SHA256.txt`：記錄來源檔 SHA256，方便之後確認訓練 Repo 與正式 Monitor 引擎是否同步。
