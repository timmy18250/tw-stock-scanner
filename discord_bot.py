import os
import sys
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import urllib3
import time

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
PRICE_MIN = 15.0       # 股價下限
PRICE_MAX = 500.0      # 股價上限
VOL_AVG_DAYS = 5       # 平均量天數
VOL_MULTIPLIER = 1.3   # 帶量突破倍數 (1.3倍即視為有動能)

# ==========================================
# 🛠️ 智慧動能分析模組
# ==========================================
def analyze_momentum(sid, name):
    """分析股票動能並給予評分"""
    ticker = f"{sid}.TW"
    try:
        # 抓取 100 天資料以確保指標計算準確
        df = yf.Ticker(ticker).history(period="100d")
        if len(df) < 60: return None
        
        c = df['Close'].iloc[-1]
        v_today = df['Volume'].iloc[-1]
        
        # 基本價格過濾
        if not (PRICE_MIN <= c <= PRICE_MAX): return None

        # 技術指標計算
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]
        v_avg = df['Volume'].iloc[-VOL_AVG_DAYS-1:-1].mean()
        
        score = 0
        
        # 條件 1：均線多頭排列 (確認上升趨勢)
        if c > ma5 > ma20 > ma60: 
            score += 50
        
        # 條件 2：帶量突破 (確認主力進場)
        if v_today > (v_avg * VOL_MULTIPLIER): 
            score += 30
        
        # 條件 3：價格強勢度 (接近月新高)
        if c >= df['Close'].iloc[-20:].max() * 0.97: 
            score += 20
        
        # 門檻設定：60分以上才進入推薦名單
        if score >= 60:
            return {
                'id': sid, 
                'name': name, 
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
    print(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] 啟動等級 A 智慧動能全市場掃描...")
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 多路徑備援網址
    urls = [
        "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
        "https://openapi.twse.com.tw/v1/exchange_report/BWIBBU_ALL"
    ]
    
    data = None
    for url in urls:
        print(f"嘗試抓取資料源: {url}")
        for i in range(3): # 自動重試 3 次
            try:
                res = requests.get(url, verify=False, timeout=20)
                if res.status_code == 200:
                    data = res.json()
                    if data: break
            except:
                print(f"連線失敗，5秒後進行第 {i+1} 次重試...")
                time.sleep(5)
        if data: break

    if not data:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": f"📅 {today} 報告：證交所伺服器連線異常，請稍後再試。"})
        return

    # 智慧解析欄位：不依賴名稱，直接抓取前兩欄 (iloc)
    all_stocks = pd.DataFrame(data)
    pool_raw = all_stocks.iloc[:, [0, 1]].values.tolist()
    print(f"成功取得資料，開始分析全市場 {len(pool_raw)} 檔標的...")

    recommend_list = []
    for row in pool_raw:
        sid, name = str(row[0]), str(row[1])
        # 過濾標的：僅處理 4 位數純數字的普通股，避開權證與雜訊
        if len(sid) == 4 and sid.isdigit():
            result = analyze_momentum(sid, name)
            if result:
                recommend_list.append(result)

    # 排序邏輯：優先比星等(分數)，再比成交量爆發倍數
    recommend_list = sorted(recommend_list, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)

    if recommend_list:
        top_15 = recommend_list[:15]
        msg = f"🧠 **AI 智慧動能推薦報告** ({today})\n> 篩選：強勢多頭排列 + 主力帶量突破\n```diff\n"
        for item in top_15:
            stars = "⭐" * (item['score'] // 20)
            msg += f"+ {item['id']} {item['name'][:4]} | {item['status']} {stars}\n  價格: {item['price']} | 成交量比: {item['vol_ratio']}x\n"
        msg += "```\n💡 *註：價格站上 5/20/60MA 且成交量爆發，預測未來成長行情較佳。*"
    else:
        msg = f"📅 {today} 掃描完成：今日市場動能不足，無符合「等級 A」強勢條件標的。"
    
    requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
    print(f"✅ 任務圓滿完成。")

if __name__ == "__main__":
    main()
