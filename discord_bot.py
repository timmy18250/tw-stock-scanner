import os
import sys
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import urllib3

# 忽略不安全的請求警告（證交所 API 有時會需要）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 🔑 設定區
# ==========================================
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") 
if not DISCORD_WEBHOOK_URL:
    print("❌ 錯誤：找不到 Discord Webhook 網址！")
    sys.exit()

# 強勢股篩選參數
PRICE_MIN = 15.0       # 股價門檻 (避開太低價的雞蛋股)
PRICE_MAX = 200.0      # 股價上限 (你可以根據財力調整)
VOL_AVG_DAYS = 5       # 計算平均成交量的天數
VOL_MULTIPLIER = 1.5   # 成交量必須是均量的幾倍 (帶量)

# ==========================================
# 🛠️ 智慧動能分析模組
# ==========================================
def analyze_momentum(sid, name):
    """分析股票動能並給予評分"""
    ticker = f"{sid}.TW"
    try:
        # 抓取較長天數以計算 60MA (季線)
        df = yf.Ticker(ticker).history(period="100d")
        if len(df) < 60: return None
        
        # 1. 取得最新資料
        c = df['Close'].iloc[-1]
        v_today = df['Volume'].iloc[-1]
        
        # 過濾基本價格區間
        if not (PRICE_MIN <= c <= PRICE_MAX): return None

        # 2. 計算技術指標
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        ma60 = df['Close'].rolling(60).mean().iloc[-1]
        v_avg = df['Volume'].iloc[-VOL_AVG_DAYS-1:-1].mean()
        
        # 3. 智慧評分邏輯
        score = 0
        
        # 條件 A：多頭排列 (強烈趨勢)
        is_bullish = c > ma5 > ma20 > ma60
        if is_bullish: score += 50
        
        # 條件 B：帶量突破 (大戶進場)
        is_volume_spike = v_today > (v_avg * VOL_MULTIPLIER)
        if is_volume_spike: score += 30
        
        # 條件 C：強勢收盤 (股價接近 20 日最高點)
        if c >= df['Close'].iloc[-20:].max() * 0.97: score += 20
        
        # 只推薦 60 分以上的股票 (代表至少要有基本趨勢)
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
    print(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] 啟動全市場等級 A 智慧動能掃描...")
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 1. 抓取證交所全市場清單
    try:
        url = "https://openapi.twse.com.tw/v1/exchange_report/BWIBBU_ALL"
        res = requests.get(url, verify=False, timeout=20)
        all_stocks = pd.DataFrame(res.json())
        # 取得代號與名稱
        pool = all_stocks[['證券代號', '證券名稱']].values.tolist()
    except Exception as e:
        print(f"❌ 抓取清單失敗: {e}")
        return

    recommend_list = []
    
    # 2. 進行全市場掃描 (為避免跑太久，GitHub Actions 建議限制在熱門前 300 檔或全部掃描)
    # 這裡我們全掃描，GitHub Actions 通常能支撐 3-5 分鐘的運行
    count = 0
    for sid, name in pool:
        result = analyze_momentum(sid, name)
        if result:
            recommend_list.append(result)
        
        count += 1
        if count % 100 == 0:
            print(f"已掃描 {count} 檔...")

    # 3. 排序與發送
    # 按分數由高到低，分數相同按成交量倍數排
    recommend_list = sorted(recommend_list, key=lambda x: (x['score'], x['vol_ratio']), reverse=True)

    if recommend_list:
        # 取前 15 名最強勢的標的
        top_recommend = recommend_list[:15]
        msg = f"🧠 **AI 智慧動能推薦報告** ({today})\n> 篩選：全市場強勢多頭排列 + 主力帶量突破\n```diff\n"
        for item in top_recommend:
            stars = "⭐" * (item['score'] // 20)
            msg += f"+ {item['id']} {item['name'][:4]} | {item['status']} {stars}\n  價格: {item['price']} | 成交量比: {item['vol_ratio']}x\n"
        msg += "```\n💡 *智慧提醒：帶量突破(x > 1.5)通常是行情啟動訊號。*"
    else:
        msg = f"📅 {today} 掃描完成：今日全市場動能偏弱，無符合強勢條件標的。"
    
    # 發送至 Discord
    requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
    print(f"✅ 掃描完成，已發送至 Discord。")

if __name__ == "__main__":
    main()
