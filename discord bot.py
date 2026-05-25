import os
import sys
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import urllib3

# 關閉 SSL 憑證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 🔑 設定區 (高安全性：從系統環境變數讀取金鑰)
# ==========================================
# 程式會自動去 GitHub Secrets 找這把鑰匙，不會洩漏在程式碼裡
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") 

if not DISCORD_WEBHOOK_URL:
    print("❌ 錯誤：找不到 Discord Webhook 網址！請確認環境變數設定。")
    sys.exit()

# 策略參數預設值
PRICE_MIN = 10.0
PRICE_MAX = 30.0
MIN_YIELD = 5.0
REQUIRE_MA20 = True

# ==========================================
# 🛠️ 核心函式
# ==========================================
def send_discord_webhook(message):
    """發送 Discord Webhook 推播訊息"""
    data = {"content": message}
    response = requests.post(DISCORD_WEBHOOK_URL, json=data)
    
    if response.status_code in [200, 204]:
        print("✅ Discord 訊息發送成功！")
    else:
        print(f"❌ 發送失敗，錯誤碼：{response.status_code}, 詳細訊息：{response.text}")

def fetch_twse_fundamentals():
    """抓取證交所基本面資料 (動態欄位追蹤 + SSL 豁免)"""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        response.raise_for_status()
        df = pd.DataFrame(response.json())
        
        rename_mapping = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'code' in col_lower: rename_mapping[col] = '股票代號'
            elif 'name' in col_lower: rename_mapping[col] = '股票名稱'
            elif 'yield' in col_lower: rename_mapping[col] = '殖利率(%)'
                
        df = df.rename(columns=rename_mapping)
        if '殖利率(%)' in df.columns:
            df['殖利率(%)'] = pd.to_numeric(df['殖利率(%)'], errors='coerce')
            return df.dropna(subset=['殖利率(%)'])
    except Exception as e:
        print(f"證交所資料抓取失敗: {e}")
    return pd.DataFrame()

# ==========================================
# 🚀 主程式執行區
# ==========================================
def main():
    print("⏳ 開始執行台股量化掃描...")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    twse_df = fetch_twse_fundamentals()
    if twse_df.empty:
        send_discord_webhook(f"📅 **{today_str}**\n⚠️ 證交所資料抓取失敗，今日暫停篩選。")
        return

    # 1. 基本面過濾
    fundamental_pass = twse_df[twse_df['殖利率(%)'] >= MIN_YIELD]
    final_list = []
    total_stocks = len(fundamental_pass)
    
    # 2. 技術面過濾
    for idx, (index, row) in enumerate(fundamental_pass.iterrows()):
        ticker = f"{row['股票代號']}.TW"
        
        # 每處理 10 檔印出一次進度，避免以為當機
        if (idx + 1) % 10 == 0:
            print(f"掃描進度: {idx+1}/{total_stocks} ...")
            
        try:
            hist = yf.Ticker(ticker).history(period="40d")
            if len(hist) >= 20:
                current_price = round(hist['Close'].iloc[-1], 2)
                ma20 = round(hist['Close'].rolling(window=20).mean().iloc[-1], 2)
                
                # 價格與均線邏輯判斷
                if PRICE_MIN <= current_price <= PRICE_MAX:
                    is_above_ma20 = current_price >= ma20
                    if REQUIRE_MA20 and not is_above_ma20:
                        continue
                    
                    final_list.append({
                        '代號': row['股票代號'],
                        '名稱': row['股票名稱'],
                        '股價': current_price,
                        '殖利率': row['殖利率(%)']
                    })
        except:
            pass
            
    # 3. 整理訊息並發送 Discord
    if final_list:
        # 依殖利率由高到低排序，並取前 15 名避免訊息過長
        final_list = sorted(final_list, key=lambda x: x['殖利率'], reverse=True)[:15]
        
        # 利用 Markdown 語法排版
        msg = f"📊 **台股每日量化掃描完成！**\n> 📅 日期：{today_str}\n> 🔍 條件：{PRICE_MIN}-{PRICE_MAX}元 / 殖利率>{MIN_YIELD}% / 站上月線\n\n**⭐ 今日精選標的 (依殖利率排序)：**\n```diff\n"
        
        for item in final_list:
            # 加入 + 號讓 Discord 顯示綠色文字
            msg += f"+ {item['代號']:<6} {item['名稱']:<6} | 股價: {item['股價']:>5} 元 | 殖利率: {item['殖利率']:>5}%\n"
        
        msg += f"```\n💡 *共篩選出 {len(final_list)} 檔標的。(最多顯示前15檔)*"
        send_discord_webhook(msg)
    else:
        send_discord_webhook(f"📊 **台股每日量化掃描完成！**\n> 📅 日期：{today_str}\n⚠️ 今日無符合所有嚴格條件之標的。")

if __name__ == "__main__":
    main()