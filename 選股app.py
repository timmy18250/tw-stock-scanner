from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from typing import Iterable

import pandas as pd
import requests
import streamlit as st
import urllib3
import yfinance as yf


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TWSE_FUNDAMENTALS_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


@dataclass(frozen=True)
class ScanSettings:
    price_min: float
    price_max: float
    min_yield: float
    require_ma20: bool
    max_candidates: int


def normalize_stock_code(value: object) -> str:
    code = str(value).strip().split(".")[0]
    if code.endswith(".0"):
        code = code[:-2]
    return code.zfill(4) if code.isdigit() else code


def first_matching_column(columns: Iterable[str], candidates: tuple[str, ...]) -> str | None:
    normalized = {col: col.lower().replace(" ", "").replace("_", "") for col in columns}
    for col, key in normalized.items():
        if any(candidate in col or candidate in key for candidate in candidates):
            return col
    return None


def normalize_fundamentals(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame()

    code_col = first_matching_column(raw_df.columns, ("code", "stockno", "證券代號", "股票代號"))
    name_col = first_matching_column(raw_df.columns, ("name", "stockname", "證券名稱", "股票名稱"))
    yield_col = first_matching_column(
        raw_df.columns,
        ("dividendyield", "yield", "殖利率", "股利殖利率"),
    )
    pe_col = first_matching_column(raw_df.columns, ("peratio", "pe", "本益比"))
    pb_col = first_matching_column(raw_df.columns, ("pbratio", "pb", "股價淨值比"))

    required = {"股票代號": code_col, "股票名稱": name_col, "殖利率(%)": yield_col}
    missing = [target for target, source in required.items() if source is None]
    if missing:
        raise ValueError(f"缺少必要欄位：{', '.join(missing)}。API 欄位：{list(raw_df.columns)}")

    df = pd.DataFrame(
        {
            "股票代號": raw_df[code_col].map(normalize_stock_code),
            "股票名稱": raw_df[name_col].astype(str).str.strip(),
            "殖利率(%)": pd.to_numeric(raw_df[yield_col], errors="coerce"),
        }
    )

    df["本益比"] = pd.to_numeric(raw_df[pe_col], errors="coerce") if pe_col else pd.NA
    df["股價淨值比"] = pd.to_numeric(raw_df[pb_col], errors="coerce") if pb_col else pd.NA

    df = df.dropna(subset=["股票代號", "股票名稱", "殖利率(%)"])
    df = df[df["股票代號"].str.fullmatch(r"\d{4}")]
    return df.drop_duplicates(subset=["股票代號"]).reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_twse_fundamentals() -> pd.DataFrame:
    response = requests.get(
        TWSE_FUNDAMENTALS_URL,
        headers=REQUEST_HEADERS,
        timeout=20,
        verify=False,
    )
    response.raise_for_status()
    return normalize_fundamentals(pd.DataFrame(response.json()))


@st.cache_data(ttl=900, show_spinner=False)
def fetch_price_history(tickers: tuple[str, ...]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()

    return yf.download(
        list(tickers),
        period="3mo",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        timeout=20,
    )


def close_series(history: pd.DataFrame, ticker: str) -> pd.Series:
    if history.empty:
        return pd.Series(dtype="float64")

    if isinstance(history.columns, pd.MultiIndex):
        if ticker not in history.columns.get_level_values(0):
            return pd.Series(dtype="float64")
        series = history[ticker].get("Close", pd.Series(dtype="float64"))
    else:
        series = history.get("Close", pd.Series(dtype="float64"))

    return pd.to_numeric(series, errors="coerce").dropna()


def scan_stocks(fundamentals: pd.DataFrame, settings: ScanSettings) -> tuple[pd.DataFrame, dict[str, int]]:
    filtered = fundamentals[fundamentals["殖利率(%)"] >= settings.min_yield].copy()
    filtered = filtered.sort_values("殖利率(%)", ascending=False).head(settings.max_candidates)
    tickers = tuple(f"{code}.TW" for code in filtered["股票代號"])
    history = fetch_price_history(tickers)

    rows: list[dict[str, object]] = []
    skipped = {"history_too_short": 0, "price_out_of_range": 0, "below_ma20": 0, "no_price": 0}

    for _, stock in filtered.iterrows():
        ticker = f"{stock['股票代號']}.TW"
        close = close_series(history, ticker)

        if close.empty:
            skipped["no_price"] += 1
            continue
        if len(close) < 20:
            skipped["history_too_short"] += 1
            continue

        current_price = round(float(close.iloc[-1]), 2)
        ma20 = round(float(close.tail(20).mean()), 2)

        if not settings.price_min <= current_price <= settings.price_max:
            skipped["price_out_of_range"] += 1
            continue

        is_above_ma20 = current_price >= ma20
        if settings.require_ma20 and not is_above_ma20:
            skipped["below_ma20"] += 1
            continue

        rows.append(
            {
                "股票代號": stock["股票代號"],
                "股票名稱": stock["股票名稱"],
                "目前股價": current_price,
                "月線(20MA)": ma20,
                "殖利率(%)": round(float(stock["殖利率(%)"]), 2),
                "本益比": stock["本益比"],
                "股價淨值比": stock["股價淨值比"],
                "技術面狀態": "站上月線" if is_above_ma20 else "跌破月線",
            }
        )

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(["殖利率(%)", "股票代號"], ascending=[False, True]).reset_index(drop=True)
    return result, skipped


def dataframe_to_csv(df: pd.DataFrame) -> bytes:
    buffer = StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8-sig")


st.set_page_config(page_title="台股全市場量化掃描器", page_icon="📈", layout="wide")

st.title("📈 台股全市場量化掃描器")
st.caption("基本面殖利率篩選 + 技術面 20MA 防禦。資料來源：證交所 OpenAPI 與 Yahoo Finance。")

with st.sidebar:
    st.header("篩選參數")
    price_min = st.number_input("最低股價 (元)", min_value=0.0, value=10.0, step=1.0)
    price_max = st.number_input("最高股價 (元)", min_value=0.0, value=30.0, step=1.0)
    min_yield = st.slider("最低殖利率 (%)", min_value=0.0, max_value=15.0, value=5.0, step=0.5)
    require_ma20 = st.checkbox("必須站上月線 (20MA)", value=True)
    max_candidates = st.slider("最多分析幾檔高殖利率股票", min_value=20, max_value=400, value=160, step=20)

    start_scan = st.button("開始掃描", type="primary", use_container_width=True)
    clear_cache = st.button("清除快取", use_container_width=True)

if clear_cache:
    st.cache_data.clear()
    st.success("快取已清除，下一次掃描會重新下載資料。")

if price_min > price_max:
    st.error("最低股價不能高於最高股價，請先調整左側參數。")
    st.stop()

try:
    with st.spinner("正在讀取證交所基本面資料..."):
        fundamentals_df = fetch_twse_fundamentals()
except Exception as exc:
    st.error(f"證交所資料讀取失敗：{exc}")
    st.stop()

if fundamentals_df.empty:
    st.warning("目前沒有取得可用的證交所基本面資料。")
    st.stop()

metric_cols = st.columns(4)
metric_cols[0].metric("上市股票資料", f"{len(fundamentals_df):,} 檔")
metric_cols[1].metric("殖利率中位數", f"{fundamentals_df['殖利率(%)'].median():.2f}%")
metric_cols[2].metric("最高殖利率", f"{fundamentals_df['殖利率(%)'].max():.2f}%")
metric_cols[3].metric("資料快取", "1 小時")

with st.expander("查看目前基本面資料", expanded=False):
    st.dataframe(
        fundamentals_df.sort_values("殖利率(%)", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

if not start_scan:
    st.info("請在左側設定條件後按下「開始掃描」。")
    st.stop()

settings = ScanSettings(
    price_min=price_min,
    price_max=price_max,
    min_yield=min_yield,
    require_ma20=require_ma20,
    max_candidates=max_candidates,
)

with st.spinner("正在批次下載股價並計算 20MA..."):
    result_df, skipped_counts = scan_stocks(fundamentals_df, settings)

candidate_count = min(
    len(fundamentals_df[fundamentals_df["殖利率(%)"] >= min_yield]),
    max_candidates,
)
st.subheader("掃描結果")
st.caption(f"本次分析 {candidate_count:,} 檔高殖利率候選股。")

skip_cols = st.columns(4)
skip_cols[0].metric("無價格資料", skipped_counts["no_price"])
skip_cols[1].metric("歷史資料不足", skipped_counts["history_too_short"])
skip_cols[2].metric("股價區間外", skipped_counts["price_out_of_range"])
skip_cols[3].metric("未站上月線", skipped_counts["below_ma20"])

if result_df.empty:
    st.warning("目前沒有符合全部條件的標的。可以放寬股價區間、降低殖利率門檻，或取消 20MA 條件。")
    st.stop()

st.success(f"找到 {len(result_df):,} 檔符合條件的股票。")
st.dataframe(result_df, use_container_width=True, hide_index=True)

chart_df = result_df.set_index("股票代號")[["殖利率(%)", "目前股價"]].head(30)
st.bar_chart(chart_df["殖利率(%)"])

st.download_button(
    label="下載 CSV",
    data=dataframe_to_csv(result_df),
    file_name="stock_scan_result.csv",
    mime="text/csv",
)
