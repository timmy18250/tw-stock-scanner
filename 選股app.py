import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime
import urllib3

# 停用取消 SSL 驗證時會產生的煩人警告訊息
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. 頁面與基本設定
# ==========================================
st.set_page_config(page_title="台股全市場量化掃描器", page_icon="📈", layout="wide")

st.title("📈 台股全市場量化掃描器 (Daily Update)")
st.markdown("### 策略核心：基本面大數據篩選 × 技術面均線防禦")
st.markdown("---")

# ==========================================
# 2. 抓取證交所大數據 (基本面第一層過濾)
# ==========================================
@st.cache_data(ttl=3600)
def fetch_twse_fundamentals():
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    
    # 替程式碼穿上「瀏覽器偽裝」
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }
    
    try:
        # 強制略過 SSL 憑證檢查 (verify=False)
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        response.raise_for_status() 
        
        data = response.json()
        df = pd.DataFrame(data)
        
        if df.empty:
            st.error("⚠️ 證交所 API 回傳了空資料，可能是週末或伺服器維護中。")
            return pd.DataFrame()

        # 動態捕捉欄位名稱，避免 API 欄位改名導致報錯
        rename_mapping = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'code' in col_lower:
                rename_mapping[col] = '股票代號'
            elif 'name' in col_lower:
                rename_mapping[col] = '股票名稱'
            elif 'pe' in col_lower: 
                rename_mapping[col] = '本益比'
            elif 'pb' in col_lower: 
                rename_mapping[col] = '股價淨值比'
            elif 'yield' in col_lower: 
                rename_mapping[col] = '殖利率(%)'

        df = df.rename(columns=rename_mapping)
        
        # 確保「殖利率(%)」欄位真的存在，否則報錯提示
        if '殖利率(%)' not in df.columns:
            st.error(f"找不到殖利率相關欄位！目前 API 提供的欄位有：{list(df.columns)}")
            return pd.DataFrame()

        # 型態轉換
        df['殖利率(%)'] = pd.to_numeric(df['殖利率(%)'], errors='coerce')
        if '本益比' in df.columns:
            df['本益比'] = pd.to_numeric(df['本益比'], errors='coerce')
        
        # 剔除沒有殖利率資料的標的
        return df.dropna(subset=['殖利率(%)'])
        
    except Exception as e:
        st.error(f"⚠️ 證交所 API 連線或資料解析失敗細節：{e}")
        return pd.DataFrame()

# ==========================================
# 3. 側邊欄：策略參數設定
# ==========================================
st.sidebar.header("⚙️ 智慧選股參數設定")
price_min = st.sidebar.number_input("最低股價 (元)", min_value=0.0, value=10.0)
price_max = st.sidebar.number_input("最高股價 (元)", min_value=0.0, value=30.0)
min_yield = st.sidebar.slider("最低殖利率要求 (%)", min_value=0.0, max_value=15.0, value=5.0, step=0.5)
require_ma20 = st.sidebar.checkbox("必須站穩月線 (20MA)", value=True)

# 執行按鈕
start_scan = st.sidebar.button("🚀 開始全市場掃描")

# ==========================================
# 4. 主程式邏輯
# ==========================================
if start_scan:
    with st.spinner('📥 正在從台灣證交所下載全市場大數據 (已開啟 SSL 豁免與動態欄位追蹤)...'):
        twse_df = fetch_twse_fundamentals()
    
    if not twse_df.empty:
        # 第一層過濾：基本面殖利率篩選
        fundamental_pass = twse_df[twse_df['殖利率(%)'] >= min_yield]
        
        st.info(f"🔍 第一階段：全市場過濾，共有 **{len(fundamental_pass)}** 檔上市股票符合殖利率大於 {min_yield}% 的條件。接下來進行技術面解析...")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        final_list = []
        total_stocks = len(fundamental_pass)
        
        # 第二層過濾：yfinance 技術面篩選
        for idx, (index, row) in enumerate(fundamental_pass.iterrows()):
            ticker = f"{row['股票代號']}.TW"
            status_text.text(f"正在分析 ({idx+1}/{total_stocks}): {row['股票名稱']}")
            
            try:
                hist = yf.Ticker(ticker).history(period="40d")
                if len(hist) >= 20:
                    current_price = round(hist['Close'].iloc[-1], 2)
                    ma20 = round(hist['Close'].rolling(window=20).mean().iloc[-1], 2)
                    
                    if price_min <= current_price <= price_max:
                        is_above_ma20 = current_price >= ma20
                        if require_ma20 and not is_above_ma20:
                            continue 
                            
                        tech_status = '站上月線強勢' if is_above_ma20 else '跌破月線偏弱'
                        
                        final_list.append({
                            '股票代號': row['股票代號'],
                            '股票名稱': row['股票名稱'],
                            '目前大約股價': current_price,
                            '月線(20MA)': ma20,
                            '最新殖利率(%)': row['殖利率(%)'],
                            '本益比': row['本益比'] if '本益比' in row else 'N/A',
                            '技術面狀態': tech_status
                        })
            except Exception:
                pass # 忽略下市或 yfinance 抓不到的異常代號
                
            progress_bar.progress((idx + 1) / total_stocks)
            
        status_text.text("✅ 掃描完成！")
        
        # ==========================================
        # 5. 輸出結果
        # ==========================================
        if final_list:
            final_df = pd.DataFrame(final_list)
            # 依照殖利率由高到低排序
            final_df = final_df.sort_values(by='最新殖利率(%)', ascending=False)
            
            st.success(f"🎉 最終精選：共找出 **{len(final_df)}** 檔符合所有嚴格條件的標的！")
            st.dataframe(final_df, use_container_width=True, hide_index=True)
        else:
            st.warning("⚠️ 目前市場環境下，沒有符合這套參數的標的，建議放寬條件。")
            
else:
    st.info("👈 請調整左側參數後，點擊「🚀 開始全市場掃描」按鈕。")