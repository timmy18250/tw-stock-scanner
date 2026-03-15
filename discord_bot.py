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

# 強勢股篩選參數
PRICE_MIN = 15.0      # 價格太低通常沒動能
VOL_AVG_DAYS = 5      # 計算平均成交量的天數
VOL_MULTIPLIER = 1.5  # 成交量必須是均量的幾倍 (帶量)

# ==========================================
# 🛠️ 智慧動能分析模組
# ==========================================
def analyze_momentum(ticker):
    """分析股票動能並給予評分"""
    try:
        # 抓取較長天數以計算 60MA
        df = yf.Ticker(ticker).history(period="100d")
        if len(df) < 60: return None
        
        # 1. 計算均線
        c = df['Close'].iloc[-1]
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]
        
        # 2. 計算成交量 (今天量與近5日均量)
        v_today = df['Volume'].iloc[-1]
        v_avg = df['Volume'].iloc[-VOL_AVG_DAYS-1:-1].mean()
        
        # 3. 智慧判定
        score = 0
        is_bullish = c > ma5 > ma20 > ma60 # 多頭排列核心條件
        if is_bullish: score += 50
        
        is_volume_spike = v_today > (v_avg * VOL_MULTIPLIER) # 帶量突破
        if is_volume_spike: score += 30
        
        # 股價位於波段高點 (強勢特徵)
        if c >= df['Close'].iloc[-20:].max() * 0.98: score += 20
        
        if score >= 50 and PRICE_MIN <= c <= 150: # 綜合評分門檻
            return {
                'price': round(c, 2),
                'score': score,
                'vol_ratio': round(v_today / v_avg, 1),
                'status': "🔥強力爆發" if score >= 80 else "📈趨勢轉強"
            }
    except: pass
    return None

# ==========================================
# 🚀 執行與推播
# ==========================================
def main():
    print("⏳ 啟動等級 A 智慧動能掃描...")
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 使用熱門股與權值股作為初選池 (也可以串接全市場代號)
    # 這裡示範掃描 0050 成份股 + 熱門 ETF
    target_pool = ["2330", "2317", "2454", "2308", "2382", "2303", "2881", "2882", "3711", "2412",
                   "1513", "1519", "1503", "1605", "2603", "2609", "2615", "3037", "3231", "6669",
                   "0050", "0056", "00878", "00919", "00929", "00940", "00713"]
    
    recommend_list = []
    for sid in target_pool:
        ticker = f"{sid}.TW"
        result = analyze_momentum(ticker)
        if result:
            recommend_list.append({'id': sid, **result})
            
    # 按分數由高到低排序
    recommend_list = sorted(recommend_list, key=lambda x: x['score'], reverse=True)

    if recommend_list:
        msg = f"🧠 **AI 智慧動能推薦報告** ({today})\n> 策略：均線多頭排列 + 帶量突破\n```diff\n"
        for item in recommend_list:
            stars = "⭐" * (item['score'] // 20)
            msg += f"+ {item['id']} | {item['status']} {stars}\n  價格: {item['price']} | 成交量比: {item['vol_ratio']}x\n"
        msg += "```\n💡 *建議：星星越多代表趨勢越一致，請留意進場風險。*"
    else:
        msg = f"📅 {today} 掃描完成：目前市場動能較弱，建議觀望。"
    
    requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})

if __name__ == "__main__":
    main()
