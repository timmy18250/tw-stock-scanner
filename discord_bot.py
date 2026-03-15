import os
import sys
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 🔑 設定區
# ==========================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") 

if not DISCORD_WEBHOOK_URL:
    print("❌ 錯誤：找不到 Discord Webhook 網址！")
    sys.exit()

# 策略參數
PRICE_MIN, PRICE_MAX = 10.0, 40.0  # 股價範圍 (稍微放寬以涵蓋多數 ETF)
MIN_YIELD = 5.0                    # 個股最低殖利率
MIN_VOLUME_ETF = 1000              # ETF 每日最低成交量 (張)

# ==========================================
# 🛠️ 資料抓取模組
# ==========================================
def fetch_stock_data():
    """抓取證交所個股基本面"""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    try:
        res = requests.get(url, timeout=15, verify=False)
        df = pd.DataFrame(res.json())
        df.columns = ['股票代號', '股票名稱', '本益比', '殖利率(%)', '股價淨值比']
        df['殖利率(%)'] = pd.to_numeric(df['殖利率(%)'], errors='coerce')
        return df.dropna(subset=['殖利率(%)'])
    except: return pd.DataFrame()

def fetch_etf_data():
    """抓取證交所 ETF 即時行情"""
    url = "https://openapi.twse.com.tw/v1/etf/etfAll" # 取得所有 ETF 清單
    try:
        res = requests.get(url, timeout=15, verify=False)
        return pd.DataFrame(res.json())
    except: return pd.DataFrame()

def check_ma20(ticker):
    """檢查是否站上月線並回傳當前股價"""
    try:
        hist = yf.Ticker(ticker).history(period="40d")
        if len(hist) >= 20:
            current_price = hist['Close'].iloc[-1]
            ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
            volume = hist['Volume'].iloc[-1] / 1000 # 換算成「張」
            return round(current_price, 2), current_price >= ma20, int(volume)
    except: pass
    return None, False, 0

# ==========================================
# 🚀 執行與推播
# ==========================================
def main():
    print("⏳ 開始掃描全市場個股與 ETF...")
    today = datetime.now().strftime("%Y-%m-%d")
    final_list = []

    # 1. 處理個股 (高殖利率篩選)
    stocks = fetch_stock_data()
    if not stocks.empty:
        stocks = stocks[stocks['殖利率(%)'] >= MIN_YIELD].head(50) # 先取前50名加快速度
        for _, row in stocks.iterrows():
            price, is_above, _ = check_ma20(f"{row['股票代號']}.TW")
            if is_above and PRICE_MIN <= price <= PRICE_MAX:
                final_list.append({'type': '個股', 'id': row['股票代號'], 'name': row['股票名稱'], 'price': price, 'val': row['殖利率(%)']})

    # 2. 處理 ETF (篩選高流動性與趨勢)
    # 這裡我們觀察常見的台股高股息代號 (例如 0056, 00878, 00919, 00929, 00713 等)
    etf_watch = ['0056', '00878', '00919', '00929', '00713', '00915', '00918', '0050', '006208']
    for eid in etf_watch:
        price, is_above, vol = check_ma20(f"{eid}.TW")
        if is_above and vol >= MIN_VOLUME_ETF:
            final_list.append({'type': 'ETF', 'id': eid, 'name': 'ETF', 'price': price, 'val': f"量:{vol}張"})

    # 3. 發送 Discord
    if final_list:
        msg = f"📊 **台股整合選股報告** ({today})\n```diff\n"
        for item in final_list:
            prefix = "+" if item['type'] == '個股' else "!"
            msg += f"{prefix} [{item['type']}] {item['id']} {item['name'][:4]} | ${item['price']} | {item['val']}\n"
        msg += "```\n*註：+為高殖利率個股，!為強勢高標的ETF*"
    else:
        msg = f"📅 {today} 掃描完成：今日市場震盪，無符合條件標的。"
    
    requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})

if __name__ == "__main__":
    main()
