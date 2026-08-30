# S-State 歷史行情考題｜Trading Replay + R2 Active

> QUIZ v2.9｜DMI-V2-COMBINER

`quiz/index.html` 直接讀取本 repository 的 `data/cache/4h/*.csv` 真實歷史資料，並使用 `quiz/model_timeline/*.json` 還原每一個歷史日當下的 S-state 特徵。

## 操作方式

部署 GitHub Pages 後開啟：

```text
/quiz/
```

- 隨機抽一段真實歷史行情，畫面固定顯示最近 30 根日 K。
- `▶ 播放下一天` **每按一次只增加 1 天**，不預選 3 / 7 / 12 天。
- 沒有進場條件就繼續播放。
- 看到進場點時才按 `做多` 或 `做空`；沒有「觀望」按鈕。
- 進場後仍可逐日播放，並顯示目前損益、MFE / MAE、持有天數與進場後第 3 天方向結果。

## R2 Active 模型

頁面啟動時直接讀取目前 Cloudflare Worker 的：

```text
/api/model/active
```

也就是 R2：

```text
models/active/probability_model.json
```

每播放到一個新交易日，模型 HUD 都會用「那一天最後一根 4H」的歷史 S-state 特徵重新匹配目前 Active model，顯示：

- 失敗率：72H `TRUE_FAIL`
- 存活率：72H `structural_survival_probability`
- 樣本數：該條件實際匹配樣本
- Level：目前匹配到的模型層級，最高 L5
- DMI Expert：依 Active model 的 facets 對四分類機率做 reliability-weighted geometric mean 修正；HUD 顯示 `DMI×N` 與 Blend 強度

若該日不是 S0.5 / S1 / S2 / S3 的可建模狀態，畫面明確顯示「非模型狀態｜無統計」，不偽造機率。

## 歷史模型時間線

`run_training.py` 已在既有正式 4H replay 的同一輪運算中同步輸出：

```text
quiz/model_timeline/<SYMBOL>.json
```

保留：

- `midline_state`
- `bandpos` / `bandpos_bin`
- `trigger_stage`
- `bandwidth_trend`
- `state_age_bars` / `state_age_bin`

因此模型可以正常匹配到 L5，而不是由 HTML / JS 另外猜 S-state。

Daily Learning / Historical Training workflow 也已把 `quiz/model_timeline` 加入 commit，之後每天更新歷史資料時會同步更新考題時間線。

## 圖表契約

- 普通日 K：4H cache 依 UTC 日聚合。
- BB20：普通日 K close、20 日、母體標準差、±2σ。
- 平均 K：Heikin-Ashi。
- 黃階梯：HA close > HA open。
- 紫階梯：HA close < HA open。
- 圖表採 rolling 30-day 視窗，新的一天從右側進入，最舊一天從左側移出。
- ADX / DMI 直接讀取 `quiz/model_timeline` 的正式 replay 特徵：DI+ 黃、DI− 紫、ADX RISING 綠階梯、FALLING 紅階梯、20 白色虛線。
- ADX 四態膠囊：DI 主導決定黃／紫語意，ADX 階梯增減決定綠／紅點與 `↗↗ / ↘↘ / ←→`。

這個頁面不修改 `engine/scoring_rules.py`，不改既有 S-state 判斷公式，也不把使用者的考題答案寫回模型。


## DMI Expert v2 combiner（v2.9）

Quiz 不再只顯示舊 Level 1～5 機率。若 R2 Active 是 Schema v3 DMI Expert，會先匹配既有 BB/HA Level 規則，再使用 state-specific DMI facets（包含 ADX Step Regime）做與 HistoricalTraining / Terminal 相同的 reliability-weighted geometric-mean likelihood-ratio correction。`quiz/model_timeline` 直接來自同一輪 HistoricalTraining replay，因此 4H DI cross age、ADX step direction / persistence / turn event 均不由前端猜測。
