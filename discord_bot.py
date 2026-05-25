import os
import sys
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 🔑 設定區
# ==========================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") 
if not DISCORD_WEBHOOK_URL:
    print("❌ 錯誤：找不到 Discord Webhook 網址！")
    sys.exit()

# --- 靈敏度微調區 ---
PRICE_MIN = 10.0       # 降低門檻，包含更多低價轉強股
PRICE_MAX = 600.0      
VOL_AVG_DAYS = 5       
VOL_MULTIPLIER = 1.1   # 【靈敏】成交量僅需 1.1 倍
SCORE_THRESHOLD = 40   # 【靈敏】40 分即可入選
# ------------------

# ==========================================
# 🛠️ 智慧動能分析模組
# ==========================================
def analyze_momentum(sid, name):
    ticker = f"{sid}.TW"
    try:
        df = yf.Ticker(ticker).history(period="100d")
        if len(df) < 60: return None
        
        c = df['Close'].iloc[-1]
        v_today = df['Volume'].iloc[-1]
        
        if not (PRICE_MIN <= c <= PRICE_MAX): return None

        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]
        v_avg = df['Volume'].iloc[-VOL_AVG_DAYS-1:-1].mean()
        
        score = 0
        # 條件 1：多頭排列 (權重 50)
        if c > ma5 > ma20 > ma60: score += 50
        # 條件 2：帶量突破 (權重 30)
        if v_today > (v_avg * VOL_MULTIPLIER): score += 30
        # 條件 3：價格強度 (權重 20)
        if c >= df['Close'].iloc[-20:].max() * 0.96: score += 20
        
        if score >= SCORE_THRESHOLD:
            return {
                'id': sid, 'name': name, 'price': round(c, 2),
                'score': score, 'vol_ratio': round(v_today / v_avg, 1),
                'status': "🔥強力爆發" if score >= 80 else "📈趨勢轉強"
            }
    except: pass
    return None

# ==========================================
# 🚀 執行與推播
# ==========================================
def main():
    print(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] 啟動全市場靈敏版動能掃描...")
    today = datetime.now().strftime("%Y-%m-%d")
    
    urls = [
        "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
        "https://openapi.twse.com.tw/v1/exchange_report/BWIBBU_ALL"
    ]
    
    data = None
    for url in urls:
        for i in range(3):
            try:
                res = requests.get(url, verify=False, timeout=20)
                if res.status_code == 200:
                    data = res.json()
                    if data: break
            except:
                time.sleep(5)
        if data: break

    if not data:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": f"📅 {today} 報告：證交所伺服器連線異常。"})
        return

    all_stocks = pd.DataFrame(data)
    pool_raw = all_stocks.iloc[:, [0, 1]].values.tolist()
    
    recommend_list = []
    for row in pool_raw:
        sid, name = str(row[0]), str(row[1])
        if len(sid) == 4 and sid.isdigit():
            result = analyze_momentum(sid, name)
            if result:
                recommend_list.append(result)

    recommend_list = sorted(recommend_list, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)

    if recommend_list:
        top_20 = recommend_list[:20] # 靈敏版多提供幾隻參考
        msg = f"🧠 **AI 智慧動能推薦報告 (靈敏版)** ({today})\n> 篩選：多頭排列 或 帶量突破\n```diff\n"
        for item in top_20:
            stars = "⭐" * (item['score'] // 20)
            msg += f"+ {item['id']} {item['name'][:4]} | {item['status']} {stars}\n  價格: {item['price']} | 成交量比: {item['vol_ratio']}x\n"
        msg += "```\n💡 *註：靈敏版包含「剛轉強」標的，請留意進場位階。*"
    else:
        msg = f"📅 {today} 掃描完成：目前全市場仍無明顯動能標的。"
    
    requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
    print(f"✅ 靈敏版掃描完成。")

if __name__ == "__main__":
    main()
