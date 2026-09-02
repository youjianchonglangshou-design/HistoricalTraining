HistoricalTraining v3.6.0｜08:25 DAILY-CONFIRMED SETTLEMENT

覆蓋以下 12 個檔案：
.github/workflows/daily-learning.yml
README.md
VERSION.json
champion_daily.py
data/champion/generation.json
run_training.py
tests/test_champion_learning.py
tests/test_core.py
training/champion_learning.py
training/model_builder.py
training/outcomes.py
training/replay.py

核心語意：
- 08:25 為正式 Champion 出題 / 批改流程。
- 資料截止固定使用剛完成的 08:00 Daily。
- 12H 僅為 observation-only，不列入正式命中率。
- 24H / 48H / 72H 只認每日完整收線後的正式狀態。
- 盤中任一 4H 暫時閃成 S3 不得建立 SUCCESS。
- 舊 04:01 / intraday settlement 標為 legacy，不進 120 筆進化門檻。
