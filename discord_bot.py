import os
import sys
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import urllib3

# 忽略證交所 API 的安全請求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 🔑 設定區
# ==========================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") 
if not DISCORD_WEBHOOK_URL:
    print("❌ 錯誤：找不到 Discord Webhook 網址！")
    sys.exit()

# 強勢股篩選參數
PRICE_MIN = 15.0       # 股價門檻
PRICE_MAX = 500.0      # 提高上限以納入更多權值強勢股
VOL_AVG_DAYS = 5       # 平均量天數
VOL_MULTIPLIER = 1.3   # 稍微下修門檻至 1.3 倍，增加智慧推薦的靈敏度

# ==========================================
# 🛠️ 智慧動能分析模組
# ==========================================
def analyze_momentum(sid, name):
    """分析股票動能並給予評分"""
    ticker = f"{sid}.TW"
    try:
        # 抓取 100 天資料以確保 MA60 準確
        df = yf.Ticker(ticker).history(period="100d")
        if len(df) < 60: return None
        
        c = df['Close'].iloc[-1]
        v_today = df['Volume'].iloc[-1]
        
        # 過濾基本價格區間
        if not (PRICE_MIN <= c <= PRICE_MAX): return None

        # 計算技術指標
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]
        v_avg = df['Volume'].iloc[-VOL_AVG_DAYS-1:-1].mean()
        
        score = 0
        
        # 條件 1：多頭排列 (趨勢預測)
        if c > ma5 > ma20 > ma60: score += 50
        
        # 條件 2：帶量突破 (智慧動能)
        if v_today > (v_avg * VOL_MULTIPLIER): score += 30
        
        # 條件 3：接近波段新高
        if c >= df['Close'].iloc[-20:].max() * 0.97: score += 20
        
        # 推薦門檻：60分
        if score >= 60:
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
    print(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] 啟動全市場等級 A 智慧動能掃描...")
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 修正後的證交所 API 網址
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    
    try:
        res = requests.get(url, verify=False, timeout=30)
        data = res.json()
        if not data: raise ValueError("回傳資料為空")
        all_stocks = pd.DataFrame(data)
        pool = all_stocks[['證券代號', '證券名稱']].values.tolist()
        print(f"成功連接證交所，總計掃描 {len(pool)} 檔標的...")
    except Exception as e:
        print(f"❌ 抓取失敗: {e}")
        requests.post(DISCORD_WEBHOOK_URL, json={"content": f"⚠️ 證交所 API 連線異常，今日無法進行智慧掃描。"})
        return

    recommend_list = []
    for sid, name in pool:
        result = analyze_momentum(sid, name)
        if result:
            recommend_list.append(result)

    # 排序
    recommend_list = sorted(recommend_list, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)

    if recommend_list:
        top_recommend = recommend_list[:15]
        msg = f"🧠 **AI 智慧動能推薦報告** ({today})\n> 篩選：強勢多頭排列 + 主力帶量突破\n```diff\n"
        for item in top_recommend:
            stars = "⭐" * (item['score'] // 20)
            msg += f"+ {item['id']} {item['name'][:4]} | {item['status']} {stars}\n  價格: {item['price']} | 成交量比: {item['vol_ratio']}x\n"
        msg += "```"
    else:
        # 即使沒選到也會發通知，確保你知道機器人有在工作
        msg = f"📅 {today} 掃描完成：今日市場動能不足，無符合「等級 A」強勢條件標的。"
    
    requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
    print(f"✅ 任務完成，訊息已發送至 Discord。")

if __name__ == "__main__":
    main()
