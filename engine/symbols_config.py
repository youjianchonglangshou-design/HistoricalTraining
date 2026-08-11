"""市場清單設定：考試幣 + Pionex 美股/RWA 永續合約。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

TW_TZ = timezone(timedelta(hours=8))
STRUCTURE_WINDOW_DAYS = 30
BB_PERIOD = 20
# 要讓最早那個顯示點也有完整 BB20，需要 30 + 20 - 1 = 49 根日K。
RWA_MIN_DAILY_BARS = STRUCTURE_WINDOW_DAYS + BB_PERIOD - 1

EXAM_SYMBOLS = [
    "BTC", "1INCH", "RAY", "RSR", "SUI", "KAVA", "INJ", "LTC", "SNX", "SUSHI",
    "TRX", "ASTER", "BOME", "JTO", "KAS", "NEAR", "PENGU", "SHIB", "SOL", "XLM",
    "XRP", "GMX", "RPL", "RUNE", "LINK", "ETH", "PEPE", "JUP", "PENDLE", "TAO",
    "KAITO", "BNB", "CAKE", "COMP", "ORDI", "ADA", "ALGO", "ARB", "UNI", "CRV",
    "ENA", "MANA", "OKB", "APT", "DOT", "FLOKI", "HBAR", "SEI", "STRK", "TRUMP",
    "BCH", "FIL", "LPT", "AAVE", "AVAX", "DOGE", "ENJ", "ICP", "LRC", "SAND",
    "STX", "VET", "ONDO", "YFI", "ATOM", "DYDX", "IMX", "ROSE", "CHZ", "GALA",
    "GRT", "HYPE", "MEME", "TIA", "W", "WLD", "ETC", "FLR", "GLM", "POL",
    "PYTH", "WIF", "BONK", "OP", "S", "PAXG", "AXS", "EGLD", "LDO", "ZEC",
]

# 2026-08-09 實際用 Pionex /api/v1/market/klines 驗證：
# 30 日結構視窗 + BB20 需要至少 49 根日K；以下為 2026-08-09 實測已達 49 根的標的。
# key = 畫面顯示名稱；value = Pionex 真實 API symbol。
RWA_ACTIVE_SYMBOL_MAP = {
    'AAOIX': 'AAOIX_USDT_PERP',
    'AAPLX': 'AAPLX_USDT_PERP',
    'AAX': 'AAX_USDT_PERP',
    'AMATX': 'AMATX_USDT_PERP',
    'AMDX': 'AMDX_USDT_PERP',
    'AMZNX': 'AMZNX_USDT_PERP',
    'ANTHROPIC': 'ANTHROPIC_USDT_PERP',
    'APPX': 'APPX_USDT_PERP',
    'ARMX': 'ARMX_USDT_PERP',
    'ASMLX': 'ASMLX_USDT_PERP',
    'ASTSX': 'ASTSX_USDT_PERP',
    'AVGOX': 'AVGOX_USDT_PERP',
    'AXTIX': 'AXTIX_USDT_PERP',
    'BEX': 'BEX_USDT_PERP',
    'BMNRX': 'BMNRX_USDT_PERP',
    'BNOX': 'BNOX_USDT_PERP',
    'BRENTOIL': 'BRENTOIL_USDT_PERP',
    'CBRS': 'CBRS_USDT_PERP',
    'CEGX': 'CEGX_USDT_PERP',
    'CF': 'CF_USDT_PERP',
    'CIFRX': 'CIFRX_USDT_PERP',
    'WTI': 'WTI_USDT_PERP',
    'COHRX': 'COHRX_USDT_PERP',
    'COINX': 'COINX_USDT_PERP',
    'COPPER': 'COPPER_USDT_PERP',
    'CPERX': 'CPERX_USDT_PERP',
    'CRCLX': 'CRCLX_USDT_PERP',
    'CRDOX': 'CRDOX_USDT_PERP',
    'CRWVX': 'CRWVX_USDT_PERP',
    'CSCOX': 'CSCOX_USDT_PERP',
    'CVXX': 'CVXX_USDT_PERP',
    'DELLX': 'DELLX_USDT_PERP',
    'DRAMX': 'DRAMX_USDT_PERP',
    'EWJX': 'EWJX_USDT_PERP',
    'EWYX': 'EWYX_USDT_PERP',
    'FLNCX': 'FLNCX_USDT_PERP',
    'GEVX': 'GEVX_USDT_PERP',
    'GLWX': 'GLWX_USDT_PERP',
    'GMEX': 'GMEX_USDT_PERP',
    'GOOGLX': 'GOOGLX_USDT_PERP',
    'GSGX': 'GSGX_USDT_PERP',
    'HIMSX': 'HIMSX_USDT_PERP',
    'HOODX': 'HOODX_USDT_PERP',
    'HPEX': 'HPEX_USDT_PERP',
    'HYUNDAI': 'HYUNDAI_USDT_PERP',
    'IBMX': 'IBMX_USDT_PERP',
    'INTCX': 'INTCX_USDT_PERP',
    'IRENX': 'IRENX_USDT_PERP',
    'LITEX': 'LITEX_USDT_PERP',
    'LLYX': 'LLYX_USDT_PERP',
    'LMTX': 'LMTX_USDT_PERP',
    'LNGX': 'LNGX_USDT_PERP',
    'LRCXX': 'LRCXX_USDT_PERP',
    'METAX': 'METAX_USDT_PERP',
    'MOSX': 'MOSX_USDT_PERP',
    'MPX': 'MPX_USDT_PERP',
    'MRVLX': 'MRVLX_USDT_PERP',
    'MSFTX': 'MSFTX_USDT_PERP',
    'MSTRX': 'MSTRX_USDT_PERP',
    'MUX': 'MUX_USDT_PERP',
    'NATGAS': 'NATGAS_USDT_PERP',
    'NBISX': 'NBISX_USDT_PERP',
    'NFLXX': 'NFLXX_USDT_PERP',
    'NKEX': 'NKEX_USDT_PERP',
    'NOKX': 'NOKX_USDT_PERP',
    'NOWX': 'NOWX_USDT_PERP',
    'NTRX': 'NTRX_USDT_PERP',
    'NVDAX': 'NVDAX_USDT_PERP',
    'OKLOX': 'OKLOX_USDT_PERP',
    'ONDSX': 'ONDSX_USDT_PERP',
    'OPENAI': 'OPENAI_USDT_PERP',
    'ORCLX': 'ORCLX_USDT_PERP',
    'PAYPX': 'PAYPX_USDT_PERP',
    'PLTRX': 'PLTRX_USDT_PERP',
    'QCOMX': 'QCOMX_USDT_PERP',
    'QNTX': 'QNTX_USDT_PERP',
    'QQQX': 'QQQX_USDT_PERP',
    'RGTIX': 'RGTIX_USDT_PERP',
    'RKLBX': 'RKLBX_USDT_PERP',
    'RTXX': 'RTXX_USDT_PERP',
    'SITMX': 'SITMX_USDT_PERP',
    'SKHX': 'SKHX_USDT_PERP',
    'SLVX': 'SLVX_USDT_PERP',
    'SMHX': 'SMHX_USDT_PERP',
    'SMSN': 'SMSN_USDT_PERP',
    'SNDKX': 'SNDKX_USDT_PERP',
    'SOXLX': 'SOXLX_USDT_PERP',
    'SOXXX': 'SOXXX_USDT_PERP',
    'SPCX': 'SPCX_USDT_PERP',
    'SPYX': 'SPYX_USDT_PERP',
    'STXX': 'STXX_USDT_PERP',
    'TQQQX': 'TQQQX_USDT_PERP',
    'TSLAX': 'TSLAX_USDT_PERP',
    'TSMX': 'TSMX_USDT_PERP',
    'TTEX': 'TTEX_USDT_PERP',
    'TXNX': 'TXNX_USDT_PERP',
    'UNGX': 'UNGX_USDT_PERP',
    'UNHX': 'UNHX_USDT_PERP',
    'URAX': 'URAX_USDT_PERP',
    'URNMX': 'URNMX_USDT_PERP',
    'USARX': 'USARX_USDT_PERP',
    'USOX': 'USOX_USDT_PERP',
    'VGKX': 'VGKX_USDT_PERP',
    'WDCX': 'WDCX_USDT_PERP',
    'XAG': 'XAG_USDT_PERP',
    'XAU': 'XAU_USDT_PERP',
    'XPD': 'XPD_USDT_PERP',
    'XPT': 'XPT_USDT_PERP',
    'XYZX': 'XYZX_USDT_PERP',
}

# 這些合約 API 已可抓到，但截至 2026-08-09 尚不足「30 個完整 BB20 顯示點」所需的 49 根日K。
# 程式會依台灣日期估算累積日線根數，到期後自動加入「美股代幣」群組；
# 真正分析時 main.py 仍會再次檢查日K根數，避免估算提前解鎖。
RWA_PENDING_SYMBOL_MAP = {
    'ALABX': {"api_symbol": 'ALABX_USDT_PERP', "daily_bars_as_of": 48, "four_h_bars_as_of": 150, "as_of": '2026-08-09'},
    'KLACX': {"api_symbol": 'KLACX_USDT_PERP', "daily_bars_as_of": 48, "four_h_bars_as_of": 150, "as_of": '2026-08-09'},
    'ONX': {"api_symbol": 'ONX_USDT_PERP', "daily_bars_as_of": 45, "four_h_bars_as_of": 150, "as_of": '2026-08-09'},
    'SKHY': {"api_symbol": 'SKHY_USDT_PERP', "daily_bars_as_of": 30, "four_h_bars_as_of": 150, "as_of": '2026-08-09'},
    'SMCIX': {"api_symbol": 'SMCIX_USDT_PERP', "daily_bars_as_of": 48, "four_h_bars_as_of": 150, "as_of": '2026-08-09'},
    'SNXXX': {"api_symbol": 'SNXXX_USDT_PERP', "daily_bars_as_of": 28, "four_h_bars_as_of": 150, "as_of": '2026-08-09'},
    'VSHX': {"api_symbol": 'VSHX_USDT_PERP', "daily_bars_as_of": 45, "four_h_bars_as_of": 150, "as_of": '2026-08-09'},
    'KIOXIA': {"api_symbol": 'KIOXIA_USDT_PERP', "daily_bars_as_of": 4, "four_h_bars_as_of": 20, "as_of": '2026-08-09'},
    'PANWX': {"api_symbol": 'PANWX_USDT_PERP', "daily_bars_as_of": 18, "four_h_bars_as_of": 103, "as_of": '2026-08-09'},
    'SHAZX': {"api_symbol": 'SHAZX_USDT_PERP', "daily_bars_as_of": 7, "four_h_bars_as_of": 39, "as_of": '2026-08-09'},
    'SOXSX': {"api_symbol": 'SOXSX_USDT_PERP', "daily_bars_as_of": 7, "four_h_bars_as_of": 39, "as_of": '2026-08-09'},
    'XLPX': {"api_symbol": 'XLPX_USDT_PERP', "daily_bars_as_of": 4, "four_h_bars_as_of": 20, "as_of": '2026-08-09'},
    'XLVX': {"api_symbol": 'XLVX_USDT_PERP', "daily_bars_as_of": 4, "four_h_bars_as_of": 20, "as_of": '2026-08-09'},
}


def _taiwan_today() -> date:
    return datetime.now(TW_TZ).date()


def _pending_estimated_daily_bars(info: dict, today: date | None = None) -> int:
    current_day = today or _taiwan_today()
    observed_day = date.fromisoformat(str(info["as_of"]))
    elapsed_days = max(0, (current_day - observed_day).days)
    return int(info.get("daily_bars_as_of", 0)) + elapsed_days


def pending_unlock_date(symbol: str) -> date | None:
    info = RWA_PENDING_SYMBOL_MAP.get(str(symbol).upper())
    if not info:
        return None
    observed_day = date.fromisoformat(str(info["as_of"]))
    missing = max(0, RWA_MIN_DAILY_BARS - int(info.get("daily_bars_as_of", 0)))
    return observed_day + timedelta(days=missing)


def get_unlocked_rwa_symbols(today: date | None = None) -> list[str]:
    current_day = today or _taiwan_today()
    symbols = list(RWA_ACTIVE_SYMBOL_MAP)
    for symbol, info in RWA_PENDING_SYMBOL_MAP.items():
        if _pending_estimated_daily_bars(info, current_day) >= RWA_MIN_DAILY_BARS:
            symbols.append(symbol)
    return symbols


def get_locked_rwa_symbols(today: date | None = None) -> list[dict]:
    current_day = today or _taiwan_today()
    locked = []
    for symbol, info in RWA_PENDING_SYMBOL_MAP.items():
        estimated = _pending_estimated_daily_bars(info, current_day)
        if estimated < RWA_MIN_DAILY_BARS:
            locked.append({
                "symbol": symbol,
                "api_symbol": info["api_symbol"],
                "estimated_daily_bars": estimated,
                "unlock_date": pending_unlock_date(symbol),
            })
    return locked


def resolve_api_symbol(symbol: str) -> str:
    """把畫面代碼轉成 Pionex API 真實 symbol。"""
    key = str(symbol).upper()
    if key in RWA_ACTIVE_SYMBOL_MAP:
        return RWA_ACTIVE_SYMBOL_MAP[key]
    if key in RWA_PENDING_SYMBOL_MAP:
        return str(RWA_PENDING_SYMBOL_MAP[key]["api_symbol"])
    return f"{key}_USDT"


def is_rwa_symbol(symbol: str) -> bool:
    key = str(symbol).upper()
    return key in RWA_ACTIVE_SYMBOL_MAP or key in RWA_PENDING_SYMBOL_MAP


def get_symbols_config(today: date | None = None) -> dict[str, list[str]]:
    """主選單固定只提供兩個市場群組。"""
    return {
        "考試幣": list(EXAM_SYMBOLS),
        "美股代幣": get_unlocked_rwa_symbols(today),
    }


# 相容舊 main.py 的變數名稱；重新載入頁面時會按當天日期自動解鎖 pending RWA。
SYMBOLS_CONFIG = get_symbols_config()
